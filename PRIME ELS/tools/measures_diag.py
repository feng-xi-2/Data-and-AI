"""DAX measures - part 5: process diagnosis (Process Flow, Trucks, Pallet Flow, Orders, People, SAP vs WMS production) and
previous-day / 7-day values for the cockpit tiles.

Every limit, colour band, text and action comes from config (process_stages.csv -> Cfg_Stage, time_bands.csv -> Cfg_TimeBand,
kpi_thresholds.csv -> Cfg_Threshold, rca_rules.csv -> Cfg_RCA); the measures only combine them."""
import json
from pathlib import Path

from measures_core import PT, thr, rca, fill, site, SAP_LEFT_OUT
from measures_flow import RM, SHIFT_DAY, _trucks, _per_truck
from measures_ops import UA, _HV

FI = "'Flow Items'"
SH = "Shipments"
SP = "'SAP Production'"
PM = "'Pallets Movement'"
STATUS_ICON = 'SWITCH({s}, "CRITICAL", "🔴 ", "WARNING", "🟠 ", "STALE", "🟣 ", "OK", "🟢 ", "CLEAR", "⚪ ", "N/A", "⚫ ", "")'
# colours: theme/palette.json "diagnosis" (one place for the colour segmentation of every page)
_PAL = json.load(open(Path(__file__).resolve().parents[1] / "theme" / "palette.json", encoding="utf-8"))["diagnosis"]
STATUS_COLOR = ('SWITCH({s}, ' + ", ".join(f'"{k}", "{v}"' for k, v in _PAL["status"].items() if k != "default")
                + f', "{_PAL["status"]["default"]}")')
# heat-map cell fills (light tints of the status colours, readable with black numbers)
FILL_OK, FILL_WARN, FILL_CRIT, FILL_STALE = (f'"{_PAL["fill"][k]}"' for k in ("ok", "warn", "crit", "stale"))
# items older than STALE_HOURS are stale records (inventory accuracy), not a live blockage
STALE = 'VAR st = ' + thr('STALE_HOURS') + ' * 60\n'


def dur(x):
    """minutes (a DAX variable) -> '2d 03h' / '5h 07m' / '42m'."""
    return (f'IF(ISBLANK({x}), BLANK(), IF({x} >= 1440, FORMAT(INT({x} / 1440), "0") & "d " & FORMAT(INT(MOD({x}, 1440) / 60), "00") & "h", '
            f'IF({x} >= 60, FORMAT(INT({x} / 60), "0") & "h " & FORMAT(MOD({x}, 60), "00") & "m", FORMAT({x}, "0") & "m")))')


def prev(m):
    """value of a report-day measure on the previous shift day (the measure re-reads [Report Date] from the DimDate filter)."""
    return f'VAR d = [Report Date]\nRETURN CALCULATE({m}, TREATAS({{d - 1}}, DimDate[Date]))'


def avg7(m):
    """average of a report-day measure over the FORECAST_DAYS shift days before the report day (days without data are skipped)."""
    return (f'VAR d = [Report Date]\nVAR k = {thr("FORECAST_DAYS")}\nRETURN AVERAGEX(SELECTCOLUMNS(GENERATESERIES(d - k, d - 1, 1), "@d", [Value]), '
            f'CALCULATE({m}, TREATAS({{[@d]}}, DimDate[Date])))')


CONTEXT = [
    ("Feature SAP Prod", "0 Context", "0", site("Has_SAP_Prod", 0)),
    ("SAP Plant", "0 Context", None, site("SAP_Plant")),
]

