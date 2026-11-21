"""DAX measures - part 2: line RCA, inbound, outbound, warehouse, users, health."""
from measures_core import PT, thr, rca, fill

RM = "REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket)"


def _line_sum(extra):
    return (f'CALCULATE(SUM({PT}[PalletsLeftFromLine]), {RM}, REMOVEFILTERS({PT}[shift_date]), '
            f'REMOVEFILTERS({PT}[ReportHour_Sort]), REMOVEFILTERS({PT}[ReportHour]), {extra})')


LINES = [
    ("Line Latest Hr Pallets", "1 Production\\Line RCA", "0",
     f'VAR d = [Report Date]\nVAR lh = [Prod Last Hour Sort]\nRETURN COALESCE({_line_sum(f"{PT}[shift_date] = d, {PT}[ReportHour_Sort] = lh")}, 0)'),
    ("Line Baseline Same Hr", "1 Production\\Line RCA", "0.0",
     f'VAR d = [Report Date]\nVAR lh = [Prod Last Hour Sort]\nVAR L = {thr("LOOKBACK")}\n'
     f'RETURN DIVIDE({_line_sum(f"{PT}[shift_date] >= d - L, {PT}[shift_date] < d, {PT}[ReportHour_Sort] = lh")}, L)'),
    ("Line Variance", "1 Production\\Line RCA", "+0%;-0%;0%",
     'VAR b = [Line Baseline Same Hr]\nRETURN IF(b > 0, DIVIDE([Line Latest Hr Pallets], b) - 1, IF([Line Latest Hr Pallets] > 0, 1, 0))'),
    ("Line Status", "1 Production\\Line RCA", None,
     f'VAR a = [Line Latest Hr Pallets]\nVAR b = [Line Baseline Same Hr]\nVAR mb = {thr("MIN_BASE")}\n'
     f'RETURN SWITCH(TRUE(), b >= mb && a = 0, "LINE DOWN", b >= mb && a < {thr("PPH", "Warn_Pct")} * b, "LOW OUTPUT", '
     f'b >= mb && a > {thr("SURGE_FACTOR")} * b, "SURGE", "NORMAL")'),
    ("Line Last Output Hour", "1 Production\\Line RCA", "0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(MAX({PT}[ReportHour_Sort]), {RM}, REMOVEFILTERS({PT}[shift_date]), REMOVEFILTERS({PT}[ReportHour_Sort]), '
     f'{PT}[shift_date] = d, {PT}[PalletsLeftFromLine] > 0)'),
    ("Line Hours Idle", "1 Production\\Line RCA", "0",
     'VAR lh = [Prod Last Hour Sort]\nVAR lo = [Line Last Output Hour]\nRETURN IF(ISBLANK(lo), lh + 1, lh - lo)'),
    ("Line Day Pallets", "1 Production\\Line RCA", "#,##0",
     f'VAR d = [Report Date]\nRETURN {_line_sum(f"{PT}[shift_date] = d")}'),
    ("Line Hour Pallets", "1 Production\\Line RCA", "#,##0",
     '-- line x hour grid (Excel LTA_MONITOR): pallets of the report shift day, the hour column of the matrix kept\n'
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({PT}[PalletsLeftFromLine]), {RM}, REMOVEFILTERS({PT}[shift_date]), {PT}[shift_date] = d)'),
    ("Line Day vs Baseline", "1 Production\\Line RCA", "+0%;-0%;0%",
     f'VAR d = [Report Date]\nVAR L = {thr("LOOKBACK")}\n'
     f'VAR avgDay = DIVIDE({_line_sum(f"{PT}[shift_date] >= d - L, {PT}[shift_date] < d")}, L)\n'
     'RETURN IF(avgDay > 0, DIVIDE(COALESCE([Line Day Pallets], 0), avgDay) - 1)'),
    ("Constraint Short Blocked", "1 Production\\Line RCA", None,
     f'[Feature LevelA] = 1 && [KPI Free Short] < {thr("MIN_SHORT")} && [KPI LTA Queue] > {thr("LTA_QUEUE")}'),
    ("Constraint LevelA Congested", "1 Production\\Line RCA", None,
     f'[Feature LevelA] = 1 && [KPI LevelA Util] > {thr("LVLA_UTIL")}'),
    ("Constraint HOFF Backlog", "1 Production\\Line RCA", None,
     f'[Feature HOFF] = 1 && [KPI HOFF In] > {thr("HOFF_IN")}'),
    ("Line RCA Key", "1 Production\\Line RCA", None,
     'VAR st = [Line Status]\nVAR idle = [Line Hours Idle]\nVAR I = ' + thr("RCA_IDLE_HOURS") + '\nRETURN SWITCH(TRUE(),\n'
     '    st = "NORMAL", "NORMAL",\n    st = "SURGE", "SURGE",\n'
     '    idle >= I && [Constraint Short Blocked], "STORAGE_BLOCK",\n'
     '    idle >= I && [Constraint LevelA Congested], "LVLA_CONGESTED",\n'
     '    idle >= I && [Constraint HOFF Backlog], "HOFF_BACKLOG",\n'
     '    idle >= I, "EXT_STOP",\n'
     '    st = "LINE DOWN" && [KPI LTA Queue] > ' + thr("LTA_QUEUE") + ', "SHORT_STOP_QUEUE",\n'
     '    st = "LINE DOWN", "SHORT_STOP",\n    st = "LOW OUTPUT", "LOW_OUTPUT", "NORMAL")'),
    ("Line Root Cause", "1 Production\\Line RCA", None,
     'VAR t = ' + rca("LINE_RCA", "[Line RCA Key]") + '\nRETURN ' +
     fill("t", {"idle": 'FORMAT([Line Hours Idle], "0")', "free_short": 'FORMAT([KPI Free Short], "0")', "queue": 'FORMAT([KPI LTA Queue], "0")',
                "lvla_util": 'FORMAT([KPI LevelA Util], "0.0%")', "hoff": 'FORMAT([KPI HOFF In], "0")',
                "warn_pct": 'FORMAT(' + thr("PPH", "Warn_Pct") + ', "0%")'})),
    ("Line Action", "1 Production\\Line RCA", None, rca("LINE_RCA", "[Line RCA Key]", "Action")),
    ("KPI Lines In Alert", "1 Production", "0",
     f'VAR d = [Report Date]\nVAR L = {thr("LOOKBACK")}\n'
     f'VAR lines = CALCULATETABLE(VALUES({PT}[WORKSTATION_LTA]), {RM}, REMOVEFILTERS({PT}), {PT}[shift_date] >= d - L, {PT}[shift_date] <= d)\n'
     'RETURN IF([Feature Production] = 1, COUNTROWS(FILTER(lines, [Line Status] <> "NORMAL")) + 0)'),
]


