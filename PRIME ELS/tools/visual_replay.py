"""Visual replay test: every data visual of every page, for every site and several days, through the model - the way the visual queries it.

    py tools/visual_replay.py <PBIDesktop PID> [--days 4] [--report <path to .Report/definition>] [--sites A,B]
                              [--pages "A,B"] [--timeout 60]
    py tools/visual_replay.py --service <workspaceId>/<datasetId> ...   # the PUBLISHED model (executeQueries API, 4 in parallel)

For each page x visual (not slicers / text / shapes / images) the visual's fields are read from the PBIR definition
(queryState projections: grouping columns, measures, aggregations) together with its visual- and page-level filters,
and turned into the DAX query the visual runs:
    group-by columns  -> SUMMARIZECOLUMNS(cols, filters, "m", measure ...)   (rows only where a measure is non-blank)
    measures only     -> ROW("m", CALCULATE(measure, filters))
The page's slicers are set like a user would: Site slicer = the site, day slicers (DimDate[Date], shift_date,
Start/End Date) = the day; "no day" = default view (today). Result per visual / site / day:
    OK     data returned          EMPTY  0 rows / every value blank, "" or "-"
    NA     page needs a feature the site does not run (Cfg_PageGuide.Requires)   ERROR  query error
Writes _uitest/visual_replay.csv and prints the EMPTY / ERROR list grouped by page and visual.
"""
import csv
import json
import re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
args = sys.argv[1:]
# --service <workspaceId>/<datasetId>: replay against the PUBLISHED model (executeQueries REST API) instead of an open Desktop
SERVICE = args[args.index("--service") + 1] if "--service" in args else ""
PID = 0 if SERVICE else int(args[0])


def opt(name, default):
    return args[args.index(name) + 1] if name in args else default


