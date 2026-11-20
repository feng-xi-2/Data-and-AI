"""Build the WH Hypercare KPI Power BI projects (PBIP: TMDL semantic model + PBIR report).

    py tools/build_pbip.py                  # dist/ALL_SITES + one single-site file per site
    py tools/build_pbip.py XIQING ATHENS    # only those single-site files
    py tools/build_pbip.py --all-only       # only dist/ALL_SITES
    py tools/build_pbip.py BINHDUONG --service   # dist/_service/<SITE>: Power BI Service variant with incremental refresh policies

Inputs : _src_oct/tmdl_original (exported from BD Throughput.pbix via Power BI MCP), _src_oct/pbix/Report (PBIR),
         config/*.csv, sql/new/*.sql, tools/measures_*.py, tools/report_pages.py
Output : dist/ALL_SITES/WH Hypercare KPI.pbip             every site loaded, Site slicer on every page (needs access to every replica)
         dist/<SITE>/WH Hypercare KPI - <SITE>.pbip      one site loaded (share it: needs only that site's replica / gateway)
                                                         incremental tables: '<T> - <SITE>' history + '<T> - <SITE> - recent'
         dist/_service/<SITE>/...                         same, refreshPolicy (RangeStart / RangeEnd) instead of the 2 partitions
         sql/extracted/*.sql (tokenised SQL of the original queries, for review / sharing)
"""
import json
import os
import subprocess
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pbi_common import (ROOT, read_csv, q, m_str, enter_data_source, tmdl_m_table, tmdl_measure,  # noqa: E402
                        parse_tmdl_columns, empty_table_m, tag, tmdl_source_block, tmdl_column, report_sites, excluded_sites, SAP_TABLES, SAP_PAGES)
PRUNED = set()   # measures / calculated columns removed because they read a left-out (SAP) table - no visual may use them
from m_tokenizer import tokenize_m, BD_LEFTOVERS, scope_warehouse, apply_incremental, incremental_policy, INC_DEFAULTS, expand_config_blocks  # noqa: E402
import measures_core, measures_flow, measures_ops, measures_scorecard, measures_diag  # noqa: E402,E401
import report_pages  # noqa: E402
import copilot_ai  # noqa: E402
from dax_patch import patch_dax  # noqa: E402
from measures_core import INPUT_LEVELS, input_table  # noqa: E402

SRC = ROOT / "_src_oct" / "tmdl_original"     # BD Throughput as of October (exported via Power BI MCP)
SRC_REPORT = ROOT / "_src_oct" / "pbix" / "Report"
PRODUCT = "WH Hypercare KPI"
CDL_HOST = "<databricks-host>"       # fallback only - per-site value lives in Cfg_Site.Databricks_Host
CDL_HTTP_PATH = "/sql/1.0/warehouses/<warehouse-id>"

FEATURE_GATE = {
    "Level A Available Pallet Spot": "Has_LevelA", "Level A Occupied Pallet": "Has_LevelA",
    "Outbound Pallet from Inv": "Has_LevelA", "Pallet cleaned up from bin A": "Has_LevelA",
    "Pallet From LTA To Level A": "Has_LevelA", "Pallet in Level A not active shipment": "Has_LevelA",
    "Pallet From HOFFIN": "Has_HOFF",
    "Produced Pallet": "Has_Production", "Pallet from LTA to short%2Ftall location": "Has_Production",
    "WorkLine Activities": "Has_Production", "Planned Pallet PO": "Has_Production",
    "SAP Plan PO": "Has_SAP_Plan", "Shipping Market": "Has_SAP_Plan",
    "RPM Masterdata": "Has_RPM_Master", "Planned PO RPM Breakdown": "Has_Production", "Short PO": "Has_Production",
    "SAP Production": "Has_SAP_Prod",
}

BUILD_GATE = {"RPM Masterdata": "Has_RPM_Master", "SAP Plan PO": "Has_SAP_Plan", "Shipping Market": "Has_SAP_Plan", "SAP Production": "Has_SAP_Prod"}

# config/build_options.csv: what a built file may depend on besides the data replica
OPTS = {r["Setting"]: r["Value"].strip() for r in read_csv("build_options.csv")} if (ROOT / "config" / "build_options.csv").exists() else {}
INCLUDE_SAP = OPTS.get("Include_SAP_CDL", "0") == "1"
EMBED_INPUTS = OPTS.get("Embed_Inputs", "1") == "1"
SAP_FLAGS = ("Has_SAP_Plan", "Has_SAP_Prod")


def apply_build_options(rows):
    """Include_SAP_CDL = 0 -> every site built as if its SAP flags were 0 (Cfg_Site, build gates and page gates stay consistent)."""
    return rows if INCLUDE_SAP else [dict(r, **{f: "0" for f in SAP_FLAGS}) for r in rows]

# ------------------------------------------------------------------ config tables (stored IN the model)
SITE_NUM = {"UTC_Offset_h": "type number", "Shift1_Start": "Int64.Type", "Shift2_Start": "Int64.Type", "Shift3_Start": "Int64.Type",
            "Is_Default": "Int64.Type", "ACT_DAYS": "Int64.Type", "CAL_FUTURE_DAYS": "Int64.Type",
            "Has_Production": "Int64.Type", "Has_LevelA": "Int64.Type", "Has_HOFF": "Int64.Type", "Has_SAP_Plan": "Int64.Type", "Has_SAP_Prod": "Int64.Type",
            "ShiftDay_Start_Min": "Int64.Type", "Has_RPM_Master": "Int64.Type", "WO_WINDOW_DAYS": "Int64.Type", "MOVEMENT_DAYS": "Int64.Type", "DETAIL_DAYS": "Int64.Type"}
THR_NUM = {"Pillar_No": "Int64.Type", "Target": "type number", "Warn_Pct": "type number", "Crit_Pct": "type number",
           "Warn_Abs": "type number", "Crit_Abs": "type number"}
TDMAP = {"type number": "double", "Int64.Type": "int64", "type text": "string", "type logical": "boolean"}


def typed(cols, nums):
    pairs = ", ".join(f'{{"{c}", {nums.get(c, "type text")}}}' for c in cols)
    return f"Table.TransformColumnTypes(Source, {{{pairs}}})"


def _sort_by(tmdl, col, by):
    """sortByColumn on a config-table column (the build asserts the 1:1 mapping)."""
    out, k = re.subn(r"(\tcolumn " + re.escape(col) + r"\n(?:\t\t[^\n]*\n)*?\t\tsourceColumn: " + re.escape(col) + r"\n)",
                     lambda m: m.group(1) + f"\t\tsortByColumn: {by}\n", tmdl, count=1)
    assert k == 1, f"sort column {col} not found"
    return out


STAGE_NUM = {"Flow_No": "Int64.Type", "Stage_No": "Int64.Type", "Warn_Min": "type number", "Crit_Min": "type number", "Applicable": "Int64.Type"}


def stage_rows():
    """config/process_stages.csv x sites: Site = <SiteCode> rows override the '*' default of the same Stage_Key; Flow_No 0 = feed-only rules.
    Applicable = 0 when the Requires flag is 0 or the Requires token is ~NA~ for the site (resolved at build from config/site_config.csv)."""
    base = read_csv("process_stages.csv")
    out, sort_map = [], {}
    for s in SITES:
        code, by_key = s["SiteCode"], {}
        for r in base:
            if r["Site"] in ("*", code) and int(r["Flow_No"] or 0) > 0 and (r["Site"] == code or r["Stage_Key"] not in by_key):
                by_key[r["Stage_Key"]] = r
        for k, r in by_key.items():
            req, ok, why = r["Requires"].strip(), True, ""
            if req:
                v = str(s.get(req, "")).strip()
                ok = v == "1" if req.startswith("Has_") else v not in ("", "~NA~")
                why = f"not used at this site ({req} = {v or 'blank'} in config/site_config.csv)"
            for a, b in (("Stage", "Stage_No"), ("Flow", "Flow_No")):
                if sort_map.setdefault((a, r[a]), r[b]) != r[b]:
                    raise SystemExit(f"process_stages.csv: {a} '{r[a]}' has two {b} values - a site override may change limits / texts only")
            out.append({"SiteCode": code, "Stage_Key": k, "Stage_Site_Key": f"{code}|{k}", "Flow_No": r["Flow_No"], "Flow": r["Flow"],
                        "Stage_No": r["Stage_No"], "Stage": r["Stage"], "Object": r["Object"], "Unit": r["Unit"],
                        "Warn_Min": r["Warn_Min"], "Crit_Min": r["Crit_Min"], "Applicable": "1" if ok else "0", "NA_Reason": "" if ok else why,
                        "Meaning": r["Meaning"], "Action": r["Action"], "Owner": r["Owner"]})
    return out

def config_table(name, csv_name, nums, extra_steps="", extra_cols=(), desc="", rows=None):
    rows = read_csv(csv_name) if rows is None else rows
    cols = list((rows[0] if rows else read_csv(csv_name)[0]).keys())
    m = f"let\n    Source = {enter_data_source(rows, cols)},\n    Typed = {typed(cols, nums)}{extra_steps}\nin\n    Result"
    if not extra_steps:
        m = m.replace("\nin\n    Result", ",\n    Result = Typed\nin\n    Result")
    tcols = [(c, TDMAP[nums.get(c, "type text")]) for c in cols] + list(extra_cols)
    return tmdl_m_table(name, tcols, m, description=desc)


