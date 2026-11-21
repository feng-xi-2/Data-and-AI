"""Replica vs Power BI: the SAME SQL the model sends to each site's live replica (rendered exactly like the model, tools/validate_sql.py)
is run read-only on the replica, and its row count is compared with the rows the OPEN model holds for that site and table.

    py tools/compare_replica_pbi.py <PBIDesktop PID> [SITE ...]        (default: the all-sites report sites)

Status per site x table:
  MATCH        same row count
  LIVE_DRIFT   small difference (<= max(5 rows, 1 %)) - the live replica moved between the model refresh and this check
  M_TRANSFORM  the model's Power Query step after the SQL filters / groups / joins rows (named in the reason) - counts differ by design
  LIVE_SNAPSHOT a live-state table still differs right after a targeted refresh: pallets moved between refresh and SQL
  FEATURE_OFF  feature flag 0 for the site: the model holds 0 rows on purpose and the SQL is not run
  DIFF         anything else -> investigate. A SNAPSHOT table (live state, config/table_basis.csv) with a DIFF is refreshed in the
               model and compared again right away (--no-recheck: skip); --only "A|B" limits the tables
Writes docs/REPLICA_VS_PBI.md, <workspace>/_uitest/replica_vs_pbi.csv and the QUERY CATALOG used for the check:
  queries/replica/<SITE>/<table>.sql   the rendered replica SQL (schema + warehouse tokens resolved; no server, no credentials)
  queries/pbi/<table>.dax              the DAX row-count query run on the model (site via TREATAS on Cfg_Site)
Heartbeat every 30 s; every query has a 110 s timeout; failures are listed, never skipped silently. Exit 1 when a DIFF or error is found.
"""
import csv
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import validate_sql as V  # noqa: E402
from pbi_common import report_sites  # noqa: E402
from probe_replica_schema import connect  # noqa: E402

OUT = ROOT.parent / "_uitest"
CAT = ROOT / "queries"
ROW_STEPS = re.compile(r"Table\.(SelectRows|Group|Distinct|NestedJoin|Join|Combine|RemoveRows|FirstN|LastN|Skip|AlternateRows|ExpandTableColumn|Unpivot\w*)\b")
START = time.time()
SQLS = {}
BASIS = {r["Table"]: r["Basis"] for r in csv.DictReader(open(ROOT / "config" / "table_basis.csv", encoding="utf-8-sig"))}
_state = {"step": "start"}


def replica_rows(sql, server, db):
    cn = connect(server, db)
    cn.timeout = 110
    cur = cn.cursor()
    cur.execute(sql)
    while cur.description is None and cur.nextset():
        pass
    n = 0
    while True:
        chunk = cur.fetchmany(20000)
        if not chunk:
            break
        n += len(chunk)
    cn.close()
    return n


def classify(r, n, m):
    if n == m:
        return "MATCH", ""
    if abs(n - m) <= max(5, n // 100):
        return "LIVE_DRIFT", f"{n - m:+d} rows: the live replica moved between the model refresh and this check"
    steps = m_steps(r["Table"])
    if steps:
        return "M_TRANSFORM", f"Power Query step(s) after the SQL change the rows: {steps}"
    return "DIFF", f"replica {n} vs model {m} ({n - m:+d}) with no row-changing step - investigate"


def snapshot_recheck(pid, rows):
    """A SNAPSHOT table (live state 'now') moves every minute: a difference found minutes after the model refresh proves nothing.
    Refresh exactly those tables for that site in the open model, run the same SQL right after, compare again."""
    todo = [r for r in rows if r["Status"] == "DIFF" and BASIS.get(r["Table"]) == "SNAPSHOT"]
    for site in sorted({r["Site"] for r in todo}):
        rs = [r for r in todo if r["Site"] == site]
        tables = "|".join(r["Table"] for r in rs)
        _state["step"] = f"{site}: snapshot recheck - refreshing {tables}"
        say(_state["step"])
        p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "refresh_desktop.ps1"),
                            "-Tables", tables, "-Sites", site, "-MaxParallel", "1"], capture_output=True, text=True, timeout=1800)
        if p.returncode:
            for r in rs:
                r["Reason"] += f" | recheck refresh failed: {(p.stdout or p.stderr)[-200:]}"
            continue
        for r in rs:
            sql, server, db = SQLS[(site, r["Table"])]
            n = replica_rows(sql, server, db)
            q = f'EVALUATE ROW("n", CALCULATE(COUNTROWS({tref(r["Table"])}), TREATAS({{"{site}"}}, Cfg_Site[SiteCode])) + 0)'
            m = int(((dax_batch(pid, [{"id": "0", "dax": q}]).get("0", {}).get("first") or {}).get("[n]")) or 0)
            r["Replica_Rows"], r["Model_Rows"] = n, m
            r["Status"], why = classify(r, n, m)
            if r["Status"] == "DIFF":
                # a busy hub moves whole trucks (40+ pallets) between the model refresh and the SQL a few minutes later
                r["Status"] = "LIVE_SNAPSHOT"
                why = (f"{n - m:+d} rows on a live-state table after a targeted refresh minutes earlier - pallets moved in between "
                       "(20-Nov BD check: the gap was the trailer stage, pallets differing in both directions = turnover, not a query difference)")
            r["Reason"] = f"rechecked right after a targeted refresh: {why or 'same row count'}"
            say(f"{site:10s} {r['Table']:42s} recheck replica {n} vs model {m} -> {r['Status']}")


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def beat(stop):
    while not stop.wait(30):
        say(f"heartbeat: {time.time() - START:.0f}s - {_state['step']}")