DAYS = int(opt("--days", "4"))
REPORT = Path(opt("--report", str(ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.Report" / "definition")))
PAGES_ONLY = [x.strip() for x in opt("--pages", "").split(",") if x.strip()]     # display names, e.g. "Process Flow,Trucks & TTAT"
TIMEOUT_S = opt("--timeout", "60")   # per-query seconds; raise on a low-memory PC
OUT_DIR = Path(__file__).resolve().parents[2] / "_uitest"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)
SKIP_TYPES = {"slicer", "textbox", "shape", "image", "actionButton", None}
AGG = {0: "SUM", 1: "AVERAGE", 2: "COUNT", 3: "MIN", 4: "MAX", 5: "DISTINCTCOUNT", 6: "MEDIAN"}
DATE_COLS = {("DimDate", "Date"), ("Produced Pallet", "shift_date"), ("StartDate", "Start Date"), ("EndDate", "End Date")}
CMP = {0: "=", 1: ">", 2: ">=", 3: "<", 4: "<="}


def tref(t):
    return "'" + t.replace("'", "''") + "'"


def cref(t, c):
    return f"{tref(t)}[{c.replace(']', ']]')}]"


def lit(v):
    s = str(v)
    if s == "null":
        return "BLANK()"
    if s in ("true", "false"):
        return s.upper() + "()"
    m = re.fullmatch(r"datetime'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?'", s)
    if m:
        y, mo, d, h, mi, se = map(int, m.groups())
        return f"DATE({y},{mo},{d})" + (f" + TIME({h},{mi},{se})" if (h, mi, se) != (0, 0, 0) else "")
    if s.startswith("'") and s.endswith("'"):
        return '"' + s[1:-1].replace("''", "'").replace('"', '""') + '"'
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)[LDM]?", s)
    if m:
        return m.group(1)
    raise ValueError(f"literal {s}")


class Unsupported(Exception):
    pass


def field_ref(f, alias=None):
    """PBIR field -> (kind, dax, table)."""
    if "Column" in f:
        x = f["Column"]
        src = x["Expression"]["SourceRef"]
        t = src.get("Entity") or (alias or {}).get(src.get("Source"))
        return "col", cref(t, x["Property"]), t
    if "Measure" in f:
        x = f["Measure"]
        return "meas", f"[{x['Property'].replace(']', ']]')}]", None
    if "Aggregation" in f:
        a = f["Aggregation"]
        k, c, t = field_ref(a["Expression"], alias)
        return "meas", f"{AGG.get(a.get('Function', 0), 'SUM')}({c})", t
    raise Unsupported(list(f)[0])


def cond(c, alias):
    """PBIR filter condition -> (dax boolean, set of tables, uses_measure)."""
    if "In" in c:
        x = c["In"]
        refs = [field_ref(e, alias) for e in x["Expressions"]]
        if any(k == "meas" for k, _, _ in refs):
            raise Unsupported("measure filter")
        vals = x.get("Values", [])
        if len(refs) == 1:
            return f"{refs[0][1]} IN {{{', '.join(lit(v[0]['Literal']['Value']) for v in vals)}}}", {refs[0][2]}
        rows = " || ".join("(" + " && ".join(f"{r[1]} = {lit(v[i]['Literal']['Value'])}" for i, r in enumerate(refs)) + ")" for v in vals)
        return f"({rows or 'FALSE()'})", {r[2] for r in refs}
    if "Not" in c:
        e, ts = cond(c["Not"]["Expression"], alias)
        return f"NOT ({e})", ts
    if "And" in c or "Or" in c:
        k = "And" if "And" in c else "Or"
        a, ta = cond(c[k]["Left"], alias)
        b, tb = cond(c[k]["Right"], alias)
        return f"({a} {'&&' if k == 'And' else '||'} {b})", ta | tb
    if "Comparison" in c:
        x = c["Comparison"]
        k, l, t = field_ref(x["Left"], alias)
        if k == "meas":
            raise Unsupported("measure filter")
        return f"{l} {CMP.get(x['ComparisonKind'], '=')} {lit(x['Right']['Literal']['Value'])}", {t}
    raise Unsupported(list(c)[0])


def filters_of(fc):
    out, skipped = [], []
    for f in (fc or {}).get("filters", []):
        flt = f.get("filter")
        if not flt or f.get("type") == "TopN":
            if flt:
                skipped.append("TopN")
            continue
        alias = {x["Name"]: x["Entity"] for x in flt.get("From", [])}
        for w in flt.get("Where", []):
            c = w["Condition"]
            cmp = c.get("Not", {}).get("Expression", {}).get("Comparison")
            if cmp and "Measure" in cmp.get("Left", {}) and cmp.get("Right", {}).get("Literal", {}).get("Value") == "null":
                # measure "is not blank" (e.g. the site-scope filter of column-only visuals) -> applied on the result rows
                out.append("MEASURE_NOT_BLANK:" + field_ref(cmp["Left"], alias)[1])
                continue
            cmp = c.get("Comparison")
            if cmp and "Measure" in cmp.get("Left", {}) and "Literal" in cmp.get("Right", {}):
                # measure comparison (e.g. [Truck Close Time Range] = 1) -> applied on the result rows, like the visual does
                op = CMP.get(cmp["ComparisonKind"], "=")
                out.append("MEASURE_NOT_BLANK:" + field_ref(cmp["Left"], alias)[1] + "\x1f" + f"{op} {lit(cmp['Right']['Literal']['Value'])}")
                continue
            try:
                e, ts = cond(c, alias)
                if len(ts) != 1:
                    raise Unsupported("multi-table filter")
                t = next(iter(ts))
                cols = sorted(set(re.findall(re.escape(tref(t)) + r"\[[^\]]+\]", e)))
                out.append(f"KEEPFILTERS(FILTER(ALL({', '.join(cols)}), {e}))")
            except (Unsupported, ValueError, KeyError) as ex:
                skipped.append(str(ex))
    return out, skipped


def title_of(j, fallback):
    for t in j.get("visual", {}).get("visualContainerObjects", {}).get("title", []):
        v = t.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        if v:
            return v.strip("'")
    return fallback


# ------------------------------------------------------------------ read report
pages = []
for pj in sorted(REPORT.glob("pages/*/page.json")):
    p = json.loads(pj.read_text(encoding="utf-8"))
    if PAGES_ONLY and p["displayName"] not in PAGES_ONLY:
        continue
    pflt, pskip = filters_of(p.get("filterConfig"))
    vis, dslic, oslic = [], set(), set()
    for vf in (pj.parent / "visuals").glob("*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        v = j.get("visual", {})
        vt = v.get("visualType")
        projs = [pr for role in v.get("query", {}).get("queryState", {}).values() for pr in role.get("projections", [])]
        if vt == "slicer":
            for pr in projs:
                if "Column" in pr["field"]:
                    x = pr["field"]["Column"]
                    key = (x["Expression"]["SourceRef"].get("Entity"), x["Property"])
                    if key in DATE_COLS:
                        dslic.add(key)
                    elif key[0] and key[0] != "Cfg_Site" and not key[0].startswith("Input ") and key[0] not in ("StartTime", "EndTime"):
                        oslic.add(key)
            continue
        if vt in SKIP_TYPES or j.get("isHidden") or not projs:
            continue
        cols, meas, bad = [], [], []
        for pr in projs:
            try:
                k, d, _ = field_ref(pr["field"])
                (cols if k == "col" else meas).append((pr.get("queryRef", d), d))
            except Unsupported as e:
                bad.append(str(e))
        vflt, vskip = filters_of(j.get("filterConfig"))
        name = title_of(j, (meas[0][0] if meas else cols[0][0]) if (meas or cols) else vf.parent.name)
        vis.append({"id": vf.parent.name, "type": vt, "title": name, "cols": cols, "meas": meas, "filters": vflt,
                    "skipped": vskip + bad})
    pages.append({"name": p["displayName"], "hidden": p.get("visibility") == "HiddenInViewMode", "filters": pflt, "skipped": pskip,
                  "date_slicers": sorted(dslic), "slicers": sorted(oslic), "visuals": vis})

# ------------------------------------------------------------------ sites, page requirements
_svc_tok = {"t": None, "at": 0}


def svc_query(dax, all_rows=False):
    """One DAX query on the published model (executeQueries): same result shape as run_dax_batch.ps1. Retries 429 / network drops."""
    import hashlib
    import requests
    sys.path.insert(0, str(HERE))
    from publish import token
    if time.time() - _svc_tok["at"] > 1800:
        _svc_tok.update(t=token("https://analysis.windows.net/powerbi/api/.default"), at=time.time())
    ws, ds = SERVICE.split("/")
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{ds}/executeQueries"
    t0 = time.time()
    for attempt in range(6):
        try:
            r = requests.post(url, headers={"Authorization": "Bearer " + _svc_tok["t"]}, timeout=int(TIMEOUT_S) + 60,
                              json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}})
        except requests.RequestException as e:
            time.sleep(10 * (attempt + 1))
            err = f"network: {type(e).__name__}"
            continue
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "20")))
            continue
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            try:
                e = r.json().get("error", {})
                det = e.get("pbi.error", {}).get("details", [])
                msg = next((d.get("detail", {}).get("value") for d in det if d.get("code") == "DetailsMessage"), None) or e.get("message") or r.text
            except ValueError:
                msg = r.text
            return {"rows": 0, "first": None, "error": str(msg)[:400], "ms": ms}
        res = r.json()["results"][0]
        if res.get("error"):
            return {"rows": 0, "first": None, "error": json.dumps(res["error"])[:400], "ms": ms}
        rows = res["tables"][0].get("rows", []) if res.get("tables") else []
        blob = "\x1e".join("\x1f".join("" if v is None else str(v) for v in row.values()) for row in rows)
        return {"rows": len(rows), "first": rows[0] if rows else None, "ms": ms,
                "hash": hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16], **({"all": rows} if all_rows else {})}
    return {"rows": 0, "first": None, "error": f"executeQueries failed after retries ({err if 'err' in dir() else 'HTTP 429'})",
            "ms": int((time.time() - t0) * 1000)}


