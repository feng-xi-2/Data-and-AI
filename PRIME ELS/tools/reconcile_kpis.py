"""KPI reconciliation: every KPI x site x day of the open model against INDEPENDENT SQL on the site's replica.

    py tools/reconcile_kpis.py <PBIDesktop PID> [--sites A,B] [--days 3]

config/kpi_reference.csv lists the KPIs: the model measure, a reference query (sql/reference/<KPI>.sql, written from the KPI
definition - not copied from the model's queries) and two windows:
    Model_Window   the day the measure implements (CAL = calendar date, SHIFT = shift day from Shift1_Start, NOW = live snapshot)
    Intent_Window  the day the report promises (page guide: "report day = shift day starting at Shift1_Start")
Result per KPI x site x day:
    IMPL    model vs reference over the Model_Window   -> MATCH / DIFF  (DIFF = the measure or its query is wrong)
    INTENT  model vs reference over the Intent_Window  -> MATCH / DIFF  (DIFF = definition gap, e.g. calendar vs shift day)
Live snapshots (NOW) are compared with the model's last refresh time shown (values move between refresh and check).
Writes _uitest/reconcile.csv and docs/RECONCILIATION.md. Heartbeat: DAX through run_dax_batch.ps1 (30 s), one line per SQL.
"""
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import validate_sql as v  # noqa: E402
from probe_replica_schema import connect  # noqa: E402

args = sys.argv[1:]
PID = int(args[0])
ONLY = set(args[args.index("--sites") + 1].upper().split(",")) if "--sites" in args else set()
NDAYS = int(args[args.index("--days") + 1]) if "--days" in args else 3
OUT = Path(__file__).resolve().parents[2] / "_uitest"
OUT.mkdir(parents=True, exist_ok=True)
OUT.mkdir(exist_ok=True)
KPIS = list(csv.DictReader(open(ROOT / "config" / "kpi_reference.csv", encoding="utf-8-sig")))


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def window(kind, d, shift_h):
    if kind == "CAL":
        return datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())
    s = datetime.combine(d, datetime.min.time()) + timedelta(hours=shift_h)
    return s, s + timedelta(days=1)


def dax_batch(queries):
    qf, rf = OUT / "_q_reconcile.json", OUT / "_r_reconcile.json"
    qf.write_text(json.dumps(queries), encoding="utf-8")
    if rf.exists():
        rf.unlink()
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_dax_batch.ps1"),
                        "-ProcId", str(PID), "-InJson", str(qf), "-OutJson", str(rf), "-TimeoutSec", "120"], timeout=7200)
    if p.returncode != 0 or not rf.exists():
        raise SystemExit("!! DAX batch failed")
    res = json.loads(rf.read_text(encoding="utf-8-sig"))
    return {r["id"]: r for r in (res if isinstance(res, list) else [res])}


def close(a, b, tol_abs, tol_pct):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= max(tol_abs, tol_pct * max(abs(a), abs(b)))


def num(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


sites = [r for r in v.rows("site_config.csv") if (r["SiteCode"] in ONLY if ONLY else r["SiteCode"].upper() not in __import__("pbi_common").excluded_sites())]
plan, dax = [], []
for site in sites:
    code = site["SiteCode"]
    _, tok = v.tokens(code)
    plc = tok.get("PROD_LEFT_COND", "")
    tok["PROD_LEFT_REF"] = tok.get("PROD_SCOPE", "1=0") if "LTA_SOURCE" in plc else re.sub(r"\bc\.", "d.", plc or "1=0")
    off = float(site.get("UTC_Offset_h") or 0)
    shift_h = float(site.get("Shift1_Start") or 0)
    local_now = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=off)
    shift_today = (local_now - timedelta(hours=shift_h)).date()
    days = [shift_today - timedelta(days=i) for i in range(NDAYS)]
    for k in KPIS:
        req = k["Requires"]
        if req and str(site.get(req, "0")) != "1":
            plan.append(dict(site=code, kpi=k, day=None, na=True))
            continue
        for d in (days if k["Kind"] == "DAY" else [None]):
            qid = f"{code}|{k['KPI_Key']}|{d or 'now'}"
            flt = f'TREATAS({{"{code}"}}, Cfg_Site[SiteCode])' + (f", TREATAS({{DATE({d.year},{d.month},{d.day})}}, DimDate[Date])" if d else "")
            dax.append({"id": qid, "dax": f'EVALUATE ROW("v", CALCULATE([{k["Measure"]}], {flt}))'})
            plan.append(dict(site=code, kpi=k, day=d, tok=tok, shift_h=shift_h, qid=qid))
    dax.append({"id": f"{code}|refresh", "dax": f'EVALUATE ROW("v", CALCULATE(MAX(\'Data Health\'[Db_Utc_Now]), TREATAS({{"{code}"}}, Cfg_Site[SiteCode])))'})