# ---------------------------------------------------------------- process flow (Cfg_Stage rows x Flow Items)
FLOW = [
    ("Orders Flow Used", "10 Process Flow", None,
     '-- shipments progress beyond Ready somewhere in the window = the site runs orders through WMS statuses\n'
     f'CALCULATE(COUNTROWS({SH}), {SH}[Stage_Key] <> "O_READY") > 0'),
    ("Stage Applicable", "10 Process Flow", "0",
     'VAR a = SELECTEDVALUE(Cfg_Stage[Applicable], 1)\nVAR obj = SELECTEDVALUE(Cfg_Stage[Object])\n'
     'RETURN IF(a = 0 || (obj = "Shipment" && NOT [Orders Flow Used]), 0, 1)'),
    ("Stage NA Reason", "10 Process Flow", None,
     'IF(SELECTEDVALUE(Cfg_Stage[Applicable], 1) = 0, SELECTEDVALUE(Cfg_Stage[NA_Reason]),\n'
     '    IF(SELECTEDVALUE(Cfg_Stage[Object]) = "Shipment" && NOT [Orders Flow Used], ' + rca("NARRATIVE", '"ORDERS_NA"') + '))'),
    ("Stage Items", "10 Process Flow", "#,##0", f'IF([Stage Applicable] = 1, COUNTROWS({FI}) + 0)'),
    ("Stage Over Warn", "10 Process Flow", "#,##0",
     STALE + f'RETURN IF([Stage Applicable] = 1, COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Warn_Min]) && {FI}[Age_Min] < st)) + 0)'),
    ("Stage Over Crit", "10 Process Flow", "#,##0",
     STALE + f'RETURN IF([Stage Applicable] = 1, COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st)) + 0)'),
    ("Stage Stale", "10 Process Flow", "#,##0",
     STALE + f'RETURN IF([Stage Applicable] = 1, COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= st)) + 0)'),
    ("Stage Oldest Min", "10 Process Flow", "#,##0",
     STALE + f'RETURN IF([Stage Applicable] = 1, MAXX(FILTER({FI}, {FI}[Age_Min] < st), {FI}[Age_Min]))'),
    ("Stage Oldest", "10 Process Flow", None, 'VAR m = [Stage Oldest Min]\nRETURN ' + dur("m")),
    ("Stage Status", "10 Process Flow", None,
     'VAR n = [Stage Items]\nVAR c = [Stage Over Crit]\nVAR w = [Stage Over Warn]\nVAR s = [Stage Stale]\n'
     'RETURN SWITCH(TRUE(), NOT HASONEVALUE(Cfg_Stage[Stage_Key]), BLANK(), [Stage Applicable] = 0, "N/A", c > 0, "CRITICAL", w > 0, "WARNING", '
     's > 0 && s = n, "STALE", n > 0, "OK", "CLEAR")'),
    ("Stage Status Label", "10 Process Flow", None, 'VAR s = [Stage Status]\nRETURN IF(ISBLANK(s), BLANK(), ' + STATUS_ICON.format(s="s") + ' & s)'),
    ("Stage Status Color", "10 Process Flow", None, 'VAR s = [Stage Status]\nRETURN ' + STATUS_COLOR.format(s="s")),
    ("Stage Limits", "10 Process Flow", None,
     'VAR w = SELECTEDVALUE(Cfg_Stage[Warn_Min])\nVAR c = SELECTEDVALUE(Cfg_Stage[Crit_Min])\n'
     'RETURN IF(NOT ISBLANK(w), "warn " & ' + dur("w") + ' & " | crit " & ' + dur("c") + ')'),
    ("Stage Action Now", "10 Process Flow", None,
     'VAR s = [Stage Status]\nVAR stl = [Stage Stale]\n'
     'VAR staleTxt = ' + fill(rca("NARRATIVE", '"STALE_ACTION"'), {"n": 'FORMAT(stl, "#,0")', "unit": "SELECTEDVALUE(Cfg_Stage[Unit])",
                                                                  "hours": 'FORMAT(' + thr("STALE_HOURS") + ', "0")'}) + '\n'
     'RETURN SWITCH(s, "CRITICAL", SELECTEDVALUE(Cfg_Stage[Action]) & " (" & SELECTEDVALUE(Cfg_Stage[Owner]) & ")" & IF(stl > 0, " | " & staleTxt),\n'
     '    "WARNING", SELECTEDVALUE(Cfg_Stage[Action]) & " (" & SELECTEDVALUE(Cfg_Stage[Owner]) & ")" & IF(stl > 0, " | " & staleTxt),\n'
     '    "STALE", staleTxt, "OK", IF(stl > 0, staleTxt), "N/A", [Stage NA Reason], BLANK())'),
    ("Flow Items Waiting", "10 Process Flow", "#,##0", f'COUNTROWS({FI}) + 0'),
    ("Flow Items Warning", "10 Process Flow", "#,##0",
     STALE + f'RETURN COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Warn_Min]) && {FI}[Age_Min] < RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st)) + 0'),
    ("Flow Items Critical", "10 Process Flow", "#,##0",
     STALE + f'RETURN COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st)) + 0'),
    ("Flow Items Stale", "10 Process Flow", "#,##0", STALE + f'RETURN COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= st)) + 0'),
    ("Flow Snapshot", "10 Process Flow", "yyyy-mm-dd hh:nn",
     "MAXX({MAX('Open Trailers'[Snapshot]), MAX(Shipments[Snapshot]), MAX('Pallets In Flow'[Snapshot])}, [Value])"),
    ("Flow Snapshot Label", "10 Process Flow", None,
     'VAR s = [Flow Snapshot]\nRETURN IF(ISBLANK(s), "No snapshot loaded yet - refresh the model", '
     '"Waiting now = snapshot " & FORMAT(s, "ddd dd-mmm hh:nn") & " (site time, last refresh). Age = time in the current stage. '
     'Colours: green below the stage warning age, amber from warning, red from critical (limits: Cfg_Stage).")'),
    ("Flow Verdict", "10 Process Flow", None,
     STALE + 'VAR used = [Orders Flow Used]\n'
     'VAR T = ADDCOLUMNS(FILTER(SUMMARIZE(Cfg_Stage, Cfg_Stage[Stage_Key], Cfg_Stage[Stage], Cfg_Stage[Unit], Cfg_Stage[Crit_Min], Cfg_Stage[Warn_Min],\n'
     '        Cfg_Stage[Action], Cfg_Stage[Owner], Cfg_Stage[Object], Cfg_Stage[Applicable]),\n'
     '        Cfg_Stage[Applicable] = 1 && (Cfg_Stage[Object] <> "Shipment" || used)),\n'
     f'    "@c", CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st))),\n'
     f'    "@w", CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Warn_Min]) && {FI}[Age_Min] < st))),\n'
     f'    "@s", CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= st))),\n'
     f'    "@o", CALCULATE(MAXX(FILTER({FI}, {FI}[Age_Min] < st), {FI}[Age_Min])))\n'
     'VAR T2 = FILTER(T, [@w] > 0)\n'
     'VAR vTop = TOPN(1, T2, [@c], DESC, [@w], DESC, [@o], DESC, Cfg_Stage[Stage_Key], ASC)\n'
     'VAR crit = MAXX(vTop, [@c]) > 0\nVAR n = MAXX(vTop, IF([@c] > 0, [@c], [@w]))\nVAR lim = MAXX(vTop, IF([@c] > 0, Cfg_Stage[Crit_Min], Cfg_Stage[Warn_Min]))\n'
     'VAR o = MAXX(vTop, [@o])\n'
     'VAR stN = SUMX(T, [@s])\nVAR stTop = MAXX(TOPN(1, FILTER(T, [@s] > 0), [@s], DESC, Cfg_Stage[Stage_Key], ASC), Cfg_Stage[Stage])\n'
     'VAR staleNote = IF(stN > 0, ' + fill(rca("NARRATIVE", '"STALE_NOTE"'), {"n": 'FORMAT(stN, "#,0")', "hours": 'FORMAT(st / 60, "0")', "stage": "stTop"}) + ')\n'
     'RETURN IF(ISEMPTY(T2), ' + rca("NARRATIVE", '"FLOW_CLEAR"') + ' & staleNote,\n    ' +
     fill(rca("NARRATIVE", '"FLOW_BLOCK"'), {"icon": 'IF(crit, "🔴", "🟠")', "stage": "MAXX(vTop, Cfg_Stage[Stage])", "n": 'FORMAT(n, "#,0")',
                                             "unit": "MAXX(vTop, Cfg_Stage[Unit])", "limit": 'IF(crit, "critical ", "warning ") & ' + dur("lim"),
                                             "oldest": dur("o"), "action": "MAXX(vTop, Cfg_Stage[Action])", "owner": "MAXX(vTop, Cfg_Stage[Owner])"}) + ' & staleNote)'),
    # ---- one waiting item (rows of the 'Stuck now' tables)
    ("Item Age Min", "10 Process Flow\\Items", "#,##0", f'MAX({FI}[Age_Min])'),
    ("Item Age", "10 Process Flow\\Items", None, 'VAR m = [Item Age Min]\nRETURN ' + dur("m")),
    ("Item Status", "10 Process Flow\\Items", None,
     STALE + f'VAR a = [Item Age Min]\nVAR w = MAXX({FI}, RELATED(Cfg_Stage[Warn_Min]))\nVAR c = MAXX({FI}, RELATED(Cfg_Stage[Crit_Min]))\n'
     'RETURN IF(ISBLANK(a), BLANK(), IF(a >= st, "STALE", IF(a >= c, "CRITICAL", IF(a >= w, "WARNING", "OK"))))'),
    ("Item Status Label", "10 Process Flow\\Items", None, 'VAR s = [Item Status]\nRETURN IF(ISBLANK(s), BLANK(), ' + STATUS_ICON.format(s="s") + ' & s)'),
    ("Item Status Color", "10 Process Flow\\Items", None, 'VAR s = [Item Status]\nRETURN ' + STATUS_COLOR.format(s="s")),
    ("Item Action", "10 Process Flow\\Items", None,
     f'VAR s = [Item Status]\nRETURN SWITCH(s, "CRITICAL", MAXX({FI}, RELATED(Cfg_Stage[Action])) & " (" & MAXX({FI}, RELATED(Cfg_Stage[Owner])) & ")",\n'
     f'    "WARNING", MAXX({FI}, RELATED(Cfg_Stage[Action])) & " (" & MAXX({FI}, RELATED(Cfg_Stage[Owner])) & ")",\n'
     '    "STALE", ' + fill(rca("NARRATIVE", '"STALE_ACTION"'), {"n": '"1"', "unit": f'MAXX({FI}, RELATED(Cfg_Stage[Unit]))', "hours": 'FORMAT(' + thr("STALE_HOURS") + ', "0")'}) + ', BLANK())'),
    ("Item Over Warn", "10 Process Flow\\Items", "0",
     '-- 1 = a LIVE item waiting longer than its stage warning age (filter of the Stuck now tables); stale records excluded\n'
     + STALE + f'VAR a = [Item Age Min]\nVAR w = MAXX({FI}, RELATED(Cfg_Stage[Warn_Min]))\nRETURN IF(NOT ISBLANK(a) && a >= w && a < st, 1, 0)'),
    ("Item Stale", "10 Process Flow\\Items", "0",
     '-- 1 = the item waits longer than STALE_HOURS (filter of the Stale records tables)\n' + STALE + 'VAR a = [Item Age Min]\nRETURN IF(NOT ISBLANK(a) && a >= st, 1, 0)'),
    # ---- heat map: Cfg_Stage[Stage] rows x Cfg_TimeBand[Band] columns
    ("Band Items", "10 Process Flow\\Heat map", "#,##0",
     f'VAR f = SELECTEDVALUE(Cfg_TimeBand[From_Min])\nVAR t = SELECTEDVALUE(Cfg_TimeBand[To_Min])\n'
     f'VAR n = IF(ISBLANK(f), COUNTROWS({FI}), COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= f && {FI}[Age_Min] < t)))\nRETURN IF(n > 0, n)'),
    ("Band Cell Color", "10 Process Flow\\Heat map", None,
     'VAR n = [Band Items]\nVAR f = SELECTEDVALUE(Cfg_TimeBand[From_Min])\nVAR t = SELECTEDVALUE(Cfg_TimeBand[To_Min])\n'
     'VAR w = SELECTEDVALUE(Cfg_Stage[Warn_Min])\nVAR c = SELECTEDVALUE(Cfg_Stage[Crit_Min])\n' + STALE +
     f'RETURN IF(ISBLANK(n) || ISBLANK(w) || ISBLANK(f), BLANK(), IF(f >= st, {FILL_STALE}, IF(f >= c, {FILL_CRIT}, IF(t > w, {FILL_WARN}, {FILL_OK}))))'),
]