def run_batch(queries, tag):
    """Runs the queries with live heartbeat output (never captured / silent); a non-zero exit or missing result file stops the test."""
    if SERVICE:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        out, t0, beat, nerr = {}, time.time(), time.time(), 0
        svc_query("EVALUATE ROW(\"x\", 1)")            # token once, before the threads
        with ThreadPoolExecutor(4) as ex:              # executeQueries allows 120 queries / minute per user
            futs = {ex.submit(svc_query, q["dax"]): q["id"] for q in queries}
            for i, f in enumerate(as_completed(futs), 1):
                out[futs[f]] = dict(f.result(), id=futs[f])
                nerr += bool(out[futs[f]].get("error"))
                if time.time() - beat > 30:
                    print(f"[{time.strftime('%H:%M:%S')}] heartbeat: {i}/{len(queries)} done, errors {nerr} ({time.time() - t0:.0f}s)", flush=True)
                    beat = time.time()
        return out
    qf, rf = OUT_DIR / f"_q_{tag}.json", OUT_DIR / f"_r_{tag}.json"
    qf.write_text(json.dumps(queries), encoding="utf-8")
    if rf.exists():
        rf.unlink()
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_dax_batch.ps1"), "-ProcId", str(PID),
                        "-InJson", str(qf), "-OutJson", str(rf), "-TimeoutSec", TIMEOUT_S], timeout=14400)
    if p.returncode != 0 or not rf.exists():
        raise SystemExit(f"!! DAX batch '{tag}' failed (exit {p.returncode}) - see the lines above")
    res = json.loads(rf.read_text(encoding="utf-8-sig"))
    return {r["id"]: r for r in (res if isinstance(res, list) else [res])}


