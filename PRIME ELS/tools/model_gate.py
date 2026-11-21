"""Model + report best-practice gate (BPA-style), run by build_pbip.py on every built PBIP. Rules from Microsoft
skills-for-fabric (semantic-model-authoring/modeling-guidelines) and Tabular Editor BPA / data-goblin review-report:

CRITICAL (build fails)
  C1  report field binding points to a table / column / measure that does not exist in the model ("broken visual")
  C2  relationship columns with different data types (a text '06' never matches the number 6)      [build_pbip]
  C3  measure that applies its own report-day window ([Report Date]) to a table related to the date table but keeps
      the date-table filter: the slicer's day then ALSO filters that table through the relationship (e.g. TTAT by Close
      Date) and silently drops rows (30-Oct: trucks checked in / closed on another calendar day vanished from TTAT KPIs)
  C4  visual type that is neither a core visual nor a registered custom visual (31-Oct: 'stackedColumnChart' rendered as
      "To see this custom visual, add it to this report first" - stacked column = columnChart, stacked bar = barChart)
  C5  two fields of one visual with the same label (nativeQueryRef) - 31-Oct: KPI strips with several "prev day" fields
      showed "Error fetching data for this visual"
RECOMMENDED (listed in docs/MODEL_CHECK.md)
  R1  visible measure without formatString
  R2  inactive relationship not activated by USERELATIONSHIP in any measure
  R3  bi-directional relationship
  R4  '/' division in a measure (use DIVIDE)
  R5  chart without an explicit sort
  R6  table with no date table marked (dataCategory Time)
"""
import json
import re
from pathlib import Path

TREF = r"('(?:[^']|'')+'|[A-Za-z_][\w]*)"
# core Power BI visual types (PBIR visualType) - anything else must be a custom visual registered in report.json
CORE_VISUALS = {"actionButton", "areaChart", "barChart", "basicShape", "card", "cardVisual", "clusteredBarChart", "clusteredColumnChart",
                "columnChart", "decompositionTreeVisual", "donutChart", "filledMap", "funnel", "gauge", "hundredPercentStackedAreaChart",
                "hundredPercentStackedBarChart", "hundredPercentStackedColumnChart", "image", "keyDriversVisual", "kpi", "lineChart",
                "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "map", "multiRowCard", "pieChart", "pivotTable",
                "qnaVisual", "ribbonChart", "scatterChart", "shape", "slicer", "advancedSlicerVisual", "stackedAreaChart", "tableEx",
                "textbox", "treemap", "waterfallChart", "azureMap", "listSlicer", "textSlicer", "bookmarkNavigator", "pageNavigator"}
_CUSTOM = {}


def custom_visuals(report_def: Path):
    if report_def not in _CUSTOM:
        names = set()
        rj = report_def / "report.json"
        if rj.exists():
            j = json.loads(rj.read_text(encoding="utf-8"))
            names = set(j.get("publicCustomVisuals", [])) | {x.get("name") for x in j.get("organizationCustomVisuals", []) if isinstance(x, dict)}
        _CUSTOM[report_def] = names
    return _CUSTOM[report_def]


def _name(x):
    x = x.strip()
    return x[1:-1].replace("''", "'") if x.startswith("'") else x


def inventory(defn: Path):
    tables, measures, cols, fmt, hidden, exprs = {}, {}, {}, {}, set(), {}
    datecat = set()
    for f in (defn / "tables").glob("*.tmdl"):
        t = f.read_text(encoding="utf-8")
        m = re.search(r"(?m)^table (.+)$", t)
        if not m:
            continue
        tn = _name(m.group(1))
        tables[tn] = f
        if re.search(r"(?m)^\tdataCategory: Time", t):
            datecat.add(tn)
        for mm in re.finditer(r"(?m)^\tcolumn ('(?:[^']|'')+'|[^\s=]+)", t):
            cols.setdefault(tn, set()).add(_name(mm.group(1)))
        for mm in re.finditer(r"(?m)^\tmeasure ('(?:[^']|'')+'|[^\s=]+) =([^\n]*)\n((?:\t\t.*\n|\n(?=\t\t))*)", t):
            n = _name(mm.group(1))
            measures[n] = tn
            body = mm.group(2) + "\n" + mm.group(3)
            exprs[n] = body
            fmt[n] = bool(re.search(r"(?m)^\t\tformatString:", mm.group(3)))
            if re.search(r"(?m)^\t\tisHidden", mm.group(3)):
                hidden.add(n)
    return tables, cols, measures, fmt, hidden, exprs, datecat


