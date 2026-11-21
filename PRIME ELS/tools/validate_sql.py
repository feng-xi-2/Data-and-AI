"""Validate every replica query of the WH Hypercare KPI model against each site's live replica (read-only).

    py tools/validate_sql.py BINHDUONG MINHANG JAKARTA [--no-exec]
    py tools/validate_sql.py [SITE ...] --inc-check     # incremental partitions: history + recent rows == full rows

1. Renders each query exactly like the model does (Cfg_Engine defaults + non-blank Cfg_Site overrides + derived tokens).
2. COMPILE : sp_describe_first_result_set -> binds every table / column on that engine (2014 prodwms vs 2022 dbo) without reading data.
3. EXECUTE : runs the queries whose feature flag is ON for the site (timeout 110 s) and records the row count.
Writes tools/_validate_<SITE>.json and prints a summary table.
"""
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from probe_replica_schema import connect  # noqa: E402
from m_tokenizer import scope_warehouse, apply_incremental, incremental_policy, INC_DEFAULTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GATE = {"Level A Available Pallet Spot": "Has_LevelA", "Level A Occupied Pallet": "Has_LevelA", "Outbound Pallet from Inv": "Has_LevelA",
        "Pallet cleaned up from bin A": "Has_LevelA", "Pallet From LTA To Level A": "Has_LevelA",
        "Pallet in Level A not active shipment": "Has_LevelA", "Pallet From HOFFIN": "Has_HOFF", "Produced Pallet": "Has_Production",
        "Pallet from LTA to short%2Ftall location": "Has_Production", "WorkLine Activities": "Has_Production",
        "Planned Pallet PO": "Has_Production", "Short PO": "Has_Production", "Planned PO RPM Breakdown": "Has_Production"}
SKIP = {"SAP Plan PO", "Shipping Market", "Date Refresh", "FG GCAS", "RPM Masterdata"}  # Databricks / no replica SQL


def rows(name):
    return list(csv.DictReader(open(ROOT / "config" / name, encoding="utf-8-sig")))


def tokens(code):
    site = next(r for r in rows("site_config.csv") if r["SiteCode"] == code)
    if "--overrides" in sys.argv and (ROOT / "config" / "service_overrides.csv").exists():   # same rows as build_pbip --overrides / --service
        site = dict(site, **{o["Setting"]: o["Value"] for o in rows("service_overrides.csv") if o["SiteCode"] == code})
    if "--server" in sys.argv:          # e.g. the non-prod rehearsal replica of the same warehouse (row counts with real history)
        site = dict(site, ReplicaServer=sys.argv[sys.argv.index("--server") + 1])
    eng = next(r for r in rows("engine_profiles.csv") if r["WMS_Version"] == site["WMS_Version"])
    tok = {k: v for k, v in eng.items() if k not in ("WMS_Version", "Notes")}
    tok.update({k: v for k, v in site.items() if v not in ("", None)})
    start = datetime.strptime(site["Hypercare_Start"], "%Y-%m-%d %H:%M:%S")
    lines = [r for r in rows("line_map.csv") if r["Site"] == code]
    tok.update(START_DT=start.strftime("%Y-%m-%d %H:%M:%S"), START_YYYYMMDD=start.strftime("%Y%m%d"), ACT_DAYS="14",
               LTA_MAP_VALUES=",".join(f"('{r['LTA_Source']}','{r['Prod_Line']}','{r['Category']}')" for r in lines) or "('~NA~','~NA~','~NA~')")
    tok.update(INC_DEFAULTS)
    return site, tok


def render(t, tok):
    for _ in range(2):
        for k, v in tok.items():
            t = t.replace("{" + k + "}", str(v))
    return t


def m_unescape(s):
    return s.replace('""', '"').replace("#(lf)", "\n").replace("#(cr)", "\r").replace("#(tab)", "\t")


def read_m_string(src, i, varmap):
    """src[i] == '"'. Returns (text, end_index) following `" & Var & "` concatenations."""
    out = []
    while True:
        j = i + 1
        buf = []
        while True:
            if src[j] == '"' and src[j + 1:j + 2] == '"':
                buf.append('""'); j += 2; continue
            if src[j] == '"':
                break
            buf.append(src[j]); j += 1
        out.append(m_unescape("".join(buf)))
        m = re.match(r'\s*&\s*(\w+)\s*&\s*"', src[j + 1:])
        if not m:
            return "".join(out), j + 1
        out.append(varmap.get(m.group(1), "{" + m.group(1) + "}"))
        i = j + 1 + m.end() - 1


def sql_from_m(m, tok):
    varmap = {"StartDateValue": tok["START_DT"], "FormattedDate": tok["START_DT"]}
    hit = re.search(r'(?:SqlQuery|SQL|SqlTemplate)\s*=\s*"', m) or re.search(r'fnSiteSql\("', m)
    if not hit:
        return None
    return read_m_string(m, hit.end() - 1, varmap)[0]