csv_sites = list(csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig")))
if "--overrides" in sys.argv and (ROOT / "config" / "service_overrides.csv").exists():   # same settings as build_pbip --overrides
    _ov = list(csv.DictReader(open(ROOT / "config" / "service_overrides.csv", encoding="utf-8-sig")))
    csv_sites = [dict(s, **{o["Setting"]: o["Value"] for o in _ov if o["SiteCode"] == s["SiteCode"]}) for s in csv_sites]
_ex = {v.strip().upper() for r in csv.DictReader(open(ROOT / "config" / "build_options.csv", encoding="utf-8-sig"))
       if r["Setting"] == "AllSites_Exclude" for v in r["Value"].split("|") if v.strip()} if (ROOT / "config" / "build_options.csv").exists() else set()
_only_arg = opt("--sites", "")
if not _only_arg:                               # default = the sites of the all-sites report (build_options AllSites_Exclude)
    csv_sites = [s for s in csv_sites if s["SiteCode"].upper() not in _ex]
_opts = {r["Setting"]: r["Value"].strip() for r in csv.DictReader(open(ROOT / "config" / "build_options.csv", encoding="utf-8-sig"))} \
    if (ROOT / "config" / "build_options.csv").exists() else {}
if _opts.get("Include_SAP_CDL", "0") != "1":   # same as build_pbip.apply_build_options: SAP / CDL left out of the built files
    csv_sites = [dict(s, Has_SAP_Plan="0", Has_SAP_Prod="0") for s in csv_sites]
only = set(opt("--sites", "").upper().split(",")) - {""}
SITES = [s for s in csv_sites if not only or s["SiteCode"] in only]
REQ = {r["Page"]: r.get("Requires", "") for r in csv.DictReader(open(ROOT / "config" / "page_guide.csv", encoding="utf-8-sig"))}

today = date.today()
DAYS_LIST = [None] + [today - timedelta(days=i) for i in range(DAYS)]


def day_filters(page, d):
    if d is None:
        return []
    out = []
    for t, c in page["date_slicers"]:
        out.append(f"TREATAS({{DATE({d.year},{d.month},{d.day})}}, {cref(t, c)})")
    return out


FILTER_N = int(opt("--filters", "0"))   # filter-by-filter mode: N most frequent values of every slicer per site


def dax_value(v):
    m = re.match(r"/Date\((-?\d+)\)/", str(v))
    if m:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
        return f"DATE({dt.year},{dt.month},{dt.day})"
    if isinstance(v, bool):
        return "TRUE()" if v else "FALSE()"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace('"', '""') + '"'


def slicer_values(t, c, site, n):
    dax = (f'EVALUATE TOPN({n}, FILTER(ADDCOLUMNS(CALCULATETABLE(VALUES({cref(t, c)}), TREATAS({{"{site}"}}, Cfg_Site[SiteCode])), '
           f'"@n", CALCULATE(COUNTROWS({tref(t)}), TREATAS({{"{site}"}}, Cfg_Site[SiteCode]))), NOT ISBLANK({cref(t, c)}) && [@n] > 0), [@n], DESC)')
    if SERVICE:
        for attempt in range(3):     # 21-Nov: one transient Service error on this query marked a whole page ERROR - retry first
            r = svc_query(dax, all_rows=True)
            if not r.get("error"):
                break
            time.sleep(5 * (attempt + 1))
        if r.get("error"):
            return None
        q = r.get("all") or []
        key = next((k for k in (q[0] if q else {}) if k != "[@n]"), None)
        return [x[key] for x in q] if key else []
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(PID),
                        "-Dax", dax, "-TimeoutSec", "120"], capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(p.stdout.strip())
    except json.JSONDecodeError:
        return None
    if isinstance(d, dict):
        return None
    key = next((k for k in (d[0] if d else {}) if k != "[@n]"), None)
    return [r[key] for r in d] if key else []