def _fields(o, out):
    if isinstance(o, dict):
        for k in ("Column", "Measure"):
            if k in o and isinstance(o[k], dict) and "Property" in o[k]:
                src = o[k].get("Expression", {}).get("SourceRef", {})
                out.append((k, src.get("Entity"), src.get("Source"), o[k]["Property"]))
        for v in o.values():
            _fields(v, out)
    elif isinstance(o, list):
        for v in o:
            _fields(v, out)


def prune_broken_filters(defn: Path, report_def: Path):
    """Visual / page / report filters whose field is not in the model make the visual fail ('Something went wrong').
    They are removed at build and listed (a broken field that is SHOWN in a visual stays a critical error)."""
    tables, cols, measures, *_ = inventory(defn)

    def ok(f):
        found = []
        _fields(f.get("field", {}), found)
        for kind, ent, _, prop in found:
            if ent and (ent not in tables or (kind == "Column" and prop not in cols.get(ent, set())) or
                        (kind == "Measure" and prop not in measures)):
                return False
        return True

    removed = []
    for jf in report_def.rglob("*.json"):
        try:
            j = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        fc = j.get("filterConfig") if isinstance(j, dict) else None
        if not fc or not fc.get("filters"):
            continue
        keep = [f for f in fc["filters"] if ok(f)]
        if len(keep) != len(fc["filters"]):
            removed += [f"{jf.parent.name}: {json.dumps(f.get('field'))[:120]}" for f in fc["filters"] if f not in keep]
            fc["filters"] = keep
            jf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")
    return removed


def apply_default_formats(defn: Path, types_csv: Path):
    """Visible numeric measures without a formatString get a standard one. Return types come from the engine
    (config/measure_types.csv, refreshed by tools/sync_measure_types.py from INFO.MEASURES of the open model):
    text / boolean measures need no format; a measure missing from the snapshot stays an R1 finding."""
    if not types_csv.exists():
        return {}, []
    import csv
    types = {r["Measure"]: int(r["DataType"]) for r in csv.DictReader(open(types_csv, encoding="utf-8-sig"))}
    fixed = []
    for f in (defn / "tables").glob("*.tmdl"):
        t = f.read_text(encoding="utf-8")
        parts, last = [], 0
        for mm in re.finditer(r"(?m)^\tmeasure ('(?:[^']|'')+'|[^\s=]+) =([^\n]*)\n((?:\t\t.*\n|\n(?=\t\t))*)", t):
            n, body = _name(mm.group(1)), mm.group(3)
            if re.search(r"(?m)^\t\tformatString:", body) or types.get(n) not in (6, 8, 10):
                continue
            fs = "0.0%" if re.search(r"%|\bPct\b", n) else "#,0" if types[n] == 6 else "#,0.##"
            # properties go right after the expression, before lineageTag / annotations (child objects)
            prop = re.search(r"(?m)^\t\t[^\t\n]", body)
            at = mm.start(3) + (prop.start() if prop else len(body))
            parts += [t[last:at], f"\t\tformatString: {fs}\n"]
            last = at
            fixed.append(f"[{n}] -> {fs}")
        if parts:
            f.write_text("".join(parts) + t[last:], encoding="utf-8")
    return types, fixed


