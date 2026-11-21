"""DAX measures - part 3: warehouse space (KPI #4), users (KPI #5), daily health checks (KPI #6)."""
from measures_core import PT, thr, rca, fill
from measures_flow import RM

LU = "'Location Utilisation'"
LA = "'Level A Available Pallet Spot'"
UA = "'User Activity'"
DH = "'Data Health'"
SP = "'Shipped Pallet'"

WAREHOUSE = [
    ("Loc Locations", "4 Warehouse", "#,##0", f'SUM({LU}[Locations])'),
    ("Loc Occupied", "4 Warehouse", "#,##0", f'SUM({LU}[Occupied_Locations])'),
    ("Loc Free", "4 Warehouse", "#,##0", '[Loc Locations] - [Loc Occupied]'),
    ("KPI Loc Util", "4 Warehouse", "0.0%", 'DIVIDE([Loc Occupied], [Loc Locations])'),
    ("Flow In Pallets Day", "4 Warehouse", "#,##0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({SP}[LTA Pallet]) + SUM({SP}[Received Pallet]), {RM}, REMOVEFILTERS({SP}), {SP}[shift_date] = d)'),
    ("Flow Out Pallets Day", "4 Warehouse", "#,##0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({SP}[Total Shipped Pallet]), {RM}, REMOVEFILTERS({SP}), {SP}[shift_date] = d)'),
    ("Flow Net Per Hour", "4 Warehouse", "+0.0;-0.0;0.0",
     'DIVIDE(COALESCE([Flow In Pallets Day], 0) - COALESCE([Flow Out Pallets Day], 0), [Elapsed Hours])'),
    ("KPI Loc Util Predicted", "4 Warehouse", "0.0%",
     '-- + PRED_HORIZON_H hours at the current net in-minus-out pallet rate; 1 pallet ~ 1 location\n'
     'VAR occ = [Loc Occupied] + ' + thr("PRED_HORIZON_H") + ' * COALESCE([Flow Net Per Hour], 0)\n'
     'RETURN IF(ISBLANK([Loc Locations]), BLANK(), MIN(1, MAX(0, DIVIDE(occ, [Loc Locations]))))'),
    ("Space Runway Hours", "4 Warehouse", "0.0",
     f'VAR r = [Flow Net Per Hour]\nVAR critOcc = [Loc Locations] * {thr("LOC_UTIL", "Crit_At")}\n'
     'RETURN IF(r > 0, MAX(0, DIVIDE(critOcc - [Loc Occupied], r)))'),
    ("LevelA Locations", "4 Warehouse\\Level A", "#,##0", f'CALCULATE(SUM({LU}[Locations]), {LU}[Level_Class] = "Level A")'),
    ("KPI Free Short", "4 Warehouse\\Level A", "0", f'IF([Feature LevelA] = 1, SUM({LA}[pallet_spots_height_150_or_less]) + 0)'),
    ("KPI Free Tall", "4 Warehouse\\Level A", "0", f'IF([Feature LevelA] = 1, SUM({LA}[pallet_spots_height_over_150]) + 0)'),
    ("LevelA Free Spots", "4 Warehouse\\Level A", "0", f'SUM({LA}[pallet_spots])'),
    ("KPI LevelA Util", "4 Warehouse\\Level A", "0.0%",
     '-- occupied / total Level A locations, both from the same locmst snapshot (spots and locations are different units)\n'
     f'IF([Feature LevelA] = 1 && [LevelA Locations] > 0, DIVIDE(CALCULATE(SUM({LU}[Occupied_Locations]), {LU}[Level_Class] = "Level A"), [LevelA Locations]))'),
    ("LevelA In Day", "4 Warehouse\\Level A", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(SUM('Pallet From LTA To Level A'[PALLETS]), REMOVEFILTERS('Pallet From LTA To Level A'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Pallet From LTA To Level A'[LEVEL_TYPE] = \"LEVEL_A\", 'Pallet From LTA To Level A'[Day] = d)"),
    ("LevelA Other Day", "4 Warehouse\\Level A", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(SUM('Pallet From LTA To Level A'[PALLETS]), REMOVEFILTERS('Pallet From LTA To Level A'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Pallet From LTA To Level A'[LEVEL_TYPE] = \"LEVEL_OTHER\", 'Pallet From LTA To Level A'[Day] = d)"),
    ("KPI LevelA Util Predicted", "4 Warehouse\\Level A", "0.0%",
     'VAR r = DIVIDE(COALESCE([LevelA In Day], 0) - COALESCE([Out Alloc LevelA], 0), [Elapsed Hours])\n'
     'RETURN IF([Feature LevelA] = 1 && [LevelA Locations] > 0, MIN(1, MAX(0, 1 - DIVIDE([LevelA Free Spots] - ' + thr('PRED_HORIZON_H') + ' * r, [LevelA Locations]))))'),
    ("KPI Store A Split", "4 Warehouse\\Level A", "0%",
     'IF([Feature LevelA] = 1, DIVIDE([LevelA In Day], [LevelA In Day] + [LevelA Other Day]))'),
    ("KPI Idle A", "4 Warehouse\\Level A", "0%",
     "IF([Feature LevelA] = 1, DIVIDE(DISTINCTCOUNT('Pallet in Level A not active shipment'[Location]), [LevelA Locations]))"),
    ("LevelA Idle Locations", "4 Warehouse\\Level A", "0", "DISTINCTCOUNT('Pallet in Level A not active shipment'[Location])"),
    ("KPI HOFF In", "4 Warehouse", "0",
     "IF([Feature HOFF] = 1, CALCULATE(DISTINCTCOUNT('Pallet From HOFFIN'[lodnum]), 'Pallet From HOFFIN'[metric_type] IN {\"HOFF_IN_FG\", \"HOFF_IN_PM\"}) + 0)"),
    ("KPI LTA Queue", "4 Warehouse", "0",
     "IF([Feature Production] = 1, DISTINCTCOUNT('Pallet from LTA to short/tall location'[lodnum]) + 0)"),
    ("KPI Imbalance", "4 Warehouse", "0%",
     'VAR i = [Prod Pallets Day]\nVAR o = [Out Alloc LevelA] + [Out Alloc Other]\nRETURN IF([Feature LevelA] = 1 && i > 0, DIVIDE(ABS(i - o), i))'),
]

USERS = [
    # report day = shift day (Shift_Date); a pallet counts once per user-hour (Pallets_User_Hour) - reconciled with
    # sql/reference/USER_PROD.sql / ACTIVE_USERS.sql by tools/reconcile_kpis.py
    ("User Pallets Moved", "5 Users", "#,##0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({UA}[Pallets_User_Hour]), {UA}[Shift_Date] = d)'),
    ("User Transactions", "5 Users", "#,##0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({UA}[Transactions]), {UA}[Shift_Date] = d)'),
    ("KPI Active Users", "5 Users", "0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(DISTINCTCOUNT({UA}[User_Id]), {UA}[Shift_Date] = d) + 0'),
    ("User Active Hours", "5 Users", "#,##0",
     f'VAR d = [Report Date]\nRETURN COUNTROWS(CALCULATETABLE(SUMMARIZE({UA}, {UA}[User_Id], {UA}[Activity_Date], {UA}[Activity_Hour]), {UA}[Shift_Date] = d))'),
    ("KPI User Productivity", "5 Users", "0.0", 'DIVIDE([User Pallets Moved], [User Active Hours])'),
    ("User Productivity 7d", "5 Users", "0.0",
     f'VAR d = [Report Date]\nVAR fd = ' + thr('FORECAST_DAYS') + f'\nVAR p = CALCULATE(SUM({UA}[Pallets_User_Hour]), {UA}[Shift_Date] > d - fd, {UA}[Shift_Date] <= d)\n'
     f'VAR h = COUNTROWS(CALCULATETABLE(SUMMARIZE({UA}, {UA}[User_Id], {UA}[Activity_Date], {UA}[Activity_Hour]), {UA}[Shift_Date] > d - fd, {UA}[Shift_Date] <= d))\n'
     'RETURN DIVIDE(p, h)'),
    ("User Status", "5 Users", None,
     f'VAR a = [KPI User Productivity]\nRETURN IF(ISBLANK(a), BLANK(), IF(a < {thr("USER_PROD", "Crit_At")}, "CRITICAL", '
     f'IF(a < {thr("USER_PROD", "Warn_At")}, "WARNING", "OK")))'),
]


def _hc(key, expr):
    return f'"{key}", {expr}'


def site_all(t):
    """All rows of a site table for the site picked in the slicer (build_pbip.site_safe adds the site filter after REMOVEFILTERS)."""
    return f"CALCULATETABLE({t}, REMOVEFILTERS({t}))"


NOT_LIVE_DAYS = 3     # under 72 h of transactions = not live (tools/site_config_check.py, hypercare-site-setup skill)
_NUM = 'IF({v} = INT({v}), FORMAT({v}, "#,##0"), FORMAT({v}, "#,##0.##"))'   # "#,##0.##" alone prints "0." for whole numbers

HEALTH = [
    ("Data Last Txn", "6 Health", "yyyy-mm-dd hh:nn", f'CALCULATE(MAX({DH}[Last_Event_Local]), {DH}[Source_Object] = "dlytrn")'),
    ("Replica First Txn", "6 Health", "yyyy-mm-dd hh:nn",
     f'-- oldest transaction the replica still holds for the site (retention differs per site)\nCALCULATE(MIN({DH}[First_Event_Local]), {DH}[Source_Object] = "dlytrn")'),
    ("Replica History Days", "6 Health", "0", 'IF(ISBLANK([Replica First Txn]), BLANK(), INT([Data Last Txn]) - INT([Replica First Txn]))'),
    ("Report Day In Replica", "6 Health", None,
     'VAR f = [Replica First Txn]\nRETURN ISBLANK(f) || [Report Date] >= INT(f)'),
    ("Data Snapshot UTC", "6 Health", "yyyy-mm-dd hh:nn", f'MAX({DH}[Db_Utc_Now])'),
    ("KPI Data Lag Min", "6 Health", "0",
     '-- replica lag at refresh time = site-local DB clock - newest dlytrn row (both site-local)\n'
     'VAR snapLocal = [Data Snapshot UTC] + [Site UTC Offset h] / 24\n'
     'RETURN IF(ISBLANK([Data Last Txn]), BLANK(), MAX(0, (snapLocal - [Data Last Txn]) * 1440))'),
    ("KPI Refresh Age h", "6 Health", "0.0", 'IF(ISBLANK([Data Snapshot UTC]), BLANK(), MAX(0, (UTCNOW() - [Data Snapshot UTC]) * 24))'),
    ("Health Check Value", "6 Health", "#,##0.##",
     'VAR k = SELECTEDVALUE(Cfg_HealthCheck[Check_Key])\nVAR d = [Report Date]\n'
     f'VAR L = {thr("LOOKBACK")}\n'
     'RETURN SWITCH(k,\n'
     '    ' + _hc("H_DATA_LAG", "[KPI Data Lag Min]") + ',\n'
     '    ' + _hc("H_REFRESH_AGE", "[KPI Refresh Age h]") + ',\n'
     '    ' + _hc("H_TTAT_ROWS", 'VAR t0 = [Site Now] - ' + thr("FORECAST_DAYS") + ' RETURN CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Check-in] >= t0) + 0') + ',\n'
     '    ' + _hc("H_LOC_ROWS", f"CALCULATE(SUM({LU}[Locations]), REMOVEFILTERS({LU})) + 0") + ',\n'
     '    ' + _hc("H_USER_ROWS", f"COUNTROWS({site_all(UA)}) + 0") + ',\n'
     '    ' + _hc("H_PROD_ROWS", f"CALCULATE(SUM({PT}[PalletsLeftFromLine]), {RM}, REMOVEFILTERS({PT}), {PT}[shift_date] >= d - L) + 0") + ',\n'
     '    ' + _hc("H_NEG_TTAT", f"COUNTROWS(FILTER({site_all('TTAT')}, TTAT[TTAT (Minutes)] < 0)) + 0") + ',\n'
     '    ' + _hc("H_GR_GT_TTAT", f'COUNTROWS(FILTER({site_all("TTAT")}, TTAT[Direction] = "Inbound" && TTAT[Loading/GR Time (Minutes)] > TTAT[TTAT (Minutes)])) + 0') + ',\n'
     '    ' + _hc("H_NEG_PALLETS", f"COUNTROWS(FILTER({site_all(PT)}, {PT}[PalletsLeftFromLine] < 0)) + 0") + ',\n'
     '    ' + _hc("H_BLANK_DATES", f"COUNTROWS(FILTER({site_all(PT)}, ISBLANK({PT}[ReportDate]))) + 0") + ',\n'
     '    ' + _hc("H_BAD_HOURS", f"COUNTROWS(FILTER({site_all(PT)}, VAR h = IFERROR(VALUE({PT}[ReportHour]), -1) RETURN h < 0 || h > 23)) + 0") + ',\n'
     '    ' + _hc("H_UNMAPPED_LINES", f'CALCULATE(DISTINCTCOUNT({PT}[WORKSTATION_LTA]), {RM}, REMOVEFILTERS({PT}), {PT}[PRODUCT_LINE] = "UNMAPPED", {PT}[shift_date] >= d - L) + 0') + ',\n'
     '    ' + _hc("H_SITE_FOUND", "COUNTROWS(VALUES(Cfg_Site[SiteCode])) + 0") + ',\n'
     '    ' + _hc("H_THRESHOLDS", "CALCULATE(COUNTROWS(Cfg_Threshold), REMOVEFILTERS(Cfg_Threshold)) + 0") + ',\n'
     '    ' + _hc("H_SITE_LOADED", f"COUNTROWS({DH}) + 0") + ',\n'
     '    ' + _hc("H_HISTORY_DAYS", "[Replica History Days]") + ',\n'
     '    ' + _hc("H_LINEMAP_ROWS", "COUNTROWS(Cfg_LineMap) + 0") + ',\n'
     '    ' + _hc("H_PROD_LAG", "IF([Report Is Today] && NOT ISBLANK([Prod Last Hour Sort]), MAX(0, [Win Off Start h] + [Elapsed Hours] - ([Prod Last Hour Sort] + 1)))") + ',\n'
     '    ' + _hc("H_OUT_TTAT_ROWS", 'VAR t0 = [Site Now] - ' + thr("FORECAST_DAYS") + ' RETURN CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "Outbound", TTAT[Close] >= t0) + 0') + ',\n'
     '    ' + _hc("H_FEED_SAME_DAY", 'VAR i = CALCULATE(MAX(TTAT[Dispatch]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "Inbound")\n'
     '        VAR o = CALCULATE(MAX(TTAT[Close]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "Outbound")\n'
     '        RETURN IF(ISBLANK(i) || ISBLANK(o), BLANK(), ABS(INT(i) - INT(o)))') + ',\n'
     '    BLANK())'),
    ("Health Check Applicable", "6 Health", None,
     'VAR req = SELECTEDVALUE(Cfg_HealthCheck[Requires])\n'
     'RETURN SWITCH(req, "Has_Production", [Feature Production] = 1, "Has_LevelA", [Feature LevelA] = 1, "Has_HOFF", [Feature HOFF] = 1, TRUE())'),
    ("Health Check Status", "6 Health", None,
     'VAR v = [Health Check Value]\nVAR op = SELECTEDVALUE(Cfg_HealthCheck[Operator])\nVAR e = SELECTEDVALUE(Cfg_HealthCheck[Expected])\n'
     'VAR raw = SWITCH(TRUE(), ISBLANK(SELECTEDVALUE(Cfg_HealthCheck[Check_Key])), BLANK(), NOT [Health Check Applicable], "N/A", ISBLANK(v), "NO DATA",\n'
     '    op = "<=", IF(v <= e, "PASS", "FAIL"), op = ">=", IF(v >= e, "PASS", "FAIL"), op = "=", IF(v = e, "PASS", "FAIL"), "N/A")\n'
     '-- a warehouse that is not live yet has no activity: its activity checks wait for go-live instead of failing (nothing to fix)\n'
     'RETURN IF(raw IN {"FAIL", "NO DATA"} && [Health Site Not Live] && SELECTEDVALUE(Cfg_HealthCheck[Needs_Activity]) = 1, "NOT LIVE", raw)'),
    ("Health Site Not Live", "6 Health", None,
     f'-- same rule as tools/site_config_check.py: under {NOT_LIVE_DAYS} days of transactions in the replica = the warehouse is not live yet\n'
     'VAR l = [Data Last Txn]\nRETURN COUNTROWS(' + DH + f') > 0 && (ISBLANK(l) || [Replica History Days] < {NOT_LIVE_DAYS})'),
    ("Health Not Live Checks", "6 Health", "0",
     'SUMX(ALL(Cfg_HealthCheck), IF([Health Check Status] = "NOT LIVE", 1, 0))'),
    ("Health Check Status Icon", "6 Health", None,
     'VAR s = [Health Check Status]\nRETURN SWITCH(s, "PASS", "✅ PASS", "FAIL", "❌ FAIL", "NOT LIVE", "⏳ NOT LIVE", "NO DATA", "⚪ NO DATA", s)'),
    ("Health Verdict", "6 Health", None,
     '-- ONE cause for the page (first match): refresh failed > site not loaded > site not live > replica behind > single checks\n'
     'VAR f = [KPI Health Fails]\nVAR r = [Health Checks Run]\nVAR w = [Health Not Live Checks]\n'
     'VAR refreshBad = CALCULATE([Health Check Status], Cfg_HealthCheck[Check_Key] = "H_REFRESH_AGE") = "FAIL"\n'
     'VAR notLoaded = CALCULATE([Health Check Status], Cfg_HealthCheck[Check_Key] = "H_SITE_LOADED") = "FAIL"\n'
     'VAR lagBad = CALCULATE([Health Check Status], Cfg_HealthCheck[Check_Key] = "H_DATA_LAG") = "FAIL"\n'
     'VAR last = FORMAT([Data Last Txn], "dd-mmm hh:nn")\n'
     'RETURN SWITCH(TRUE(),\n'
     '    refreshBad, ' + fill(rca("NARRATIVE", '"HEALTH_V_REFRESH"'), {"age": 'FORMAT([KPI Refresh Age h], "0")'}) + ',\n'
     '    notLoaded, ' + rca("NARRATIVE", '"HEALTH_V_NOTLOADED"') + ',\n'
     '    [Health Site Not Live], ' + fill(rca("NARRATIVE", '"HEALTH_V_NOTLIVE"'),
                                       {"days": 'FORMAT(COALESCE([Replica History Days], 0), "0")', "last": 'COALESCE(last, "none")', "wait": 'FORMAT(w, "0")',
                                        "fail": 'FORMAT(f, "0")'}) + ',\n'
     '    lagBad, ' + fill(rca("NARRATIVE", '"HEALTH_V_LAG"'), {"lag": 'FORMAT([KPI Data Lag Min], "#,##0")'}) + ',\n'
     '    f > 0, ' + fill(rca("NARRATIVE", '"HEALTH_V_OTHER"'), {"fail": 'FORMAT(f, "0")'}) + ',\n'
     '    ' + fill(rca("NARRATIVE", '"HEALTH_V_OK"'), {"run": 'FORMAT(r, "0")'}) + ')'),
    ("KPI Health Fails", "6 Health", "0",
     'SUMX(ALL(Cfg_HealthCheck), IF([Health Check Status] = "FAIL", 1, 0))'),
    ("Health Checks Run", "6 Health", "0",
     'SUMX(ALL(Cfg_HealthCheck), IF([Health Check Status] IN {"PASS", "FAIL"}, 1, 0))'),
    ("Health Check Value Text", "6 Health", None,
     'VAR v = [Health Check Value]\nRETURN IF(ISBLANK(v), "-", ' + _NUM.format(v="v") + ' & " " & SELECTEDVALUE(Cfg_HealthCheck[Unit]))'),
    ("Health Check Rule", "6 Health", None,
     'VAR e = SELECTEDVALUE(Cfg_HealthCheck[Expected])\n'
     'RETURN IF(HASONEVALUE(Cfg_HealthCheck[Check_Key]), SELECTEDVALUE(Cfg_HealthCheck[Operator]) & " " & ' + _NUM.format(v="e") +
     ' & " " & SELECTEDVALUE(Cfg_HealthCheck[Unit]))'),
    ("Health Banner", "6 Health", None,
     'VAR f = [KPI Health Fails]\nVAR r = [Health Checks Run]\nVAR w = [Health Not Live Checks]\nRETURN SWITCH(TRUE(), f > 0, "❌ " & ' +
     fill(rca("NARRATIVE", '"HEALTH_FAIL"'), {"fail": "f", "run": "r"}) + ', w > 0, "⏳ " & ' +
     fill(rca("NARRATIVE", '"HEALTH_NOTLIVE"'), {"wait": "w", "run": "r"}) + ', "✅ " & ' + fill(rca("NARRATIVE", '"HEALTH_OK"'), {"run": "r"}) + ')'),
]


# ---------------- generic hour-by-hour report (Excel HOURLY_ALERT without the LTA dependency) - use with DimHour on rows
_HV = ('VAR d = [Report Date]\nVAR h = IF([Hour In Window] = 1, SELECTEDVALUE(DimHour[Hour]))\nVAR cd = IF(h >= [Site Shift1 Start h], d, d + 1)\n'
       '-- hour position in the SITE\'s shift day (DimHour[Hour Sort] follows the default site only)\n'
       'VAR done = NOT ISBLANK(h) && MOD(h - [Site Shift1 Start h], 24) < [Prod Completed Hours]\n')
_THR_IN = thr("TTAT_IN", "Crit_At")
_THR_OUT = thr("TTAT_OUT", "Crit_At")


def _truck_ttat(direction, col):
    return (_HV + 'VAR t0 = cd + h / 24\n'
            f'RETURN IF(done, AVERAGEX(CALCULATETABLE(VALUES(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "{direction}", '
            f'TTAT[{col}] >= t0, TTAT[{col}] < t0 + 1 / 24), CALCULATE(MAX(TTAT[TTAT (Minutes)]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "{direction}")))')


HOURLY = [
    ("Hour Pallets Moved", "8 Hourly", "#,##0",
     _HV + f'RETURN IF(done, COALESCE(CALCULATE(SUM({UA}[Pallets_User_Hour]), REMOVEFILTERS({UA}), {UA}[Activity_Date] = cd, {UA}[Activity_Hour] = h), 0))'),
    ("Hour Moves Baseline", "8 Hourly", "0.0",
     _HV + f'VAR L = {thr("LOOKBACK")}\nRETURN IF(NOT ISBLANK(h), DIVIDE(CALCULATE(SUM({UA}[Pallets_User_Hour]), REMOVEFILTERS({UA}), {UA}[Activity_Date] >= cd - L, '
     f'{UA}[Activity_Date] < cd, {UA}[Activity_Hour] = h), L))'),
    ("Hour Moves vs Baseline", "8 Hourly", "+0%;-0%;0%",
     'VAR b = [Hour Moves Baseline]\nRETURN IF(NOT ISBLANK([Hour Pallets Moved]) && b > 0, DIVIDE([Hour Pallets Moved], b) - 1)'),
    ("Hour Active Users", "8 Hourly", "0",
     _HV + f'RETURN IF(done, CALCULATE(DISTINCTCOUNT({UA}[User_Id]), REMOVEFILTERS({UA}), {UA}[Activity_Date] = cd, {UA}[Activity_Hour] = h) + 0)'),
    ("Hour Inbound TTAT", "8 Hourly", "0", _truck_ttat("Inbound", "Check-in")),
    ("Hour Outbound TTAT", "8 Hourly", "0", _truck_ttat("Outbound", "Close")),
    # completion basis = the trucks of the TTAT KPIs and of 'Where the truck time goes' (inbound at dispatch, outbound at close);
    # Hour Inbound Trucks / TTAT above count ARRIVALS (check-in), so a truck that waited overnight never showed on its KPI day
    ("Hour Inbound Done", "8 Hourly", "0",
     _HV + 'VAR t0 = cd + h / 24\n'
     'RETURN CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), '
     'TTAT[Direction] = "Inbound", TTAT[Dispatch] >= t0, TTAT[Dispatch] < t0 + 1 / 24)'),
    ("Hour Inbound Done TTAT", "8 Hourly", "0", _truck_ttat("Inbound", "Dispatch")),
    ("Hour Status", "8 Hourly", None,
     '-- hours outside the report window (global Shift slicer) stop here - the hourly chain is not evaluated for them\n'
     'IF([Hour In Window] <> 1, "",\nVAR p = [Hour Pallets Moved]\nVAR b = [Hour Moves Baseline]\nVAR mb = ' + thr("MIN_BASE") + '\nVAR r = DIVIDE(p, b)\n'
     'RETURN SWITCH(TRUE(), ISBLANK(p), "", b >= mb && p = 0, "NO MOVEMENT", b >= mb && r < ' + thr("HOUR_VS_BASE", "Crit_At") + ', "CRITICAL", '
     'b >= mb && r < ' + thr("HOUR_VS_BASE", "Warn_At") + ', "WARNING", "OK"))'),
    ("Hour Status Label", "8 Hourly", None,
     'VAR s = [Hour Status]\nRETURN SWITCH(s, "NO MOVEMENT", "⛔ NO MOVEMENT", "CRITICAL", "🔴 CRITICAL", "WARNING", "🟠 WARNING", "OK", "🟢 OK", "")'),
    ("Hour Status Color", "8 Hourly", None,
     'SWITCH([Hour Status], "NO MOVEMENT", "#D13438", "CRITICAL", "#D13438", "WARNING", "#F7A600", "OK", "#107C10", "#8A8886")'),
    ("Hour Verdict Key", "8 Hourly", None,
     'IF([Hour In Window] <> 1, "",\nVAR p = [Hour Pallets Moved]\nVAR inT = [Hour Inbound Trucks]\nVAR outT = [Hour Outbound Loads]\nVAR st = [Hour Status]\n'
     'VAR prodStop = [Feature Production] = 1 && COALESCE([Hour Pallets], 0) = 0 && [Hour Baseline] >= ' + thr("MIN_BASE") + ' && outT > 0\n'
     'RETURN SWITCH(TRUE(), ISBLANK(p), "",\n'
     '    p = 0 && inT = 0 && outT = 0, "NOTHING_MOVED",\n    prodStop, "PROD_STOPPED_SHIPPING",\n'
     '    [Hour Inbound TTAT] > ' + _THR_IN + ', "IN_TTAT_HIGH",\n    [Hour Outbound TTAT] > ' + _THR_OUT + ', "OUT_TTAT_HIGH",\n'
     '    st = "OK", "ALL_NORMAL", st = "NO MOVEMENT", "NO_MOVEMENT", "BELOW_BASE"))'),
    ("Hour Verdict", "8 Hourly", None,
     '-- inside the report window the verdict does not depend on the shift: evaluated without the Cfg_Shift filter (about 5x faster)\n'
     'IF([Hour In Window] <> 1, "", CALCULATE(\nVAR k = [Hour Verdict Key]\nRETURN IF(k = "", "", ' +
     fill(rca("HOURLY", "k"), {"in_ttat": 'FORMAT([Hour Inbound TTAT], "0")', "out_ttat": 'FORMAT([Hour Outbound TTAT], "0")',
                               "base": 'FORMAT([Hour Moves Baseline], "0")', "pct": 'FORMAT(-[Hour Moves vs Baseline], "0%")'}) + '), REMOVEFILTERS(Cfg_Shift)))'),
    ("Hourly Scan Summary", "8 Hourly", None,
     'VAR T = ADDCOLUMNS(FILTER(ALL(DimHour[Hour], DimHour[Hour Sort], DimHour[Hour Label]), NOT ISBLANK(DimHour[Hour])), "@s", CALCULATE([Hour Status]))\n'
     'VAR crit = COUNTROWS(FILTER(T, [@s] = "CRITICAL"))\nVAR warn = COUNTROWS(FILTER(T, [@s] = "WARNING"))\n'
     'VAR idle = COUNTROWS(FILTER(T, [@s] = "NO MOVEMENT"))\nVAR done = COUNTROWS(FILTER(T, [@s] <> ""))\nRETURN ' +
     fill(rca("NARRATIVE", '"HOURLY_SCAN"'), {"crit": "crit + 0", "warn": "warn + 0", "idle": "idle + 0", "done": "done + 0"})),
]