# ---------------------------------------------------------------- trucks (TTAT where the time goes + live yard)
# per-truck charts (Trucks & TTAT, Process Mining Gantt) show the trucks COMPLETED in [Truck Day Start, +1 day): inbound = dispatch, outbound = close
_TRUCK_END = 'IF(TTAT[Direction] = "Inbound", TTAT[Dispatch], TTAT[Close])'
TRUCK_DAY_MEASURES = [
    ("Truck Day Start", "11 Trucks\\Gantt", "ddd dd-mmm hh:nn",
     '-- start of the shift day whose trucks the per-truck charts show: the report shift day once a truck completed in it, otherwise the\n'
     '-- latest earlier shift day with a completed truck - early in the day (or on a quiet day) the charts show the last real picture, not empty.\n'
     '-- A day picked on the Shift day slicer is kept as it is (the slicer filters the truck axis to that day)\n'
     'VAR h = [Site Shift1 Start h] / 24\nVAR off = [Win Off Start h] / 24\nVAR sR = [Win Start]\nVAR eR = sR + [Win Days]\nVAR picked = ISFILTERED(DimDate[Date]) && HASONEVALUE(DimDate[Date])\n'
     f'VAR doneT = FILTER(CALCULATETABLE(SELECTCOLUMNS(TTAT, "@end", {_TRUCK_END}), REMOVEFILTERS(TTAT), {RM}), NOT ISBLANK([@end]))\n'
     'VAR inR = COUNTROWS(FILTER(doneT, [@end] >= sR && [@end] < eR))\n'
     'VAR lastEnd = MAXX(FILTER(doneT, [@end] < sR), [@end])\n'
     'RETURN IF(ISBLANK([Report Date]), BLANK(), IF(inR > 0 || picked || ISBLANK(lastEnd), sR, INT(lastEnd - h - off) + h + off))'),
    ("Truck Day Label", "11 Trucks\\Gantt", None,
     '-- subtitle of the per-truck charts: which shift day is shown and why (distinct trucks - TTAT has several rows per truck)\n'
     'VAR s = [Truck Day Start]\nVAR sR = [Win Start]\nVAR eR = sR + [Win Days]\nVAR picked = ISFILTERED(DimDate[Date]) && HASONEVALUE(DimDate[Date])\n'
     f'VAR n = CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), {RM}, FILTER(ALL(TTAT[Direction], TTAT[Dispatch], TTAT[Close]),\n'
     '    (TTAT[Direction] = "Inbound" && TTAT[Dispatch] >= s && TTAT[Dispatch] < s + 1) || (TTAT[Direction] = "Outbound" && TTAT[Close] >= s && TTAT[Close] < s + 1))) + 0\n'
     'RETURN IF(ISBLANK(s), BLANK(), IF(n = 0,\n'
     '    IF(picked, "No truck completed in the selected shift day " & FORMAT(sR, "ddd dd-mmm") & " - clear the Shift day slicer to see the last day with completed trucks",\n'
     '        "No completed truck in the TTAT feed up to " & FORMAT(sR, "ddd dd-mmm") & " - check Config & Health (feed completeness)"),\n'
     '    IF(s = sR, FORMAT(n, "#,##0") & " trucks completed in the report shift day " & FORMAT(s, "ddd dd-mmm") & " (inbound = dispatched, outbound = closed)",\n'
     '        "No truck completed yet in the report shift day " & FORMAT(sR, "ddd dd-mmm") & " - showing " & FORMAT(s, "ddd dd-mmm") & " (" & FORMAT(n, "#,##0") & " trucks), the last shift day with completed trucks")))'),
    ("Truck Report Day Label", "11 Trucks\\Gantt", None,
     '-- subtitle of the hourly truck chart (report day = the KPI day, no fall-back): why it can be empty early in the day\n'
     'VAR sR = [Win Start]\nVAR eR = sR + [Win Days]\n'
     f'VAR n = CALCULATE(DISTINCTCOUNT(TTAT[TrailerID]), REMOVEFILTERS(TTAT), {RM}, FILTER(ALL(TTAT[Direction], TTAT[Dispatch], TTAT[Close]),\n'
     '    (TTAT[Direction] = "Inbound" && TTAT[Dispatch] >= sR && TTAT[Dispatch] < eR) || (TTAT[Direction] = "Outbound" && TTAT[Close] >= sR && TTAT[Close] < eR))) + 0\n'
     'RETURN IF(ISBLANK([Report Date]), BLANK(), IF(n = 0, "No truck completed yet in the report shift day " & FORMAT(sR, "ddd dd-mmm") & '
     '" - bars appear when trucks are dispatched (inbound) / closed (outbound); previous day: KPI strip", '
     'FORMAT(n, "#,##0") & " trucks completed in the report shift day " & FORMAT(sR, "ddd dd-mmm") & " (the KPI trucks)"))'),
]
_TRUCK_DAY = ('VAR s0 = [Truck Day Start]\nVAR e0 = s0 + [Win Days]\nVAR inDay = HASONEVALUE(TTAT[TrailerID]) && COUNTROWS(FILTER(CALCULATETABLE(TTAT, ' + RM + '),\n'
              '    (TTAT[Direction] = "Inbound" && TTAT[Dispatch] >= s0 && TTAT[Dispatch] < e0) || (TTAT[Direction] = "Outbound" && TTAT[Close] >= s0 && TTAT[Close] < e0))) > 0\n'
              f'VAR vWait = MAX(0, CALCULATE(MAX(TTAT[Scan - Checkin (Minutes)]), {RM}))\nVAR vWork = MAX(0, CALCULATE(MAX(TTAT[Loading/GR Time (Minutes)]), {RM}))\n'
              f'VAR vTot = CALCULATE(MAX(TTAT[TTAT (Minutes)]), {RM})\n')


def _band_trucks(direction, datecol):
    return ('VAR s0 = [Truck Day Start]\nVAR e0 = s0 + [Win Days]\nVAR f = SELECTEDVALUE(Cfg_TimeBand[From_Min])\nVAR t = SELECTEDVALUE(Cfg_TimeBand[To_Min])\n'
            f'RETURN IF(ISBLANK(f), BLANK(), COUNTROWS(FILTER({_trucks(direction, datecol)}, VAR x = {_per_truck("TTAT (Minutes)", direction)} RETURN x >= f && x < t)) + 0)')


TRUCKS = [
    ("Trucks On Site", "11 Trucks", "#,##0", "COUNTROWS('Open Trailers') + 0"),
    ("Trucks On Site In", "11 Trucks", "#,##0", "CALCULATE(COUNTROWS('Open Trailers'), 'Open Trailers'[Direction] = \"Inbound\") + 0"),
    ("Trucks On Site Out", "11 Trucks", "#,##0", "CALCULATE(COUNTROWS('Open Trailers'), 'Open Trailers'[Direction] = \"Outbound\") + 0"),
    ("Trucks Over Crit", "11 Trucks", "#,##0",
     STALE + f'RETURN CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st)), {FI}[Object] = "Truck") + 0'),
    ("Trucks Stale", "11 Trucks", "#,##0",
     STALE + f'RETURN CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= st)), {FI}[Object] = "Truck") + 0'),
    ("Truck Wait Min", "11 Trucks\\Per truck", "#,##0", _TRUCK_DAY + 'RETURN IF(inDay, vWait)'),
    ("Truck Work Min", "11 Trucks\\Per truck", "#,##0", _TRUCK_DAY + 'RETURN IF(inDay, vWork)'),
    ("Truck Rest Min", "11 Trucks\\Per truck", "#,##0", _TRUCK_DAY + 'RETURN IF(inDay, MAX(0, vTot - vWait - vWork))'),
    ("Truck TTAT Min", "11 Trucks\\Per truck", "#,##0", _TRUCK_DAY + 'RETURN IF(inDay, vTot)'),
    ("Band Trucks In", "11 Trucks\\Distribution", "#,##0", _band_trucks("Inbound", "Dispatch Date")),
    ("Band Trucks Out", "11 Trucks\\Distribution", "#,##0", _band_trucks("Outbound", "Close Date")),
    ("Inbound Trucks Prev", "11 Trucks\\Previous day", "#,##0", prev("[Inbound Trucks]")),
    ("Outbound Trucks Prev", "11 Trucks\\Previous day", "#,##0", prev("[Outbound Trucks]")),
    ("KPI TTAT In Prev", "11 Trucks\\Previous day", "0.0", prev("[KPI TTAT In]")),
    ("KPI TTAT Out Prev", "11 Trucks\\Previous day", "0.0", prev("[KPI TTAT Out]")),
]

# ---------------------------------------------------------------- pallet flow (User Activity by process step; Pallets Movement area to area)
PALLETS = [
    ("Moves Hour", "12 Pallet Flow", "#,##0",
     _HV + f'RETURN IF(NOT ISBLANK(h), CALCULATE(SUM({UA}[Pallets_User_Hour]), REMOVEFILTERS({UA}[Activity_Date], {UA}[Activity_Hour], {UA}[Shift_Date]), '
     f'{UA}[Activity_Date] = cd, {UA}[Activity_Hour] = h))'),
    ("Moves Day Trend", "12 Pallet Flow", "#,##0",
     f'VAR r = [Report Date]\nVAR d = SELECTEDVALUE({UA}[Shift_Date])\nVAR L = {thr("LOOKBACK")}\n'
     f'RETURN IF(NOT ISBLANK(d) && d > r - L && d <= r, SUM({UA}[Pallets_User_Hour]))'),
    ("Pallets Moved Prev", "12 Pallet Flow", "#,##0", prev("[User Pallets Moved]")),
    ("Pallets Moved Prior Avg", "12 Pallet Flow", "#,##0", avg7("[User Pallets Moved]")),
    ("Area Moves Day", "12 Pallet Flow", "#,##0",
     SHIFT_DAY + f'VAR T = FILTER(CALCULATETABLE({PM}, {RM}), {PM}[txn_time] >= s0 && {PM}[txn_time] < e0 && {PM}[from_area] <> {PM}[to_area] && NOT ISBLANK({PM}[lodnum]))\n'
     'RETURN IF(NOT ISEMPTY(T), COUNTROWS(DISTINCT(SELECTCOLUMNS(T, "@l", [lodnum]))))'),
    ("Pallets In Flow Now", "12 Pallet Flow", "#,##0", "COUNTROWS('Pallets In Flow') + 0"),
    ("Pallets Over Crit", "12 Pallet Flow", "#,##0",
     STALE + f'RETURN CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= RELATED(Cfg_Stage[Crit_Min]) && {FI}[Age_Min] < st)), {FI}[Object] = "Pallet") + 0'),
    ("Pallets Stale", "12 Pallet Flow", "#,##0",
     STALE + f'RETURN CALCULATE(COUNTROWS(FILTER({FI}, {FI}[Age_Min] >= st)), {FI}[Object] = "Pallet") + 0'),
]

# ---------------------------------------------------------------- orders / shipments
ORDERS = [
    ("Shipments Open", "13 Orders", "#,##0", f'CALCULATE(COUNTROWS({SH}), {SH}[Is_Open] = 1) + 0'),
    ("Shipments Late", "13 Orders", "#,##0", f'CALCULATE(COUNTROWS({SH}), {SH}[Is_Late] = 1) + 0'),
    ("Shipments Created Day", "13 Orders", "#,##0", f'VAR d = [Report Date]\nRETURN CALCULATE(COUNTROWS({SH}), {SH}[Created Date] = d) + 0'),
    ("Shipments Loaded Day", "13 Orders", "#,##0", SHIFT_DAY + f'RETURN COUNTROWS(FILTER({SH}, {SH}[Loaded] >= s0 && {SH}[Loaded] < e0)) + 0'),
    ("Shipments Created Prev", "13 Orders", "#,##0", prev("[Shipments Created Day]")),
    ("Shipments Loaded Prev", "13 Orders", "#,##0", prev("[Shipments Loaded Day]")),
    ("Orders Flow Text", "13 Orders", None,
     'IF([Orders Flow Used], "Shipments move through WMS statuses at this site (Ready -> In-Process -> Staged -> Loading -> Load Complete).", '
     '"Shipments " & ' + rca("NARRATIVE", '"ORDERS_NA"') + ')'),
]

