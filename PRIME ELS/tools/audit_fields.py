"""Field-by-field audit of the open WH Hypercare KPI model: every column of every site table, for every site.

    py tools/audit_fields.py <PBIDesktop PID> [--sites A,B]

Per site x table x column: rows, empty (BLANK or "") count, min / max for numbers and dates. Flags:
  EMPTY_FOR_SITE   column 100 % empty at this site but filled at another site with rows  -> query / config issue to check
  EMPTY_ALL_SITES  column 100 % empty at every site that has rows                         -> source column not mapped
  NEGATIVE         numeric minimum < 0 (durations, quantities, counts)
  FUTURE_DATE      date / datetime later than tomorrow;  OLD_DATE  before 2020
  NO_ROWS          table has 0 rows at a site whose feature flag is ON
Queries run through run_dax_batch.ps1 (heartbeat every 30 s). Writes _uitest/audit_fields.csv; prints flagged rows.
"""
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# --service <workspaceId>/<datasetId> --model <...SemanticModel>: audit the PUBLISHED model (executeQueries; metadata from the TMDL)
SVC = None
if "--service" in sys.argv:
    sys.path.insert(0, str(HERE))
    from svc_dax import Svc, tmdl_columns
    SVC = Svc(sys.argv[sys.argv.index("--service") + 1])
    MODEL_DIR = Path(sys.argv[sys.argv.index("--model") + 1])
PID = 0 if SVC else int(sys.argv[1])
ONLY = set(sys.argv[sys.argv.index("--sites") + 1].upper().split(",")) if "--sites" in sys.argv else set()
OUT = Path(__file__).resolve().parents[2] / "_uitest"
OUT.mkdir(parents=True, exist_ok=True)
OUT.mkdir(exist_ok=True)
NEG_OK = re.compile(r"(?i)delta|diff|gap|variance|offset|balance|sort|rank|index|Δ|vs")
GATES = {"Level A": "Has_LevelA", "bin A": "Has_LevelA", "Outbound Pallet from Inv": "Has_LevelA", "HOFF": "Has_HOFF",
         "Produced": "Has_Production", "LTA": "Has_Production", "WorkLine": "Has_Production", "Planned": "Has_Production",
         "Short PO": "Has_Production", "SAP Plan": "Has_SAP_Plan", "Shipping Market": "Has_SAP_Plan", "SAP Production": "Has_SAP_Prod",
         "RPM Masterdata": "Has_RPM_Master"}


def batch(queries, tag):
    if SVC:
        return SVC.batch(queries, tag)
    qf, rf = OUT / f"_q_{tag}.json", OUT / f"_r_{tag}.json"
    qf.write_text(json.dumps(queries), encoding="utf-8")
    if rf.exists():
        rf.unlink()
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_dax_batch.ps1"), "-ProcId", str(PID),
                        "-InJson", str(qf), "-OutJson", str(rf), "-TimeoutSec", "120"], timeout=14400)
    if p.returncode != 0 or not rf.exists():
        raise SystemExit(f"!! DAX batch '{tag}' failed (exit {p.returncode})")
    res = json.loads(rf.read_text(encoding="utf-8-sig"))
    return {r["id"]: r for r in (res if isinstance(res, list) else [res])}


def tref(t):
    return "'" + t.replace("'", "''") + "'"


def all_rows(dax):
    if SVC:
        return SVC.rows(dax)
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(PID),
                        "-Dax", dax, "-TimeoutSec", "120"], capture_output=True, text=True, timeout=300)
    d = json.loads(p.stdout.strip())
    if isinstance(d, dict):
        raise SystemExit(f"!! meta query failed: {d}")
    return d


if SVC:
    _tc = tmdl_columns(MODEL_DIR)
    _names = sorted({t for t, _, _ in _tc})
    tables = {i: n for i, n in enumerate(_names)}
    _ids = {n: i for i, n in tables.items()}
    cols = [{"[T]": _ids[t], "[C]": c, "[DT]": dt} for t, c, dt in _tc]
else:
    tables = {r["[ID]"]: r["[Name]"] for r in all_rows('EVALUATE SELECTCOLUMNS(INFO.TABLES(), "ID", [ID], "Name", [Name])')}
    cols = all_rows('EVALUATE SELECTCOLUMNS(FILTER(INFO.COLUMNS(), [Type] IN {1, 2}), "T", [TableID], "C", [ExplicitName], "DT", [ExplicitDataType])')
