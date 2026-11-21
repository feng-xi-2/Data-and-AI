"""Report intent catalogue + intent checks.

    py tools/report_intent.py <PBIDesktop PID> [--report <.Report/definition>] [--replay _uitest/visual_replay.csv]

1. CATALOGUE  docs/REPORT_INTENT.md: every page (business question from config/page_guide.csv) and every visual with its fields,
              the tables they really depend on (INFO.CALCDEPENDENCY of the open model, measures resolved transitively) and the
              resulting TIME BASIS from config/table_basis.csv:
                 DAY       report day (shift day) - must change with the day slicer when there is activity
                 SNAPSHOT  live "now" state of the warehouse (locmst / inventory) - cannot change with the day; must say so
                 WINDOW    rolling detail window (last N days)      PLAN   plans / orders      MASTER / CONFIG   reference data
2. CHECKS     (on tools/visual_replay.py results, every visual x site x day):
   I1 DAY_INSENSITIVE      DAY visual returns the identical result on every replayed day with data (day filter not applied)
   I2 SNAPSHOT_UNLABELLED  SNAPSHOT-only visual whose title / page does not tell the user it is live (now / live / current)
   I3 SAME_FOR_ALL_SITES   identical result for every site (site filter not applied) - DAY / SNAPSHOT / WINDOW visuals
   I4 BLANK / ERROR        visual blank or failing where the page applies to the site (from the replay status)
Writes docs/REPORT_INTENT.md and _uitest/intent_check.csv; exit code 1 when an I1 / I3 / I4 defect is found.
"""
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
args = sys.argv[1:]
PID = int(args[0])
REPORT = Path(args[args.index("--report") + 1]) if "--report" in args else ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.Report" / "definition"
REPLAY = Path(args[args.index("--replay") + 1]) if "--replay" in args else (Path(__file__).resolve().parents[2] / "_uitest" / "visual_replay.csv")
OUT = Path(__file__).resolve().parents[2] / "_uitest"
OUT.mkdir(parents=True, exist_ok=True)
LIVE_WORDS = re.compile(r"(?i)\b(now|live|current|right now|snapshot|real[- ]time|on hand|in stock)\b")
SKIP_TYPES = {"slicer", "textbox", "shape", "image", "actionButton", None}


def dax(q):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(PID),
                        "-Dax", q, "-TimeoutSec", "120"], capture_output=True, text=True, timeout=300)
    d = json.loads(p.stdout.strip() or "{}")
    if not isinstance(d, list):
        raise SystemExit(f"!! DAX failed: {p.stdout[:300]} {p.stderr[:300]}")
    return d


# ---------------------------------------------------------------- dependencies (live model)
deps = dax('EVALUATE SELECTCOLUMNS(FILTER(INFO.CALCDEPENDENCY(), [OBJECT_TYPE] = "MEASURE"), "o", [OBJECT], '
           '"rt", [REFERENCED_OBJECT_TYPE], "rtab", [REFERENCED_TABLE], "ro", [REFERENCED_OBJECT])')
m_meas, m_tabs = defaultdict(set), defaultdict(set)
for r in deps:
    if r["[rt]"] == "MEASURE":
        m_meas[r["[o]"]].add(r["[ro]"])
    elif r["[rtab]"]:
        m_tabs[r["[o]"]].add(r["[rtab]"])
closure = {}


def tables_of(m, seen=None):
    if m in closure:
        return closure[m]
    seen = seen or set()
    if m in seen:
        return set()
    seen.add(m)
    t = set(m_tabs.get(m, set()))
    for x in m_meas.get(m, set()):
        t |= tables_of(x, seen)
    closure[m] = t
    return t


BASIS = {r["Table"]: r for r in csv.DictReader(open(ROOT / "config" / "table_basis.csv", encoding="utf-8-sig"))}
GUIDE = {r["Page"]: r for r in csv.DictReader(open(ROOT / "config" / "page_guide.csv", encoding="utf-8-sig"))}
_EXP = ROOT / "config" / "visual_expectations.csv"
EXPECT = list(csv.DictReader(open(_EXP, encoding="utf-8-sig"))) if _EXP.exists() else []
_cond = {}