# ---------------------------------------------------------------- people (user x hour heat map coloured by the USER_PROD limits)
PEOPLE = [
    ("User Hour Color", "14 People", None,
     f'VAR v = [Moves Hour]\nVAR tg = {thr("USER_PROD")}\nVAR w = {thr("USER_PROD", "Warn_At")}\nVAR c = {thr("USER_PROD", "Crit_At")}\n'
     f'RETURN IF(ISBLANK(v) || v = 0 || NOT HASONEVALUE({UA}[User_Id]), BLANK(), IF(v >= w, {FILL_OK}, IF(v >= c, {FILL_WARN}, {FILL_CRIT})))'),
    ("User Main Step", "14 People", None,
     f'VAR d = [Report Date]\nVAR T = ADDCOLUMNS(CALCULATETABLE(VALUES({UA}[Move_Class]), {UA}[Shift_Date] = d), "@p", CALCULATE(SUM({UA}[Pallets_User_Hour]), {UA}[Shift_Date] = d))\n'
     f'RETURN MAXX(TOPN(1, T, [@p], DESC, {UA}[Move_Class], ASC), {UA}[Move_Class])'),
    ("Active Users Prev", "14 People", "0", prev("[KPI Active Users]")),
    ("Hour Pallets Per User", "14 People", "0.0", 'DIVIDE([Moves Hour], [Hour Active Users])'),
    # ---- productivity by hour (People + User Productivity pages): pallets per active user in the hour vs the USER_PROD limits
    ("Hour Productivity Target", "14 People\\By hour", "0.0",
     f'IF(NOT ISBLANK([Hour Active Users]) && [Hour Active Users] > 0, {thr("USER_PROD")})'),
    ("Hour Productivity Status", "14 People\\By hour", None,
     f'VAR v = [Hour Pallets Per User]\nVAR w = {thr("USER_PROD", "Warn_At")}\nVAR c = {thr("USER_PROD", "Crit_At")}\n'
     'RETURN IF(ISBLANK(v), BLANK(), IF(v >= w, "🟢 OK", IF(v >= c, "🟠 WARNING", "🔴 CRITICAL")))'),
    ("Hour Productivity Color", "14 People\\By hour", None,
     f'VAR v = [Hour Pallets Per User]\nVAR w = {thr("USER_PROD", "Warn_At")}\nVAR c = {thr("USER_PROD", "Crit_At")}\n'
     f'RETURN IF(ISBLANK(v), BLANK(), IF(v >= w, {FILL_OK}, IF(v >= c, {FILL_WARN}, {FILL_CRIT})))'),
    ("Hour Productivity Font", "14 People\\By hour", None,
     'VAR s = [Hour Productivity Status]\nRETURN SWITCH(TRUE(), ISBLANK(s), BLANK(), CONTAINSSTRING(s, "CRITICAL"), "' + _PAL["status"]["CRITICAL"] + '", '
     'CONTAINSSTRING(s, "WARNING"), "' + _PAL["status"]["WARNING"] + '", "' + _PAL["status"]["OK"] + '")'),
    ("Hour Users Below", "14 People\\By hour", "0",
     '-- users in the hour whose pallets per hour are below the USER_PROD warning limit\n'
     f'VAR w = {thr("USER_PROD", "Warn_At")}\nVAR U = CALCULATETABLE(VALUES({UA}[User_Id]), REMOVEFILTERS({UA}))\n'
     'RETURN IF(NOT ISBLANK([Hour Active Users]), COUNTROWS(FILTER(U, VAR v = [Moves Hour] RETURN NOT ISBLANK(v) && v > 0 && v < w)) + 0)'),
    ("User Productivity Prev", "14 People", "0.0", prev("[KPI User Productivity]")),
    ("User Pallets Prev", "14 People", "#,##0", prev("[User Pallets Moved]")),
]

# ---------------------------------------------------------------- truck dock + staging lanes (Truck Staging feed) - same trucks as the Gantt
TS = "'Truck Staging'"
_STG = ('VAR s0 = [Truck Day Start]\nVAR e0 = s0 + [Win Days]\n'
        '-- Direction slicer of the page (TTAT[Direction]); none = both\n'
        'VAR dirs = IF(ISFILTERED(TTAT[Direction]), CONCATENATEX(VALUES(TTAT[Direction]), TTAT[Direction], "|"), "Inbound|Outbound")\n'
        f'VAR T = FILTER({TS}, VAR t = IF({TS}[Direction] = "Inbound", {TS}[Dispatch], {TS}[Close]) RETURN t >= s0 && t < e0 && CONTAINSSTRING(dirs, {TS}[Direction]))\n')
STAGING = [
    ("Staging Pallets", "11 Trucks\\Dock & staging", "#,##0",
     '-- pallets per truck x lane of the trucks completed in the truck window (inbound dispatched / outbound closed), Direction slicer kept\n'
     + _STG + f'RETURN IF(NOT ISEMPTY(T), SUMX(T, {TS}[Pallets]))'),
    ("Staging Trucks", "11 Trucks\\Dock & staging", "#,##0", _STG + f'RETURN COUNTROWS(DISTINCT(SELECTCOLUMNS(T, "@t", {TS}[TrailerID]))) + 0'),
    ("Staging Pallets Per Truck", "11 Trucks\\Dock & staging", "0.0", 'DIVIDE([Staging Pallets], [Staging Trucks])'),
    ("Staging Lanes Used", "11 Trucks\\Dock & staging", "#,##0",
     _STG + f'RETURN COUNTROWS(DISTINCT(SELECTCOLUMNS(FILTER(T, LEFT({TS}[Staging Lane], 1) <> "("), "@l", {TS}[Staging Lane]))) + 0'),
    ("Staging Truck TTAT", "11 Trucks\\Dock & staging", "#,##0",
     f'VAR trk = SELECTEDVALUE({TS}[TrailerID])\nRETURN IF(NOT ISBLANK(trk) && NOT ISBLANK([Staging Pallets]), '
     'CALCULATE(MAX(TTAT[TTAT (Minutes)]), REMOVEFILTERS(TTAT), REMOVEFILTERS(DimDate), TTAT[TrailerID] = trk))'),
    ("Staging Rule Text", "11 Trucks\\Dock & staging", None,
     '"Dock = door at close (else at a status change / check-in). Outbound lane = last location of each loaded pallet before the trailer that is not a '
     'forklift / RF device area (storage location when loaded directly); inbound lane = first location after the receipt. Trucks of " & '
     'FORMAT([Truck Day Start], "ddd dd-mmm hh:nn") & " - " & FORMAT([Truck Day Start] + [Win Days], "ddd dd-mmm hh:nn") & " (same trucks as the Gantt)"'),
]