SHIFT_DAY = 'VAR d = [Report Date]\nVAR s0 = [Win Start]\nVAR e0 = s0 + [Win Days]\n'     # report window [s0, e0) = shift day or the selected shift
_DT = {"Dispatch Date": "Dispatch", "Close Date": "Close"}


def _trucks(direction, datecol):
    """Trucks whose dispatch / close TIME falls in the shift day (not the calendar date) - reconciled by tools/reconcile_kpis.py."""
    c = _DT[datecol]
    return (f'CALCULATETABLE(VALUES(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "{direction}", TTAT[{c}] >= s0, TTAT[{c}] < e0)')


def _per_truck(col, direction):
    return f'CALCULATE(MAX(TTAT[{col}]), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "{direction}")'


def _ttat_forecast(direction, datecol, col):
    return (
        'VAR d = [Report Date]\nVAR fd = ' + thr('FORECAST_DAYS') + '\n'
        f'VAR T = ADDCOLUMNS(CALCULATETABLE(VALUES(TTAT[{datecol}]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), TTAT[Direction] = "{direction}", '
        f'TTAT[{datecol}] > d - fd, TTAT[{datecol}] <= d),\n'
        f'    "@x", 1.0 * INT(TTAT[{datecol}]),\n'
        f'    "@y", VAR dd = TTAT[{datecol}] RETURN AVERAGEX(CALCULATETABLE(VALUES(TTAT[TrailerID]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), '
        f'TTAT[Direction] = "{direction}", TTAT[{datecol}] = dd), {_per_truck(col, direction)}))\n'
        'VAR T2 = FILTER(T, NOT ISBLANK([@y]))\n'
        'VAR n = COUNTROWS(T2)\n'
        'VAR mn = ' + thr('FORECAST_MIN_DAYS') + '\n'
        'VAR slope = IF(n >= mn, MAXX(LINESTX(T2, [@y], [@x]), [Slope1]))\nVAR icpt = IF(n >= mn, MAXX(LINESTX(T2, [@y], [@x]), [Intercept]))\n'
        '-- next-day forecast from the FORECAST_DAYS linear trend; fewer than FORECAST_MIN_DAYS days -> average\n'
        'RETURN IF(n >= mn, MAX(0, slope * (INT(d) + 1) + icpt), AVERAGEX(T2, [@y]))')