def expected(page, label, site, day, check="EMPTY"):
    """config/visual_expectations.csv: an EMPTY visual is explained only when the row's DAX condition is TRUE for that site and
    day in the open model (data-proven, no site list) - at a site where the condition is false the same EMPTY stays a defect."""
    for e in EXPECT:
        if (e.get("Check") or "EMPTY") != check or not (re.search(e["Page"], page) and re.search(e["Visual"], label)):
            continue
        k = (e["Condition"], site, day)
        if k not in _cond:
            flt = f'TREATAS({{"{site}"}}, Cfg_Site[SiteCode])'
            if day != "default":
                y, m, d = day[:10].split("-")
                flt += f", TREATAS({{DATE({int(y)},{int(m)},{int(d)})}}, DimDate[Date])"
            res = dax(f'EVALUATE ROW("v", CALCULATE(IF({e["Condition"]}, 1, 0), {flt}))')
            _cond[k] = bool(res) and res[0].get("[v]") == 1
        if _cond[k]:
            return e["Reason"]
    return None


def basis_of(tables):
    b = {BASIS[t]["Basis"] for t in tables if t in BASIS}
    for k in ("DAY", "WINDOW", "PLAN", "SNAPSHOT", "MASTER", "META"):
        if k in b:
            return k
    return "CONFIG"


def title_of(j):
    for t in j.get("visual", {}).get("visualContainerObjects", {}).get("title", []):
        txt = t.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        if txt:
            return txt.strip("'")
    return ""