def m_lit(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    return m_str(str(v))


def embedded_targets(path):
    """Embed_Inputs = 1: the AlertTargets rows copied into the M at build (same checks downstream, no file read at refresh).
    A missing / unreadable workbook embeds no rows -> every KPI keeps the built-in BD thresholds (Cfg_ThresholdBase)."""
    import openpyxl
    import inputs_file
    cols = ["Site", "KPI_Key", "Target", "Warning_At", "Critical_At", "Changed_By", "Reason"]
    p = Path(path)
    try:
        rows = inputs_file._table_rows(openpyxl.load_workbook(p, data_only=True), "AlertTargets")
        where = f"embedded at build {datetime.now():%Y-%m-%d %H:%M} from {p.name} (change a target = edit the workbook + rebuild)"
    except (Exception, SystemExit) as e:
        print(f"   !! inputs workbook not embedded ({p}): {e} - built-in BD thresholds only", flush=True)
        rows, where = [], f"inputs workbook not found at build ({p.name}) - built-in BD thresholds only"
    body = ", ".join("{" + ", ".join(m_lit(r.get(c)) for c in cols) + "}" for r in rows)
    return (f'''Where = {m_str(where)},
    Book = "embedded",
    Tbl = #table({{{", ".join(m_str(c) for c in cols)}}}, {{{body}}}),''')


def target_input_table():
    """Cfg_TargetInput: the 'Alert targets' table of the ONE inputs file, read at EVERY refresh (no rebuild for a target change).
    Desktop / site files read the OneDrive-synced copy (no extra sign-in); --service builds read SharePoint (OAuth2 once). Every problem
    (file missing, table renamed, unknown KPI / site, text in a number, warning beyond critical) becomes a row with an Issue - the refresh
    never fails because of the inputs file. Known KPI keys / directions / site codes are literals of this build (no query references:
    combining the file with other queries would trip the Power Query privacy firewall)."""
    import inputs_file
    src = inputs_file.source()
    path = os.path.expandvars(src["Local_Path"])
    th = {r["KPI_Key"]: r["Direction"] for r in read_csv("kpi_thresholds.csv") if r["Site"] == "*"}
    codes = [s["SiteCode"] for s in SITES]
    getter = (f'Web.Contents({m_str(src["SharePoint_Url"])})' if SERVICE else f'File.Contents({m_str(path)})')
    dirs = "[" + ", ".join(f'{k} = {m_str(v)}' for k, v in th.items()) + "]"
    read_book = (f'''Where = {m_str(src["SharePoint_Url"] if SERVICE else path)},
    Book = try Excel.Workbook({getter}, true, true) otherwise null,
    Tbl = if Book = null then null else try Book{{[Item = "AlertTargets", Kind = "Table"]}}[Data] otherwise null,''')
    if EMBED_INPUTS:
        read_book = embedded_targets(path)
    m = f'''let
    {read_book}
    Shape = type table [Row = Int64.Type, Site = text, KPI_Key = text, Target = nullable number, Warning_At = nullable number, Critical_At = nullable number,
        Changed_By = text, Reason = text, Issue = text],
    Problem = (msg) => #table(Shape, {{{{0, "*", "*", null, null, null, "", "", msg}}}}),
    Dirs = {dirs},
    Sites = {{{", ".join(m_str(c) for c in codes)}}},
    Num = (v) => if v = null or Text.Trim(Text.From(v)) = "" then null else try Number.From(v, "en-US") otherwise "BAD",
    Rows = if Book = null then Problem("inputs file not found / not readable: " & Where)
        else if Tbl = null then Problem("Excel table 'AlertTargets' not found in the inputs file (tab renamed or table deleted)")
        else let
            Cols = Table.SelectColumns(Tbl, {{"Site", "KPI_Key", "Target", "Warning_At", "Critical_At", "Changed_By", "Reason"}}, MissingField.UseNull),
            Indexed = Table.AddIndexColumn(Cols, "Row", 2, 1, Int64.Type),
            Recs = List.Transform(Table.ToRecords(Indexed), (r) =>
                let
                    s0 = Text.Upper(Text.Trim(Text.From(if r[Site] = null then "" else r[Site]))),
                    site = if s0 = "" or s0 = "ALL SITES" or s0 = "*" then "All sites" else s0,
                    key = Text.Upper(Text.Trim(Text.From(if r[KPI_Key] = null then "" else r[KPI_Key]))),
                    t = Num(r[Target]), w = Num(r[Warning_At]), c = Num(r[Critical_At]),
                    dir = Record.FieldOrDefault(Dirs, key, null),
                    bad = List.Contains({{t, w, c}}, "BAD"),
                    issue = if key = "" then "skip"
                        else if dir = null then "unknown KPI_Key '" & key & "'"
                        else if site <> "All sites" and not List.Contains(Sites, site) then "site '" & site & "' is not in this report"
                        else if bad then "Target / Warning_At / Critical_At must be numbers"
                        else if w <> null and c <> null and ((dir = "Higher" and w < c) or (dir <> "Higher" and w > c)) then
                            "Warning_At beyond Critical_At for a '" & dir & "' KPI"
                        else ""
                in
                    [Row = r[Row], Site = site, KPI_Key = key, Target = if bad then null else t, Warning_At = if bad then null else w,
                     Critical_At = if bad then null else c, Changed_By = Text.From(if r[Changed_By] = null then "" else r[Changed_By]),
                     Reason = Text.From(if r[Reason] = null then "" else r[Reason]), Issue = issue]),
            Kept = List.Select(Recs, each [Issue] <> "skip")
        in
            Table.FromRecords(Kept, Shape),
    Out = Table.TransformColumnTypes(Rows, {{{{"Row", Int64.Type}}, {{"Target", type number}}, {{"Warning_At", type number}}, {{"Critical_At", type number}}}})
in
    Out'''
    cols = [("Row", "int64"), ("Site", "string"), ("KPI_Key", "string"), ("Target", "double"), ("Warning_At", "double"), ("Critical_At", "double"),
            ("Changed_By", "string"), ("Reason", "string"), ("Issue", "string")]
    return tmdl_m_table("Cfg_TargetInput", cols, m, hidden=True,
                        description=("ALERT TARGETS copied from the inputs workbook at build (config/build_options.csv Embed_Inputs = 1) - no file read at refresh"
                                     if EMBED_INPUTS else "ALERT TARGETS from the inputs file (config/inputs_source.csv) - read at every refresh")
                        + "; Issue <> '' = row ignored.")


def threshold_calc_table():
    """Cfg_Threshold = built-in targets (Cfg_ThresholdBase) overridden by the inputs file, recalculated after every refresh:
    site row of the file > site row of the config > 'All sites' row of the file > built-in default. A new file Target without
    Warning / Critical re-derives them from the KPI's percentage rule. Source says where each value comes from."""
    base_cols = list(read_csv("kpi_thresholds.csv")[0].keys())
    tb = "Cfg_ThresholdBase"

    def pick(col):
        return (f'VAR s_ = {tb}[SiteCode] VAR k_ = {tb}[KPI_Key]\n'
                f'        VAR vSite = MAXX(FILTER(inp, [Site] = s_ && [KPI_Key] = k_), [{col}])\n'
                f'        VAR vAll = MAXX(FILTER(inp, [Site] = "All sites" && [KPI_Key] = k_), [{col}])\n'
                f'        RETURN IF(NOT ISBLANK(vSite), vSite, IF({tb}[Site] <> "*", BLANK(), vAll))')
    sel = [f'"{c}", {tb}[{c}]' for c in base_cols if c != "Target"] + [f'"SiteCode", {tb}[SiteCode]']
    dax = (f'VAR inp = FILTER(Cfg_TargetInput, Cfg_TargetInput[Issue] = "")\n'
           f'VAR b = ADDCOLUMNS({tb},\n    "@t", {pick("Target")},\n    "@w", {pick("Warning_At")},\n    "@c", {pick("Critical_At")},\n'
           f'    "@src", VAR s_ = {tb}[SiteCode] VAR k_ = {tb}[KPI_Key]\n'
           f'        RETURN IF(NOT ISEMPTY(FILTER(inp, [Site] = s_ && [KPI_Key] = k_)), "inputs file - " & s_,\n'
           f'            IF({tb}[Site] <> "*", "config - site row", IF(NOT ISEMPTY(FILTER(inp, [Site] = "All sites" && [KPI_Key] = k_)), '
           f'"inputs file - All sites", "built-in default"))))\n'
           'RETURN SELECTCOLUMNS(b,\n    ' + ",\n    ".join(sel) + ',\n'
           f'    "Target", COALESCE([@t], {tb}[Target]),\n'
           f'    "Warn_At", VAR t = COALESCE([@t], {tb}[Target]) VAR d = {tb}[Direction]\n'
           f'        RETURN IF(NOT ISBLANK([@w]), [@w], IF(NOT ISBLANK([@t]) && [@t] <> {tb}[Target] && ISBLANK({tb}[Warn_Abs]),\n'
           f'            SWITCH(d, "Higher", t * {tb}[Warn_Pct], "Lower", t * (1 + {tb}[Warn_Pct]), {tb}[Warn_At]), {tb}[Warn_At])),\n'
           f'    "Crit_At", VAR t = COALESCE([@t], {tb}[Target]) VAR d = {tb}[Direction]\n'
           f'        RETURN IF(NOT ISBLANK([@c]), [@c], IF(NOT ISBLANK([@t]) && [@t] <> {tb}[Target] && ISBLANK({tb}[Crit_Abs]),\n'
           f'            SWITCH(d, "Higher", t * {tb}[Crit_Pct], "Lower", t * (1 + {tb}[Crit_Pct]), {tb}[Crit_At]), {tb}[Crit_At])),\n'
           '    "Source", [@src])')
    num = {c: TDMAP[THR_NUM[c]] for c in THR_NUM}
    cols = [(c, num.get(c, "string")) for c in base_cols if c != "Target"] + [("SiteCode", "string"), ("Target", "double"), ("Warn_At", "double"), ("Crit_At", "double"),
                                                                               ("Source", "string")]
    s = ("/// KPI TARGETS IN USE - built-in targets (config/kpi_thresholds.csv, Site='*' = Binh Duong defaults) overridden by the inputs file\n"
         "/// (Hypercare_KPI_Inputs.xlsx, tab Alert targets) at every refresh. Page inputs (Config & Health) override at report time.\n"
         f"table Cfg_Threshold\n\tlineageTag: {tag('Cfg_Threshold')}\n\n")
    for c, dt_ in cols:
        s += (f"\tcolumn {q(c)}\n\t\tdataType: {dt_}\n\t\tlineageTag: {tag('Cfg_Threshold', 'col', c)}\n\t\tsummarizeBy: none\n"
              f"\t\tisNameInferred\n\t\tsourceColumn: [{c}]\n" + ("\t\tsortByColumn: Pillar_No\n" if c == "Pillar" else "") +
              "\n\t\tannotation SummarizationSetBy = User\n\n")
    s += "\tpartition Cfg_Threshold = calculated\n\t\tmode: import\n" + tmdl_source_block(dax) + "\n\tannotation PBI_Id = calculated\n"
    return s


def build_config_tables():
    t = {}
    t["Cfg_Site"] = config_table(
        "Cfg_Site", "site_config.csv", SITE_NUM, rows=SITES,
        desc="SITE REGISTRY - one row per site loaded in this file (all-sites file: the Site slicer picks one; site file: one row). "
             "Tokens feed every replica SQL via fnSiteSql. Server / database are baked into each site's partitions at build "
             "(config/site_config.csv + py tools/build_pbip.py).")
    t["Cfg_ThresholdBase"] = config_table(
        "Cfg_ThresholdBase", "kpi_thresholds.csv", THR_NUM,
        ',\n    Sites = List.Distinct(Table.Column(Cfg_Site, "SiteCode")),'
        '\n    PerSite = List.Transform(Sites, (s) =>'
        '\n        let'
        '\n            SiteRows = Table.SelectRows(Typed, each [Site] = s),'
        '\n            Defaults = Table.SelectRows(Typed, each [Site] = "*" and not List.Contains(SiteRows[KPI_Key], [KPI_Key]))'
        '\n        in'
        '\n            Table.AddColumn(Table.Combine({SiteRows, Defaults}), "SiteCode", each s, type text)),'
        '\n    Combined = Table.Combine(PerSite),'
        '\n    WithWarn = Table.AddColumn(Combined, "Warn_At", each if [Warn_Abs] <> null then [Warn_Abs] else if [Direction] = "Higher" then [Target] * [Warn_Pct] '
        'else if [Direction] = "Lower" then [Target] * (1 + [Warn_Pct]) else null, type nullable number),'
        '\n    Result = Table.AddColumn(WithWarn, "Crit_At", each if [Crit_Abs] <> null then [Crit_Abs] else if [Direction] = "Higher" then [Target] * [Crit_Pct] '
        'else if [Direction] = "Lower" then [Target] * (1 + [Crit_Pct]) else null, type nullable number)',
        extra_cols=[("SiteCode", "string"), ("Warn_At", "double"), ("Crit_At", "double")],
        desc="BUILT-IN KPI TARGETS (config/kpi_thresholds.csv) - one row per site x KPI; Site='*' rows are the defaults (= Binh Duong). "
             "Cfg_Threshold = these values overridden by the inputs file (Cfg_TargetInput) at every refresh.")
    t["Cfg_ThresholdBase"] = t["Cfg_ThresholdBase"].replace("table Cfg_ThresholdBase\n", "table Cfg_ThresholdBase\n\tisHidden\n", 1)
    t["Cfg_TargetInput"] = target_input_table()
    t["Cfg_InputIssues"] = tmdl_m_table(
        "Cfg_InputIssues", [("Row", "int64"), ("Site", "string"), ("KPI_Key", "string"), ("Issue", "string")],
        'let\n    Src = Cfg_TargetInput,\n    Bad = Table.SelectRows(Src, each [Issue] <> ""),\n'
        '    Out = if Table.IsEmpty(Bad) then #table(type table [Row = Int64.Type, Site = text, KPI_Key = text, Issue = text], '
        '{{0, "-", "-", "none - every row of the inputs file is used"}}) else Table.SelectColumns(Bad, {"Row", "Site", "KPI_Key", "Issue"})\nin\n    Out',
        description="Rows of the inputs file (Alert targets) that are ignored, with the reason - Config & Health.")
    t["Cfg_Threshold"] = threshold_calc_table()
    t["Cfg_Engine"] = config_table(
        "Cfg_Engine", "engine_profiles.csv", {},
        desc="WMS ENGINE PROFILES - token defaults per engine (PrIME 2022 = dbo + sto_zone; PrIME 2014 = prodwms + area zoning). A non-blank Cfg_Site column overrides.")
    t["Cfg_LineMap"] = config_table(
        "Cfg_LineMap", "line_map.csv", {}, rows=[r for r in read_csv("line_map.csv") if r["Site"] in {s["SiteCode"] for s in SITES}],
        desc="LTA takeaway source -> production line / category per site (replaces the hard-coded VALUES list).")
    t["Cfg_AlertRule"] = config_table("Cfg_AlertRule", "alert_rules.csv", {"Rule_No": "Int64.Type"},
                                      desc="Alert rules + RCA insight + recommended action (Excel ALERTS sheet).")
    t["Cfg_HealthCheck"] = config_table("Cfg_HealthCheck", "health_checks.csv", {"Check_No": "Int64.Type", "Expected": "type number"},
                                        desc="Daily data-health checks (Excel VALIDATION sheet, generic part).")
    t["Cfg_RCA"] = config_table("Cfg_RCA", "rca_rules.csv", {"Priority": "Int64.Type"},
                                desc="Root-cause, verdict and narrative TEXTS ({placeholders} are filled by the _KPI measures). Type = LINE_RCA / VERDICT / NARRATIVE.")
    t["Cfg_Market"] = config_table("Cfg_Market", "market_colors.csv", {},
                                   desc="Shipping market -> colour for the Predicted Plt/h matrix (*MULTI / *UNMAPPED are the fall-backs).")
    sap_pages = set() if INCLUDE_SAP else {r["Page"] for r in read_csv("page_guide.csv") if r["Page_Key"] in SAP_PAGES}
    t["Cfg_PageGuide"] = config_table("Cfg_PageGuide", "page_guide.csv", {},
                                      rows=[r for r in read_csv("page_guide.csv") if INCLUDE_SAP or r["Page_Key"] not in SAP_PAGES],
                                      desc="'How it is calculated' + 'How to configure' text shown at the bottom of every page; Requires = Cfg_Site flag the page needs.")
    t["Cfg_Stage"] = _sort_by(_sort_by(config_table(
        "Cfg_Stage", "process_stages.csv", STAGE_NUM, rows=stage_rows(),
        desc="PROCESS MODEL - one row per site x process stage (config/process_stages.csv, Site = <SiteCode> rows override '*'). "
             "Warn_Min / Crit_Min = age limits for an item waiting in the stage; Applicable = 0 when the site lacks the token / flag in Requires. "
             "Drives the Process Flow, Trucks, Pallet Flow and Orders pages (Flow Items relate here)."), "Stage", "Stage_No"), "Flow", "Flow_No")
    t["Cfg_TimeBand"] = _sort_by(config_table(
        "Cfg_TimeBand", "time_bands.csv", {"Band_No": "Int64.Type", "From_Min": "type number", "To_Min": "type number"},
        desc="Time bands (minutes) for the TTAT distribution and the time-in-stage heat maps (config/time_bands.csv)."), "Band", "Band_No")
    t["Cfg_MoveClass"] = _sort_by(config_table(
        "Cfg_MoveClass", "movement_classes.csv", {"Priority": "Int64.Type", "Counts_As_Move": "Int64.Type"},
        desc="Pallet movement classes = process steps of an RF transaction (config/movement_classes.csv): activity / operation codes and "
             "location rules -> class, chart colour, meaning. Counts_As_Move = 0 rows are status events excluded from pallets moved."),
        "Move_Class", "Priority")
    t["Cfg_FieldGuide"] = config_table(
        "Cfg_FieldGuide", "field_guide.csv", {"Order": "Int64.Type"}, rows=[r for r in read_csv("field_guide.csv") if r["Page"] not in sap_pages],
        desc="FIELD GUIDE - every page field: meaning, unit of measure, grouping, colour rule and source (config/field_guide.csv).")
    t["Cfg_CopilotQuestions"] = config_table(
        "Cfg_CopilotQuestions", "copilot_questions.csv", {"Order": "Int64.Type"},
        desc="COPILOT QUESTION TEMPLATES (config/copilot_questions.csv): template, example, what you get - the Ask Copilot page; "
             "the Steps column is the answer recipe in the Copilot AI instructions.")
    t["Cfg_StockAge"] = _sort_by(config_table(
        "Cfg_StockAge", "stock_age_bands.csv", {"From_Days": "type number", "To_Days": "type number", "Sort": "Int64.Type"},
        desc="Stock age bands (days since FIFO / receipt) of the Inventory page (config/stock_age_bands.csv; also generates the SQL band)."),
        "Band", "Sort")
    t["Cfg_Refresh"] = config_table(
        "Cfg_Refresh", "refresh_policy.csv", {"Every_Minutes": "Int64.Type"},
        desc="Refresh tiers (config/refresh_policy.csv) - the same file drives tools/auto_refresh.py; HOT Every_Minutes = the 'next refresh' on the banner.")
    # Scheduled_Refresh: 1 = the all-sites file: refreshed by the scheduled task and published to SharePoint as a .pbix WITH data
    # (Snapshot_Hour_* of config/desktop_refresh.csv, PC clock); shared single-site project files are refreshed by whoever opens them.
    # Publisher_UTC_Offset_Min: the publishing PC's clock vs UTC at build - the banner converts the snapshot hours to site time
    # (a downloaded copy cannot use its own NOW() for that: the reader's PC is in another time zone)
    dr = read_csv("desktop_refresh.csv")
    pub_off = int(round(datetime.now().astimezone().utcoffset().total_seconds() / 900)) * 15
    dr = dr + [{"Setting": "Scheduled_Refresh", "Value": "1" if len(SITES) > 1 else "0",
                "Why": "1 = all-sites file: refreshed by the scheduled task and published as a .pbix with data; 0 = site project file, refreshed with Home > Refresh"},
               {"Setting": "Publisher_UTC_Offset_Min", "Value": str(pub_off),
                "Why": "clock of the PC that publishes the .pbix vs UTC (minutes, at build) - converts Snapshot_Hour_* to site time on the banner"}]
    t["Cfg_DesktopRefresh"] = config_table(
        "Cfg_DesktopRefresh", "desktop_refresh.csv", {"Value": "Int64.Type"}, rows=dr,
        desc="Office hours without automatic Desktop refresh (config/desktop_refresh.csv, PC clock) - read by tools/auto_refresh.py and the banner 'next refresh'.")
    t["Cfg_KpiExplain"] = config_table(
        "Cfg_KpiExplain", "kpi_explain.csv", {},
        desc="Per KPI: how it is calculated, the numbers behind it ({DAX|format} template -> [KPI Numbers Text]), the prediction method and "
             "the diagnosis (config/kpi_explain.csv) - shown in the Alerts control tower and its detail panel.")
    sql_classes = set(re.findall(r"THEN '([^']+)'|ELSE '([^']+)' END AS Loc_Class", (ROOT / "sql" / "new" / "Inventory.sql").read_text(encoding="utf-8")))
    sql_classes = {a or b for a, b in sql_classes} - {"Finished goods", "Materials"}
    cfg_classes = {r["Location_Class"] for r in read_csv("stock_old_causes.csv")}
    if sql_classes != cfg_classes:
        raise SystemExit(f"config/stock_old_causes.csv Location_Class must match sql/new/Inventory.sql Loc_Class values: "
                         f"missing {sorted(sql_classes - cfg_classes)}, unknown {sorted(cfg_classes - sql_classes)}")
    t["Cfg_StockCause"] = config_table(
        "Cfg_StockCause", "stock_old_causes.csv", {},
        desc="Old stock: likely cause + action per location class of the Inventory feed (config/stock_old_causes.csv) - Inventory page.")
    t["Cfg_Shift"] = _sort_by(config_table(
        "Cfg_Shift", "shifts.csv", {"Shift_No": "Int64.Type"},
        desc="Shift rows of the TTAT-by-shift diagnostic (hours come from Cfg_Site Shift1/2/3_Start; 2-shift sites leave shift 3 empty)."),
        "Shift", "Shift_No")
    for r in read_csv("threshold_inputs.csv"):
        for lvl, _ in INPUT_LEVELS:
            name = input_table(r["KPI_Key"], lvl)
            unit = r["Input_Unit"]
            fmt = f'"{r["Input_Format"]} ""{unit}"""'
            t[name] = (f"/// Page input box: {r['Label']} - {lvl} ({unit}). Empty = Cfg_Threshold value.\ntable {q(name)}\n\tisHidden\n"
                       f"\tlineageTag: {tag(name)}\n\n\tcolumn Value\n\t\tdataType: double\n\t\tformatString: {fmt}\n"
                       f"\t\tlineageTag: {tag(name, 'col', 'Value')}\n\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [Value]\n\n"
                       f"\t\tannotation SummarizationSetBy = User\n\n"
                       f"\tpartition {q(name)} = calculated\n\t\tmode: import\n"
                       f"\t\tsource = GENERATESERIES({r['Input_Min']}, {r['Input_Max']}, {r['Input_Step']})\n\n")
    return t


# ------------------------------------------------------------------ new replica feed tables
NEW_TABLES = {
    "Location Utilisation": ([("Area", "string"), ("Level_Class", "string"), ("Height_Class", "string"), ("Locations", "int64", "#,##0"),
                              ("Occupied_Locations", "int64", "#,##0"), ("Capacity_Qvl", "double"), ("Used_Qvl", "double"), ("Free_Qvl", "double")],
                             '{"Locations", Int64.Type}, {"Occupied_Locations", Int64.Type}, {"Capacity_Qvl", type number}, {"Used_Qvl", type number}, {"Free_Qvl", type number}', None),
    "User Activity": ([("Activity_Date", "dateTime", "yyyy-mm-dd"), ("Activity_Hour", "int64"), ("Shift_Date", "dateTime", "yyyy-mm-dd"), ("User_Id", "string"),
                       ("Operation", "string"), ("Activity_Code", "string"), ("Move_Class", "string"), ("Transactions", "int64"), ("Pallets_Moved", "int64"),
                       ("Pallets_User_Hour", "int64")],
                      '{"Activity_Date", type date}, {"Activity_Hour", Int64.Type}, {"Shift_Date", type date}, {"Transactions", Int64.Type}, '
                      '{"Pallets_Moved", Int64.Type}, {"Pallets_User_Hour", Int64.Type}', None),
    "Data Health": ([("Source_Object", "string"), ("Last_Event_Local", "dateTime", "yyyy-mm-dd hh:nn"), ("Rows_Last_24h", "int64"),
                     ("Db_Utc_Now", "dateTime", "yyyy-mm-dd hh:nn"), ("First_Event_Local", "dateTime", "yyyy-mm-dd hh:nn")],
                    '{"Last_Event_Local", type datetime}, {"Rows_Last_24h", Int64.Type}, {"Db_Utc_Now", type datetime}, {"First_Event_Local", type datetime}', None),
    "Outbound TTA": ([("TrailerID", "string"), ("Load", "string"), ("Trailer Type", "string"), ("Dock ID", "string"),
                      ("Check-in", "dateTime"), ("Start Loading", "dateTime"), ("End Loading", "dateTime"),
                      ("Transport Equipment Close", "dateTime"), ("Dispatch", "dateTime"), ("Route To", "string"), ("Pallets", "int64"),
                      ("Load Time (Minutes)", "int64"), ("TTAT (Minutes)", "int64"), ("Close Date", "dateTime", "yyyy-mm-dd"),
                      ("Load Time (hh:mm)", "string"), ("TTAT (hh:mm)", "string")],
                     '{"Check-in", type datetime}, {"Start Loading", type datetime}, {"End Loading", type datetime}, {"Transport Equipment Close", type datetime}, '
                     '{"Dispatch", type datetime}, {"Pallets", Int64.Type}, {"Load Time (Minutes)", Int64.Type}, {"TTAT (Minutes)", Int64.Type}',
                     ',\n    AddDate = Table.AddColumn(Typed, "Close Date", each if [Transport Equipment Close] = null then null else DateTime.Date([Transport Equipment Close]), type date),'
                     '\n    HHMM = (m) => if m = null then null else Text.PadStart(Text.From(Number.IntegerDivide(m, 60)), 2, "0") & ":" & Text.PadStart(Text.From(Number.Mod(m, 60)), 2, "0"),'
                     '\n    AddLoad = Table.AddColumn(AddDate, "Load Time (hh:mm)", each HHMM([#"Load Time (Minutes)"]), type text),'
                     '\n    Result = Table.AddColumn(AddLoad, "TTAT (hh:mm)", each HHMM([#"TTAT (Minutes)"]), type text)'),
    "Truck Staging": ([("Direction", "string"), ("TrailerID", "string"), ("Dock", "string"), ("Staging Lane", "string"), ("Lane Area", "string"),
                       ("Pallets", "int64", "#,##0"), ("First Pallet", "dateTime", "yyyy-mm-dd hh:nn"), ("Last Pallet", "dateTime", "yyyy-mm-dd hh:nn"),
                       ("Check-in", "dateTime", "yyyy-mm-dd hh:nn"), ("Close", "dateTime", "yyyy-mm-dd hh:nn"), ("Dispatch", "dateTime", "yyyy-mm-dd hh:nn")],
                      '{"Pallets", Int64.Type}, {"First Pallet", type datetime}, {"Last Pallet", type datetime}, {"Check-in", type datetime}, '
                      '{"Close", type datetime}, {"Dispatch", type datetime}', None),
    # ---- process diagnosis snapshots (sql/new/*.sql + config/process_stages.csv, trailer_status.csv, shipment_status.csv)
    "Open Trailers": ([("TrailerID", "string"), ("Trailer Number", "string"), ("Carrier", "string"), ("Direction", "string"), ("Trailer Code", "string"),
                       ("Status Code", "string"), ("Status", "string"), ("Stage_Key", "string"), ("Door / Yard", "string"),
                       ("Check-in", "dateTime", "yyyy-mm-dd hh:nn"), ("Last Status Change", "dateTime", "yyyy-mm-dd hh:nn"),
                       ("Minutes On Site", "int64"), ("Minutes In Status", "int64"), ("Pallets On Trailer", "int64"), ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn")],
                      '{"Check-in", type datetime}, {"Last Status Change", type datetime}, {"Minutes On Site", Int64.Type}, {"Minutes In Status", Int64.Type}, '
                      '{"Pallets On Trailer", Int64.Type}, {"Snapshot", type datetime}', None),
    "Shipments": ([("Shipment", "string"), ("Status Code", "string"), ("Status", "string"), ("Stage_Key", "string"), ("Is_Open", "int64"),
                   ("Carrier", "string"), ("Dest Location", "string"), ("Created", "dateTime", "yyyy-mm-dd hh:nn"), ("Created Date", "dateTime", "yyyy-mm-dd"),
                   ("Allocated", "dateTime", "yyyy-mm-dd hh:nn"), ("Staged", "dateTime", "yyyy-mm-dd hh:nn"), ("Loaded", "dateTime", "yyyy-mm-dd hh:nn"),
                   ("Late Ship", "dateTime", "yyyy-mm-dd hh:nn"), ("Lines", "int64"), ("Status Since", "dateTime", "yyyy-mm-dd hh:nn"),
                   ("Minutes In Status", "int64"), ("Minutes Since Created", "int64"), ("Is_Late", "int64"), ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn")],
                  '{"Is_Open", Int64.Type}, {"Created", type datetime}, {"Created Date", type date}, {"Allocated", type datetime}, {"Staged", type datetime}, '
                  '{"Loaded", type datetime}, {"Late Ship", type datetime}, {"Lines", Int64.Type}, {"Status Since", type datetime}, {"Minutes In Status", Int64.Type}, '
                  '{"Minutes Since Created", Int64.Type}, {"Is_Late", Int64.Type}, {"Snapshot", type datetime}', None),
    "Pallets In Flow": ([("Stage_Key", "string"), ("Pallet", "string"), ("Location", "string"), ("Area", "string"), ("Item", "string"), ("Items", "int64"),
                         ("Units", "double"), ("Last Move", "dateTime", "yyyy-mm-dd hh:nn"), ("Minutes In Location", "int64"), ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn")],
                        '{"Items", Int64.Type}, {"Units", type number}, {"Last Move", type datetime}, {"Minutes In Location", Int64.Type}, {"Snapshot", type datetime}', None),
    # ---- process mining (event logs -> directly-follows graph) and the all-material inventory snapshot
    "Process Edges": ([("Flow", "string"), ("From_Step", "string"), ("To_Step", "string"), ("From_No", "int64"), ("To_No", "int64"),
                       ("Is_Open_Edge", "int64"), ("Edge_Kind", "string"), ("Transitions", "int64"), ("Cases", "int64"), ("Median_Min", "double"), ("P95_Min", "double"),
                       ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn")],
                      '{"From_No", Int64.Type}, {"To_No", Int64.Type}, {"Is_Open_Edge", Int64.Type}, {"Transitions", Int64.Type}, {"Cases", Int64.Type}, '
                      '{"Median_Min", type number}, {"P95_Min", type number}, {"Snapshot", type datetime}', None),
    "Inventory": ([("Area", "string"), ("Location Class", "string"), ("Status Code", "string"), ("Status", "string"), ("Material", "string"),
                   ("Age_Band", "string"), ("Pallets", "int64"), ("Qty_BUoM", "double"), ("Max_Age_Days", "int64"), ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn")],
                  '{"Pallets", Int64.Type}, {"Qty_BUoM", type number}, {"Max_Age_Days", Int64.Type}, {"Snapshot", type datetime}', None),
}

# CDL (Databricks SAP silver) feeds: sql/cdl/<name>.sql, one partition per site with the site's Databricks host / path
NEW_CDL_TABLES = {
    "SAP Production": ([("Plant", "string"), ("Posting_Date", "dateTime", "yyyy-mm-dd"), ("MatNr", "string"), ("MatDesc", "string"), ("BUoM", "string"),
                        ("GR_Lines", "int64"), ("Qty_BUoM", "double"), ("Pallets", "double"), ("Pallet_Basis", "string")],
                       '{"Posting_Date", type date}, {"GR_Lines", Int64.Type}, {"Qty_BUoM", type number}, {"Pallets", type number}', None),
}
CDL_CATALOG = "cdl_oss_prod.silver_sap_a6p"


SITES = apply_build_options(report_sites())


def set_sites(codes=None):
    """Sites built into the next model: the all-sites report = site_config.csv minus build_options AllSites_Exclude, or a subset
    of ALL configured sites (a single-site file makes its site the default; an excluded site can still have its own file)."""
    global SITES
    rows = apply_build_options(read_csv("site_config.csv"))
    if SERVICE and (ROOT / "config" / "service_overrides.csv").exists():
        # the Service (workspace) model of a site may read another warehouse than the shared Desktop file, e.g. Jakarta ID12 (production,
        # not live yet) in the workspace while the shared .pbix keeps ID01 (DC, live) - config/service_overrides.csv
        ov = read_csv("service_overrides.csv")
        bad = [o["Setting"] for o in ov if rows and o["Setting"] not in rows[0]]
        if bad:
            raise SystemExit(f"config/service_overrides.csv: unknown site_config columns {bad}")
        rows = [dict(r, **{o["Setting"]: o["Value"] for o in ov if o["SiteCode"] == r["SiteCode"]}) for r in rows]
        for o in ov:
            print(f"   service override {o['SiteCode']}.{o['Setting']} = {o['Value']} ({o['Why']})")
    if codes:
        unknown = set(codes) - {r["SiteCode"] for r in rows}
        if unknown:
            raise SystemExit(f"Unknown SiteCode(s) {sorted(unknown)} - add them to config/site_config.csv")
        rows = [r for r in rows if r["SiteCode"] in codes]
        if len(rows) == 1:
            rows = [dict(rows[0], Is_Default="1")]
    else:
        ex = excluded_sites()
        rows = [r for r in rows if r["SiteCode"].upper() not in ex]
        if ex:
            print(f"   all-sites report: {', '.join(r['SiteCode'] for r in rows)} (left out by config/build_options.csv AllSites_Exclude: {', '.join(sorted(ex))})")
        if not any(str(r.get("Is_Default")) == "1" for r in rows) and rows:
            rows[0] = dict(rows[0], Is_Default="1")
    SITES = rows
# M queries that other queries reference by name -> one shared expression per site (<alias>_<SITE>) so a per-site partition
# references only its own site's copy. key = table, value = (alias, tables whose M references it)
REFERENCED = {"Pallet Pattern": ("PalletPattern", ["SAP Plan PO"]), "SAP Plan PO": ("SapPlanPO", ["FG GCAS"]),
              "FG GCAS": ("FgGcas", ["Shipping Market"])}
DROP_TABLES = {"FG GCAS"}            # text helper query, kept only as per-site expressions (FgGcas_<SITE>)
# Include_SAP_CDL = 0: these BD queries only carry SAP data (FG GCAS feeds Shipping Market) -> left out with every object built on them
SAP_QUERIES = {"SAP Plan PO", "Shipping Market", "FG GCAS"}
# one-side lookup tables shared by several site facts: relationship keys become '<SITE>|<key>' so codes never collide across sites
SITE_KEYS = {"RPM Masterdata": ["Material No."], "Planned PO RPM Breakdown": ["material_gcas"], "Pallets Location": ["GCAS"]}
NO_SITE_REL = {"RPM Masterdata"}     # filtered through its facts (a direct Cfg_Site link would make the paths ambiguous)
SITE_TABLES = set()                  # every table with one partition per site (filled while building)
SITE_EXPRS = {}                      # name -> M of the per-site shared expressions
SERVICE = False                      # --service: refresh policies instead of the Desktop history / recent partitions


def site_key_col(col):
    return f"{col} @Site"


def ind(text, n=8):
    return "\n".join((" " * n + ln) if ln.strip() else ln for ln in text.splitlines())


def site_body(table, body, site):
    """Bind a tokenised query to ONE site: static server / database / CDL literals (Service-safe), __Tok record, own-site references."""
    code = site["SiteCode"]
    b = body.replace("Sql.Database(ReplicaServer, ReplicaDatabase,", f"Sql.Database({m_str(site['ReplicaServer'])}, {m_str(site['ReplicaDatabase'])},")
    b = b.replace("Databricks.Catalogs(DatabricksHost, DatabricksHttpPath,",
                  f"Databricks.Catalogs({m_str(site.get('Databricks_Host') or CDL_HOST)}, {m_str(site.get('Databricks_HttpPath') or CDL_HTTP_PATH)},")
    b = b.replace("fnSiteSql(", "fnSiteSql(__Tok, ").replace("fnFeature(", "fnFeature(__Tok, ")
    b = re.sub(r"\bSiteTokens\b", "__Tok", b)
    b = re.sub(r"\bShiftStartH\b", "__ShiftH", b)
    b = b.replace("DateTime.From(StartDateParameter)", 'DateTime.FromText(__Tok[START_DT], [Format = "yyyy-MM-dd HH:mm:ss", Culture = "en-US"])')
    b = re.sub(r'Text\.From\(Record\.FieldOrDefault\(__Tok, "(RPM_\w+)", ""\)\)', lambda m: m_str(site.get(m.group(1)) or ""), b)
    for ref, (alias, users) in REFERENCED.items():
        if table in users:
            b, k = re.subn(r'(?<![\[\w])#"' + re.escape(ref) + r'"(?!\s*=)', f"{alias}_{code}", b)
            assert k, f"{table}: reference to {ref} not found"
    left = re.findall(r"\b(ReplicaServer|ReplicaDatabase|DatabricksHost|DatabricksHttpPath|StartDateParameter|ActivityLookbackDays|Rpm\w+File|RpmFolder)\b", b)
    assert not left, f"{table}/{code}: parameter left {set(left)}"
    return (f"let\n    __Site = {m_str(code)},\n    __Tok = SiteTokens(__Site),\n"
            f"    __ShiftH = Number.From(Record.FieldOrDefault(__Tok, \"Shift1_Start\", 0)),\n    __Body =\n{ind(b)}\nin\n    __Body")


def tag_site(src, table, code):
    """Partition M = site query + SiteCode column (+ '<SITE>|key' columns for shared lookup keys)."""
    m = f"let\n    __Src = {src},\n    __Out = Table.AddColumn(__Src, \"SiteCode\", each {m_str(code)}, type text)"
    last = "__Out"
    for i, c in enumerate(SITE_KEYS.get(table, [])):
        step = f"__Key{i}"
        m += (f",\n    {step} = Table.AddColumn({last}, {m_str(site_key_col(c))}, each if Record.Field(_, {m_str(c)}) = null then null "
              f"else {m_str(code + '|')} & Text.Upper(Text.Trim(Text.From(Record.Field(_, {m_str(c)})))), type text)")
        last = step
    return m + f"\nin\n    {last}"


def site_partitions(table, body_by_site):
    """TMDL: one import partition per site; tables in config/incremental_policy.csv get two (history + recent)."""
    SITE_TABLES.add(table)
    inc = incremental_policy().get(table)
    out = ""
    for s in SITES:
        code = s["SiteCode"]
        src = body_by_site[code]
        if table in REFERENCED:
            src = f"{REFERENCED[table][0]}_{code}"
        else:
            src = "\n" + ind(src, 8)
        parts = [(table + " - " + code, src)]
        if inc and SERVICE and "__Tok = SiteTokens(__Site)," in src:
            # Power BI Service incremental refresh: one partition filtered by RangeStart / RangeEnd + the refresh policy
            if len(SITES) != 1:
                raise SystemExit("--service builds single-site files only (a refresh policy has one source expression per table)")
            rsrc = src.replace("__Tok = SiteTokens(__Site),",
                               "__Tok = Record.Combine({SiteTokens(__Site), [INC_FROM = \"'\" & DateTime.ToText(RangeStart, [Format = \"yyyy-MM-dd HH:mm:ss\", "
                               "Culture = \"en-US\"]) & \"'\", INC_TO = \"'\" & DateTime.ToText(RangeEnd, [Format = \"yyyy-MM-dd HH:mm:ss\", Culture = \"en-US\"]) & \"'\"]}),", 1)
            expr = tag_site(rsrc, table, code)
            win = inc["Service_Window"]
            if win == "HYPERCARE":
                days = (date.today() - datetime.strptime(s["Hypercare_Start"][:10], "%Y-%m-%d").date()).days + 366
            else:
                days = int(s.get(win) or 30) + 1
            out += ("\trefreshPolicy\n\t\tpolicyType: basic\n\t\trollingWindowGranularity: day\n"
                    f"\t\trollingWindowPeriods: {days}\n\t\tincrementalGranularity: day\n\t\tincrementalPeriods: {int(inc['Recent_Days'])}\n"
                    + tmdl_source_block(expr).replace("\t\tsource = ", "\t\tsourceExpression = ", 1) + "\n")
            parts = [(table + " - " + code, rsrc)]
        elif inc and "__Tok = SiteTokens(__Site)," in src:
            rd = int(inc["Recent_Days"])
            rng = lambda field: src.replace("__Tok = SiteTokens(__Site),",
                                            f"__Tok = Record.Combine({{SiteTokens(__Site), [{field} = fnIncBoundary(SiteTokens(__Site), {rd})]}}),", 1)
            parts = [(table + " - " + code, rng("INC_TO")), (table + " - " + code + " - recent", rng("INC_FROM"))]
        elif inc and not SERVICE:   # feature switched off at build for this site -> the empty table also gets its (empty) recent partition
            parts.append((table + " - " + code + " - recent", src))
        for pname, psrc in parts:
            out += f"\tpartition {q(pname)} = m\n\t\tmode: import\n" + tmdl_source_block(tag_site(psrc, table, code)) + "\n"
    return out


def site_columns(table):
    s = tmdl_column(table, "SiteCode", "string", hidden=True)
    for c in SITE_KEYS.get(table, []):
        s += tmdl_column(table, site_key_col(c), "string", hidden=True)
    return s


def per_site_bodies(table, body, gate_cols):
    """Build-time gate per site (source left out when the flag is 0) + site binding."""
    out = {}
    bgate = BUILD_GATE.get(table)
    for s in SITES:
        if bgate and str(s.get(bgate, "0")) != "1":
            how = (f"Include_SAP_CDL = 1 in config/build_options.csv and {bgate} = 1 in config/site_config.csv" if bgate in SAP_FLAGS
                   else f"{bgate} = 1 in config/site_config.csv")
            out[s["SiteCode"]] = (f"// {bgate} = 0 for {s['SiteCode']}: source not included. Set {how} and rebuild.\n"
                                  + (empty_table_m(gate_cols) if gate_cols is not None else '""'))
        else:
            out[s["SiteCode"]] = site_body(table, body, s)
        if table in REFERENCED:
            SITE_EXPRS[f"{REFERENCED[table][0]}_{s['SiteCode']}"] = out[s["SiteCode"]]
    return out


def new_table(name):
    cdl = name in NEW_CDL_TABLES
    cols, types, extra = (NEW_CDL_TABLES if cdl else NEW_TABLES)[name]
    if cdl:
        sql = expand_config_blocks((ROOT / "sql" / "cdl" / f"{name}.sql").read_text(encoding="utf-8"))
        src = (f'Value.NativeQuery(Databricks.Catalogs(DatabricksHost, DatabricksHttpPath, [Catalog="{CDL_CATALOG}", Database=null, QueryTags=null, '
               f'EnableAutomaticProxyDiscovery=null, Implementation="2.0", Protocol=null]){{[Name="{CDL_CATALOG}",Kind="Database"]}}[Data], fnSiteSql(SqlTemplate))')
    else:
        sql = scope_warehouse((ROOT / "sql" / "new" / f"{name}.sql").read_text(encoding="utf-8"))[0]
        sql, k = apply_incremental(name, sql)
        if k == 0:
            raise SystemExit(f"!! {name}: incremental anchor from config/incremental_policy.csv not found in sql/new/{name}.sql")
        src = "Sql.Database(ReplicaServer, ReplicaDatabase, [Query = fnSiteSql(SqlTemplate), CommandTimeout = #duration(0, 0, 20, 0)])"
    m = (f"let\n    SqlTemplate = {m_str(sql)},\n"
         f"    Source = {src},\n"
         f"    Typed = Table.TransformColumnTypes(Source, {{{types}}})")
    m += (extra or ",\n    Result = Typed") + "\nin\n    Result"
    t = tmdl_m_table(name, cols, m, description=sql.splitlines()[0].lstrip("- "))
    i = t.index(f"\tpartition {q(name)} = m")
    j = t.index("\tannotation PBI_ResultType")
    return t[:i] + site_columns(name) + site_partitions(name, per_site_bodies(name, m, [(c[0], c[1]) for c in cols])) + t[j:]


def site_activity_table():
    """Hidden calculated table, one row per site: newest RF-move shift day and newest truck close / dispatch (site-local).
    Read by [Report Date Auto] - a lookup instead of a scan of User Activity / TTAT on every [Report Date] evaluation."""
    name = "Site Activity"
    dax = ("ADDCOLUMNS(VALUES(Cfg_Site[SiteCode]),\n"
           "    \"Last_Move_Shift\", CALCULATE(MAX('User Activity'[Shift_Date])),\n"
           "    \"Last_Truck_Event\", CALCULATE(MAX(MAX(TTAT[Close]), MAX(TTAT[Dispatch]))))")
    cols = [("SiteCode", "string"), ("Last_Move_Shift", "dateTime", "yyyy-mm-dd"), ("Last_Truck_Event", "dateTime", "yyyy-mm-dd hh:nn")]
    s = f"/// {site_activity_table.__doc__.splitlines()[0]}\ntable {q(name)}\n\tisHidden\n\tlineageTag: {tag(name)}\n\n"
    for c in cols:
        s += (f"\tcolumn {q(c[0])}\n\t\tdataType: {c[1]}\n" + (f"\t\tformatString: {c[2]}\n" if len(c) > 2 else "")
              + f"\t\tisHidden\n\t\tlineageTag: {tag(name, 'col', c[0])}\n\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [{c[0]}]\n\n"
              "\t\tannotation SummarizationSetBy = Automatic\n\n")
    s += f"\tpartition {q(name)} = calculated\n\t\tmode: import\n" + tmdl_source_block(dax) + "\n"
    return s


def kpi_snapshot_table():
    """Hidden calculated table, one row per site x KPI: actual + forecast of the default view (report day, whole shift day), at refresh.
    [KPI Actual] / [KPI Predicted] read it when no day / hour / shift is picked - pages open without recomputing every KPI per cell."""
    from measures_scorecard import SNAP_KEYS
    name = "KPI Snapshot"
    keys = ", ".join("{" + m_str(k) + "}" for k in SNAP_KEYS)
    dax = (f"VAR keys = DATATABLE(\"KPI_Key\", STRING, {{{keys}}})\n"
           "RETURN ADDCOLUMNS(GENERATE(VALUES(Cfg_Site[SiteCode]), keys),\n"
           "    \"Report_Date\", CALCULATE([Report Date]),\n"
           "    \"Actual\", CALCULATE([KPI Actual Live], TREATAS({[KPI_Key]}, Cfg_Threshold[KPI_Key])),\n"
           "    \"Predicted\", CALCULATE([KPI Predicted Live], TREATAS({[KPI_Key]}, Cfg_Threshold[KPI_Key])),\n"
           "    \"Computed_UTC\", UTCNOW())")
    cols = [("SiteCode", "string"), ("KPI_Key", "string"), ("Report_Date", "dateTime", "yyyy-mm-dd"), ("Actual", "double"),
            ("Predicted", "double"), ("Computed_UTC", "dateTime", "yyyy-mm-dd hh:nn")]
    s = f"/// {kpi_snapshot_table.__doc__.splitlines()[0]}\ntable {q(name)}\n\tisHidden\n\tlineageTag: {tag(name)}\n\n"
    for c in cols:
        s += (f"\tcolumn {q(c[0])}\n\t\tdataType: {c[1]}\n" + (f"\t\tformatString: {c[2]}\n" if len(c) > 2 else "")
              + f"\t\tisHidden\n\t\tlineageTag: {tag(name, 'col', c[0])}\n\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [{c[0]}]\n\n"
              "\t\tannotation SummarizationSetBy = Automatic\n\n")
    s += f"\tpartition {q(name)} = calculated\n\t\tmode: import\n" + tmdl_source_block(dax) + "\n"
    return s


def copilot_answer_tables():
    """'KPI Scorecard' + 'Site Summary' (tools/copilot_ai.py ANSWER_TABLES): flat rows calculated at refresh for Copilot answers."""
    out = {}
    for name, (desc, dax, cols) in copilot_ai.ANSWER_TABLES.items():
        s = f"/// {desc}\ntable {q(name)}\n\tlineageTag: {tag(name)}\n\n"
        for c, typ, fmt, cdesc in cols:
            s += (f"\t/// {cdesc}\n\tcolumn {q(c)}\n\t\tdataType: {typ}\n" + (f"\t\tformatString: {fmt}\n" if fmt else "")
                  + f"\t\tlineageTag: {tag(name, 'col', c)}\n\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [{c}]\n\n"
                  "\t\tannotation SummarizationSetBy = Automatic\n\n")
        s += f"\tpartition {q(name)} = calculated\n\t\tmode: import\n" + tmdl_source_block(dax) + "\n"
        out[name] = s
    return out


FLOW_ITEM_COLS = [("SiteCode", "string"), ("Stage_Key", "string"), ("Object", "string"), ("Item", "string"), ("Where", "string"),
                  ("Detail", "string"), ("Since", "dateTime", "yyyy-mm-dd hh:nn"), ("Age_Min", "int64"), ("Snapshot", "dateTime", "yyyy-mm-dd hh:nn"),
                  ("Stage_Site_Key", "string")]


def flow_items_table():
    """Calculated table: every truck / pallet / open shipment waiting in a process stage now (union of the three snapshot feeds).
    Age_Min = minutes in the current stage at the feed's Snapshot. Related to Cfg_Stage (Stage_Site_Key) -> Cfg_Site.
    Shipments only for sites where some shipment moved beyond Ready (BD keeps every shipment Ready - order stages N/A there)."""
    name = "Flow Items"
    dax = ("VAR T = SELECTCOLUMNS('Open Trailers', \"SiteCode\", 'Open Trailers'[SiteCode], \"Stage_Key\", 'Open Trailers'[Stage_Key], \"Object\", \"Truck\",\n"
           "    \"Item\", 'Open Trailers'[Direction] & \" truck \" & COALESCE('Open Trailers'[Trailer Number], 'Open Trailers'[TrailerID]),\n"
           "    \"Where\", 'Open Trailers'[Door / Yard],\n"
           "    \"Detail\", 'Open Trailers'[Status] & \" | \" & 'Open Trailers'[Carrier] & \" | \" & FORMAT('Open Trailers'[Pallets On Trailer], \"0\") & \" plt on trailer | on site \" & FORMAT('Open Trailers'[Minutes On Site], \"#,0\") & \" min\",\n"
           "    \"Since\", 'Open Trailers'[Last Status Change], \"Age_Min\", 'Open Trailers'[Minutes In Status], \"Snapshot\", 'Open Trailers'[Snapshot])\n"
           "VAR P = SELECTCOLUMNS('Pallets In Flow', \"SiteCode\", 'Pallets In Flow'[SiteCode], \"Stage_Key\", 'Pallets In Flow'[Stage_Key], \"Object\", \"Pallet\",\n"
           "    \"Item\", \"Pallet \" & 'Pallets In Flow'[Pallet],\n"
           "    \"Where\", 'Pallets In Flow'[Location] & \" (\" & 'Pallets In Flow'[Area] & \")\",\n"
           "    \"Detail\", \"Item \" & 'Pallets In Flow'[Item] & IF('Pallets In Flow'[Items] > 1, \" +\" & FORMAT('Pallets In Flow'[Items] - 1, \"0\") & \" more\", \"\"),\n"
           "    \"Since\", 'Pallets In Flow'[Last Move], \"Age_Min\", 'Pallets In Flow'[Minutes In Location], \"Snapshot\", 'Pallets In Flow'[Snapshot])\n"
           "VAR OrderSites = CALCULATETABLE(VALUES(Shipments[SiteCode]), Shipments[Stage_Key] <> \"O_READY\")\n"
           "VAR S = SELECTCOLUMNS(FILTER(Shipments, Shipments[Is_Open] = 1 && Shipments[SiteCode] IN OrderSites), \"SiteCode\", Shipments[SiteCode], \"Stage_Key\", Shipments[Stage_Key], \"Object\", \"Shipment\",\n"
           "    \"Item\", \"Shipment \" & Shipments[Shipment],\n"
           "    \"Where\", Shipments[Dest Location],\n"
           "    \"Detail\", Shipments[Status] & \" | \" & Shipments[Carrier] & \" | \" & FORMAT(Shipments[Lines], \"0\") & \" lines\" & IF(Shipments[Is_Late] = 1, \" | LATE vs late ship date\", \"\"),\n"
           "    \"Since\", Shipments[Status Since], \"Age_Min\", Shipments[Minutes In Status], \"Snapshot\", Shipments[Snapshot])\n"
           "RETURN ADDCOLUMNS(UNION(T, P, S), \"Stage_Site_Key\", [SiteCode] & \"|\" & [Stage_Key])")
    s = f"/// {flow_items_table.__doc__.splitlines()[0]}\ntable {q(name)}\n\tlineageTag: {tag(name)}\n\n"
    for c in FLOW_ITEM_COLS:
        s += (f"\tcolumn {q(c[0])}\n\t\tdataType: {c[1]}\n" + (f"\t\tformatString: {c[2]}\n" if len(c) > 2 else "")
              + ("\t\tisHidden\n" if c[0] in ("SiteCode", "Stage_Site_Key", "Stage_Key") else "")
              + f"\t\tlineageTag: {tag(name, 'col', c[0])}\n\t\tsummarizeBy: none\n\t\tisNameInferred\n\t\tsourceColumn: [{c[0]}]\n\n"
              "\t\tannotation SummarizationSetBy = Automatic\n\n")
    s += f"\tpartition {q(name)} = calculated\n\t\tmode: import\n" + tmdl_source_block(dax) + "\n"
    return s


# ------------------------------------------------------------------ shared expressions (helpers + per-site referenced queries)
def expressions_tmdl():
    helpers = {
        "SiteTokens": (
            "(site as text) as record =>\nlet\n    Rows = Table.SelectRows(Cfg_Site, each [SiteCode] = site),\n"
            "    Row = if Table.RowCount(Rows) = 0 then error Error.Record(\"Cfg_Site\", \"SiteCode '\" & site & \"' not found in Cfg_Site\") else Rows{0},\n"
            "    Eng = Table.SelectRows(Cfg_Engine, each [WMS_Version] = Row[WMS_Version]),\n"
            "    EngRow = if Table.RowCount(Eng) = 0 then error Error.Record(\"Cfg_Engine\", \"WMS_Version '\" & Row[WMS_Version] & \"' not in Cfg_Engine\") else Record.RemoveFields(Eng{0}, {\"WMS_Version\", \"Notes\"}),\n"
            "    SiteNonBlank = Record.FromTable(Table.SelectRows(Record.ToTable(Row), each [Value] <> null and Text.From([Value]) <> \"\")),\n"
            "    Lines = Table.SelectRows(Cfg_LineMap, each [Site] = site),\n"
            "    MapValues = if Table.RowCount(Lines) = 0 then \"('~NA~','~NA~','~NA~')\" else Text.Combine(List.Transform(Table.ToRecords(Lines), "
            "each \"('\" & [LTA_Source] & \"','\" & [Prod_Line] & \"','\" & [Category] & \"')\"), \",\"),\n"
            "    Start = Text.Start(Text.From(Row[Hypercare_Start]), 19),\n"
            "    Extra = [\n        START_DT = Start,\n        START_YYYYMMDD = Text.Replace(Text.Start(Start, 10), \"-\", \"\"),\n"
            "        LTA_MAP_VALUES = MapValues,\n"
            f"        INC_FROM = {m_str(INC_DEFAULTS['INC_FROM'])},\n        INC_TO = {m_str(INC_DEFAULTS['INC_TO'])}\n    ]\nin\n    Record.Combine({{EngRow, SiteNonBlank, Extra}})",
            "Record of every {TOKEN} of one site (Cfg_Engine defaults + non-blank Cfg_Site columns + derived tokens)."),
        "fnIncBoundary": (
            "(tok as record, recentDays as number) as text =>\nlet\n"
            "    Off = Number.From(Record.FieldOrDefault(tok, \"UTC_Offset_h\", 0)),\n"
            "    LocalNow = DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(DateTimeZone.UtcNow(), Number.RoundTowardZero(Off), Number.Round(Number.Mod(Off, 1) * 60))),\n"
            "    B = Date.AddDays(Date.From(LocalNow), 1 - recentDays)\nin\n"
            "    \"'\" & Date.ToText(B, [Format = \"yyyy-MM-dd\", Culture = \"en-US\"]) & \"'\"",
            "Incremental refresh boundary as a SQL date literal: site-local midnight (recentDays - 1) days ago. "
            "'<table> - <SITE>' holds rows before it (history), '<table> - <SITE> - recent' from it on (config/incremental_policy.csv)."),
        "fnSiteSql": (
            "(tok as record, sqlTemplate as text) as text =>\nlet\n    Names = Record.FieldNames(tok),\n"
            "    Pass = (t as text) as text => List.Accumulate(Names, t, (s, n) => Text.Replace(s, \"{\" & n & \"}\", "
            "let v = Record.Field(tok, n) in if v = null then \"\" else Text.From(v))),\n"
            "    Rendered = Pass(Pass(sqlTemplate)),\n"
            "    // refresh stamp: makes every refresh a new query text, so Power BI Desktop's query cache can never return an older result\n"
            "    Out = Rendered & \"#(lf)-- refresh \" & DateTime.ToText(DateTime.FixedLocalNow(), \"yyyy-MM-dd HH:mm:ss\")\nin\n    Out",
            "Render a SQL template for one site: replaces {TOKEN} with the site's value (2 passes so tokens may contain tokens) "
            "and appends a refresh-time comment (cache buster for refreshes started outside the Desktop ribbon)."),
        "fnFeature": (
            "(tok as record, flag as text) as logical =>\nlet\n    v = Record.FieldOrDefault(tok, flag, 0)\nin\n    v <> null and Text.From(v) = \"1\"",
            "True when the Cfg_Site feature flag (Has_Production / Has_LevelA / Has_HOFF / Has_SAP_Plan) is 1 for the site."),
    }
    out = ""
    for n, (body, desc) in helpers.items():
        out += f"/// {desc}\nexpression {n} = ```\n" + "\n".join("\t\t" + ln if ln else "" for ln in body.splitlines()) + "\n\t\t```\n"
        out += f"\tlineageTag: {tag('expr', n)}\n\n\tannotation PBI_ResultType = Function\n\n"
    for n, body in SITE_EXPRS.items():
        out += (f"/// Per-site copy of a referenced query (generated - edit the source table / config, not this).\nexpression {n} = ```\n"
                + "\n".join("\t\t" + ln if ln.strip() else "" for ln in body.splitlines()) + "\n\t\t```\n")
        out += f"\tlineageTag: {tag('expr', n)}\n\n\tannotation PBI_ResultType = {'Text' if n.startswith('FgGcas') else 'Table'}\n\n"
    if SERVICE:
        # reserved incremental-refresh parameters; the Service replaces them per partition, Desktop loads only this small range
        for n, d in (("RangeStart", date.today() - timedelta(days=2)), ("RangeEnd", date.today() + timedelta(days=1))):
            out += (f"/// Incremental refresh parameter (Power BI Service sets it per partition; Desktop uses this value).\n"
                    f"expression {n} = #datetime({d.year}, {d.month}, {d.day}, 0, 0, 0) meta [IsParameterQuery = true, "
                    f"Type = \"DateTime\", IsParameterQueryRequired = true]\n\tlineageTag: {tag('expr', n)}\n\n"
                    f"\tannotation PBI_ResultType = DateTime\n\n")
    return out


# ------------------------------------------------------------------ original tables: tokenise + gate + one partition per site
PART_RX = re.compile(r"(\tpartition [^\n]+ = m\n\t\tmode: import\n)\t\tsource =(?: ```)?\n(.*?)(?=\n\t[^\t]|\Z)", re.S)


def dedent_m(block):
    lines = block.split("\n")
    lines = [ln[4:] if ln.startswith("\t\t\t\t") else ln for ln in lines]
    txt = "\n".join(lines).rstrip()
    if txt.endswith("```"):
        txt = txt[:-3].rstrip()
    return txt


TEXT_COLS = {"Pallets Movement": ("from_zone", "to_zone")}   # zone = int on PrIME 2022, area code (text) on PrIME 2014


def force_text_columns(name, text):
    for col in TEXT_COLS.get(name, ()):
        rx = re.compile(r"(?m)^(\tcolumn " + re.escape(col) + r"\n)((?:\t\t.*\n|\n(?=\t\t))*)")
        m = rx.search(text)
        if not m:
            raise SystemExit(f"{name}: column {col} not found for TEXT_COLS")
        body = re.sub(r"(?m)^\t\tdataType: \w+$", "\t\tdataType: string", m.group(2))
        body = re.sub(r"(?m)^\t\tformatString: .*\n", "", body)
        body = re.sub(r"(?m)^\t\tsummarizeBy: \w+$", "\t\tsummarizeBy: none", body)
        text = text[:m.start(2)] + body + text[m.end(2):]
    return text


def transform_table(fname, text, report):
    name = fname[:-5]                                   # file-name form (config keys, e.g. 'short%2Ftall')
    text = force_text_columns(name, text)
    real = re.search(r"(?m)^table (.+)$", text).group(1).strip()
    real = real[1:-1].replace("''", "'") if real.startswith("'") else real
    mm = PART_RX.search(text)
    if not mm:
        return text
    m = dedent_m(mm.group(2))
    if not INCLUDE_SAP and name in SAP_QUERIES:
        return None
    if not re.search(r"Sql\.Database|Databricks|DateTimeZone\.SwitchZone|#\"FG GCAS\"|#\"SAP Plan PO\"|File\.Contents", m):
        return text
    new_m, notes = tokenize_m(name, m)
    gate = FEATURE_GATE.get(name)
    cols = parse_tmdl_columns(text) if name != "FG GCAS" else None
    if gate:
        new_m = (f"let\n    __Enabled = fnFeature(\"{gate}\"),\n    __Body =\n" + "\n".join("        " + ln for ln in new_m.splitlines()) +
                 f",\n    __Result = if __Enabled then __Body else {empty_table_m(cols)}\nin\n    __Result")
        notes.append(f"gated by {gate}")
    left = BD_LEFTOVERS.findall(new_m)
    if re.search(r"Sql\.Database|Databricks", new_m) and "fnSiteSql(" not in new_m:
        raise SystemExit(f"{name}: SQL is not wrapped in fnSiteSql - tokens would reach the server unresolved")
    report.append({"table": name, "notes": notes, "bd_leftovers": sorted(set(left))})
    (ROOT / "sql" / "extracted").mkdir(parents=True, exist_ok=True)
    (ROOT / "sql" / "extracted" / f"{fname[:-5]}.m").write_text(new_m, encoding="utf-8")
    bodies = per_site_bodies(name, new_m, cols)
    if BUILD_GATE.get(name):
        notes.append(f"source excluded at build for sites with {BUILD_GATE[name]}=0: " +
                     ",".join(s["SiteCode"] for s in SITES if str(s.get(BUILD_GATE[name], "0")) != "1"))
    if name in DROP_TABLES:
        return None
    return text[:mm.start()] + site_columns(real) + site_partitions(real, bodies) + text[mm.end():].lstrip("\n")


TREF = r"('(?:[^']|'')+'|[A-Za-z_]\w*)"


def _tname(ref):
    ref = ref.strip()
    return ref[1:-1].replace("''", "'") if ref.startswith("'") else ref


def site_safe(name, dax):
    """REMOVEFILTERS(<site fact>) also drops the Site slicer (expanded table) -> re-apply the selected site right after it."""
    dax = re.sub(r"REMOVEFILTERS\(\s*" + TREF + r"\s*\)",
                 lambda m: m.group(0) + (", VALUES(Cfg_Site[SiteCode])" if _tname(m.group(1)) in SITE_TABLES else ""), dax)
    # whole-table ALL(<site fact>) drops the Site slicer; ALL(<site fact>[column]) only clears that column - allowed
    bad = [t for t in re.findall(r"\bALL(?:EXCEPT|NOBLANKROW)?\(\s*" + TREF + r"\s*(?=[,)])", dax) if _tname(t) in SITE_TABLES]
    assert not bad, f"measure {name}: ALL({bad}) would ignore the Site slicer - use site_all()"
    return dax


SHIFT_COLS = {r["Table"]: r for r in read_csv("shift_columns.csv")}
_SHIFT_EQ = re.compile(r"(?<=[,(])(\s*)(" + "|".join(re.escape(q(t)) for t in SHIFT_COLS) + r")\[(\w+)\] = (d|cd)(?=\s*[,)])")
SHIFT_HITS = []


def shift_safe(dax):
    """Global Shift slicer: a filter '<table>[<shift day>] = d' of a shift-column table (config/shift_columns.csv) also keeps the
    selected shift's rows (TREATAS over the table's Shift_No column; no selection = every shift)."""
    def rep(m):
        t = m.group(2).strip("'")
        if m.group(3) != SHIFT_COLS[t]["Day_Column"]:
            return m.group(0)
        SHIFT_HITS.append(t)
        return f"{m.group(1)}{m.group(2)}[{m.group(3)}] = {m.group(4)}, TREATAS(VALUES(Cfg_Shift[Shift_No]), {m.group(2)}[Shift_No])"
    return _SHIFT_EQ.sub(rep, dax)


def add_shift_columns(defn):
    """Calculated column Shift_No (1 / 2 / 3) on every table of config/shift_columns.csv: the clock hour against the site's shift starts
    (Cfg_Site Shift1/2/3_Start; 2-shift sites have Shift3_Start = Shift2_Start and never get shift 3)."""
    n = 0
    for t, r in SHIFT_COLS.items():
        f = defn / "tables" / f"{t}.tmdl"
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        if "\tcolumn Shift_No" in txt:
            continue
        expr = (f"VAR h = {r['Hour_Expr']} VAR s1 = RELATED(Cfg_Site[Shift1_Start]) VAR o = MOD(h - s1, 24) "
                "VAR o2 = MOD(RELATED(Cfg_Site[Shift2_Start]) - s1, 24) VAR o3 = MOD(RELATED(Cfg_Site[Shift3_Start]) - s1, 24) "
                "RETURN IF(ISBLANK(h), BLANK(), IF(o < o2, 1, IF(o3 <= o2 || o < o3, 2, 3)))")
        col = (f"\tcolumn Shift_No = {expr}\n\t\tdataType: int64\n\t\tisHidden\n\t\tformatString: 0\n\t\tlineageTag: {tag(t, 'col', 'Shift_No')}\n"
               "\t\tsummarizeBy: none\n\n\t\tannotation SummarizationSetBy = User\n\n")
        i = txt.index("\tpartition ")
        f.write_text(txt[:i] + col + txt[i:], encoding="utf-8")
        n += 1
    return n


def kpi_table():
    s = f"/// Hypercare KPI measures - scorecard, prediction, alerts, RCA, health. Generated by tools/build_pbip.py\ntable _KPI\n\tlineageTag: {tag('_KPI')}\n\n"
    allm = (measures_core.CONTEXT + measures_core.PRODUCTION + measures_flow.LINES + measures_flow.FLOWS +
            measures_ops.WAREHOUSE + measures_ops.USERS + measures_ops.HEALTH + measures_ops.HOURLY + measures_scorecard.ALL_SCORECARD +
            measures_diag.all_measures(measures_scorecard.CARD_KEYS))
    allm = [(n, f, fmt, shift_safe(site_safe(n, dax))) for n, f, fmt, dax in allm]
    # row count per site table: drives the site-scope filter of column-only visuals (report_pages.scope_column_visuals)
    allm += [(f"Rows {t}", "9 Helpers\\Row counts", "#,0", f"COUNTROWS({q(t)})") for t in sorted(SITE_TABLES)]
    names = [x[0] for x in allm]
    dup = {n for n in names if names.count(n) > 1}
    assert not dup, f"duplicate measures {dup}"
    # config/kpi_explain.csv Numbers templates may only reference measures of the model (a typo would put the measure in error)
    refs = {m for r in measures_scorecard.EXPLAIN for m in re.findall(r"\[([^\]]+)\]", r["Numbers"])}
    bad = sorted(refs - set(names))
    assert not bad, f"config/kpi_explain.csv Numbers reference unknown measures: {bad}"
    # field-list tooltip = config/field_guide.csv meaning + unit (one source for the Field Guide page and the model)
    desc = {r["Measure"]: f"{r['Meaning']} Unit: {r['Unit']}." + (f" Source: {r['Source']}." if r["Source"] else "")
            for r in read_csv("field_guide.csv") if r.get("Measure")}
    desc = {**copilot_ai.descriptions(), **desc}  # config/copilot_descriptions.csv for key measures Copilot needs (field guide wins)
    unknown = sorted(set(desc) - set(names))
    assert not unknown, f"config/field_guide.csv / copilot_descriptions.csv Measure names unknown measures: {unknown}"
    for n, folder, fmt, dax in allm:
        s += tmdl_measure("_KPI", n, folder, fmt, dax, description=desc.get(n))
    s += (f"\tcolumn Value\n\t\tisHidden\n\t\tformatString: 0\n\t\tlineageTag: {tag('_KPI', 'col', 'Value')}\n\t\tsummarizeBy: none\n"
          "\t\tisNameInferred\n\t\tsourceColumn: [Value]\n\n\t\tannotation SummarizationSetBy = Automatic\n\n"
          "\tpartition _KPI = calculated\n\t\tmode: import\n\t\tsource = DATATABLE(\"Value\", INT64, {{1}})\n\n")
    return s, len(allm)


def drop_auto_datetime(defn):
    """Auto date/time = 42 hidden LocalDateTable_* tables (one per date column) built at every refresh; no visual uses them."""
    tables = defn / "tables"
    gone = [f for f in tables.glob("*.tmdl") if f.name.startswith(("LocalDateTable_", "DateTableTemplate_"))]
    for f in gone:
        f.unlink()
    for f in tables.glob("*.tmdl"):
        t = f.read_text(encoding="utf-8")
        t2 = re.sub(r"\n\t\tvariation Variation\n(?:\t\t\t[^\n]*\n)+", "\n", t)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    rel = defn / "relationships.tmdl"
    blocks = re.split(r"\n(?=relationship )", rel.read_text(encoding="utf-8"))
    rel.write_text("\n".join(b for b in blocks if not re.search(r"LocalDateTable_|DateTableTemplate_", b)), encoding="utf-8")
    model = defn / "model.tmdl"
    m = model.read_text(encoding="utf-8")
    m = re.sub(r"ref table (?:LocalDateTable_|DateTableTemplate_)[^\n]*\n", "", m)
    m = m.replace("annotation __PBI_TimeIntelligenceEnabled = 1", "annotation __PBI_TimeIntelligenceEnabled = 0")
    model.write_text(m, encoding="utf-8")
    return len(gone)


def apply_measure_units(defn):
    """config/measure_units.csv -> every numeric measure gets its unit inside the format string (e.g. 12.5 plt/h)."""
    units = {r["Measure"]: (r["Base_Format"], r["Unit"]) for r in read_csv("measure_units.csv")}
    seen = set()
    rx = re.compile(r"^\tmeasure ('(?:[^']|'')+'|[^\s=]+)\s*=", re.M)
    for f in (defn / "tables").glob("*.tmdl"):
        t = f.read_text(encoding="utf-8")
        heads = list(rx.finditer(t))
        if not heads:
            continue
        parts, last = [], 0
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
            nxt = re.search(r"^\t(?!\t)(?!measure)\S", t[m.end():end], re.M)
            end = m.end() + nxt.start() if nxt else end
            name = m.group(1).strip("'").replace("''", "'")
            block = t[m.start():end]
            if name in units and units[name][1]:
                base, unit = units[name]
                fmt = ";".join(f'{sec} ""{unit}""' for sec in base.split(";"))
                line = f'\t\tformatString: "{fmt}"'
                if re.search(r"^\t\tformatString:.*$", block, re.M):
                    block = re.sub(r"^\t\tformatString:.*$", lambda _m: line, block, count=1, flags=re.M)
                else:
                    block = re.sub(r"^(\t\tlineageTag:)", lambda _m: line + "\n" + _m.group(1), block, count=1, flags=re.M)
                    assert line in block, f"no lineageTag to anchor the unit of {name}"
                seen.add(name)
            parts += [t[last:m.start()], block]
            last = end
        parts.append(t[last:])
        t2 = "".join(parts)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    missing = sorted(set(k for k, v in units.items() if v[1]) - seen - PRUNED)
    assert not missing, f"measure_units.csv lists unknown measures: {missing}"
    return len(seen)


def apply_strip_formats(defn):
    """KPI-strip twins '<m> (strip)' (measures_diag.strip_twins): the base measure's FINAL format (unit included) + a zero
    section '–' -> a multi-row card shows '–' for no value instead of '(Blank)'. Runs after apply_measure_units."""
    from kpi_strips import STRIP_SUFFIX
    f = defn / "tables" / "_KPI.tmdl"
    t = f.read_text(encoding="utf-8")
    rx = re.compile(r"^\tmeasure ('(?:[^']|'')+'|[^\s=]+)\s*=", re.M)
    heads = list(rx.finditer(t))
    spans = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
        nxt = re.search(r"^\t(?!\t)(?!measure)\S", t[m.end():end], re.M)
        spans[m.group(1).strip("'").replace("''", "'")] = (m.start(), m.end() + nxt.start() if nxt else end)

    def fmt_of(name):
        s, e = spans[name]
        fm = re.search(r"^\t\tformatString: (.*)$", t[s:e], re.M)
        v = fm.group(1).strip() if fm else "0"
        return v[1:-1].replace('""', '"') if v.startswith('"') else v

    edits = []
    for name, (s, e) in spans.items():
        if not name.endswith(STRIP_SUFFIX):
            continue
        base = name[: -len(STRIP_SUFFIX)]
        assert base in spans, f"KPI strip twin [{name}]: base measure [{base}] is not in _KPI"
        pos = re.split(r';(?=(?:[^"]*"[^"]*")*[^"]*$)', fmt_of(base))[0]
        line = '\t\tformatString: "' + f'{pos};-{pos};"–"'.replace('"', '""') + '"'
        block = t[s:e]
        if re.search(r"^\t\tformatString:.*$", block, re.M):
            block = re.sub(r"^\t\tformatString:.*$", lambda _m: line, block, count=1, flags=re.M)
        else:
            block = re.sub(r"^(\t\tlineageTag:)", lambda _m: line + "\n" + _m.group(1), block, count=1, flags=re.M)
            assert line in block, f"no lineageTag to anchor the format of [{name}]"
        edits.append((s, e, block))
    for s, e, block in sorted(edits, reverse=True):
        t = t[:s] + block + t[e:]
    f.write_text(t, encoding="utf-8")
    return len(edits)


def apply_column_units(defn):
    """config/column_units.csv -> every visible numeric column carries its unit in the format string (e.g. 45 min, 12 plt).
    Rules are regexes on 'Table|Column', first match wins; '#hide' hides technical sort keys, '#clock' = hour of day as hh:00."""
    rules = [(re.compile(r["Pattern"]), r["Base_Format"], r["Unit"]) for r in read_csv("column_units.csv")]
    rx = re.compile(r"(?m)^\tcolumn ([^\n]+)\n((?:(?:\t\t[^\n]*)?\n)*?)(?=^\t\S|\Z)")
    done, unmatched = 0, []
    for f in (defn / "tables").glob("*.tmdl"):
        if f.stem.startswith(("Cfg_", "_KPI", "Input ")):
            continue
        t = f.read_text(encoding="utf-8")
        tname = re.search(r"(?m)^table (.+)$", t).group(1).strip().strip("'")

        def fix(m):
            nonlocal done
            decl, body = m.group(1), m.group(2)
            dt = re.search(r"^\t\tdataType: (\w+)", body, re.M)
            if not dt or dt.group(1) not in ("int64", "double", "decimal") or re.search(r"^\t\tisHidden", body, re.M):
                return m.group(0)
            col = decl.split(" = ")[0].strip().strip("'")
            rule = next(((b, u) for r, b, u in rules if r.search(f"{tname}|{col}")), None)
            if rule is None:
                unmatched.append(f"{tname}[{col}]")
                return m.group(0)
            base, unit = rule
            if unit == "#hide":
                body = re.sub(r"^(\t\tlineageTag:)", "\t\tisHidden\n\\1", body, count=1, flags=re.M)
            else:
                fmt = base if unit in ("#clock", "#literal", "%") else ";".join(f'{sec} "{unit}"' for sec in base.split(";"))
                line = '\t\tformatString: "' + fmt.replace('"', '""') + '"'
                if re.search(r"^\t\tformatString:.*$", body, re.M):
                    body = re.sub(r"^\t\tformatString:.*$", lambda _m: line, body, count=1, flags=re.M)
                else:
                    body = re.sub(r"^(\t\tlineageTag:)", lambda _m: line + "\n" + _m.group(1), body, count=1, flags=re.M)
            done += 1
            return f"\tcolumn {decl}\n{body}"
        t2 = rx.sub(fix, t)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    return done, unmatched


def site_relationships(defn):
    """Cfg_Site[SiteCode] 1 -> * every site table (single direction). Removes / deactivates the links that would make two filter paths."""
    rel = defn / "relationships.tmdl"
    t = rel.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = re.split(r"\n(?=relationship )", t.strip("\n"))
    out = []
    for b in blocks:
        if "'Pallet from LTA to short/tall location'.prtnum" in b and "'Pallet Pattern'.prtnum" in b:
            continue        # auto-detected, unused by DAX / visuals; would be a 2nd path Cfg_Site -> short/tall
        if "'WorkLine Activities'.'FG GCAS'" in b and "'Produced Pallet'.FG_GCAS" in b:
            continue        # M:M both-ways would make 2 filter paths; inactive + never used by USERELATIONSHIP = dead (BPA) -> removed
        for table, cols in SITE_KEYS.items():
            for c in cols:
                b = b.replace(f"{q(table)}.{q(c)}", f"{q(table)}.{q(site_key_col(c))}")
        # source model joined the text hour "06" to the integer DimHour[Hour] -> hours 00-09 never matched; join the text label
        b = b.replace("fromColumn: 'Produced Pallet'.ReportHour\n\ttoColumn: DimHour.Hour", "fromColumn: 'Produced Pallet'.ReportHour\n\ttoColumn: DimHour.'Hour Label'")
        out.append(b)
    found = "\n".join(out)
    assert "'Pallet Pattern'.prtnum" not in found and "'WorkLine Activities'.'FG GCAS'" not in found, "relationship rework did not match the source model"
    for table in sorted(SITE_TABLES - NO_SITE_REL):
        out.append(f"relationship {tag('rel', 'site', table)}\n\tfromColumn: {q(table)}.SiteCode\n\ttoColumn: Cfg_Site.SiteCode")
    out.append(f"relationship {tag('rel', 'site', 'Cfg_Threshold')}\n\tfromColumn: Cfg_Threshold.SiteCode\n\ttoColumn: Cfg_Site.SiteCode")
    out.append(f"relationship {tag('rel', 'site', 'Cfg_LineMap')}\n\tfromColumn: Cfg_LineMap.Site\n\ttoColumn: Cfg_Site.SiteCode")
    # process model snowflake: Cfg_Site -> Cfg_Stage -> Flow Items (the waiting trucks / pallets / shipments of every stage)
    out.append(f"relationship {tag('rel', 'site', 'Cfg_Stage')}\n\tfromColumn: Cfg_Stage.SiteCode\n\ttoColumn: Cfg_Site.SiteCode")
    out.append(f"relationship {tag('rel', 'stage', 'Flow Items')}\n\tfromColumn: 'Flow Items'.Stage_Site_Key\n\ttoColumn: Cfg_Stage.Stage_Site_Key")
    rel.write_text("\n\n".join(out) + "\n", encoding="utf-8")
    return len(SITE_TABLES - NO_SITE_REL) + 4


def check_relationship_types(defn):
    """Best-practice gate: both columns of every relationship must have the same data type (a text '06' never matches the number 6)."""
    types = {}
    for f in (defn / "tables").glob("*.tmdl"):
        t = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        tn = _tname(re.search(r"(?m)^table (.+)$", t).group(1).strip())
        for m in re.finditer(r"(?m)^\tcolumn ('(?:[^']|'')+'|[^\s=]+)[^\n]*\n((?:\t\t[^\n]*\n|\n(?=\t\t))*)", t):
            dt = re.search(r"(?m)^\t\tdataType: (\w+)", m.group(2))
            types[(tn, _tname(m.group(1)))] = dt.group(1) if dt else None
        for m in re.finditer(r"(?m)^\tcolumn ('(?:[^']|'')+'|[^\s=]+) = ", t):   # calculated columns without dataType line -> unknown
            types.setdefault((tn, _tname(m.group(1))), None)
    bad = []
    rel = (defn / "relationships.tmdl").read_text(encoding="utf-8").replace("\r\n", "\n")
    for fr, to in re.findall(r"fromColumn: ([^\n]+)\n\ttoColumn: ([^\n]+)", rel):
        def split(x):
            m = re.match(r"(" + TREF + r")\.(.+)$", x.strip())
            return _tname(m.group(1)), _tname(m.groups()[-1])           # TREF has its own group: the column is the LAST group
        for side in (fr, to):
            if split(side) not in types:                         # Desktop refuses the whole project ("refers to an object which cannot be found")
                bad.append(f"{side}: column does not exist (relationship {fr} -> {to})")
        a, b = types.get(split(fr)), types.get(split(to))
        if a and b and a != b:
            bad.append(f"{fr} ({a}) -> {to} ({b})")
    if bad:
        raise SystemExit("Relationship column missing / data-type mismatch:\n  " + "\n  ".join(bad))
    return len(re.findall(r"fromColumn:", rel))


def check_site_dax(defn):
    """Original DAX (calculated columns / measures): keep the Site slicer when a fact is cleared; no ALL(<site fact>)."""
    for f in (defn / "tables").glob("*.tmdl"):
        if f.stem == "_KPI":
            continue
        t = f.read_text(encoding="utf-8")
        t2 = re.sub(r"REMOVEFILTERS\(\s*" + TREF + r"\s*\)",
                    lambda m: m.group(0) + (", VALUES(Cfg_Site[SiteCode])" if _tname(m.group(1)) in SITE_TABLES else ""), t)
        bad = [x for x in re.findall(r"\bALL(?:EXCEPT|NOBLANKROW)?\(\s*" + TREF, t2) if _tname(x) in SITE_TABLES]
        assert not bad, f"{f.name}: ALL({bad}) ignores the Site slicer"
        if t2 != t:
            f.write_text(t2, encoding="utf-8")


def zero_count_cards(defn):
    """Cards of the source report that show a COUNT (DISTINCTCOUNT / COUNTROWS / COUNT) display 0 instead of (Blank) when nothing
    matched - a zero violation count is a result, not missing data. Measures are taken from the report's card visuals."""
    names = set()
    for vf in SRC_REPORT.glob("definition/pages/*/visuals/*/visual.json"):
        v = json.loads(vf.read_text(encoding="utf-8")).get("visual", {})
        if v.get("visualType") not in ("card", "cardVisual", "multiRowCard"):
            continue
        for role in v.get("query", {}).get("queryState", {}).values():
            for p in role.get("projections", []):
                if "Measure" in p["field"]:
                    names.add(p["field"]["Measure"]["Property"])
    f = defn / "tables" / "_DaxMeasure.tmdl"
    t = f.read_text(encoding="utf-8")
    done = []
    for n in sorted(names):
        rx = re.compile(r"(\tmeasure " + re.escape(q(n)) + r" =)(.*?)(?=\n\t\t(?:formatString|lineageTag|displayFolder|annotation))", re.S)
        m = rx.search(t)
        if not m:
            continue
        body = m.group(2)
        if not re.search(r"\b(DISTINCTCOUNT|COUNTROWS|COUNT)\s*\(", body) or re.search(r"\+\s*0\s*$|COALESCE\(", body.strip().strip("`").strip()):
            continue
        inner = body.strip()
        inner = inner[3:-3] if inner.startswith("```") and inner.endswith("```") else inner
        new = " ```\n\t\t\tCOALESCE((\n" + "\n".join("\t\t\t" + ln.strip("\t") for ln in inner.strip("\n").splitlines()) + "\n\t\t\t), 0)\n\t\t\t```"
        t = t[:m.start(2)] + new + t[m.end(2):]
        done.append(n)
    f.write_text(t, encoding="utf-8")
    return done


def mark_date_table(defn):
    """Best practice: the calendar is marked as the model's date table (dataCategory Time + key Date column)."""
    f = defn / "tables" / "DimDate.tmdl"
    t = f.read_text(encoding="utf-8")
    if "\tdataCategory: Time" not in t:
        t = re.sub(r"(?m)^(table DimDate\n\tlineageTag: [^\n]+\n)", r"\1\tdataCategory: Time\n", t, count=1)
        t = re.sub(r"(?m)^(\tcolumn Date\n)", r"\1\t\tisKey\n", t, count=1)
        assert "\tdataCategory: Time" in t and "\t\tisKey" in t, "DimDate layout changed - cannot mark as date table"
        f.write_text(t, encoding="utf-8")


def _tmdl_blocks(text):
    """Split a table .tmdl into (kind, name, is_calculated, block_text) per top-level member (one tab); the header is kind 'head'."""
    out, cur, doc = [], ["head", None, False, []], []
    for ln in text.split("\n"):
        if ln.startswith("\t///"):            # description lines belong to the NEXT member
            doc.append(ln)
            continue
        m = re.match(r"^\t(measure|column|partition|hierarchy|annotation|changedProperty|calculationGroup)\b ?(.*)$", ln)
        if m:
            out.append(cur)
            nm = re.match(r"('(?:[^']|'')+'|[^ =]+)\s*(=?)", m.group(2) or "")
            cur = [m.group(1), _tname(nm.group(1)) if nm else None, bool(nm and nm.group(2)), doc + [ln]]
        else:
            cur[3].extend(doc + [ln])
        doc = []
    cur[3].extend(doc)
    out.append(cur)
    return [(k, n, c, "\n".join(b)) for k, n, c, b in out]


def prune_left_out(defn, gone):
    """Remove every model object that reads a left-out table (Include_SAP_CDL = 0): calculated tables built only on them, relationships,
    calculated columns and measures (transitively). Returns the removed names; the report check afterwards fails on any visual still using one."""
    tdir = defn / "tables"
    gone = set(gone)
    def reads(text, tables):
        # DAX: a name with spaces is always quoted ('SAP Plan PO'); a simple name may be bare before [ or ) (Dim_GCAS[GCAS])
        return any(f"'{t}'" in text or (re.fullmatch(r"\w+", t) and re.search(rf"(?<![\w']){re.escape(t)}\s*[\[),]", text)) for t in tables)
    changed = True
    while changed:                       # calculated tables whose source only reads left-out tables
        changed = False
        for f in tdir.glob("*.tmdl"):
            t = f.read_text(encoding="utf-8")
            name = _tname(re.search(r"(?m)^table (.+)$", t).group(1))
            if name in gone:
                continue
            part = re.search(r"(?ms)^\tpartition .*?= calculated\n(.*?)(?=^\t\S|\Z)", t)
            if part and reads(part.group(1), gone):
                gone.add(name)
                changed = True
    for f in tdir.glob("*.tmdl"):
        name = _tname(re.search(r"(?m)^table (.+)$", f.read_text(encoding="utf-8")).group(1))
        if name in gone:
            f.unlink()
    removed_m, removed_c = set(), set()
    files = {f: _tmdl_blocks(f.read_text(encoding="utf-8")) for f in tdir.glob("*.tmdl")}
    changed = True
    while changed:
        changed = False
        for f, blocks in files.items():
            for k, n, calc, b in blocks:
                if k == "measure" and n not in removed_m:
                    body = b.split("=", 1)[1] if "=" in b else ""
                    if (reads(body, gone) or any(f"[{x}]" in body for x in removed_m | removed_c)
                            or re.search(r"(?m)^\t\tdisplayFolder: [^\n]*\bSAP\b", b)):   # measures filed under an SAP folder
                        removed_m.add(n); changed = True
                elif k == "column" and calc and n not in removed_c:
                    if reads(b.split("=", 1)[1], gone):
                        removed_c.add(n); changed = True
    for f, blocks in files.items():
        for k, n, calc, b in blocks:
            if k == "partition" and "= calculated" in b and any(f"[{x}]" in b for x in removed_m):
                raise SystemExit(f"!! {f.stem}: calculated table reads a measure removed with the SAP tables - rewrite it for Include_SAP_CDL = 0")
    for f, blocks in files.items():
        keep = [b for k, n, calc, b in blocks if not ((k == "measure" and n in removed_m) or (k == "column" and calc and n in removed_c))]
        f.write_text("\n".join(keep), encoding="utf-8")
    rf = defn / "relationships.tmdl"
    if rf.exists():
        rels = re.split(r"(?m)^(?=relationship )", rf.read_text(encoding="utf-8"))
        rels = [r for r in rels if not re.search(r"(?m)^\t(?:from|to)Column: " + "(?:" + "|".join(re.escape(q(t)) for t in gone) + r")\.", r)]
        rf.write_text("".join(rels), encoding="utf-8")
    # Q&A / Copilot linguistic schema: entities bound to a removed table, measure or column
    for cf in (defn / "cultures").glob("*.tmdl"):
        t = cf.read_text(encoding="utf-8")
        mm = re.search(r"(linguisticMetadata = )(\{.*\})(\s*\n)", t)
        if not mm:
            continue
        lm = json.loads(mm.group(2))
        ents = lm.get("Entities", {})
        def dead(v):
            b = (v.get("Definition") or {}).get("Binding") or {}
            return b.get("ConceptualEntity") in gone or b.get("ConceptualProperty") in (removed_m | removed_c)
        lm["Entities"] = {k: v for k, v in ents.items() if not dead(v)}
        rels = lm.get("Relationships", {})
        if rels:
            lm["Relationships"] = {k: v for k, v in rels.items()
                                   if not dead(v) and all(r in lm["Entities"] for r in (v.get("Roles") or {}))}
        if len(lm["Entities"]) != len(ents) or len(lm.get("Relationships", {})) != len(rels):
            cf.write_text(t[:mm.start(2)] + json.dumps(lm, ensure_ascii=False, separators=(",", ":")) + t[mm.end(2):], encoding="utf-8")
    return gone, removed_m, removed_c


def build_model(out_sm):
    defn = out_sm / "definition"
    if out_sm.exists():
        shutil.rmtree(out_sm)
    shutil.copytree(SRC, defn)
    report = []
    SITE_TABLES.clear()
    SITE_EXPRS.clear()
    sp = defn / "tables" / "Short PO.tmdl"
    if sp.exists():
        sp.write_text(sp.read_text(encoding="utf-8").replace("mode: directQuery", "mode: import"), encoding="utf-8")
    dropped = []
    for f in sorted((defn / "tables").glob("*.tmdl"), key=lambda x: (x.stem not in REFERENCED, x.stem)):
        t = f.read_text(encoding="utf-8")
        t2 = transform_table(f.name, t, report)
        if t2 is None:
            f.unlink()
            dropped.append(f.stem)
            continue
        if f.name == "Date Refresh.tmdl":
            t2 = t2.replace("NOW() + TIME(7,0,0)", "UTCNOW() + [Site UTC Offset h] / 24")
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
    patch_dax(defn / "tables")
    mark_date_table(defn)
    zeroed = zero_count_cards(defn)
    print(f"   count cards showing 0 instead of blank: {len(zeroed)} ({', '.join(zeroed[:8])}{' ...' if len(zeroed) > 8 else ''})")
    drop_auto_datetime(defn)
    new = build_config_tables()
    for n in list(NEW_TABLES) + (list(NEW_CDL_TABLES) if INCLUDE_SAP else []):
        new[n] = new_table(n)
    new["Flow Items"] = flow_items_table()
    new["Site Activity"] = site_activity_table()
    new["KPI Snapshot"] = kpi_snapshot_table()
    new.update(copilot_answer_tables())
    kt, nmeas = kpi_table()
    new["_KPI"] = kt
    for n, txt in new.items():
        (defn / "tables" / f"{n}.tmdl").write_text(txt, encoding="utf-8")
    if not INCLUDE_SAP:
        gone, pm, pc = prune_left_out(defn, set(SAP_TABLES) | {"Cfg_Market"})   # Cfg_Market = market colours of the SAP plan matrix only
        dropped += sorted(gone - set(dropped))
        PRUNED.update(pm | pc)
        print(f"   SAP left out (Include_SAP_CDL = 0): tables {', '.join(sorted(gone))}; {len(pm)} measures, {len(pc)} calculated columns removed")
    check_site_dax(defn)
    nrel = site_relationships(defn)
    nshift = add_shift_columns(defn)
    print(f"   shift window: Shift_No on {nshift} tables, shift filter added to {len(SHIFT_HITS)} measure filters ({', '.join(sorted(set(SHIFT_HITS)))})")
    SHIFT_HITS.clear()
    check_relationship_types(defn)
    apply_measure_units(defn)
    apply_strip_formats(defn)
    ncol, unmatched = apply_column_units(defn)
    (defn / "expressions.tmdl").write_text(expressions_tmdl(), encoding="utf-8")
    model = (defn / "model.tmdl").read_text(encoding="utf-8")
    for d in dropped:
        model = re.sub(r"ref table " + re.escape(q(d)) + r"\n", "", model)
    order = json.loads(re.search(r"annotation PBI_QueryOrder = (\[.*\])", model).group(1))
    order = ["SiteTokens", "fnSiteSql", "fnFeature", "Cfg_Site", "Cfg_Engine", "Cfg_ThresholdBase", "Cfg_TargetInput", "Cfg_InputIssues", "Cfg_LineMap", "Cfg_AlertRule",
             "Cfg_HealthCheck", "Cfg_RCA", "Cfg_Market", "Cfg_PageGuide", "Cfg_Stage", "Cfg_TimeBand", "Cfg_MoveClass", "Cfg_FieldGuide", "Cfg_CopilotQuestions",
             "Cfg_StockAge", "Cfg_Refresh", "Cfg_DesktopRefresh", "Cfg_KpiExplain", "Cfg_StockCause", "Cfg_Shift"] + list(SITE_EXPRS) + \
        [o for o in order if o not in dropped and o != "StartDateParameter"] + list(NEW_TABLES) + (list(NEW_CDL_TABLES) if INCLUDE_SAP else [])
    order = [o for o in dict.fromkeys(order) if o not in dropped]
    model = re.sub(r"annotation PBI_QueryOrder = \[.*\]", "annotation PBI_QueryOrder = " + json.dumps(order, ensure_ascii=False), model)
    refs = "".join(f"ref table {q(n)}\n" for n in new if n not in dropped)
    model = re.sub(r"(ref table [^\n]+\n)(?!ref table)", lambda m_: m_.group(1) + refs, model, count=1)
    scope = "all configured PrIME 2014 / 2022 sites in one model; the Site slicer picks one" if len(SITES) > 1 else \
        f"site {SITES[0]['SiteName']} only (single-site file - loads and needs credentials for this replica only)"
    model = model.replace("model Model\n", f"/// WH Hypercare KPI - {scope}. See README.md\nmodel Model\n", 1)
    (defn / "model.tmdl").write_text(model, encoding="utf-8")
    (out_sm / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    nai = copilot_ai.apply_pbip(out_sm, SITES)
    print(f"   Copilot AI instructions: {nai} / {copilot_ai.LIMIT} characters (config/copilot_instructions.md) in culture {copilot_ai.CULTURE}")
    return report, nmeas, nrel, ncol, unmatched


def build_all(out=None, base=PRODUCT):
    """One PBIP for the sites currently in SITES (set_sites)."""
    out = out or ROOT / "dist" / "ALL_SITES"
    out.mkdir(parents=True, exist_ok=True)
    report, nmeas, nrel, ncol, unmatched = build_model(out / f"{base}.SemanticModel")
    rep_dir = out / f"{base}.Report"
    if rep_dir.exists():
        for attempt in range(6):
            try:
                shutil.rmtree(rep_dir)
                break
            except PermissionError as e:
                print(f"   .. {rep_dir.name} locked by another process ({e.filename}); retry {attempt + 1}/5 in 5 s", flush=True)
                if attempt == 5:
                    raise SystemExit(f"!! cannot replace {rep_dir} - close the file in Power BI Desktop / Explorer and rebuild")
                time.sleep(5)
    shutil.copytree(SRC_REPORT, rep_dir)
    (rep_dir / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{base}.SemanticModel"}}}, indent=2), encoding="utf-8")
    default = next((s["SiteName"] for s in SITES if str(s.get("Is_Default")) == "1"), SITES[0]["SiteName"])
    npages = report_pages.add_pages(rep_dir / "definition", default)
    scoped = report_pages.scope_column_visuals(rep_dir / "definition", SITE_TABLES)
    if scoped:
        print(f"   column-only visuals scoped to the selected site: {len(scoped)} ({'; '.join(scoped[:6])})")
    ranged = report_pages.scope_range_visuals(rep_dir / "definition")
    hourly = report_pages.scope_hour_visuals(rep_dir / "definition")
    lp = subprocess.run([sys.executable, str(ROOT / "tools" / "layout_preview.py"), str(rep_dir / "definition"), "--out", str(ROOT.parent / "_uitest" / "layout" / out.name)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if lp.returncode:
        raise SystemExit("layout check failed (docs/LAYOUT_CHECK.md):\n" + lp.stdout[-1500:] + lp.stderr[-800:])
    print("   layout check: no overlap / off-page / tiny visual on any page (docs/LAYOUT_CHECK.md)")
    print(f"   hour-axis visuals limited to the report window (global Shift slicer): {len(hourly)}")
    if ranged:
        print(f"   truck tables limited to the Start / End date-time range: {len(ranged)}")
    report_pages.register_resources(rep_dir, ROOT)
    import model_gate
    crit, rec = model_gate.run(out / f"{base}.SemanticModel" / "definition", rep_dir / "definition", ROOT / "docs" / "MODEL_CHECK.md")
    print(f"   best-practice gate: {len(crit)} critical, {len(rec)} recommended -> docs/MODEL_CHECK.md")
    if crit:
        raise SystemExit("CRITICAL model / report findings:\n  " + "\n  ".join(crit[:30]))
    (out / f"{base}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{base}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    (out / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8")
    write_platform_files(out, base)
    return report, nmeas, npages, nrel, ncol, unmatched


def write_platform_files(out, base):
    """Fabric Git integration: every item folder needs a .platform (type, display name, logicalId). The logicalId is derived from the
    item name, so it stays the same on every rebuild - Git then updates the workspace item instead of creating a new one.
    Display name = config/build_options.csv Fabric_DisplayName (empty = the file name)."""
    import uuid
    name = OPTS.get("Fabric_DisplayName", "").strip() or base
    for kind, folder in (("SemanticModel", f"{base}.SemanticModel"), ("Report", f"{base}.Report")):
        (out / folder / ".platform").write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": name},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"prime-els-hypercare/{out.name}/{base}/{kind}"))}},
            indent=2), encoding="utf-8")


def check_tokens():
    """Every {TOKEN} used by any query must be a Cfg_Site / Cfg_Engine column or a derived token (case-sensitive, like M).
    Queries are checked after the {{BLOCKS}} from config/*.csv are expanded (stage / status / movement rules carry tokens too)."""
    known = set(read_csv("site_config.csv")[0]) | set(read_csv("engine_profiles.csv")[0]) | {"START_DT", "START_YYYYMMDD", "LTA_MAP_VALUES"} | set(INC_DEFAULTS)
    used = {}
    for f in (list((ROOT / "sql" / "extracted").glob("*.m")) + list((ROOT / "sql" / "new").glob("*.sql"))
              + list((ROOT / "sql" / "cdl").glob("*.sql"))):
        for t in re.findall(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})", expand_config_blocks(f.read_text(encoding="utf-8"))):
            used.setdefault(t, set()).add(f.stem)
    for v in [r[c] for r in read_csv("site_config.csv") + read_csv("engine_profiles.csv") for c in r if r[c]]:
        for t in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", v):
            used.setdefault(t, set()).add("config value")
    bad = {t: sorted(s) for t, s in used.items() if t not in known}
    if bad:
        raise SystemExit(f"Unknown tokens (no Cfg_Site / Cfg_Engine column): {bad}")
    return len(used)


def build_one(label, out, base, codes):
    set_sites(codes)
    report, nmeas, npages, nrel, ncol, unmatched = build_all(out, base)
    print(f"== {label} ({', '.join(s['SiteCode'] for s in SITES)}) -> {out.relative_to(ROOT)}: {len(report)} source tables x {len(SITES)} site partitions, "
          f"{len(SITE_TABLES)} site tables, {nrel} site relationships, {nmeas} KPI measures, {ncol} columns with units, {npages} new pages")
    for r in report:
        flag = "  !! BD literal left: " + ",".join(r["bd_leftovers"]) if r["bd_leftovers"] else ""
        if flag or any("WARN" in n for n in r["notes"]):
            print(f"   - {r['table']}: {'; '.join(r['notes'])}{flag}")
    missed = [f"{r['table']}: {n}" for r in report for n in r["notes"] if "extra rule not applied" in n]
    if missed:
        raise SystemExit("!! query rewrite rule(s) no longer match the source SQL (fix m_tokenizer.EXTRA): " + " | ".join(missed))
    if unmatched:
        print("   !! numeric columns without a unit rule (config/column_units.csv): " + ", ".join(unmatched))


def main(argv):
    """no argument  : dist/ALL_SITES (every site, Site slicer) + dist/<SITE>/WH Hypercare KPI - <SITE>.pbip for every site
       SITE [SITE]  : only those single-site files
       --all-only   : only dist/ALL_SITES"""
    codes = [a.upper() for a in argv if not a.startswith("--")]
    if "--service" in argv:
        global SERVICE
        SERVICE = True
        for code in codes or [r["SiteCode"] for r in read_csv("site_config.csv")]:
            build_one("SERVICE FILE (incremental refresh policy)", ROOT / "dist" / "_service" / code, f"{PRODUCT} - {code}", [code])
        set_sites(None)
        print(f"tokens check: {check_tokens()} distinct tokens, all resolvable")
        return
    if not codes:
        build_one("ALL SITES", ROOT / "dist" / "ALL_SITES", PRODUCT, None)
    if "--all-only" not in argv:
        for code in codes or [r["SiteCode"] for r in read_csv("site_config.csv")]:
            build_one("SITE FILE", ROOT / "dist" / code, f"{PRODUCT} - {code}", [code])
    set_sites(None)
    print(f"tokens check: {check_tokens()} distinct tokens, all resolvable")


if __name__ == "__main__":
    main(sys.argv[1:])