# ---------------------------------------------------------------- SAP confirmed production (CDL MATDOC 101/102) vs PrIME production
_SAPDAY = f'VAR r = [Report Date]\nVAR d = SELECTEDVALUE({SP}[Posting_Date])\nVAR L = {thr("LOOKBACK")}\nVAR inWin = NOT ISBLANK(d) && d > r - L && d <= r\n'
_CMP = thr("COMPARE_DAYS")
SAP = [
    ("SAP Pallets Day", "15 SAP Production", "#,##0",
     f'VAR d = [Report Date]\nRETURN IF([Feature SAP Prod] = 1, CALCULATE(SUM({SP}[Pallets]), {SP}[Posting_Date] = d) + 0)'),
    ("SAP GR Lines Day", "15 SAP Production", "#,##0",
     f'VAR d = [Report Date]\nRETURN IF([Feature SAP Prod] = 1, CALCULATE(SUM({SP}[GR_Lines]), {SP}[Posting_Date] = d) + 0)'),
    ("SAP Pallets Prev", "15 SAP Production", "#,##0", prev("[SAP Pallets Day]")),
    ("SAP Pallets Prior Avg", "15 SAP Production", "#,##0", avg7("[SAP Pallets Day]")),
    ("SAP Pallets Window", "15 SAP Production", "#,##0",
     f'VAR d = [Report Date]\nVAR k = {_CMP}\nRETURN IF([Feature SAP Prod] = 1, CALCULATE(SUM({SP}[Pallets]), {SP}[Posting_Date] > d - k, {SP}[Posting_Date] <= d) + 0)'),
    ("WMS Pallets Window", "15 SAP Production", "#,##0",
     f'VAR d = [Report Date]\nVAR k = {_CMP}\nRETURN IF([Feature Production] = 1, CALCULATE(SUM({PT}[PalletsLeftFromLine]), {RM}, REMOVEFILTERS({PT}), '
     f'{PT}[shift_date] > d - k, {PT}[shift_date] <= d) + 0)'),
    ("KPI WMS Coverage", "15 SAP Production", "0%", 'VAR s = [SAP Pallets Window]\nRETURN IF([Feature Production] = 1 && s > 0, DIVIDE([WMS Pallets Window], s))'),
    ("SAP Pallets By Day", "15 SAP Production", "#,##0", _SAPDAY + f'RETURN IF(inWin, SUM({SP}[Pallets]))'),
    ("SAP GR Lines By Day", "15 SAP Production", "#,##0", _SAPDAY + f'RETURN IF(inWin, SUM({SP}[GR_Lines]))'),
    ("WMS Pallets By Day", "15 SAP Production", "#,##0",
     _SAPDAY + f'RETURN IF(inWin && [Feature Production] = 1, CALCULATE(SUM({PT}[PalletsLeftFromLine]), {RM}, REMOVEFILTERS({PT}), {PT}[shift_date] = d) + 0)'),
    ("WMS Coverage By Day", "15 SAP Production", "0%", 'VAR s = [SAP Pallets By Day]\nRETURN IF(s > 0, DIVIDE([WMS Pallets By Day], s))'),
    ("SAP Pallet Basis", "15 SAP Production", None, f'CONCATENATEX(VALUES({SP}[Pallet_Basis]), {SP}[Pallet_Basis], " + ")'),
    ("SAP Material Pallets Day", "15 SAP Production", "#,##0.#",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({SP}[Pallets]), {SP}[Posting_Date] = d)'),
    ("SAP Material Qty Day", "15 SAP Production", "#,##0",
     f'VAR d = [Report Date]\nRETURN CALCULATE(SUM({SP}[Qty_BUoM]), {SP}[Posting_Date] = d)'),
    ("Production Explanation", "15 SAP Production", None,
     f'VAR sap = [SAP Pallets Window]\nVAR wms = [WMS Pallets Window]\nVAR k = {_CMP}\nVAR plant = [SAP Plant]\n'
     f'VAR minCov = {thr("WMS_COVERAGE", "Crit_At")}\n'
     'RETURN SWITCH(TRUE(),\n'
     '    [Feature SAP Prod] <> 1, ' + fill(rca("NARRATIVE", '"SAP_NONE"'), {"site": "[Site Name]"}) + ',\n'
     '    sap <= 0, ' + fill(rca("NARRATIVE", '"SAP_STOPPED"'), {"plant": "plant", "days": 'FORMAT(k, "0")'}) + ',\n'
     '    [Feature Production] <> 1, ' + fill(rca("NARRATIVE", '"SAP_NOT_TRACKED"'), {"plant": "plant", "sap": 'FORMAT(sap, "#,0")', "days": 'FORMAT(k, "0")',
                                                                                    "perday": 'FORMAT(DIVIDE(sap, k), "#,0")'}) + ',\n'
     '    DIVIDE(wms, sap) < minCov, ' + fill(rca("NARRATIVE", '"SAP_WMS_MISSING"'), {"plant": "plant", "sap": 'FORMAT(sap, "#,0")', "wms": 'FORMAT(wms, "#,0")',
                                                                                     "days": 'FORMAT(k, "0")'}) + ',\n'
     '    ' + fill(rca("NARRATIVE", '"SAP_COVERAGE"'), {"wms": 'FORMAT(wms, "#,0")', "sap": 'FORMAT(sap, "#,0")', "days": 'FORMAT(k, "0")',
                                                       "cov": 'FORMAT(DIVIDE(wms, sap), "0%")', "basis": "[SAP Pallet Basis]"}) + ')'),
    ("Production Explanation Action", "15 SAP Production", None,
     f'VAR sap = [SAP Pallets Window]\nVAR wms = [WMS Pallets Window]\nVAR minCov = {thr("WMS_COVERAGE", "Crit_At")}\n'
     'RETURN SWITCH(TRUE(), [Feature SAP Prod] <> 1, ' + rca("NARRATIVE", '"SAP_NONE"', "Action") + ',\n'
     '    sap <= 0, ' + rca("NARRATIVE", '"SAP_STOPPED"', "Action") + ',\n'
     '    [Feature Production] <> 1, ' + rca("NARRATIVE", '"SAP_NOT_TRACKED"', "Action") + ',\n'
     '    DIVIDE(wms, sap) < minCov, ' + rca("NARRATIVE", '"SAP_WMS_MISSING"', "Action") + ',\n'
     '    ' + rca("NARRATIVE", '"SAP_COVERAGE"', "Action") + ')'),
]

# ---------------------------------------------------------------- last activity (why today is empty) - newest event per stream, site-local
LAST = [
    ("Last Pallet Move", "16 Last activity", "ddd dd-mmm hh:nn",
     f'MAXX(CALCULATETABLE(SUMMARIZE({UA}, {UA}[Activity_Date], {UA}[Activity_Hour]), REMOVEFILTERS({UA}[Activity_Date], {UA}[Activity_Hour], {UA}[Shift_Date])), '
     f'{UA}[Activity_Date] + {UA}[Activity_Hour] / 24)'),
    ("Last Truck Closed", "16 Last activity", "ddd dd-mmm hh:nn", f'CALCULATE(MAX(TTAT[Close]), {RM})'),
    ("Last Production Pallet", "16 Last activity", "ddd dd-mmm hh:nn", '[Prod Last Pallet Time]'),
    ("Last SAP Receipt Day", "16 Last activity", "ddd dd-mmm", f'IF([Feature SAP Prod] = 1, CALCULATE(MAX({SP}[Posting_Date]), {SP}[Pallets] > 0))'),
    ("Last Activity Text", "16 Last activity", None,
     'VAR m = [Last Pallet Move]\nVAR t = [Last Truck Closed]\nVAR p = [Last Production Pallet]\n' + ('' if SAP_LEFT_OUT else 'VAR s = [Last SAP Receipt Day]\n') +
     'RETURN "Last pallet move " & IF(ISBLANK(m), "-", FORMAT(m, "ddd dd-mmm hh:00")) & "  |  last truck closed " & IF(ISBLANK(t), "-", FORMAT(t, "ddd dd-mmm hh:nn")) & '
     'IF([Feature Production] = 1, "  |  last WMS production pallet " & IF(ISBLANK(p), "-", FORMAT(p, "ddd dd-mmm hh:00")), "")' +
     ('' if SAP_LEFT_OUT else ' & IF([Feature SAP Prod] = 1, "  |  last SAP FG receipt day " & IF(ISBLANK(s), "-", FORMAT(s, "ddd dd-mmm")), "")')),
]

# ---------------------------------------------------------------- previous day / prior-days average for the scorecard rows (Cfg_Threshold context)
_DAY_KPI = '[KPI Applicable] && SELECTEDVALUE(Cfg_Threshold[Basis], "DAY") = "DAY"'
_TREND = thr("FORECAST_DAYS")


def _kpi_text(v):
    return (f'IF(NOT [KPI Applicable], "N/A", IF(SELECTEDVALUE(Cfg_Threshold[Basis], "DAY") = "LIVE", {rca("NARRATIVE", chr(34) + "PREV_LIVE" + chr(34))}, '
            f'IF(ISBLANK({v}), "-", FORMAT({v}, SELECTEDVALUE(Cfg_Threshold[Format], "0.0")) & [KPI Unit Suffix])))')


SCORE_PREV = [
    ("KPI Prev Value", "0 Scorecard", "#,##0.00",
     f'VAR d = [Report Date]\nRETURN IF({_DAY_KPI}, CALCULATE([KPI Actual], TREATAS({{d - 1}}, DimDate[Date])))'),
    ("KPI Avg Prior Value", "0 Scorecard", "#,##0.00",
     f'VAR d = [Report Date]\nVAR k = {_TREND}\nRETURN IF({_DAY_KPI}, AVERAGEX(SELECTCOLUMNS(GENERATESERIES(d - k, d - 1, 1), "@d", [Value]), '
     'CALCULATE([KPI Actual], TREATAS({[@d]}, DimDate[Date]))))'),
    ("KPI Prev Text", "0 Scorecard", None, 'VAR v = [KPI Prev Value]\nRETURN ' + _kpi_text("v")),
    ("KPI Avg Prior Text", "0 Scorecard", None, 'VAR v = [KPI Avg Prior Value]\nRETURN ' + _kpi_text("v")),
]


def card_prev_measures(card_keys):
    out = []
    for k in card_keys:
        flt = f'Cfg_Threshold[KPI_Key] = "{k}"'
        out += [(f"Card {k} Prev", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Prev Text], {flt})'),
                (f"Card {k} Avg Prior", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Avg Prior Text], {flt})')]
    return out


# ---------------------------------------------------------------- process mining (sql/new/Process Edges.sql = directly-follows graph)
PE = "'Process Edges'"
IV = "Inventory"
_PM_UNIT = 'SWITCH({f}, "Order", " orders", "Truck", " trucks", " pallets")'


def _pm_top(flow):
    """forward hand-off (Edge_Kind = Forward: main sequence, not open, not a side move) with the largest total waiting time = cases x median
    (volume AND duration, so a rare slow edge is not called the constraint) - per flow, edges below PM_MIN_CASES ignored."""
    return (f'TOPN(1, FILTER(ADDCOLUMNS(CALCULATETABLE(SUMMARIZE({PE}, {PE}[From_Step], {PE}[To_Step]), {PE}[Flow] = "{flow}", {PE}[Edge_Kind] = "Forward"), '
            f'"@c", CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "{flow}"), "@m", CALCULATE(MAX({PE}[Median_Min]), {PE}[Flow] = "{flow}")), [@c] >= mc), [@c] * [@m], DESC)')


def _pm_flow_sentence(flow, label):
    x = flow[0]     # VAR names topO / medO / txtO ... ('tO' would be the reserved word TO - DAX names are case-insensitive)
    return (f'VAR top{x} = {_pm_top(flow)}\n'
            f'VAR med{x} = MAXX(top{x}, [@m])\n'
            f'VAR txt{x} = IF(ISEMPTY(top{x}), BLANK(), "{label}: " & MAXX(top{x}, {PE}[From_Step]) & " -> " & MAXX(top{x}, {PE}[To_Step]) '
            f'& ", median " & {dur("med" + x)} & " over " & FORMAT(MAXX(top{x}, [@c]), "#,##0") & {_PM_UNIT.format(f=chr(34) + flow + chr(34))})\n')