def run(defn: Path, report_def: Path, out_md: Path):
    pruned = prune_broken_filters(defn, report_def)
    types, formatted = apply_default_formats(defn, Path(__file__).resolve().parent.parent / "config" / "measure_types.csv")
    tables, cols, measures, fmt, hidden, exprs, datecat = inventory(defn)
    crit, rec = [], []
    # C1 broken bindings (visuals, page and report filters, bookmarks)
    for jf in list(report_def.rglob("*.json")):
        try:
            j = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        found = []
        _fields(j, found)
        aliases = {}
        for frm in re.findall(r'"Name":\s*"([^"]+)",\s*"Entity":\s*"([^"]+)"', jf.read_text(encoding="utf-8")):
            aliases[frm[0]] = frm[1]
        page = jf.parts[jf.parts.index("pages") + 1] if "pages" in jf.parts else jf.parent.name
        for kind, ent, alias, prop in found:
            ent = ent or aliases.get(alias)
            if not ent:
                continue
            if ent not in tables:
                crit.append(f"C1 {page}/{jf.parent.name}: table '{ent}' not in model (field {prop})")
            elif kind == "Column" and prop not in cols.get(ent, set()):
                crit.append(f"C1 {page}/{jf.parent.name}: column '{ent}'[{prop}] not in model")
            elif kind == "Measure" and prop not in measures:
                crit.append(f"C1 {page}/{jf.parent.name}: measure [{prop}] not in model")
        # R5 chart sort
        v = j.get("visual", {}) if isinstance(j, dict) else {}
        if v.get("visualType", "").endswith(("Chart", "chart")) and v.get("query", {}).get("queryState") and \
                not v.get("query", {}).get("sortDefinition"):
            rec.append(f"R5 {page}/{jf.parent.name}: {v['visualType']} without explicit sort")
        # C4 visual type must be a core visual or a custom visual registered in the report ("add it to this report first")
        vt = v.get("visualType")
        if vt and vt not in CORE_VISUALS and vt not in custom_visuals(report_def):
            crit.append(f"C4 {page}/{jf.parent.name}: visual type '{vt}' is neither a core visual nor registered in report.json")
        # C5 the labels (nativeQueryRef) of one visual's fields must be unique - duplicates break the visual's query
        refs = [p.get("nativeQueryRef") for role in v.get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])]
        dups = sorted({r for r in refs if r and refs.count(r) > 1})
        if dups:
            crit.append(f"C5 {page}/{jf.parent.name}: duplicate field label(s) {dups} - 'Error fetching data for this visual'")
    # R1 format strings (text / boolean measures - engine type from config/measure_types.csv - need none)
    for n, has in fmt.items():
        if not has and n not in hidden and types.get(n) not in (2, 11):
            rec.append(f"R1 measure [{n}] ({measures[n]}) has no formatString"
                       + ("" if n in types else " (not in config/measure_types.csv - run tools/sync_measure_types.py)"))
    # R2 / R3 relationships
    rel = (defn / "relationships.tmdl").read_text(encoding="utf-8")
    # C3 day-window measures on date-related tables must clear the date-table filter
    date_tables = {"DimDate", "DimDateBucket"}
    related = set()
    for blk in re.split(r"\n(?=relationship )", rel):
        fr, to = re.search(r"fromColumn: ([^\n]+)", blk), re.search(r"toColumn: ([^\n]+)", blk)
        if fr and to and "isActive: false" not in blk:
            ft, tt = (_name(re.match(TREF, x.group(1).strip()).group(1)) for x in (fr, to))
            if tt in date_tables and ft not in date_tables:
                related.add(ft)
    for n, body in exprs.items():
        if "[Report Date]" not in body or "REMOVEFILTERS(DimDate)" in body:
            continue
        hit = [t for t in related if re.search(("'" + re.escape(t.replace("'", "''")) + "'" if re.search(r"\W", t) else r"\b" + re.escape(t)) + r"\[", body)]
        if hit:
            crit.append(f"C3 measure [{n}] filters {', '.join(sorted(hit))} by its own report-day window but keeps the DimDate filter "
                        "(add REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket))")
    alltext = "\n".join(exprs.values())
    for blk in re.split(r"\n(?=relationship )", rel):
        fr = re.search(r"fromColumn: ([^\n]+)", blk)
        to = re.search(r"toColumn: ([^\n]+)", blk)
        if not fr:
            continue
        if "isActive: false" in blk:
            fc = re.match(TREF + r"\.(.+)$", fr.group(1).strip())
            col = _name(fc.group(2)) if fc else fr.group(1)
            if not re.search(r"USERELATIONSHIP\s*\([^)]*" + re.escape(col), alltext):
                rec.append(f"R2 inactive relationship {fr.group(1).strip()} -> {to.group(1).strip()} not used by USERELATIONSHIP")
        if "bothDirections" in blk:
            rec.append(f"R3 bi-directional relationship {fr.group(1).strip()} -> {to.group(1).strip()}")
    # R4 division
    for n, body in exprs.items():
        code = re.sub(r'"[^"]*"', '""', re.sub(r"(--|//)[^\n]*", "", body))
        code = re.sub(r"'[^']*'|\[[^\]]*\]", "X", code)
        if re.search(r"[\w\)\]]\s*/\s*(?!\d+(\.\d+)?\b)[\w\(\[]", code):
            rec.append(f"R4 measure [{n}] uses '/' (DIVIDE is safe against 0 / blank)")
    if not datecat:
        rec.append("R6 no table is marked as date table (dataCategory: Time)")
    # C7 RETURN without any VAR before it: the engine stores the measure as SYNTAXERROR and every measure using it fails (20-Nov
    # [Prod Plan Remark] -> the banner [Report Label] on every page)
    for n, body in exprs.items():
        code = re.sub(r'"[^"]*"', '""', re.sub(r"(--|//)[^\n]*", "", body))
        if re.search(r"(?i)\bRETURN\b", code) and not re.search(r"(?i)\bVAR\b", code):
            crit.append(f"C7 measure [{n}]: RETURN without VAR - syntax error in the engine")
    # C6 VAR names the engine refuses (TOP, WORK, ON, KEY, VALUE ...): measured by tools/sync_dax_reserved.py, not typed by hand
    rw = Path(__file__).resolve().parent.parent / "config" / "dax_reserved_words.txt"
    reserved = {w.strip().lower() for w in rw.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")} if rw.exists() else set()
    for tf in defn.rglob("*.tmdl"):
        txt = tf.read_text(encoding="utf-8")
        for m in re.finditer(r"(?i)\bVAR\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", txt):
            if m.group(1).lower() in reserved:
                owner = re.findall(r"(?m)^\s*(?:measure|column|table)\s+('(?:[^']|'')+'|[^\s=]+)", txt[:m.start()])
                crit.append(f"C6 {tf.stem} {owner[-1] if owner else ''}: VAR name '{m.group(1)}' is a reserved DAX word - syntax error in the engine")
    # C8 Copilot readiness (Microsoft 'Prep data for AI'): every measure and visible column carries a description (tools/ai_descriptions.py)
    import ai_descriptions
    cov = ai_descriptions.coverage(defn.parent)
    for k, (have, tot) in cov.items():
        if have < tot:
            crit.append(f"C8 {tot - have} of {tot} {k}s without a description - Copilot cannot explain them (tools/ai_descriptions.py)")
    md = ["# Model / report best-practice check", "",
          "Run by `py tools/build_pbip.py` on every build (rules: Microsoft skills-for-fabric modeling guidelines, Tabular Editor BPA).", "",
          f"**CRITICAL: {len(crit)}** (build fails)  |  RECOMMENDED: {len(rec)}  |  broken filters removed at build: {len(pruned)}", ""]
    if pruned:
        md += ["## Broken filters removed (field not in the model)", ""] + [f"- {x}" for x in pruned] + [""]
    if formatted:
        md += [f"## Standard format applied to {len(formatted)} numeric measure(s) without one", ""] + [f"- {x}" for x in formatted] + [""]
    if crit:
        md += ["## Critical", ""] + [f"- {x}" for x in crit] + [""]
    if rec:
        from collections import Counter
        md += ["## Recommended", "", "| Rule | Count |", "|---|---|"] + \
              [f"| {k} | {v} |" for k, v in sorted(Counter(x[:2] for x in rec).items())] + ["", "<details><summary>details</summary>", ""] + \
              [f"- {x}" for x in rec] + ["", "</details>", ""]
    out_md.write_text("\n".join(md), encoding="utf-8")
    return crit, rec