def settings(p, s):
    """(label, extra filters) the page is replayed with for one site."""
    if not FILTER_N:
        return [(dd.isoformat() if dd else "default", day_filters(p, dd)) for dd in DAYS_LIST if dd is None or p["date_slicers"]]
    out = []
    for t, c in p["slicers"]:
        vals = slicer_values(t, c, s["SiteCode"], FILTER_N)
        if vals is None:
            out.append((f"{c}=<values query failed>", None))
            continue
        if not vals:
            out.append((f"{c}=<no values at site>", []))
        for v in vals:
            out.append((f"{c}={str(v)[:40]}", [f"TREATAS({{{dax_value(v)}}}, {cref(t, c)})"]))
    return out


queries, index = [], {}
for p in pages:
    for s in SITES:
        sets = settings(p, s)
        if FILTER_N:
            print(time.strftime("[%H:%M:%S] ") + f"filter values {p['name']} / {s['SiteCode']}: {len(sets)} setting(s)", flush=True)
        for label, extra in sets:
            for v in p["visuals"]:
                if extra is None:
                    index[f"x{len(index)}"] = (p, v, s, label)
                    continue
                f = [f'TREATAS({{"{s["SiteCode"]}"}}, Cfg_Site[SiteCode])'] + extra + p["filters"] + v["filters"]
                mnb = [x.split(":", 1)[1] for x in f if x.startswith("MEASURE_NOT_BLANK:")]
                f = [x for x in f if not x.startswith("MEASURE_NOT_BLANK:")]
                if v["cols"]:
                    ms = ", ".join(f'"m{i}", {m}' for i, (_, m) in enumerate(v["meas"]))
                    mf = ", ".join(f'"mf{i}", {m.split(chr(31), 1)[0]}' for i, m in enumerate(mnb))
                    body = f"SUMMARIZECOLUMNS({', '.join(c for _, c in v['cols'])}, {', '.join(f)}{', ' + ms if ms else ''}{', ' + mf if mf else ''})"
                    if mnb:
                        body = f"FILTER({body}, " + " && ".join(
                            f"[mf{i}] {m.split(chr(31), 1)[1]}" if chr(31) in m else f"NOT ISBLANK([mf{i}])" for i, m in enumerate(mnb)) + ")"
                    dax = f"EVALUATE TOPN(25, {body})"   # 25 rows: the hash must see beyond constant first rows (N/A lines, idle hours)
                else:
                    ms = ", ".join(f'"m{i}", CALCULATE({m}, {", ".join(f)})' for i, (_, m) in enumerate(v["meas"]))
                    dax = f"EVALUATE ROW({ms})"
                qid = f"{len(queries)}"
                queries.append({"id": qid, "dax": dax})
                index[qid] = (p, v, s, label)