PROCESS_MINING = [
    ("PM Min Cases", "14 Process Mining", "0", thr("PM_MIN_CASES")),
    ("PM Window Days", "14 Process Mining", "0", site("MOVEMENT_DAYS")),
    ("PM Window Text", "14 Process Mining", None,
     '-- subtitle of the Sankeys / hand-off table: the measured window and the noise floor in numbers (not config names)\n'
     'VAR d = [PM Window Days]\nRETURN IF(ISBLANK(d), BLANK(), "Measured over the last " & d & " days (Cfg_Site MOVEMENT_DAYS); hand-offs with fewer than " & '
     '[PM Min Cases] & " cases hidden (PM_MIN_CASES); \'Open: waiting after X\' = not yet at the next step now = stuck")'),
    ("PM Order Flow Note", "14 Process Mining", None,
     '-- order Sankey subtitle: says WHY it is empty (a custom visual shows no "no data" text) - else the measured window\n'
     f'VAR n = COALESCE(CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Order", {PE}[From_No] = 1), 0)\n'
     'RETURN IF(NOT [Orders Flow Used], "Not traceable at this site: shipments stay Ready in WMS (no pick-release / staged / loaded status) - follow the '
     'pallet flow and the trucks below",\n'
     '    IF(n < [PM Min Cases], "Too few orders for a reliable flow: " & FORMAT(n, "#,##0") & " orders in the last " & [PM Window Days] & '
     '" days (minimum " & [PM Min Cases] & ", Cfg_Threshold PM_MIN_CASES)", [PM Window Text]))'),
    ("PM Pallet Flow Note", "14 Process Mining", None,
     f'VAR mx = COALESCE(CALCULATE(MAX({PE}[Cases]), {PE}[Flow] = "Pallet", {PE}[Edge_Kind] IN {{"Forward", "Storage"}}), 0)\n'
     'RETURN IF(mx < [PM Min Cases], "Too few pallets for a reliable flow: the largest main-flow hand-off has " & FORMAT(mx, "#,##0") & '
     '" pallets in the last " & [PM Window Days] & " days (minimum " & [PM Min Cases] & ", Cfg_Threshold PM_MIN_CASES) - see the hand-off table", [PM Window Text])'),
    ("PM Cases", "14 Process Mining", "#,##0",
     '-- Sankey weight = distinct pallets / orders / trucks that made the hand-off From -> To in the last MOVEMENT_DAYS days. Hidden: edges below\n'
     '-- PM_MIN_CASES (one-off rescans) and the order flow where shipments stay Ready in WMS (Orders Flow Used)\n'
     f'VAR n = SUM({PE}[Cases])\nVAR f = SELECTEDVALUE({PE}[Flow])\n'
     'RETURN IF(n >= [PM Min Cases] && NOT (f = "Order" && NOT [Orders Flow Used]), n)'),
    ("PM Median Min", "14 Process Mining", "#,##0.0", f'IF(NOT ISBLANK([PM Cases]), MAX({PE}[Median_Min]))'),
    ("PM Flow Cases", "14 Process Mining", "#,##0",
     '-- Sankey weight: the main flow only (Edge_Kind Forward + Storage + Open) - a left-to-right picture without loops; side moves\n'
     '-- (transfer / other move) and back / rework hand-offs are listed in the hand-off table with their own verdict\n'
     f'VAR k = SELECTEDVALUE({PE}[Edge_Kind])\nRETURN IF(k IN {{"Forward", "Storage", "Open"}}, [PM Cases])'),
    ("PM P95 Min", "14 Process Mining", "#,##0.0", f'IF(NOT ISBLANK([PM Cases]), MAX({PE}[P95_Min]))'),
    ("PM Median Text", "14 Process Mining", None, 'VAR m = [PM Median Min]\nRETURN ' + dur("m")),
    ("PM P95 Text", "14 Process Mining", None, 'VAR m = [PM P95 Min]\nRETURN ' + dur("m")),
    ("PM Case Hours", "14 Process Mining", "#,##0",
     '-- total waiting time on the hand-off = cases x median hours (ranks the bottleneck: volume AND duration)\n'
     'VAR c = [PM Cases]\nRETURN IF(NOT ISBLANK(c), c * [PM Median Min] / 60)'),
    ("PM Edge Verdict", "14 Process Mining", None,
     f'VAR c = [PM Cases]\nVAR k = SELECTEDVALUE({PE}[Edge_Kind])\n'
     'RETURN IF(ISBLANK(c), BLANK(), SWITCH(k, "Open", "⏳ open now - stuck here", "Side", "↻ extra move (re-handling)",\n'
     '    "Storage", "▣ in storage (waits for demand)", "Back", "↩ back / rework step", "Forward", "→ forward hand-off", BLANK()))'),
    ("PM Orders Traced", "14 Process Mining", "#,##0",
     f'IF([Orders Flow Used], CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Order", {PE}[From_No] = 1))'),
    ("PM Orders Waiting", "14 Process Mining", "#,##0",
     f'IF([Orders Flow Used], CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Order", {PE}[Is_Open_Edge] = 1) + 0)'),
    ("PM Trucks Traced", "14 Process Mining", "#,##0", f'CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Truck", {PE}[From_No] = 1, {PE}[Is_Open_Edge] = 0)'),
    ("PM Trucks Waiting", "14 Process Mining", "#,##0", f'CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Truck", {PE}[Is_Open_Edge] = 1) + 0'),
    ("PM Pallet Handoffs", "14 Process Mining", "#,##0", f'CALCULATE(SUM({PE}[Transitions]), {PE}[Flow] = "Pallet")'),
    ("PM Verdict", "14 Process Mining", None,
     '-- measured from the event log (last MOVEMENT_DAYS days): per flow the forward hand-off with the largest total waiting time, then what is\n'
     '-- open (waiting) now - the same numbers as the Sankeys and the hand-off table\n'
     'VAR mc = [PM Min Cases]\n' + _pm_flow_sentence("Order", "ORDERS") + _pm_flow_sentence("Pallet", "PALLETS") + _pm_flow_sentence("Truck", "TRUCKS") +
     f'VAR openO = TOPN(3, FILTER(ADDCOLUMNS(CALCULATETABLE(SUMMARIZE({PE}, {PE}[From_Step]), {PE}[Flow] = "Order", {PE}[Is_Open_Edge] = 1), '
     f'"@c", CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Order", {PE}[Is_Open_Edge] = 1), "@m", CALCULATE(MAX({PE}[Median_Min]), {PE}[Flow] = "Order", {PE}[Is_Open_Edge] = 1)), [@c] > 0), [@c], DESC)\n'
     'VAR openTxt = IF([Orders Flow Used] && NOT ISEMPTY(openO), "STUCK NOW: " & CONCATENATEX(openO, FORMAT([@c], "#,##0") & " orders waiting after " & '
     f'{PE}[From_Step] & " (median age " & FORMAT([@m] / 60, "0.0") & " h)", "; ", [@c], DESC))\n'
     'VAR ordTxt = IF([Orders Flow Used], txtO, "ORDERS: not tracked through WMS statuses at this site (shipments stay Ready) - follow trucks")\n'
      # storage dwell (put-away -> next step) is stock waiting for demand, not a process wait: own sentence, never the bottleneck
      f'VAR stTop = TOPN(1, FILTER(ADDCOLUMNS(CALCULATETABLE(SUMMARIZE({PE}, {PE}[From_Step], {PE}[To_Step]), {PE}[Flow] = "Pallet", {PE}[Edge_Kind] = "Storage"), '
      f'"@c", CALCULATE(SUM({PE}[Cases]), {PE}[Flow] = "Pallet"), "@m", CALCULATE(MAX({PE}[Median_Min]), {PE}[Flow] = "Pallet")), [@c] >= mc), [@c], DESC)\n'
      'VAR stMed = MAXX(stTop, [@m])\n'
      f'VAR stTxt = IF(ISEMPTY(stTop), BLANK(), "STORAGE (stock waiting for demand, not a process wait): " & MAXX(stTop, {PE}[From_Step]) & " -> " & '
      f'MAXX(stTop, {PE}[To_Step]) & ", median " & {dur("stMed")} & " over " & FORMAT(MAXX(stTop, [@c]), "#,##0") & " pallets")\n'
      'VAR parts = {ordTxt, txtP, txtT, stTxt, openTxt}\n'
      f'VAR nEdges = COUNTROWS({PE})\n'
      'RETURN IF(ISBLANK(txtP) && ISBLANK(txtT) && ISBLANK(txtO) && ISBLANK(stTxt),\n'
      '    IF(nEdges > 0, "Too few cases for a reliable picture: no hand-off with at least " & mc & " cases in the last " & [PM Window Days] & '
      '" days (" & FORMAT(nEdges, "0") & " smaller hand-offs; lower Cfg_Threshold PM_MIN_CASES for this site to see them).",\n'
      '        "No process events in the last " & [PM Window Days] & " days for this site."),\n'
      '    "Where the flow loses most time (median x cases, last " & [PM Window Days] & " days): " & CONCATENATEX(FILTER(parts, NOT ISBLANK([Value]) && [Value] <> ""), [Value], "   |   "))'),
]