say(f"{len(dax)} model queries for {len(sites)} site(s), {NDAYS} day(s)")
res = dax_batch(dax)
out = []
cur_site, cur = None, None
for p in plan:
    code, k = p["site"], p["kpi"]
    row = {"Site": code, "KPI": k["KPI_Key"], "Day": str(p["day"] or "now"), "Measure": k["Measure"]}
    if p.get("na"):
        out.append({**row, "IMPL": "N/A", "INTENT": "N/A", "Note": f"{k['Requires']} = 0 at this site"})
        continue
    if code != cur_site:
        site = next(s for s in sites if s["SiteCode"] == code)
        try:
            cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
            cn.timeout = 110
            cur = cn.cursor()
        except Exception as e:
            cur = None
            say(f"!! {code}: replica connection failed {e}")
        cur_site = code
    r = res.get(p["qid"], {})
    model = None if r.get("error") else num((r.get("first") or {}).get("[v]"))
    row["Model"] = model
    row["Model_Error"] = (r.get("error") or "")[:160]
    sql_t = (ROOT / "sql" / "reference" / k["Reference_SQL"]).read_text(encoding="utf-8")
    refs = {}
    # a day still in progress is compared up to the model's data snapshot (DB clock at refresh, site-local): rows that
    # arrived after the refresh are not a model error
    snap = None
    try:
        sv = (res.get(f"{code}|refresh", {}).get("first") or {}).get("[v]")
        snap = datetime.strptime(str(sv)[:16], "%Y-%m-%d %H:%M") + timedelta(hours=float(next(s for s in sites if s["SiteCode"] == code).get("UTC_Offset_h") or 0))
    except (ValueError, TypeError, StopIteration):
        pass
    for wk in {k["Model_Window"], k["Intent_Window"]}:
        tk = dict(p["tok"])
        # SNAP = the model's data snapshot (site-local): a status the model could not see yet (e.g. a dispatch after the
        # refresh) must not count in the reference either
        tk["SNAP"] = (snap or datetime(2100, 1, 1)).strftime("%Y-%m-%d %H:%M:%S")
        if p["day"]:
            f, t = window(wk, p["day"], p["shift_h"])
            if snap and f < snap < t:
                t = snap
                row["Note"] = f"day in progress - compared up to the model snapshot {snap:%Y-%m-%d %H:%M} (site time)"
            tk.update(FROM=f.strftime("%Y-%m-%d %H:%M:%S"), TO=t.strftime("%Y-%m-%d %H:%M:%S"))
        sql = v.render(sql_t, tk)
        t0 = time.time()
        try:
            if cur is None:
                raise RuntimeError("no replica connection")
            refs[wk] = num(cur.execute(sql).fetchone()[0])
            say(f"{code:10s} {k['KPI_Key']:12s} {row['Day']:10s} {wk:5s} ref={refs[wk]} model={model}  ({time.time() - t0:.1f}s)")
        except Exception as e:
            refs[wk] = None
            row["Ref_Error"] = re.sub(r"\s+", " ", str(e))[:200]
            say(f"!! {code} {k['KPI_Key']} {wk}: {row['Ref_Error']}")
    ta, tp = float(k["Tol_Abs"]), float(k["Tol_Pct"])
    row["Ref_Model_Window"], row["Ref_Intent_Window"] = refs.get(k["Model_Window"]), refs.get(k["Intent_Window"])
    if row.get("Ref_Error") or row["Model_Error"]:
        row["IMPL"] = row["INTENT"] = "ERROR"
    else:
        # a KPI with no activity: model blank / 0 and reference blank / 0 are the same answer
        m0 = model if model not in (None,) else (0.0 if k["Measure"].startswith(("KPI Active", "Prod Pallets", "KPI LTA", "KPI HOFF")) else None)
        row["IMPL"] = "MATCH" if close(m0, row["Ref_Model_Window"], ta, tp) or (not m0 and not row["Ref_Model_Window"]) else "DIFF"
        row["INTENT"] = "MATCH" if close(m0, row["Ref_Intent_Window"], ta, tp) or (not m0 and not row["Ref_Intent_Window"]) else "DIFF"
    if k["Kind"] == "NOW":
        rr = res.get(f"{code}|refresh", {})
        row["Note"] = f"model snapshot at {(rr.get('first') or {}).get('[v]', '?')} UTC"
    out.append(row)

cols = ["Site", "KPI", "Day", "Measure", "Model", "Ref_Model_Window", "Ref_Intent_Window", "IMPL", "INTENT", "Note", "Model_Error", "Ref_Error"]
with open(OUT / "reconcile.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(out)


def fmt(x):
    return "" if x is None else (f"{x:,.3f}" if abs(x) < 10 and x != int(x) else f"{x:,.0f}")


from collections import Counter  # noqa: E402
ci, cn_ = Counter(r["IMPL"] for r in out), Counter(r["INTENT"] for r in out)
md = ["# KPI reconciliation - model vs independent replica SQL", "",
      f"Run {datetime.now():%Y-%m-%d %H:%M} by `py tools/reconcile_kpis.py` ({len(sites)} site(s), last {NDAYS} shift days). "
      "Reference queries: `sql/reference/*.sql` (written from the KPI definitions); KPI list and tolerances: `config/kpi_reference.csv`.", "",
      f"**Implementation** (model vs reference over the window the measure implements): {dict(ci)}  ",
      f"**Intent** (model vs reference over the report day the page promises = shift day): {dict(cn_)}", "",
      "| Site | KPI | Day | Model | Ref (model window) | Ref (intent window) | Impl | Intent | Note |", "|---|---|---|---|---|---|---|---|---|"]
for r in out:
    md.append(f"| {r['Site']} | {r['KPI']} | {r['Day']} | {fmt(r.get('Model'))} | {fmt(r.get('Ref_Model_Window'))} | {fmt(r.get('Ref_Intent_Window'))} | "
              f"{r['IMPL']} | {r['INTENT']} | {(r.get('Note') or '')} {(r.get('Model_Error') or '')} {(r.get('Ref_Error') or '')} |")
(ROOT / "docs" / "RECONCILIATION.md").write_text("\n".join(md) + "\n", encoding="utf-8")
say(f"DONE implementation {dict(ci)} | intent {dict(cn_)} -> docs/RECONCILIATION.md, _uitest/reconcile.csv")