FLOWS = [
    # ---------------- INBOUND (KPI #2)
    ("Inbound Trucks", "2 Inbound", "0", SHIFT_DAY + f'RETURN COUNTROWS({_trucks("Inbound", "Dispatch Date")}) + 0'),
    ("KPI TTAT In", "2 Inbound", "0.0",
     SHIFT_DAY + f'RETURN AVERAGEX({_trucks("Inbound", "Dispatch Date")}, {_per_truck("TTAT (Minutes)", "Inbound")})'),
    ("KPI TTAT In Max", "2 Inbound", "0",
     SHIFT_DAY + f'RETURN MAXX({_trucks("Inbound", "Dispatch Date")}, {_per_truck("TTAT (Minutes)", "Inbound")})'),
    ("KPI GR Time", "2 Inbound", "0.0",
     SHIFT_DAY + f'RETURN AVERAGEX({_trucks("Inbound", "Dispatch Date")}, {_per_truck("Loading/GR Time (Minutes)", "Inbound")})'),
    ("KPI TTAT In Predicted", "2 Inbound", "0.0", _ttat_forecast("Inbound", "Dispatch Date", "TTAT (Minutes)")),
    # ---------------- OUTBOUND (KPI #3)
    ("Outbound Trucks", "3 Outbound", "0", SHIFT_DAY + f'RETURN COUNTROWS({_trucks("Outbound", "Close Date")}) + 0'),
    ("KPI TTAT Out", "3 Outbound", "0.0",
     SHIFT_DAY + f'RETURN AVERAGEX({_trucks("Outbound", "Close Date")}, {_per_truck("TTAT (Minutes)", "Outbound")})'),
    ("KPI TTAT Out Predicted", "3 Outbound", "0.0", _ttat_forecast("Outbound", "Close Date", "TTAT (Minutes)")),
    ("KPI Out Load Time", "3 Outbound", "0.0",
     SHIFT_DAY + "RETURN CALCULATE(AVERAGE('Outbound TTA'[Load Time (Minutes)]), REMOVEFILTERS('Outbound TTA'), 'Outbound TTA'[Transport Equipment Close] >= s0, 'Outbound TTA'[Transport Equipment Close] < e0)"),
    ("Outbound Loads", "3 Outbound", "0",
     SHIFT_DAY + "RETURN CALCULATE(DISTINCTCOUNT('Outbound TTA'[Load]), REMOVEFILTERS('Outbound TTA'), 'Outbound TTA'[Transport Equipment Close] >= s0, 'Outbound TTA'[Transport Equipment Close] < e0) + 0"),
    ("Outbound Pallets Shipped", "3 Outbound", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(SUM('Shipped Pallet'[Total Shipped Pallet]), " + RM +
     ", REMOVEFILTERS('Shipped Pallet'), 'Shipped Pallet'[shift_date] = d)"),
    ("Out Alloc LevelA", "3 Outbound", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(SUM('Outbound Pallet from Inv'[Allocated_Pallet_Count]), REMOVEFILTERS('Outbound Pallet from Inv'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Outbound Pallet from Inv'[Allocated_FROM] = \"LEVEL_A\", 'Outbound Pallet from Inv'[Day] = d)"),
    ("Out Alloc Other", "3 Outbound", "#,##0",
     "VAR d = [Report Date]\nRETURN CALCULATE(SUM('Outbound Pallet from Inv'[Allocated_Pallet_Count]), REMOVEFILTERS('Outbound Pallet from Inv'), REMOVEFILTERS(DimDate), REMOVEFILTERS(DimDateBucket), "
     "'Outbound Pallet from Inv'[Allocated_FROM] = \"LEVEL_OTHER\", 'Outbound Pallet from Inv'[Day] = d)"),
    ("KPI Pick A Split", "3 Outbound", "0%",
     'IF([Feature LevelA] = 1, DIVIDE([Out Alloc LevelA], [Out Alloc LevelA] + [Out Alloc Other]))'),
]