# ---------------------------------------------------------------- TTAT by shift (Excel ALERTS 'TTAT diagnostic': waiting vs unloading per shift)
# trucks COMPLETED (inbound dispatch / outbound close) in the LOOKBACK shift days up to the report day, grouped by the shift of their check-in
# (Cfg_Shift x TTAT[Direction] in context); shift starts from Cfg_Site (2-shift sites: Shift3_Start = Shift2_Start -> shift 3 empty)
_SHIFT_T = ('VAR s = SELECTEDVALUE(Cfg_Shift[Shift_No])\nVAR h1 = [Site Shift1 Start h]\nVAR h2 = ' + site("Shift2_Start", 0) + '\nVAR h3 = ' + site("Shift3_Start", 0) + '\n'
            f'VAR L = {thr("LOOKBACK")}\nVAR e1 = [Report Date] + 1 + h1 / 24\nVAR e0 = e1 - L\n'
            f'VAR tr = CALCULATETABLE(ADDCOLUMNS(VALUES(TTAT[TrailerID]), "@ci", CALCULATE(MIN(TTAT[Check-in])), '
            '"@end", CALCULATE(IF(MAX(TTAT[Direction]) = "Inbound", MAX(TTAT[Dispatch]), MAX(TTAT[Close]))), '
            '"@w", CALCULATE(MAX(TTAT[Scan - Checkin (Minutes)])), "@g", CALCULATE(MAX(TTAT[Loading/GR Time (Minutes)])), '
            f'"@t", CALCULATE(MAX(TTAT[TTAT (Minutes)]))), {RM})\n'
            'VAR F = FILTER(tr, NOT ISBLANK([@end]) && [@end] >= e0 && [@end] < e1 && NOT ISBLANK([@ci]) &&\n'
            '    VAR hr = HOUR([@ci]) RETURN IF(hr >= h1 && hr < h2, 1, IF(h3 > h2 && (hr >= h3 || hr < h1), 3, 2)) = s)\n')
SHIFTS = [
    ("Shift Trucks", "11 Trucks\\By shift", "#,##0", _SHIFT_T + 'RETURN IF(NOT ISBLANK(s), COUNTROWS(F) + 0)'),
    ("Shift Avg Wait Min", "11 Trucks\\By shift", "#,##0", _SHIFT_T + 'RETURN AVERAGEX(F, MAX(0, [@w]))'),
    ("Shift Avg Work Min", "11 Trucks\\By shift", "#,##0", _SHIFT_T + 'RETURN AVERAGEX(F, MAX(0, [@g]))'),
    ("Shift Avg TTAT Min", "11 Trucks\\By shift", "#,##0", _SHIFT_T + 'RETURN AVERAGEX(F, [@t])'),
    ("Shift Verdict", "11 Trucks\\By shift", None,
     _SHIFT_T + 'VAR n = COUNTROWS(F)\nVAR w = AVERAGEX(F, MAX(0, [@w]))\nVAR g = AVERAGEX(F, MAX(0, [@g]))\nVAR t = AVERAGEX(F, [@t])\n'
     'VAR dir = SELECTEDVALUE(TTAT[Direction])\n'
     f'VAR lim = IF(dir = "Inbound", {thr("TTAT_IN", "Crit_At")}, {thr("TTAT_OUT", "Crit_At")})\nVAR wl = IF(dir = "Inbound", {thr("TTAT_IN", "Warn_At")}, {thr("TTAT_OUT", "Warn_At")})\n'
     'RETURN IF(ISBLANK(s), BLANK(), IF(n = 0, "no trucks", IF(t > lim, "🔴 CRITICAL - ", IF(t > wl, "🟠 WARNING - ", "🟢 OK - ")) & '
     'IF(w > g, "delay is WAITING (yard / gate / dock queue), not " & IF(dir = "Inbound", "unloading", "loading"), '
     '"delay is " & IF(dir = "Inbound", "UNLOADING", "LOADING") & " (labour / equipment at the dock)")))'),
    ("Shift Label", "11 Trucks\\By shift", None,
     'VAR s = SELECTEDVALUE(Cfg_Shift[Shift_No])\nVAR h1 = [Site Shift1 Start h]\nVAR h2 = ' + site("Shift2_Start", 0) + '\nVAR h3 = ' + site("Shift3_Start", 0) + '\n'
     'VAR a = SWITCH(s, 1, h1, 2, h2, 3, h3)\nVAR b = SWITCH(s, 1, h2, 2, IF(h3 > h2, h3, h1), 3, h1)\n'
     'RETURN IF(ISBLANK(s) || (s = 3 && h3 <= h2), BLANK(), "Shift " & s & " (" & FORMAT(a, "00") & ":00-" & FORMAT(b, "00") & ":00)")'),
    ("Shift Window Text", "11 Trucks\\By shift", None,
     f'VAR L = {thr("LOOKBACK")}\nRETURN "Trucks completed in the last " & L & " shift days up to " & FORMAT([Report Date], "ddd dd-mmm") & '
     '" (inbound = dispatched, outbound = closed), grouped by the shift of their check-in; wait = check-in to first scan, work = unload / load"'),
    ("Stale Rule Text", "10 Process Flow", None,
     f'VAR h = {thr("STALE_HOURS")}\nRETURN "Stale = in the same location more than " & FORMAT(h, "#,##0") & " h (" & FORMAT(DIVIDE(h, 24), "0.#") & " days): '
     'a record to check on the floor, not a live blockage"'),
    ("User Hour Rule Text", "14 People", None,
     f'VAR w = {thr("USER_PROD", "Warn_At")}\nVAR c = {thr("USER_PROD", "Crit_At")}\n'
     'RETURN "Green = at least " & FORMAT(w, "#,##0.#") & " pallets per user-hour (warning limit), amber = at least " & FORMAT(c, "#,##0.#") & '
     '" (critical limit), red = below"'),
    ("Lookback Text", "11 Trucks\\By shift", None,
     f'VAR L = {thr("LOOKBACK")}\nRETURN "Window: last " & L & " shift days up to " & FORMAT([Report Date], "ddd dd-mmm") & '
     '" (baseline / trend; look-back days are set in the alert targets)"'),
]

# ---------------------------------------------------------------- truck Gantt (report-day trucks on a timeline: offset + wait + work + close-out)
GANTT = [
    ("Gantt Start Min", "11 Trucks\\Gantt", "#,##0",
     '-- minutes from the first check-in among the report-day trucks to this truck\'s check-in (invisible first bar segment of the Gantt)\n'
     + _TRUCK_DAY +
     f'VAR base = CALCULATE(MIN(TTAT[Check-in]), REMOVEFILTERS(TTAT[TrailerID]), {RM}, FILTER(ALL(TTAT[Direction], TTAT[Dispatch], TTAT[Close]),\n'
     '    (TTAT[Direction] = "Inbound" && TTAT[Dispatch] >= s0 && TTAT[Dispatch] < e0) || (TTAT[Direction] = "Outbound" && TTAT[Close] >= s0 && TTAT[Close] < e0)))\n'
     f'VAR t = CALCULATE(MIN(TTAT[Check-in]), {RM})\n'
     'RETURN IF(inDay && NOT ISBLANK(t) && NOT ISBLANK(base), MAX(0, (t - base) * 1440))'),
    ("Gantt First Checkin", "11 Trucks\\Gantt", "ddd hh:nn",
     'VAR s0 = [Truck Day Start]\nVAR e0 = s0 + [Win Days]\n' + f'RETURN CALCULATE(MIN(TTAT[Check-in]), REMOVEFILTERS(TTAT), {RM}, FILTER(ALL(TTAT[Direction], TTAT[Dispatch], TTAT[Close]),\n'
     '    (TTAT[Direction] = "Inbound" && TTAT[Dispatch] >= s0 && TTAT[Dispatch] < e0) || (TTAT[Direction] = "Outbound" && TTAT[Close] >= s0 && TTAT[Close] < e0)))'),
    ("Gantt Note", "11 Trucks\\Gantt", None,
     'VAR b = [Gantt First Checkin]\nRETURN IF(ISBLANK(b), "No completed truck in the TTAT feed for this site.", '
     '"Timeline starts at the first check-in of the shown trucks: " & FORMAT(b, "ddd dd-mmm hh:nn") & '
     '" (site time). Each bar = one truck: amber = waiting from check-in to the first scan, blue = unloading / loading, grey = close-out to dispatch / close.")'),
]