def queries():
    out = {}
    only = set(sys.argv[sys.argv.index("--only") + 1].split("|")) if "--only" in sys.argv else set()   # --only "A|B": just those queries
    for f in sorted((ROOT / "sql" / "extracted").glob("*.m")):
        if f.stem not in SKIP and (not only or f.stem in only):
            out[f.stem] = ("orig", f.read_text(encoding="utf-8"))
    for f in sorted((ROOT / "sql" / "new").glob("*.sql")):
        if not only or f.stem in only:
            out[f.stem] = ("new", apply_incremental(f.stem, scope_warehouse(f.read_text(encoding="utf-8"))[0])[0])
    return out


def inc_check(code):
    """config/incremental_policy.csv: rows(history < boundary) + rows(recent >= boundary) must equal rows(full) on the replica."""
    site, tok = tokens(code)
    cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
    cn.timeout = 110
    cur = cn.cursor()
    off = float(site.get("UTC_Offset_h") or 0)
    local_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=off)
    bad = 0
    for name, (kind, body) in queries().items():
        p = incremental_policy().get(name)
        gate = GATE.get(name)
        if not p or (gate and site.get(gate, "1") != "1"):
            continue
        b = "'" + (local_now.date() - timedelta(days=int(p["Recent_Days"]) - 1)).isoformat() + "'"
        n = {}
        for part, extra in (("full", {}), ("history", {"INC_TO": b}), ("recent", {"INC_FROM": b})):
            sql = render(sql_from_m(body, {**tok, **extra}) if kind == "orig" else body, {**tok, **extra})
            t0 = time.time()
            cur.execute(sql)
            while cur.description is None and cur.nextset():
                pass
            n[part] = (len(cur.fetchall()), time.time() - t0)
        diff = n["full"][0] - n["history"][0] - n["recent"][0]
        # live replica + rolling windows: between the 3 queries old rows age out (diff > 0) and new rows arrive (diff < 0) - tiny
        ok = abs(diff) <= max(5, n["full"][0] // 1000)
        bad += not ok
        why = ("aged out of the rolling window" if diff > 0 else "arrived") + " between the 3 queries"
        print(f"[{datetime.now():%H:%M:%S}] {code:10s} {name:34s} boundary {b}  full {n['full'][0]:>7} ({n['full'][1]:.1f}s) = history "
              f"{n['history'][0]:>7} ({n['history'][1]:.1f}s) + recent {n['recent'][0]:>6} ({n['recent'][1]:.1f}s)  "
              f"{'OK' if diff == 0 else (f'OK ({abs(diff)} row(s) {why})' if ok else f'!! MISMATCH {diff}')}",
              flush=True)
    return bad


def run(code, do_exec=True):
    site, tok = tokens(code)
    cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
    cn.timeout = 110
    cur = cn.cursor()
    res = []
    for name, (kind, body) in queries().items():
        sql = render(sql_from_m(body, tok) if kind == "orig" else body, tok)
        gate = GATE.get(name)
        enabled = (site.get(gate, "1") == "1") if gate else True
        r = {"table": name, "gate": gate or "-", "enabled": enabled}
        left = re.findall(r"\{[A-Z_0-9]+\}", sql)
        if left:
            r["compile"] = "UNRESOLVED " + ",".join(sorted(set(left)))
        else:
            try:
                cols = cur.execute("EXEC sp_describe_first_result_set @tsql = ?", sql).fetchall()
                r["compile"] = f"OK ({len(cols)} cols)"
            except Exception as e:
                r["compile"] = "FAIL " + re.sub(r"\s+", " ", str(e))[:260]
        if do_exec and enabled and r["compile"].startswith("OK"):
            t0 = time.time()
            try:
                cur.execute(sql)
                while cur.description is None and cur.nextset():
                    pass
                n = len(cur.fetchall()) if cur.description else 0
                r["exec"] = f"OK {n} rows {time.time() - t0:.1f}s"
            except Exception as e:
                r["exec"] = f"FAIL {time.time() - t0:.0f}s " + re.sub(r"\s+", " ", str(e))[:200]
        else:
            r["exec"] = "skipped (feature OFF)" if not enabled else ("-" if not do_exec else "not run")
        res.append(r)
        print(f"[{datetime.now():%H:%M:%S}] {code:10s} {name:42s} {r['compile'][:60]:60s} {r['exec'][:60]}", flush=True)
    (ROOT / "tools" / f"_validate_{code}.json").write_text(json.dumps({"site": code, "engine": site["WMS_Version"],
                                                                       "server": site["ReplicaServer"], "db": site["ReplicaDatabase"],
                                                                       "results": res}, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--only", "--server")]
    if "--inc-check" in sys.argv:
        nbad = sum(inc_check(s.upper()) for s in args or [r["SiteCode"] for r in rows("site_config.csv")])
        sys.exit(1 if nbad else 0)
    for s in args or [r["SiteCode"] for r in rows("site_config.csv")]:
        run(s.upper(), "--no-exec" not in sys.argv)