sites = all_rows('EVALUATE SELECTCOLUMNS(Cfg_Site, "c", Cfg_Site[SiteCode], "p", Cfg_Site[Has_Production], "a", Cfg_Site[Has_LevelA], '
                 '"h", Cfg_Site[Has_HOFF], "s", Cfg_Site[Has_SAP_Plan], "q", Cfg_Site[Has_SAP_Prod], "r", Cfg_Site[Has_RPM_Master])')
FLAGKEY = {"Has_Production": "[p]", "Has_LevelA": "[a]", "Has_HOFF": "[h]", "Has_SAP_Plan": "[s]", "Has_SAP_Prod": "[q]", "Has_RPM_Master": "[r]"}
SITES = {s["[c]"]: s for s in sites if not ONLY or s["[c]"] in ONLY}
by_table = defaultdict(list)
for c in cols:
    by_table[tables[c["[T]"]]].append(c)
site_tables = sorted(t for t, cs in by_table.items() if any(c["[C]"] == "SiteCode" for c in cs) and not t.startswith("Cfg_"))
queries, index = [], {}
for t in site_tables:
    for s in SITES:
        flt = f'TREATAS({{"{s}"}}, Cfg_Site[SiteCode])'
        qid = f"{len(queries)}"
        queries.append({"id": qid, "dax": f'EVALUATE ROW("n", CALCULATE(COUNTROWS({tref(t)}), {flt}) + 0)'})
        index[qid] = (t, s, None, "rows")
        for c in by_table[t]:
            cn, dt = c["[C]"], c["[DT]"]
            if cn == "SiteCode" or cn.endswith(" @Site"):
                continue
            col = f"{tref(t)}[{cn.replace(']', ']]')}]"
            empty = (f"CALCULATE(COUNTROWS({tref(t)}), {flt}, KEEPFILTERS(FILTER(ALL({col}), ISBLANK({col}) || {col} = \"\"))) + 0" if dt == 2 else
                     f"CALCULATE(COUNTROWS({tref(t)}), {flt}, KEEPFILTERS(FILTER(ALL({col}), ISBLANK({col})))) + 0")
            parts = [f'"e", {empty}']
            if dt in (6, 8, 9, 10):
                parts += [f'"mn", CALCULATE(MIN({col}), {flt})', f'"mx", CALCULATE(MAX({col}), {flt})']
            qid = f"{len(queries)}"
            queries.append({"id": qid, "dax": "EVALUATE ROW(" + ", ".join(parts) + ")"})
            index[qid] = (t, s, cn, dt)
print(f"{len(site_tables)} tables, {sum(len(by_table[t]) for t in site_tables)} columns, {len(SITES)} sites -> {len(queries)} queries", flush=True)
res = batch(queries, "audit")
nrows = {}
rows = []
for qid, (t, s, cn, dt) in index.items():
    r = res.get(qid, {})
    if cn is None:
        nrows[(t, s)] = ((r.get("first") or {}).get("[n]") or 0) if not r.get("error") else None
        continue
    f = r.get("first") or {}
    rows.append({"Site": s, "Table": t, "Column": cn, "DT": dt, "Empty": f.get("[e]"), "Min": f.get("[mn]"), "Max": f.get("[mx]"),
                 "Error": r.get("error") or ""})
tomorrow = datetime.now() + timedelta(days=1)
# source state per site from the model's own Data Health table (dlytrn first / last event): an empty or not-yet-live replica
# explains empty tables - the report says so in Config & Health; it is not a query defect
from site_state import QUERY as _SQ, source_state
state = source_state(all_rows(_SQ))
print("source state:", state or "all sites live", flush=True)
filled = defaultdict(bool)
for r in rows:
    n = nrows.get((r["Table"], r["Site"])) or 0
    r["Rows"] = n
    if n and r["Empty"] is not None and r["Empty"] < n:
        filled[(r["Table"], r["Column"])] = True