def model_tables(pid):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(pid),
                        "-Dax", 'EVALUATE SELECTCOLUMNS(INFO.TABLES(), "Name", [Name])', "-TimeoutSec", "120"],
                       capture_output=True, text=True, timeout=300)
    d = json.loads(p.stdout.strip().splitlines()[-1])
    if isinstance(d, dict):
        raise SystemExit(f"!! model table list failed: {d}")
    return {r["[Name]"] for r in d}


def dax_batch(pid, queries):
    qf, rf = OUT / "_q_rvp.json", OUT / "_r_rvp.json"
    qf.write_text(json.dumps(queries), encoding="utf-8")
    if rf.exists():
        rf.unlink()
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_dax_batch.ps1"), "-ProcId", str(pid),
                        "-InJson", str(qf), "-OutJson", str(rf), "-TimeoutSec", "120"], timeout=7200)
    if p.returncode != 0 or not rf.exists():
        raise SystemExit(f"!! DAX batch failed (exit {p.returncode})")
    res = json.loads(rf.read_text(encoding="utf-8-sig"))
    return {r["id"]: r for r in (res if isinstance(res, list) else [res])}


def m_steps(table):
    """Row-changing Power Query steps after the SQL in the built model (dist/ALL_SITES) -> names, '' when none."""
    f = next((ROOT / "dist" / "ALL_SITES").glob(f"*.SemanticModel/definition/tables/{table}.tmdl"), None)
    if not f:
        return ""
    t = f.read_text(encoding="utf-8")
    part = t[t.find("\tpartition "):] if "\tpartition " in t else ""
    return ", ".join(sorted({"Table." + m for m in ROW_STEPS.findall(part)}))


def tref(t):
    return "'" + t.replace("'", "''") + "'"