# ---------------------------------------------------------------- inventory (all pallets, finished goods and materials; Location Utilisation)
INVENTORY = [
    ("Inv Pallets", "16 Inventory", "#,##0", f'SUM({IV}[Pallets]) + 0'),
    # matrix cells: BLANK (not 0) where the site has no such area / status - a '+ 0' value would list every area of every site
    ("Inv Pallets Cell", "16 Inventory", "#,##0", f'SUM({IV}[Pallets])'),
    ("Inv FG Pallets", "16 Inventory", "#,##0", f'CALCULATE(SUM({IV}[Pallets]), {IV}[Material] = "Finished goods") + 0'),
    ("Inv Material Pallets", "16 Inventory", "#,##0", f'CALCULATE(SUM({IV}[Pallets]), {IV}[Material] = "Materials") + 0'),
    ("Inv Old Pallets", "16 Inventory", "#,##0",
     '-- pallets older than STOCK_OLD_DAYS (days since receipt; FIFO date when no receipt date) = the age bands that start at or after that age\n'
     f'VAR od = {thr("STOCK_OLD_DAYS")}\n'
     f'RETURN CALCULATE(SUM({IV}[Pallets]), TREATAS(SELECTCOLUMNS(FILTER(ALL(Cfg_StockAge), Cfg_StockAge[From_Days] >= od), "@b", Cfg_StockAge[Band]), {IV}[Age_Band])) + 0'),
    ("Inv Old Share", "16 Inventory", "0.0%", 'DIVIDE([Inv Old Pallets], [Inv Pallets])'),
    ("Inv Old Rule Text", "16 Inventory", None,
     f'VAR od = {thr("STOCK_OLD_DAYS")}\nVAR o = [Inv Old Pallets]\n'
     'RETURN IF(ISBLANK(od), BLANK(), "Old = in stock more than " & od & " days since receipt (Cfg_Threshold STOCK_OLD_DAYS): " & FORMAT(o, "#,##0") & '
     '" pallets = " & FORMAT(DIVIDE(o, [Inv Pallets]), "0%") & " of " & FORMAT([Inv Pallets], "#,##0") & " pallets in stock")'),
    # old-stock table: blank when the row has no old stock -> the row is hidden (no measure filter needed)
    ("Inv Old Pallets Row", "16 Inventory", "#,##0", 'VAR o = [Inv Old Pallets]\nRETURN IF(o > 0, o)'),
    ("Inv Old Row All Pallets", "16 Inventory", "#,##0", 'IF([Inv Old Pallets] > 0, [Inv Pallets])'),
    ("Inv Old Row Max Age", "16 Inventory", "#,##0", f'IF([Inv Old Pallets] > 0, MAX({IV}[Max_Age_Days]))'),
    # likely cause + action per location class (config/stock_old_causes.csv) - only on rows with old stock
    ("Inv Old Cause", "16 Inventory", None,
     f'IF([Inv Old Pallets] > 0 && HASONEVALUE({IV}[Location Class]), LOOKUPVALUE(Cfg_StockCause[Likely_Cause], Cfg_StockCause[Location_Class], VALUES({IV}[Location Class])))'),
    ("Inv Old Action", "16 Inventory", None,
     f'IF([Inv Old Pallets] > 0 && HASONEVALUE({IV}[Location Class]), LOOKUPVALUE(Cfg_StockCause[Action], Cfg_StockCause[Location_Class], VALUES({IV}[Location Class])))'),
    ("Inv Band FG Pallets", "16 Inventory", "#,##0",
     f'CALCULATE(SUM({IV}[Pallets]), {IV}[Material] = "Finished goods", TREATAS(VALUES(Cfg_StockAge[Band]), {IV}[Age_Band]))'),
    ("Inv Band Material Pallets", "16 Inventory", "#,##0",
     f'CALCULATE(SUM({IV}[Pallets]), {IV}[Material] = "Materials", TREATAS(VALUES(Cfg_StockAge[Band]), {IV}[Age_Band]))'),
    ("Inv Max Age Days", "16 Inventory", "#,##0", f'MAX({IV}[Max_Age_Days])'),
    ("Loc Area Occupied", "16 Inventory", "#,##0", "SUM('Location Utilisation'[Occupied_Locations])"),
    ("Loc Area Util", "16 Inventory", "0.0%", "DIVIDE(SUM('Location Utilisation'[Occupied_Locations]), SUM('Location Utilisation'[Locations]))"),
]

# ---------------------------------------------------------------- refresh time line (banner): last / next refresh and now, site-local
REFRESH = [
    # feed completeness (Config & Health): rows of each replica source in the last 24 h per site - empty = red, how to check empties
    ("Feed Rows 24h", "6 Health", "#,##0", "SUM('Data Health'[Rows_Last_24h])"),
    ("Feed Last Event", "6 Health", "dd-mmm hh:nn", "MAX('Data Health'[Last_Event_Local])"),
    ("Feed Fill", "6 Health", None,
     f"VAR n = [Feed Rows 24h]\nRETURN IF(ISBLANK(n), BLANK(), IF(n = 0, {FILL_CRIT}, IF(n < 10, {FILL_WARN}, {FILL_OK})))"),
    ("Refresh Every Min", "0 Context", "0", 'LOOKUPVALUE(Cfg_Refresh[Every_Minutes], Cfg_Refresh[Tier], "HOT")'),
    ("Last Refresh Site", "0 Context", "yyyy-mm-dd hh:nn", "MAX('Date Refresh'[Last Refresh DateTime])"),
    ("Now Site", "0 Context", "yyyy-mm-dd hh:nn", 'UTCNOW() + [Site UTC Offset h] / 24'),
    ("Next Refresh Site", "0 Context", "yyyy-mm-dd hh:nn",
     '-- the scheduled task repeats every HOT interval on the grid from 00:00 of the scheduler clock (tools/auto_refresh.py --install):\n'
     '-- next run = the next grid slot after the last refresh, computed on the machine clock (NOW - UTCNOW) and shown in site time\n'
     'VAR l = [Last Refresh Site]\nVAR m = [Refresh Every Min]\n'
     'VAR shift = DIVIDE(DIVIDE(ROUND((NOW() - UTCNOW()) * 96, 0), 4) - [Site UTC Offset h], 24)\nVAR lm = l + shift\n'
     'VAR nm0 = INT(lm) + DIVIDE((INT(DIVIDE(ROUND((lm - INT(lm)) * 1440, 6), m)) + 1) * m, 1440)\n'
     '-- office hours of config/desktop_refresh.csv (PC clock): the Desktop report is not refreshed then -> next = end of the quiet hours\n'
     'VAR qf = LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Quiet_From_Hour")\n'
     'VAR qt = LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Quiet_To_Hour")\n'
     'VAR hm = HOUR(nm0)\nVAR nm = IF(NOT ISBLANK(qf) && hm >= qf && hm < qt, INT(nm0) + qt / 24, nm0)\n'
     'RETURN IF(ISBLANK(l) || ISBLANK(m) || m <= 0, BLANK(), nm - shift)'),
    ("Refresh Line", "0 Context", None,
     '-- site-local times. All-sites file (Scheduled_Refresh = 1): it is published to SharePoint as a .pbix WITH data at Snapshot_Hour_1/2\n'
     '-- (publisher PC clock, Publisher_UTC_Offset_Min) -> "data as of" + when the next copy appears (site time) + a warning when the copy\n'
     '-- someone opened is older than the gap between two copies. Site project files: the user refreshes them (Home > Refresh)\n'
     'VAR l = [Last Refresh Site]\nVAR nw = [Now Site]\nVAR so = [Site UTC Offset h]\n'
     'VAR sched = LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Scheduled_Refresh") <> 0\n'
     'VAR h1 = LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Snapshot_Hour_1")\n'
     'VAR h2 = LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Snapshot_Hour_2")\n'
     'VAR po = DIVIDE(LOOKUPVALUE(Cfg_DesktopRefresh[Value], Cfg_DesktopRefresh[Setting], "Publisher_UTC_Offset_Min"), 60)\n'
     '-- copy ready ~30 min after the hour (refresh + save + upload), shown in site time\n'
     'VAR s1 = IF(NOT ISBLANK(h1) && h1 >= 0, MOD(h1 + 0.5 - po + so, 24))\nVAR s2 = IF(NOT ISBLANK(h2) && h2 >= 0, MOD(h2 + 0.5 - po + so, 24))\n'
     'VAR t1 = IF(NOT ISBLANK(s1), FORMAT(TIME(INT(s1), ROUND(MOD(s1, 1) * 60, 0), 0), "hh:nn"))\n'
     'VAR t2 = IF(NOT ISBLANK(s2), FORMAT(TIME(INT(s2), ROUND(MOD(s2, 1) * 60, 0), 0), "hh:nn"))\n'
     'VAR gap = IF(ISBLANK(s1) || ISBLANK(s2), 24, MAX(MOD(s2 - s1, 24), MOD(s1 - s2, 24)))\n'
     'VAR ageH = (nw - l) * 24\n'
     'RETURN IF(ISBLANK(l) || ISBLANK([Site Code]), "",\n'
     '    IF(sched,\n'
     '        "data as of " & FORMAT(l, "ddd dd-mmm hh:nn")\n'
     '        & IF(NOT ISBLANK(t1), " · new copy on SharePoint daily ≈ " & t1 & IF(NOT ISBLANK(t2), " & " & t2, ""), "")\n'
     '        & " · now " & FORMAT(nw, "hh:nn") & " (site time UTC" & FORMAT(so, "+0;-0") & ")"\n'
     '        & IF(ageH > gap + 3, "  ⚠ this copy is " & FORMAT(ageH, "0") & " h old - open the current file in SharePoint (PRIME ELS > Hypercare KPI)", ""),\n'
     '        "refreshed " & FORMAT(l, "ddd hh:nn") & " · update: Home > Refresh · now " & FORMAT(nw, "hh:nn")\n'
     '        & " (site time UTC" & FORMAT(so, "+0;-0") & ")"))'),
]


def strip_twins():
    """Display twin '<m> (strip)' of every KPI-strip measure (kpi_strips.STRIPS): 0 instead of blank; the build gives it the base
    measure's unit format plus a zero section '–' (build_pbip.apply_strip_formats), so a multi-row card never shows '(Blank)'."""
    from kpi_strips import STRIPS, STRIP_SUFFIX
    seen, out = set(), []
    for fields in STRIPS.values():
        for m, _ in fields:
            if m not in seen:
                seen.add(m)
                out.append((m + STRIP_SUFFIX, "99 Display\\KPI strips", None,
                            f'-- KPI strip value of [{m}]: blank (no truck / user / pallet that day) shows as "–", never "(Blank)"\n'
                            f'[{m}] + 0'))
    return out


def all_measures(card_keys):
    return (CONTEXT + FLOW + TRUCK_DAY_MEASURES + TRUCKS + PALLETS + ORDERS + PEOPLE + SAP + LAST + SCORE_PREV + card_prev_measures(card_keys)
            + PROCESS_MINING + SHIFTS + GANTT + INVENTORY + REFRESH + STAGING + strip_twins())