out = []
for (t, s), n in sorted(nrows.items()):
    gates = {g for k, g in GATES.items() if k.lower() in t.lower()}          # every matching gate must be ON (LTA -> Level A = production AND Level A)
    on = all(str(SITES[s].get(FLAGKEY[g])) == "1" for g in gates)
    if n == 0 and on:
        out.append({"Site": s, "Table": t, "Column": "*", "Rows": 0, "Empty": "", "Min": "", "Max": "", "Flag": "NO_ROWS", "Error": ""})
    if n is None:
        out.append({"Site": s, "Table": t, "Column": "*", "Rows": "", "Empty": "", "Min": "", "Max": "", "Flag": "ERROR", "Error": "row count failed"})
for r in rows:
    f = []
    n = r["Rows"]
    if r["Error"]:
        f.append("ERROR")
    elif n and r["Empty"] == n:
        f.append("EMPTY_FOR_SITE" if filled[(r["Table"], r["Column"])] else "EMPTY_ALL_SITES")
    if r["DT"] in (6, 8, 10) and isinstance(r["Min"], (int, float)) and r["Min"] < 0 and not NEG_OK.search(r["Column"]):
        f.append("NEGATIVE")
    if r["DT"] == 9:
        for k in ("Min", "Max"):
            try:
                r[k] = datetime.strptime(str(r[k])[:16], "%Y-%m-%d %H:%M") if r[k] else None
            except ValueError:
                r[k] = None
        if r["Max"] and r["Max"] > tomorrow:
            f.append("FUTURE_DATE")
        if r["Min"] and r["Min"].year < 2020:
            f.append("OLD_DATE")
        r["Min"] = r["Min"].strftime("%Y-%m-%d %H:%M") if r["Min"] else ""
        r["Max"] = r["Max"].strftime("%Y-%m-%d %H:%M") if r["Max"] else ""
    r["Flag"] = ",".join(f)
    out.append(r)
# verified, explained patterns (config/field_expectations.csv) -> EXPECTED with the reason; anything else stays a defect
EXPECT = list(csv.DictReader(open(ROOT / "config" / "field_expectations.csv", encoding="utf-8-sig")))
ONE_SITE = len({r["Site"] for r in out}) == 1      # single-site file: 'empty at this site' and 'empty at every site' are the same fact
for r in out:
    if not r["Flag"]:
        continue
    keep, why = [], []
    for fl in r["Flag"].split(","):
        hit = None
        same = {fl, "EMPTY_FOR_SITE", "EMPTY_ALL_SITES"} if ONE_SITE and fl in ("EMPTY_FOR_SITE", "EMPTY_ALL_SITES") else {fl}
        for e in EXPECT:
            sites = {x.strip() for x in e["Sites"].split(",")}
            if (e["Flag"] in same and ("*" in sites or r["Site"] in sites) and re.search(e["Table"], r["Table"])
                    and ((e["Column"] == "*") == (r["Column"] == "*")) and (e["Column"] == "*" or re.search(e["Column"], r["Column"]))):
                if fl == "FUTURE_DATE" and e["Max_Days_Ahead"] and r["Max"]:
                    if datetime.strptime(r["Max"], "%Y-%m-%d %H:%M") > datetime.now() + timedelta(days=int(e["Max_Days_Ahead"])):
                        continue
                hit = e
                break
        if not hit and fl in ("NO_ROWS", "EMPTY_FOR_SITE") and r["Site"] in state:
            hit = {"Reason": state[r["Site"]]}
        (why if hit else keep).append(f"{fl}: {hit['Reason']}" if hit else fl)
    r["Flag"], r["Expected"] = ",".join(keep), " | ".join(why)
with open(OUT / "audit_fields.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["Site", "Table", "Column", "Rows", "Empty", "Min", "Max", "Flag", "Expected", "Error"], extrasaction="ignore")
    w.writeheader()
    w.writerows(out)
flagged = [r for r in out if r["Flag"]]
from collections import Counter
print(f"DONE {len(out)} field checks, defects {len(flagged)}: {dict(Counter(x for r in flagged for x in r['Flag'].split(',')))}, "
      f"expected (explained in config/field_expectations.csv) {sum(1 for r in out if r.get('Expected'))} -> _uitest/audit_fields.csv")
for r in sorted(flagged, key=lambda r: (r["Flag"], r["Table"], r["Column"], r["Site"]))[:120]:
    print(f"  {r['Flag']:16s} {r['Site']:10s} {r['Table']} [{r['Column']}] rows={r['Rows']} empty={r['Empty']} min={r['Min']} max={r['Max']} {r['Error'][:80]}")