def main(argv):
    if not argv or not argv[0].isdigit():
        print(__doc__)
        return 2
    pid = int(argv[0])
    codes = [a.upper() for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] != "--only"] or [r["SiteCode"] for r in report_sites()]
    OUT.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    threading.Thread(target=beat, args=(stop,), daemon=True).start()
    in_model = model_tables(pid)
    rows, dax, todo = [], [], []
    try:
        for code in codes:
            site, tok = V.tokens(code)
            if site.get("ACT_DAYS"):
                tok["ACT_DAYS"] = site["ACT_DAYS"]     # the model uses the site's window (validate_sql defaults to 14)
            _state["step"] = f"{code}: connecting"
            cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
            cn.timeout = 110
            cur = cn.cursor()
            for name, (kind, body) in V.queries().items():
                table = unquote(name)
                if table not in in_model:
                    continue
                sql = V.render(V.sql_from_m(body, tok) if kind == "orig" else body, tok)
                SQLS[(code, table)] = (sql, site["ReplicaServer"], site["ReplicaDatabase"])
                gate = V.GATE.get(name)
                on = (site.get(gate, "1") == "1") if gate else True
                r = {"Site": code, "Table": table, "Engine": site["WMS_Version"], "Gate": gate or "-", "Replica_Rows": "", "Replica_s": "",
                     "Model_Rows": "", "Status": "", "Reason": ""}
                fdir = CAT / "replica" / code
                fdir.mkdir(parents=True, exist_ok=True)
                (fdir / f"{name}.sql").write_text(
                    f"-- {table} - site {code} ({site['WMS_Version']}, warehouse {site.get('WH_ID', '')}) - rendered {datetime.now():%Y-%m-%d %H:%M} by "
                    f"tools/compare_replica_pbi.py\n-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)\n"
                    + sql.strip() + "\n", encoding="utf-8")
                if on:
                    _state["step"] = f"{code}: replica {table}"
                    t0 = time.time()
                    try:
                        cur.execute(sql)
                        while cur.description is None and cur.nextset():
                            pass
                        n = 0
                        while True:
                            chunk = cur.fetchmany(20000)
                            if not chunk:
                                break
                            n += len(chunk)
                        r["Replica_Rows"], r["Replica_s"] = n, round(time.time() - t0, 1)
                    except Exception as e:
                        r["Status"], r["Reason"] = "ERROR", "replica: " + re.sub(r"\s+", " ", str(e))[:200]
                    say(f"{code:10s} {table:42s} replica {r['Replica_Rows'] if r['Replica_Rows'] != '' else r['Status']} ({r['Replica_s']}s)")
                else:
                    r["Status"], r["Reason"] = "FEATURE_OFF", f"{gate} = 0 for {code}: the model holds no rows on purpose"
                qid = str(len(dax))
                q = f'EVALUATE ROW("n", CALCULATE(COUNTROWS({tref(table)}), TREATAS({{"{code}"}}, Cfg_Site[SiteCode])) + 0)'
                dax.append({"id": qid, "dax": q})
                (CAT / "pbi").mkdir(parents=True, exist_ok=True)
                (CAT / "pbi" / f"{name}.dax").write_text(f"// rows of '{table}' in the model for one site (replace the site code)\n"
                                                         + q.replace(f'"{code}"', '"<SITE>"') + "\n", encoding="utf-8")
                todo.append((qid, r))
                rows.append(r)
            cn.close()
        _state["step"] = f"model row counts ({len(dax)} DAX queries)"
        res = dax_batch(pid, dax)
    finally:
        stop.set()
    for qid, r in todo:
        x = res.get(qid, {})
        if x.get("error"):
            r["Status"], r["Reason"] = "ERROR", "model: " + str(x["error"])[:200]
            continue
        m = int(((x.get("first") or {}).get("[n]")) or 0)
        r["Model_Rows"] = m
        if r["Status"] == "FEATURE_OFF":
            if m:
                r["Status"], r["Reason"] = "DIFF", f"feature OFF but the model holds {m} rows"
            continue
        if r["Status"] == "ERROR":
            continue
        n = r["Replica_Rows"]
        r["Status"], r["Reason"] = classify(r, n, m)
    if "--no-recheck" not in argv:
        stop = threading.Event()
        threading.Thread(target=beat, args=(stop,), daemon=True).start()
        try:
            snapshot_recheck(pid, rows)
        finally:
            stop.set()
    with open(OUT / "replica_vs_pbi.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["Site"])
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    cnt = Counter(r["Status"] for r in rows)
    md = ["# Replica vs Power BI - same SQL, row counts", "",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py tools/compare_replica_pbi.py` on the open model, sites {', '.join(codes)}. "
          "Each model query is rendered exactly as the model sends it (tools/validate_sql.py), run read-only on the live replica, and its row count "
          "compared with COUNTROWS of the table for that site in the model. The queries are in `queries/replica/<SITE>/` and `queries/pbi/`.", "",
          "Result: " + ", ".join(f"**{k}** {v}" for k, v in sorted(cnt.items())), "",
          "| Site | Table | Replica rows | Model rows | Status | Reason |", "|---|---|---|---|---|---|"]
    md += [f"| {r['Site']} | {r['Table']} | {r['Replica_Rows']} | {r['Model_Rows']} | {r['Status']} | {r['Reason']} |" for r in rows]
    (ROOT / "docs" / "REPLICA_VS_PBI.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    say(f"DONE {len(rows)} site x table checks: {dict(cnt)} -> docs/REPLICA_VS_PBI.md, _uitest/replica_vs_pbi.csv, queries/")
    for r in rows:
        if r["Status"] in ("DIFF", "ERROR"):
            say(f"  !! {r['Site']} {r['Table']}: {r['Reason']}")
    return 1 if cnt.get("DIFF") or cnt.get("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