# ---------------------------------------------------------------- report inventory
pages = []
for pj in sorted(REPORT.glob("pages/*/page.json")):
    p = json.loads(pj.read_text(encoding="utf-8"))
    if p.get("visibility") == "HiddenInViewMode":
        continue
    texts = []
    vis = []
    for vf in (pj.parent / "visuals").glob("*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        v = j.get("visual", {})
        vt = v.get("visualType")
        if vt == "textbox":
            texts.append(json.dumps(v.get("objects", {}))[:2000])
        projs = [pr for role in v.get("query", {}).get("queryState", {}).values() for pr in role.get("projections", [])]
        if vt in SKIP_TYPES or j.get("isHidden") or not projs:
            continue
        fields, tabs, labels = [], set(), []
        for pr in projs:
            f = pr["field"]
            labels.append(pr.get("displayName") or pr.get("nativeQueryRef") or "")
            if "Measure" in f:
                n = f["Measure"]["Property"]
                fields.append(f"[{n}]")
                tabs |= tables_of(n)
            else:
                x = f.get("Column") or f.get("Aggregation", {}).get("Expression", {}).get("Column")
                if x:
                    t = x["Expression"]["SourceRef"].get("Entity")
                    fields.append(f"{t}[{x['Property']}]")
                    tabs.add(t)
        b = basis_of(tabs)
        vis.append({"id": vf.parent.name, "type": vt, "title": title_of(j), "fields": fields, "tables": sorted(tabs), "basis": b,
                    "labels": " ".join(labels)})
    pages.append({"name": p["displayName"], "visuals": vis, "text": " ".join(texts)})

# ---------------------------------------------------------------- checks on the replay
defects = []
rep = list(csv.DictReader(open(REPLAY, encoding="utf-8"))) if REPLAY.exists() else []
by_vis = defaultdict(list)
for r in rep:
    by_vis[(r["Page"], r.get("VisualId") or r["Visual"])].append(r)

# activity of every DAY table per site x replayed day: an EMPTY day-visual is EXPLAINED only when the report-day tables it
# depends on really have no rows for that site and day (replica retention / no operation), otherwise it is a defect
site_today = {r["[s]"]: str(r["[d]"])[:10] for r in dax(
    'EVALUATE SELECTCOLUMNS(Cfg_Site, "s", Cfg_Site[SiteCode], "d", FORMAT(CALCULATE([Site Shift Today]), "yyyy-mm-dd"))')}
days = sorted({r["Day"] for r in rep if r["Day"] != "default"})
activity = {}
qs = []
in_model = {r["[n]"] for r in dax('EVALUATE SELECTCOLUMNS(INFO.TABLES(), "n", [Name])')}   # e.g. SAP tables left out at build
for t, b in BASIS.items():
    if b["Basis"] != "DAY" or not b["Day_Field"] or t not in in_model:
        continue
    col = f"'{t}'[{b['Day_Field']}]"
    for s in site_today:
        for d in days + ["default"]:
            dd = site_today[s] if d == "default" else d
            y, m, dy = dd.split("-")
            qs.append((t, s, d, f'ROW("k", {len(qs)}, "n", CALCULATE(COUNTROWS(\'{t}\'), REMOVEFILTERS(\'{t}\'), TREATAS({{"{s}"}}, Cfg_Site[SiteCode]), '
                                 f'{col} >= DATE({int(y)},{int(m)},{int(dy)}), {col} < DATE({int(y)},{int(m)},{int(dy)}) + 1) + 0)'))
for i in range(0, len(qs), 60):
    chunk = qs[i:i + 60]
    res = dax("EVALUATE UNION(" + ", ".join(q[3] for q in chunk) + ")") if len(chunk) > 1 else dax("EVALUATE " + chunk[0][3])
    got = {int(r["[k]"]): r.get("[n]", 0) for r in res}
    for j, (t, s, d, _) in enumerate(chunk):
        if i + j not in got:
            raise SystemExit(f"!! activity query lost row {i + j} ({t} {s} {d})")
        activity[(t, s, d)] = got[i + j]
sys.path.insert(0, str(HERE))
from site_state import QUERY as _SQ, source_state  # noqa: E402
STATE = source_state(dax(_SQ))
print("source state:", STATE or "all sites live", flush=True)
for pg in pages:
    for v in pg["visuals"]:
        rows = by_vis.get((pg["name"], v["id"]), [])
        label = v["title"] or (v["fields"][0] if v["fields"] else v["id"])
        guide = GUIDE.get(pg["name"], {}).get("How_Calculated", "")
        if v["basis"] == "SNAPSHOT" and not (LIVE_WORDS.search(v["title"]) or LIVE_WORDS.search(v["labels"]) or LIVE_WORDS.search(pg["name"])
                                             or LIVE_WORDS.search(pg["text"]) or LIVE_WORDS.search(guide)):
            defects.append(("I2", "SNAPSHOT_UNLABELLED", pg["name"], label, "", "live state - title / page should say 'now' or 'live'"))
        if not rows:
            continue
        ok = [r for r in rows if r["Status"] == "OK" and r.get("Hash")]
        dtabs_v = [t for t in v["tables"] if BASIS.get(t, {}).get("Basis") == "DAY"]
        if v["basis"] in ("DAY",):
            for site in {r["Site"] for r in ok}:
                # only days on which the visual's own day tables have rows: a day outside the replica / without activity may
                # legitimately show the same "not in replica" / "no activity" text
                days = {r["Day"]: r["Hash"] for r in ok if r["Site"] == site and r["Day"] != "default"
                        and sum(activity.get((t, site, r["Day"]), 0) for t in dtabs_v) > 0}
                if len(days) >= 2 and len(set(days.values())) == 1:
                    if (why := expected(pg["name"], label, site, "default", "DAY_INSENSITIVE")):
                        defects.append(("I5", "CONSTANT_BY_DESIGN", pg["name"], label, site, "explained: " + why))
                    else:
                        defects.append(("I1", "DAY_INSENSITIVE", pg["name"], label, site, f"identical on {len(days)} days with activity {sorted(days)}"))
        if v["basis"] in ("DAY", "SNAPSHOT", "WINDOW"):
            def trivial(r):
                try:
                    vals = list(json.loads(r["Sample"]).values())
                except Exception:
                    return False
                return str(r.get("Rows")) in ("1", "1.0") and all(x in (None, 0, "", "-", 0.0) for x in vals)
            dflt = {r["Site"]: r["Hash"] for r in ok if r["Day"] == "default" and not trivial(r)}
            if len(dflt) >= 3 and len(set(dflt.values())) == 1:
                whys = [expected(pg["name"], label, s_, "default", "SAME_FOR_ALL_SITES") for s_ in dflt]
                if all(whys):
                    defects.append(("I5", "SAME_BY_DESIGN", pg["name"], label, ",".join(sorted(dflt)), "explained: " + whys[0]))
                else:
                    defects.append(("I3", "SAME_FOR_ALL_SITES", pg["name"], label, ",".join(sorted(dflt)), "identical result for every site"))
        for r in rows:
            if r["Status"] in ("EMPTY", "ERROR", "NO VALUE"):
                dtabs = [t for t in v["tables"] if BASIS.get(t, {}).get("Basis") == "DAY" and (t, r["Site"], r["Day"]) in activity]
                if r["Status"] != "ERROR" and dtabs and all(activity[(t, r["Site"], r["Day"])] == 0 for t in dtabs):
                    defects.append(("I5", "EMPTY_NO_ACTIVITY", pg["name"], label, f"{r['Site']}@{r['Day']}",
                                    "explained: no rows that day in " + ", ".join(dtabs)))
                elif r["Status"] != "ERROR" and (why := expected(pg["name"], label, r["Site"], r["Day"])):
                    defects.append(("I5", "EMPTY_EXPECTED", pg["name"], label, f"{r['Site']}@{r['Day']}", "explained: " + why))
                elif r["Status"] != "ERROR" and r["Site"] in STATE:
                    defects.append(("I5", "EMPTY_SOURCE_STATE", pg["name"], label, f"{r['Site']}@{r['Day']}", "explained: " + STATE[r["Site"]]))
                elif r["Status"] != "ERROR" and v["basis"] in ("SNAPSHOT", "PLAN", "WINDOW", "MASTER"):
                    defects.append(("I5", "EMPTY_SOURCE", pg["name"], label, f"{r['Site']}@{r['Day']}",
                                    f"explained if the {v['basis'].lower()} source is empty at this site (see audit_fields NO_ROWS)"))
                else:
                    defects.append(("I4", r["Status"], pg["name"], label, f"{r['Site']}@{r['Day']}", (r.get("Error") or "")[:120]))

with open(OUT / "intent_check.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["Rule", "Check", "Page", "Visual", "Where", "Detail"])
    w.writerows(defects)

# ---------------------------------------------------------------- catalogue
from collections import Counter  # noqa: E402
md = ["# Report intent catalogue", "",
      f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py tools/report_intent.py` from the report definition, `config/page_guide.csv`, "
      "`config/table_basis.csv` and the model's real dependencies (INFO.CALCDEPENDENCY). Time basis: **DAY** = report day "
      "(shift day from Shift1_Start, site-local) - changes with the day slicer; **SNAPSHOT** = the warehouse right now - "
      "cannot change with the day; **WINDOW** = last N days of detail; **PLAN** = plans / orders; **MASTER / CONFIG** = reference.", "",
      f"Intent checks on `{REPLAY.name}` ({len(rep)} visual x site x day results): " + (", ".join(f"{k} {v}" for k, v in sorted(Counter(d[1] for d in defects).items())) or "no defects"), ""]
for pg in pages:
    g = GUIDE.get(pg["name"], {})
    md += [f"## {pg['name']}" + (f"  _(needs {g['Requires']})_" if g.get("Requires") else ""), "",
           f"**Question it answers:** {g.get('How_Calculated', '(no page guide entry)')}", "",
           "| Visual | Type | Basis | Fields | Depends on |", "|---|---|---|---|---|"]
    for v in sorted(pg["visuals"], key=lambda x: (x["basis"], x["title"])):
        md.append(f"| {v['title'] or '(untitled)'} | {v['type']} | {v['basis']} | {', '.join(v['fields'])[:160]} | "
                  f"{', '.join(t for t in v['tables'] if t in BASIS)[:120]} |")
    md.append("")
if defects:
    md += ["## Intent check findings", "", "| Rule | Check | Page | Visual | Where | Detail |", "|---|---|---|---|---|---|"]
    md += [f"| {' | '.join(str(x).replace('|', '/') for x in d)} |" for d in defects[:400]]
(ROOT / "docs" / "REPORT_INTENT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
print(f"{sum(len(p['visuals']) for p in pages)} visuals on {len(pages)} pages catalogued -> docs/REPORT_INTENT.md; "
      f"intent findings: {dict(Counter(d[1] for d in defects))} -> _uitest/intent_check.csv")
sys.exit(1 if any(d[0] in ("I1", "I3", "I4") for d in defects) else 0)


