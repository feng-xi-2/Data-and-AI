"""DAX measures - part 1: site context + production (KPI #1, Excel LTA_MONITOR / LTA_RCA / HOURLY_ALERT).

Each entry: (name, display_folder, format_string, dax_expression).
All measures live in the `_KPI` measure table; existing `_DaxMeasure` measures are untouched.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from pbi_common import read_csv  # noqa: E402

PT = "'Produced Pallet'"
SITE = "[Site Code]"

# ---- page threshold inputs (config/threshold_inputs.csv): one what-if table per KPI x level, empty box = Cfg_Threshold value
INPUT_LEVELS = [("Target", "Target"), ("Warn", "Warning at"), ("Crit", "Critical at")]
INPUTS = sorted(read_csv("threshold_inputs.csv"), key=lambda r: int(r["Order"]))
INPUT_KEYS = [r["KPI_Key"] for r in INPUTS]
_COL_LVL = {"Target": "Target", "Warn_At": "Warn", "Crit_At": "Crit"}


def input_table(key, lvl):
    return f"Input {key} {lvl}"


def lookup(key, col):
    """Saved value from Cfg_Threshold for the site picked in the Site slicer (LOOKUPVALUE ignores visual filters)."""
    return f'LOOKUPVALUE(Cfg_Threshold[{col}], Cfg_Threshold[KPI_Key], "{key}", Cfg_Threshold[SiteCode], {SITE})'


def thr(key, col="Target"):
    if key in INPUT_KEYS and col in _COL_LVL:
        return f"[Thr {key} {_COL_LVL[col]}]"
    return lookup(key, col)


def rca(typ, key_expr, col="Text"):
    """Text from Cfg_RCA; key_expr is a DAX expression (quote literals yourself)."""
    return f'LOOKUPVALUE(Cfg_RCA[{col}], Cfg_RCA[Type], "{typ}", Cfg_RCA[Key], {key_expr})'


# config/build_options.csv Include_SAP_CDL = 0: SAP pages say the SAP data is left out of the file (not that the site has none)
_OPTS = {r["Setting"]: r["Value"].strip() for r in read_csv("build_options.csv")} if (Path(__file__).resolve().parents[1] / "config" / "build_options.csv").exists() else {}
SAP_LEFT_OUT = _OPTS.get("Include_SAP_CDL", "0") != "1"
PAGE_NA_TEXT = (f'IF(na IN {{"Has_SAP_Plan", "Has_SAP_Prod"}}, {rca("NARRATIVE", chr(34) + "PAGE_NA_SAP" + chr(34))}, {rca("NARRATIVE", chr(34) + "PAGE_NA" + chr(34))})'
                if SAP_LEFT_OUT else rca("NARRATIVE", '"PAGE_NA"'))


def fill(text_expr, mapping):
    """Nested SUBSTITUTE for {placeholder} tokens in a Cfg_RCA template."""
    out = text_expr
    for k, v in mapping.items():
        out = f'SUBSTITUTE({out}, "{{{k}}}", {v})'
    return out


def site(col, default=None):
    """Column of the site picked in the Site slicer (single select, synced on every page)."""
    e = f'SELECTEDVALUE(Cfg_Site[{col}])'
    return f'COALESCE({e}, {default})' if default is not None else e


def _thr_measures():
    out = []
    for r in INPUTS:
        k, scale = r["KPI_Key"], r["Input_Scale"]
        for lvl, _ in INPUT_LEVELS:
            t = f"'{input_table(k, lvl)}'[Value]"
            div = f" / {scale}" if scale not in ("1", "") else ""
            out.append((f"Input {k} {lvl}", "0 Scorecard\\Inputs", None, f'IF(ISFILTERED({t}), SELECTEDVALUE({t}){div})'))
        out.append((f"Thr {k} Target", "0 Scorecard\\Inputs", None,
                    f'VAR inp = [Input {k} Target]\nRETURN IF(NOT ISBLANK(inp), inp, {lookup(k, "Target")})'))
        for lvl, col, pct, ab in (("Warn", "Warn_At", "Warn_Pct", "Warn_Abs"), ("Crit", "Crit_At", "Crit_Pct", "Crit_Abs")):
            out.append((f"Thr {k} {lvl}", "0 Scorecard\\Inputs", None,
                        f'-- page input wins; a new page Target re-derives the level from Cfg_Threshold {pct} (unless {ab} is set)\n'
                        f'VAR inp = [Input {k} {lvl}]\nVAR t = [Thr {k} Target]\nVAR tc = {lookup(k, "Target")}\n'
                        f'VAR saved = {lookup(k, col)}\nVAR p = {lookup(k, pct)}\nVAR a = {lookup(k, ab)}\nVAR dir = {lookup(k, "Direction")}\n'
                        f'RETURN SWITCH(TRUE(), NOT ISBLANK(inp), inp, NOT ISBLANK(a) || t = tc, saved, dir = "Higher", t * p, dir = "Lower", t * (1 + p), saved)'))
        # an empty what-if box shows the bottom of its range ("0 plt") - this card says what is actually in use, in the box's unit
        mul = f" * {scale}" if scale not in ("1", "") else ""
        fmt = r["Input_Format"]
        out.append((f"Thr {k} In Use", "0 Scorecard\\Inputs", None,
                    f'FORMAT([Thr {k} Target]{mul}, "{fmt}") & " / " & FORMAT([Thr {k} Warn]{mul}, "{fmt}") & " / " & '
                    f'FORMAT([Thr {k} Crit]{mul}, "{fmt}")'))
    for lvl, col in (("Target", "Target"), ("Warn", "Warn_At"), ("Crit", "Crit_At")):
        body = ",\n    ".join(f'"{r["KPI_Key"]}", [Thr {r["KPI_Key"]} {lvl}]' for r in INPUTS)
        out.append((f"Thr Eff {lvl}", "0 Scorecard\\Inputs", None,
                    f'-- value in use for the KPI row in context: page input (if typed) else Cfg_Threshold\n'
                    f'SWITCH(SELECTEDVALUE(Cfg_Threshold[KPI_Key]),\n    {body},\n    SELECTEDVALUE(Cfg_Threshold[{col}]))'))
    any_inp = " || ".join(f'NOT ISBLANK([Input {r["KPI_Key"]} {lvl}])' for r in INPUTS for lvl, _ in INPUT_LEVELS)
    src = ",\n    ".join('"{k}", IF({c}, "page input (not saved)", SELECTEDVALUE(Cfg_Threshold[Source]))'.format(
        k=r["KPI_Key"], c=" || ".join(f'NOT ISBLANK([Input {r["KPI_Key"]} {lvl}])' for lvl, _ in INPUT_LEVELS)) for r in INPUTS)
    out.append(("Thr Source", "0 Scorecard\\Inputs", None,
                f'IF(HASONEVALUE(Cfg_Threshold[KPI_Key]), SWITCH(SELECTEDVALUE(Cfg_Threshold[KPI_Key]),\n    {src},\n    SELECTEDVALUE(Cfg_Threshold[Source])))'))
    out.append(("Thr Inputs Active", "0 Scorecard\\Inputs", "0", f'IF({any_inp}, 1, 0)'))
    return out


CONTEXT = [
    ("Site Code", "0 Context", None, 'SELECTEDVALUE(Cfg_Site[SiteCode])'),
    ("Site Name", "0 Context", None, site("SiteName")),
    ("Site WMS", "0 Context", None, site("WMS_Version")),
    ("Site UTC Offset h", "0 Context", "0.0", site("UTC_Offset_h", 0)),
    ("Site Shift1 Start h", "0 Context", "0", site("Shift1_Start", 0)),
    ("Feature Production", "0 Context", "0", site("Has_Production", 0)),
    ("Feature LevelA", "0 Context", "0", site("Has_LevelA", 0)),
    ("Feature HOFF", "0 Context", "0", site("Has_HOFF", 0)),
    ("Feature SAP Plan", "0 Context", "0", site("Has_SAP_Plan", 0)),
    ("Feature RPM", "0 Context", "0", site("Has_RPM_Master", 0)),
    ("Dashboard Title", "0 Context", None,
     'VAR t = ' + rca("NARRATIVE", '"TITLE"') + '\nRETURN IF(ISBLANK([Site Code]), "PRIME ELS Dashboard", SUBSTITUTE(t, "{site}", [Site Name]))'),
    ("Cfg Sync Cap", "0 Context", "0.00", thr("SYNC_CAP")),
    ("Cfg Bucket Hours", "0 Context", "0", thr("BUCKET_HOURS")),
    ("Page Guide Calc", "0 Context", None, 'IF(HASONEVALUE(Cfg_PageGuide[Page_Key]), "HOW IT IS CALCULATED:  " & VALUES(Cfg_PageGuide[How_Calculated]))'),
    ("Page Guide Config", "0 Context", None, 'IF(HASONEVALUE(Cfg_PageGuide[Page_Key]), "HOW TO CONFIGURE:  " & VALUES(Cfg_PageGuide[How_To_Configure]))'),
    ("Market Color", "0 Context", None,
     "VAR g = SELECTEDVALUE('SAP Plan PO'[FG GCAS])\n"
     "VAR mk = CALCULATETABLE(VALUES('Shipping Market'[MarketCode]), 'Shipping Market'[FG GCAS] = g)\n"
     "VAR n = COUNTROWS(mk)\nVAR m = MAXX(mk, [MarketCode])\n"
     'VAR c = LOOKUPVALUE(Cfg_Market[Color], Cfg_Market[Market], m)\n'
     'RETURN SWITCH(TRUE(), ISBLANK(g) || n = 0, BLANK(), n > 1, LOOKUPVALUE(Cfg_Market[Color], Cfg_Market[Market], "*MULTI"), '
     'ISBLANK(c), LOOKUPVALUE(Cfg_Market[Color], Cfg_Market[Market], "*UNMAPPED"), c)'),
    ("Market Legend Color", "0 Context", None, 'SELECTEDVALUE(Cfg_Market[Color])'),
    ("Site Now", "0 Context", "yyyy-mm-dd hh:nn",
     'UTCNOW() + [Site UTC Offset h] / 24'),
    ("Site Shift Today", "0 Context", "yyyy-mm-dd",
     'VAR x = [Site Now] - [Site Shift1 Start h] / 24\nRETURN DATE(YEAR(x), MONTH(x), DAY(x))'),
    ("Report Date Auto", "0 Context", "yyyy-mm-dd",
     '-- default report day: today\'s shift day once it has RF pallet moves or closed / dispatched trucks; before that the latest\n'
     '-- shift day with activity (start of a shift, quiet or stopped site) - never an empty page for "today".\n'
     "-- 'Site Activity' (calculated at refresh, one row per site) keeps it cheap: [Report Date] is evaluated by every measure\n"
     'VAR t = [Site Shift Today]\nVAR code = [Site Code]\n'
     "VAR lm = LOOKUPVALUE('Site Activity'[Last_Move_Shift], 'Site Activity'[SiteCode], code)\n"
     "VAR lt = LOOKUPVALUE('Site Activity'[Last_Truck_Event], 'Site Activity'[SiteCode], code)\n"
     'VAR ltShift = IF(ISBLANK(lt), BLANK(), VAR x = lt - [Site Shift1 Start h] / 24 RETURN DATE(YEAR(x), MONTH(x), DAY(x)))\n'
     'VAR last = IF(ISBLANK(lm), ltShift, IF(ISBLANK(ltShift) || lm >= ltShift, lm, ltShift))\n'
     'RETURN IF(ISBLANK(last) || last >= t, t, last)'),
    ("Report Day Fallback", "0 Context", None,
     'NOT (ISFILTERED(DimDate[Date]) && HASONEVALUE(DimDate[Date])) && [Report Date Auto] <> [Site Shift Today]'),
    ("Report Date", "0 Context", "yyyy-mm-dd",
     '-- single date picked on any DimDate slicer wins, otherwise the site-local shift day with activity (Report Date Auto)\n'
     'IF(ISFILTERED(DimDate[Date]) && HASONEVALUE(DimDate[Date]), VALUES(DimDate[Date]), [Report Date Auto])'),
    ("Report Is Today", "0 Context", None, '[Report Date] = [Site Shift Today]'),
    # ---- report window = the shift day of [Report Date], or one shift of it when the global Shift slicer has one value
    ("Site Shift2 Start h", "0 Context", "0", site("Shift2_Start", 0)),
    ("Site Shift3 Start h", "0 Context", "0", site("Shift3_Start", 0)),
    ("Shift Selected", "0 Context", "0",
     '-- the global Shift slicer (Cfg_Shift, synced on every page); blank = whole shift day\n'
     'IF(ISFILTERED(Cfg_Shift) && HASONEVALUE(Cfg_Shift[Shift_No]), VALUES(Cfg_Shift[Shift_No]))'),
    ("Win Off Start h", "0 Context", "0.0",
     '-- hours from the shift-day start to the start of the selected shift (2-shift sites: Shift3_Start = Shift2_Start -> shift 3 is empty)\n'
     'VAR s1 = [Site Shift1 Start h]\nVAR o2 = MOD([Site Shift2 Start h] - s1, 24)\nVAR o3 = MOD([Site Shift3 Start h] - s1, 24)\n'
     'RETURN SWITCH([Shift Selected], 2, o2, 3, IF(o3 <= o2, o2, o3), 0)'),
    ("Win Off End h", "0 Context", "0.0",
     'VAR s1 = [Site Shift1 Start h]\nVAR o2 = MOD([Site Shift2 Start h] - s1, 24)\nVAR o3 = MOD([Site Shift3 Start h] - s1, 24)\n'
     'RETURN SWITCH([Shift Selected], 1, IF(o2 = 0, 24, o2), 2, IF(o3 <= o2, 24, o3), 3, IF(o3 <= o2, o2, 24), 24)'),
    ("Win Start", "0 Context", "yyyy-mm-dd hh:nn", '[Report Date] + ([Site Shift1 Start h] + [Win Off Start h]) / 24'),
    ("Win End", "0 Context", "yyyy-mm-dd hh:nn", '[Report Date] + ([Site Shift1 Start h] + [Win Off End h]) / 24'),
    ("Win Hours", "0 Context", "0.0", '[Win Off End h] - [Win Off Start h]'),
    ("Win Days", "0 Context", "0.000", 'DIVIDE([Win Hours], 24)'),
    ("Hour In Window", "0 Context", "0",
     '-- 1 when the DimHour row lies in the report window (always 1 without a shift selection)\n'
     'VAR h = SELECTEDVALUE(DimHour[Hour])\nVAR o = MOD(h - [Site Shift1 Start h], 24)\n'
     'RETURN IF(ISBLANK(h), BLANK(), IF(ISBLANK([Shift Selected]) || (o >= [Win Off Start h] && o < [Win Off End h]), 1, 0))'),
    ("Window Label", "0 Context", None,
     '-- what every page shows: day + shift window in site time (the global Day / Shift slicers)\n'
     'VAR d = [Report Date]\nVAR k = [Shift Selected]\n'
     'VAR span = FORMAT([Win Start], "hh:nn") & " - " & IF(INT([Win End]) > INT([Win Start]) && FORMAT([Win End], "hh:nn") = "00:00", "24:00", '
     'FORMAT([Win End], "hh:nn") & IF(INT([Win End]) > INT([Win Start]), " (+1 day)", ""))\n'
     'VAR dayTxt = FORMAT(d, "ddd dd-mmm-yyyy") & IF(ISFILTERED(DimDate[Date]) && HASONEVALUE(DimDate[Date]), "", " (auto: " & IF([Report Is Today], "today", "last day with activity") & ")")\n'
     'RETURN IF(ISBLANK(d), BLANK(), dayTxt & "  |  " & IF(ISBLANK(k), "whole shift day " & span, IF([Win Hours] <= 0, "shift " & k & " not worked at this site", '
     '"shift " & k & " " & span)) & " (site time)")'),
    ("Elapsed Hours", "0 Context", "0.0",
     '-- hours of the report window already passed (today) or the whole window (past days)\n'
     'VAR wh = [Win Hours]\nVAR startDt = [Win Start]\n'
     'RETURN IF(wh <= 0, BLANK(), IF([Report Is Today], MIN(wh, MAX(1 / 60, ([Site Now] - startDt) * 24)), wh))'),
    ("Page Needs Flag", "0 Context", None,
     '-- Cfg_PageGuide[Requires] of the page in context (banner / guide carry a Page_Key filter) when the selected site has it = 0\n'
     'VAR req = IF(HASONEVALUE(Cfg_PageGuide[Page_Key]), SELECTEDVALUE(Cfg_PageGuide[Requires]))\n'
     'VAR featOn = SWITCH(req, "Has_Production", [Feature Production], "Has_LevelA", [Feature LevelA], "Has_HOFF", [Feature HOFF], '
     '"Has_SAP_Plan", [Feature SAP Plan], "Has_RPM_Master", [Feature RPM], "Has_SAP_Prod", [Feature SAP Prod], 1)\nRETURN IF(NOT ISBLANK(req) && req <> "" && featOn = 0, req)'),
    # ---- production plan remark: a site / day without planned production says so instead of showing empty production visuals
    ("Prod Plan Rows Site", "1 Production\\Plan", "#,##0",
     '-- planned production of the site in the plan window: PrIME work-order plan (Planned Pallet PO) + SAP production plan\n'
     "CALCULATE(COUNTROWS('Planned Pallet PO'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket)) + "
     + ("" if SAP_LEFT_OUT else "CALCULATE(COUNTROWS('SAP Plan PO'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket)) + ") + "0"),
    ("Prod Plan Rows Day", "1 Production\\Plan", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(COUNTROWS('Planned Pallet PO'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Planned Pallet PO'[shift_date] = d)" + ("" if SAP_LEFT_OUT else " + CALCULATE(COUNTROWS('SAP Plan PO'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'SAP Plan PO'[Slot Shift Date] = d)") + " + 0"),
    ("Prod Plan Next Day", "1 Production\\Plan", "ddd dd-mmm",
     "VAR d = [Report Date]\nRETURN " + ("CALCULATE(MIN('Planned Pallet PO'[shift_date]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Planned Pallet PO'[shift_date] > d)" if SAP_LEFT_OUT else
     "MIN(CALCULATE(MIN('Planned Pallet PO'[shift_date]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Planned Pallet PO'[shift_date] > d), CALCULATE(MIN('SAP Plan PO'[Slot Shift Date]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'SAP Plan PO'[Slot Shift Date] > d))")),
    ("Prod Plan Remark", "1 Production\\Plan", None,
     '-- site without planned production (feature off, or no work order / SAP plan in the window) -> say so; planned site without a plan on\n'
     '-- the report day -> say which day is next. Blank when production is planned that day.\n'
     + ("" if SAP_LEFT_OUT else "VAR sapRx = CALCULATE(COUNTROWS('SAP Production'), REMOVEFILTERS(DimDate)) + 0\nRETURN ") +
     'IF(ISBLANK([Site Code]), BLANK(),\n'
     'IF([Feature Production] = 0 || [Prod Plan Rows Site] = 0,\n'
     '    "No production planned at " & [Site Name] & " (no PrIME work orders / production plan)"'
     + ("" if SAP_LEFT_OUT else ' & IF(sapRx > 0, " - SAP still posts finished-goods receipts: see Production SAP vs PrIME", "")') + ',\n'
     'IF([Prod Plan Rows Day] = 0, "No production planned on " & FORMAT([Report Date], "ddd dd-mmm")'
     ' & IF(NOT ISBLANK([Prod Plan Next Day]), " - next planned " & FORMAT([Prod Plan Next Day], "ddd dd-mmm"), ""))))'),
    ("Prod Plan Short", "1 Production\\Plan", None,
     'IF([Feature Production] = 0 || [Prod Plan Rows Site] = 0, "No production planned", "Production planned")'),
    ("Report Label", "0 Context", None,
     'VAR na = [Page Needs Flag]\n'
     '-- feature in words (users never see config names); production pages already carry the production plan remark\n'
     'VAR naTxt = SWITCH(na, "Has_Production", "production in PrIME", "Has_LevelA", "Level A pick faces", "Has_HOFF", "hand-off lanes", '
     '"Has_SAP_Plan", "SAP production plan", "Has_RPM_Master", "RPM material master data", "Has_SAP_Prod", "SAP production feed", "this feature")\n'
     'VAR warn = IF(NOT ISBLANK(na) && na <> "Has_Production", SUBSTITUTE(SUBSTITUTE(' + PAGE_NA_TEXT + ', "{site}", [Site Name]), "{flag}", naTxt) & "  |  ")\n'     '-- production pages and the Cockpit carry the production plan remark (config/page_guide.csv Section / key)\n'
     'VAR pk = SELECTEDVALUE(Cfg_PageGuide[Page_Key])\n'
     'VAR prodPage = SELECTEDVALUE(Cfg_PageGuide[Section]) = "3 Production & Lines" || pk = "COCKPIT"\n'
     'VAR pr = IF(prodPage, [Prod Plan Remark])\n'
     'VAR prTxt = IF(NOT ISBLANK(pr), "🏭 " & pr & "  |  ")\n'
     'RETURN IF(ISBLANK([Site Code]), ' + rca("NARRATIVE", '"NO_SITE"') + ',\n'
     'prTxt & warn & [Site WMS] & "  |  shift day " & FORMAT([Report Date], "ddd dd-mmm-yyyy") & '
     'IF([Report Day Fallback], "  |  no activity yet today - showing the last day with activity", "") & '
     'IF([Report Is Today], "  |  " & FORMAT([Elapsed Hours], "0.0") & " h elapsed", "  |  full day") & '
     'IF([Report Day In Replica], "", "  |  ⚠ replica keeps data from " & FORMAT([Replica First Txn], "dd-mmm hh:nn") & " only - this day has no data") & '
     'IF([Thr Inputs Active] = 1, "  |  page threshold inputs ON", "") & '
     'IF([Refresh Line] <> "", "  |  " & [Refresh Line], ""))'),
]


def _prod(filter_extra=""):
    # production configured for the site -> 0 pallets is a real value (line stopped), not "no data" - but only once the site has
    # produced in PrIME at all: a site whose loaded window holds no production pallet (not live yet, e.g. Jakarta ID12 20-Nov) shows
    # NO DATA instead of a CRITICAL 0 plt/h that would send the team to "escalate to production"
    return (f'VAR d = [Report Date]\nVAR p = CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), '
            f'REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}[shift_date]), {PT}[shift_date] = d{filter_extra})\n'
            f'VAR seen = CALCULATE(COUNTROWS({PT}), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}[shift_date]))\n'
            'RETURN IF([Feature Production] = 1 && seen > 0, COALESCE(p, 0))')


CONTEXT += _thr_measures()

PRODUCTION = [
    ("Prod Pallets Day", "1 Production", "#,##0", _prod()),
    ("Prod Completed Hours", "1 Production", "0",
     '-- hours of the shift day (from its start) already complete: hourly rows below this are final\n'
     'IF([Report Is Today], INT([Win Off Start h] + [Elapsed Hours]), [Win Off End h])'),
    ("Prod Last Hour Sort", "1 Production", "0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(MAX({PT}[ReportHour_Sort]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), '
     f'REMOVEFILTERS({PT}), {PT}[shift_date] = d, {PT}[PalletsLeftFromLine] > 0)'),
    ("Prod Last Pallet Time", "1 Production", "dd-mmm hh:00",
     '-- newest hour with produced pallets on or before the report day (site-local)\n'
     f'VAR d = [Report Date]\nVAR T = CALCULATETABLE(SUMMARIZE({PT}, {PT}[ReportDate], {PT}[ReportHour]), REMOVEFILTERS(DimDate), '
     f'REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}), {PT}[shift_date] <= d, {PT}[PalletsLeftFromLine] > 0)\n'
     f'RETURN MAXX(T, {PT}[ReportDate] + IFERROR(VALUE({PT}[ReportHour]), 0) / 24)'),
    ("KPI PPH", "1 Production", "0.0",
     'IF([Feature Production] = 1, DIVIDE([Prod Pallets Day], [Elapsed Hours]))'),
    ("Prod Run Rate 3h", "1 Production", "0.0",
     f'VAR d = [Report Date]\nVAR h = [Prod Completed Hours]\nVAR k = MIN({thr("RUN_RATE_HOURS")}, h)\n'
     f'RETURN IF(k <= 0, BLANK(), DIVIDE(CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), '
     f'REMOVEFILTERS({PT}), {PT}[shift_date] = d, {PT}[ReportHour_Sort] >= h - k, {PT}[ReportHour_Sort] < h), k))'),
    ("Prod Projected EOD", "1 Production", "#,##0",
     'IF([Feature Production] = 1, [Prod Pallets Day] + COALESCE([Prod Run Rate 3h], [KPI PPH]) * MAX(0, [Win Hours] - [Elapsed Hours]))'),
    ("KPI PPH Predicted", "1 Production", "0.0", 'DIVIDE([Prod Projected EOD], 24)'),
    ("Prod Ramp Plan Day", "1 Production", "#,##0", thr("RAMP_DAY_PLAN")),
    ("Prod Required Rate", "1 Production", "0.0",
     'VAR remain = [Win Hours] - [Elapsed Hours]\nRETURN IF(remain <= 0, BLANK(), DIVIDE(MAX(0, [Prod Ramp Plan Day] * [Win Hours] / 24 - [Prod Pallets Day]), remain))'),
    ("KPI Ramp Attain", "1 Production", "0%",
     'IF([Feature Production] = 1, DIVIDE([Prod Pallets Day], [Prod Ramp Plan Day] * [Elapsed Hours] / 24))'),
    ("KPI Ramp Attain Predicted", "1 Production", "0%", 'DIVIDE([Prod Projected EOD], [Prod Ramp Plan Day])'),
    ("KPI Shift Attain", "1 Production", "0%",
     'VAR s1 = [Site Shift1 Start h]\n'
     'VAR b2 = ' + site("Shift2_Start", "s1 + 8") + ' - s1\n'
     'VAR b3 = ' + site("Shift3_Start", "s1 + 16") + ' - s1\n'
     'VAR e = [Elapsed Hours]\n'
     'VAR curStart = IF(b3 > b2 && e >= b3, b3, IF(e >= b2, b2, 0))\n'
     f'VAR d = [Report Date]\n'
     f'VAR pal = CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}), '
     f'{PT}[shift_date] = d, {PT}[ReportHour_Sort] >= curStart)\n'
     f'RETURN IF([Feature Production] = 1, IF(NOT ISBLANK([Shift Selected]), DIVIDE([Prod Pallets Day], {thr("PPH")} * MAX(1 / 60, e)), '
     f'DIVIDE(pal, {thr("PPH")} * MAX(1 / 60, e - curStart))))'),
    # ---- hourly early warning (Excel HOURLY_ALERT) - use with DimHour[Hour Label] on rows
    ("Hour Pallets", "1 Production\\Hourly", "#,##0",
     f'VAR h = SELECTEDVALUE(DimHour[Hour Label])\nVAR d = [Report Date]\nRETURN CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), '
     f'REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}[shift_date]), {PT}[shift_date] = d, {PT}[ReportHour] = h)'),
    ("Hour Baseline", "1 Production\\Hourly", "0.0",
     f'VAR d = [Report Date]\nVAR L = {thr("LOOKBACK")}\nVAR h = SELECTEDVALUE(DimHour[Hour Label])\n'
     f'RETURN DIVIDE(CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}[shift_date]), '
     f'{PT}[shift_date] >= d - L, {PT}[shift_date] < d, {PT}[ReportHour] = h), L)'),
    ("Hour vs Baseline", "1 Production\\Hourly", "+0%;-0%;0%",
     'IF(ISBLANK([Hour Baseline]) || [Hour Baseline] = 0, BLANK(), DIVIDE(COALESCE([Hour Pallets], 0), [Hour Baseline]) - 1)'),
    ("Hour Inbound Trucks", "1 Production\\Hourly", "0",
     'VAR d = [Report Date]\nVAR h = IF([Hour In Window] = 1, VALUE(SELECTEDVALUE(DimHour[Hour Label])))\n'
     'VAR t0 = IF(h >= [Site Shift1 Start h], d, d + 1) + h / 24\n'
     'RETURN IF(NOT ISBLANK(h), CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "Inbound", '
     'TTAT[Check-in] >= t0, TTAT[Check-in] < t0 + 1 / 24))'),
    ("Hour Outbound Loads", "1 Production\\Hourly", "0",
     'VAR d = [Report Date]\nVAR h = IF([Hour In Window] = 1, VALUE(SELECTEDVALUE(DimHour[Hour Label])))\n'
     'VAR t0 = IF(h >= [Site Shift1 Start h], d, d + 1) + h / 24\n'
     'RETURN IF(NOT ISBLANK(h), CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "Outbound", '
     'TTAT[Close] >= t0, TTAT[Close] < t0 + 1 / 24))'),
    ("KPI Trend Hours", "1 Production", "0",
     f'VAR d = [Report Date]\nVAR lastH = [Prod Completed Hours] - 1\n'
     f'VAR T = ADDCOLUMNS(GENERATESERIES(0, MAX(0, lastH), 1), "@p", '
     f'VAR s = [Value] RETURN COALESCE(CALCULATE(SUM({PT}[PalletsLeftFromLine]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), REMOVEFILTERS({PT}), {PT}[shift_date] = d, {PT}[ReportHour_Sort] = s), 0))\n'
     f'VAR T2 = ADDCOLUMNS(T, "@prev", VAR s = [Value] RETURN MAXX(FILTER(T, [Value] = s - 1), [@p]))\n'
     f'VAR lastBreak = MAXX(FILTER(T2, [Value] >= 1 && [@p] >= [@prev]), [Value])\n'
     f'RETURN IF([Feature Production] = 1 && lastH >= 1, lastH - COALESCE(lastBreak, 0))'),
]