print(f"{len(pages)} pages, {sum(len(p['visuals']) for p in pages)} data visuals, {len(SITES)} sites, "
      f"{'filter values' if FILTER_N else str(len(DAYS_LIST)) + ' day settings'} -> {len(queries)} queries", flush=True)
res = run_batch(queries, "filters" if FILTER_N else "replay")


def is_empty_value(x):
    return x is None or (isinstance(x, str) and x.strip() in ("", "-", "(Blank)"))


NO_ACT = {r["No_Activity_Text"].strip() for r in csv.DictReader(open(ROOT / "config" / "kpi_thresholds.csv", encoding="utf-8-sig"))
          if r.get("No_Activity_Text")}


def is_no_activity(x):
    return isinstance(x, str) and x.strip() in NO_ACT


rows = []
for qid, (p, v, s, d) in index.items():
    r = res.get(qid, {})
    need = (REQ.get(p["name"]) or "").strip()
    na = bool(need) and str(s.get(need, "1")) != "1"
    if qid.startswith("x"):
        st = "ERROR"
    elif r.get("error"):
        st = "ERROR"
    elif not r.get("rows"):
        st = "EMPTY"
    else:
        first = r.get("first") or {}
        vals = [val for k, val in first.items() if re.search(r"\[m\d+\]$", k)]
        if not v["cols"] and vals and all(is_empty_value(x) for x in vals):
            st = "EMPTY"
        elif not v["cols"] and vals and is_no_activity(vals[0]):
            st = "NO ACTIVITY"       # configured message (Cfg_Threshold.No_Activity_Text): no events that day - shown as text, not blank
        elif not v["cols"] and vals and is_empty_value(vals[0]):
            st = "NO VALUE"          # KPI card: main value "-" / blank while labels around it are filled
        else:
            st = "OK"
    if na and st != "OK":
        st = "NA"
    first = r.get("first") or {}
    rows.append({"Page": p["name"], "Visual": v["title"], "VisualId": v["id"], "Type": v["type"], "Site": s["SiteCode"], "Day": d,
                 "Fields": "|".join(x[1] for x in v["meas"] + v["cols"]), "Hash": r.get("hash"),
                 "Status": st, "Rows": r.get("rows"), "Sample": json.dumps(first, ensure_ascii=False, default=str)[:200],
                 "Error": (r.get("error") or "")[:200], "Skipped filters": ";".join(v["skipped"] + p["skipped"]), "Ms": r.get("ms")})
out = OUT_DIR / ("visual_filters.csv" if FILTER_N else "visual_replay.csv")
if not rows:
    sys.exit(f"ERROR: no visuals replayed - check --report (folder not found or no pages): {REPORT}")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
from collections import Counter, defaultdict
print("status:", dict(Counter(r["Status"] for r in rows)))
g = defaultdict(list)
for r in rows:
    if r["Status"] in ("EMPTY", "ERROR", "NO VALUE"):
        g[(r["Page"], r["Visual"], r["Status"])].append(f"{r['Site']}@{r['Day']}")
for (pg, vi, st), lst in sorted(g.items()):
    print(f"  {st:5s} {pg} :: {vi} -> {len(lst)}: {', '.join(lst[:8])}{' ...' if len(lst) > 8 else ''}")
print("->", out)


