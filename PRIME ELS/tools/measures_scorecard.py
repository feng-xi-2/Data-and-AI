"""DAX measures - part 4: generic scorecard (target / warning / critical / prediction), alert control tower, narratives."""
import csv
import re
from pathlib import Path

from measures_core import thr, rca, fill

# config/kpi_explain.csv: how each KPI is calculated, the numbers behind it ({DAX|format} placeholders), prediction method, diagnosis
EXPLAIN = list(csv.DictReader(open(Path(__file__).resolve().parents[1] / "config" / "kpi_explain.csv", encoding="utf-8-sig")))


def numbers_dax(template):
    """'{[A] + [B]|#,##0} plt of ...' -> DAX text: literal pieces + FORMAT(expression, format); a blank input reads '-'."""
    parts, last = [], 0
    for m in re.finditer(r"\{([^{}|]+)\|([^{}]+)\}", template):
        if m.start() > last:
            parts.append('"' + template[last:m.start()].replace('"', '""') + '"')
        e, f = m.group(1).strip(), m.group(2).strip().replace('"', '""')
        parts.append(f'IF(ISBLANK({e}), "-", FORMAT({e}, "{f}"))')
        last = m.end()
    if last < len(template):
        parts.append('"' + template[last:].replace('"', '""') + '"')
    return " & ".join(parts) or '""'

ACTUAL = {
    "PPH": "[KPI PPH]", "RAMP_ATTAIN": "[KPI Ramp Attain]", "SHIFT_ATTAIN": "[KPI Shift Attain]",
    "LINES_IN_ALERT": "[KPI Lines In Alert]", "TREND_HOURS": "[KPI Trend Hours]", "RAMP_DAY_PLAN": "[Prod Ramp Plan Day]",
    "TTAT_IN": "[KPI TTAT In]", "TTAT_IN_MAX": "[KPI TTAT In Max]", "GR_TIME": "[KPI GR Time]",
    "TTAT_OUT": "[KPI TTAT Out]", "OUT_LOAD_TIME": "[KPI Out Load Time]", "PICK_A_SPLIT": "[KPI Pick A Split]",
    "LOC_UTIL": "[KPI Loc Util]", "LVLA_UTIL": "[KPI LevelA Util]", "MIN_SHORT": "[KPI Free Short]", "MIN_TALL": "[KPI Free Tall]",
    "HOFF_IN": "[KPI HOFF In]", "LTA_QUEUE": "[KPI LTA Queue]", "IMBALANCE": "[KPI Imbalance]", "STORE_A_SPLIT": "[KPI Store A Split]",
    "IDLE_A": "[KPI Idle A]", "USER_PROD": "[KPI User Productivity]", "ACTIVE_USERS": "[KPI Active Users]",
    "DATA_LAG": "[KPI Data Lag Min]", "REFRESH_AGE": "[KPI Refresh Age h]", "HEALTH_FAILS": "[KPI Health Fails]",
}
PREDICTED = {
    "PPH": "[KPI PPH Predicted]", "RAMP_ATTAIN": "[KPI Ramp Attain Predicted]", "TTAT_IN": "[KPI TTAT In Predicted]",
    "TTAT_OUT": "[KPI TTAT Out Predicted]", "LOC_UTIL": "[KPI Loc Util Predicted]", "LVLA_UTIL": "[KPI LevelA Util Predicted]",
}
CARD_KEYS = ["PPH", "TTAT_IN", "TTAT_OUT", "LOC_UTIL", "USER_PROD", "HEALTH_FAILS", "LVLA_UTIL", "GR_TIME"]
# KPIs measured against the clock at viewing time (refresh age, data lag, health checks that include them) are never snapshotted
LIVE_ONLY = {"DATA_LAG", "REFRESH_AGE", "HEALTH_FAILS"}
SNAP_KEYS = [k for k in ACTUAL if k not in LIVE_ONLY]


def _switch(mapping, default="BLANK()"):
    body = ",\n    ".join(f'"{k}", {v}' for k, v in mapping.items())
    return f'SWITCH(SELECTEDVALUE(Cfg_Threshold[KPI_Key]),\n    {body},\n    {default})'


def _eval(value_measure):
    return (f'VAR a = {value_measure}\n'
            'VAR dir = SELECTEDVALUE(Cfg_Threshold[Direction])\nVAR tgt = [Thr Eff Target]\n'
            'VAR w = [Thr Eff Warn]\nVAR c = [Thr Eff Crit]\n'
            'RETURN SWITCH(TRUE(),\n'
            '    ISBLANK(SELECTEDVALUE(Cfg_Threshold[KPI_Key])), BLANK(),\n'
            '    NOT [KPI Applicable], "N/A",\n    dir = "Info", "INFO",\n    ISBLANK(a), "NO DATA",\n'
            '    dir = "Higher", IF(a < c, "CRITICAL", IF(a < w, "WARNING", "OK")),\n'
            '    dir = "Lower", IF(a > c, "CRITICAL", IF(a > w, "WARNING", "OK")),\n'
            '    dir = "Band", VAR dev = ABS(a - tgt) RETURN IF(dev > c, "CRITICAL", IF(dev > w, "WARNING", "OK")),\n'
            '    "OK")')


ICON = 'SWITCH({s}, "CRITICAL", "🔴 ", "WARNING", "🟠 ", "OK", "🟢 ", "N/A", "⚪ ", "NO DATA", "⚫ ", "INFO", "ℹ ", "")'
COLOR = 'SWITCH({s}, "CRITICAL", "#D13438", "WARNING", "#F7A600", "OK", "#107C10", "#8A8886")'


def _fmt(v):
    # blank value: day older than the replica keeps -> say so; otherwise the configured "no activity" text of the KPI
    return (f'IF(ISBLANK({v}), IF(NOT [Report Day In Replica], "not in replica (keeps from " & FORMAT([Replica First Txn], "dd-mmm") & ")", '
            f'COALESCE(SELECTEDVALUE(Cfg_Threshold[No_Activity_Text]), "-")), '
            f'FORMAT({v}, SELECTEDVALUE(Cfg_Threshold[Format], "0.0")) & [KPI Unit Suffix])')


SCORECARD = [
    ("KPI Unit Suffix", "0 Scorecard", None,
     'VAR u = SELECTEDVALUE(Cfg_Threshold[Unit])\nVAR f = SELECTEDVALUE(Cfg_Threshold[Format], "0.0")\n'
     'RETURN IF(ISBLANK(u) || u = "" || u = "%" || CONTAINSSTRING(f, "%"), "", " " & u)'),
    ("Thr Target Text", "0 Scorecard\\Config", None,
     'VAR v = [Thr Eff Target] RETURN IF(NOT ISBLANK(v), FORMAT(v, SELECTEDVALUE(Cfg_Threshold[Format], "0.0")) & [KPI Unit Suffix])'),
    ("Thr Warn Text", "0 Scorecard\\Config", None,
     'VAR v = [Thr Eff Warn] RETURN IF(NOT ISBLANK(v) && SELECTEDVALUE(Cfg_Threshold[Direction]) <> "Info", FORMAT(v, SELECTEDVALUE(Cfg_Threshold[Format], "0.0")) & [KPI Unit Suffix])'),
    ("Thr Crit Text", "0 Scorecard\\Config", None,
     'VAR v = [Thr Eff Crit] RETURN IF(NOT ISBLANK(v) && SELECTEDVALUE(Cfg_Threshold[Direction]) <> "Info", FORMAT(v, SELECTEDVALUE(Cfg_Threshold[Format], "0.0")) & [KPI Unit Suffix])'),
    ("KPI Applicable", "0 Scorecard", None,
     'VAR req = SELECTEDVALUE(Cfg_Threshold[Requires])\n'
     'RETURN SWITCH(req, "Has_Production", [Feature Production] = 1, "Has_LevelA", [Feature LevelA] = 1, "Has_HOFF", [Feature HOFF] = 1, TRUE())'),
    ("KPI Actual Live", "0 Scorecard", "#,##0.00", 'IF([KPI Applicable], ' + _switch(ACTUAL) + ')'),
    ("KPI Snap Ok", "0 Scorecard", None,
     # default view (no day / hour / shift picked) and the snapshot is of the same report day -> read 'KPI Snapshot' (computed at refresh)
     'VAR k = SELECTEDVALUE(Cfg_Threshold[KPI_Key])\n'
     'RETURN NOT ISBLANK(k) && NOT ISFILTERED(DimDate) && NOT ISFILTERED(DimHour) && ISBLANK([Shift Selected])\n'
     "    && LOOKUPVALUE('KPI Snapshot'[Report_Date], 'KPI Snapshot'[SiteCode], [Site Code], 'KPI Snapshot'[KPI_Key], k) = [Report Date]"),
    ("KPI Actual", "0 Scorecard", "#,##0.00",
     '-- one KPI evaluation per refresh instead of per visual cell: the Daily report, Alerts and Cockpit read the snapshot in the default view.\n'
     '-- Shape matters (measured): the inner IF must test filters only (dflt) - the engine then skips the live branch for every row;\n'
     '-- any lookup / key test in that condition makes it evaluate [KPI Actual Live] eagerly (2.3 s instead of 1.1 s for the Daily report).\n'
     '-- The default report day only moves with refreshed data (newest activity day, capped at today), so the snapshot cannot be stale.\n'
     'VAR k = SELECTEDVALUE(Cfg_Threshold[KPI_Key])\n'
     'VAR dflt = NOT ISFILTERED(DimDate) && NOT ISFILTERED(DimHour) && ISBLANK([Shift Selected])\n'
     "RETURN IF([KPI Snap Ok], LOOKUPVALUE('KPI Snapshot'[Actual], 'KPI Snapshot'[SiteCode], [Site Code], 'KPI Snapshot'[KPI_Key], k),\n"
     '    IF(dflt, IF([KPI Applicable], ' + _switch({k: ACTUAL[k] for k in sorted(LIVE_ONLY)}).replace("SELECTEDVALUE(Cfg_Threshold[KPI_Key])", "k") + '),\n'
     '    [KPI Actual Live]))'),
    ("KPI Show", "0 Scorecard", "0",
     'VAR k = SELECTEDVALUE(Cfg_Threshold[KPI_Key])\nRETURN IF(SELECTEDVALUE(Cfg_Threshold[Direction]) <> "Info" && k IN {' +
     ", ".join(f'"{k}"' for k in ACTUAL) + '} && [KPI Applicable], 1, 0)'),
    ("KPI Predicted Live", "0 Scorecard", "#,##0.00", 'IF([KPI Applicable], ' + _switch(PREDICTED) + ')'),
    ("KPI Predicted", "0 Scorecard", "#,##0.00",
     '-- same shape as [KPI Actual]: forecasts of the default view come from the snapshot (no forecast KPI is clock-based)\n'
     'VAR k = SELECTEDVALUE(Cfg_Threshold[KPI_Key])\n'
     'VAR dflt = NOT ISFILTERED(DimDate) && NOT ISFILTERED(DimHour) && ISBLANK([Shift Selected])\n'
     "RETURN IF([KPI Snap Ok], LOOKUPVALUE('KPI Snapshot'[Predicted], 'KPI Snapshot'[SiteCode], [Site Code], 'KPI Snapshot'[KPI_Key], k),\n"
     '    IF(dflt, BLANK(), [KPI Predicted Live]))'),
    ("KPI Status", "0 Scorecard", None, _eval("[KPI Actual]")),
    ("KPI Predicted Status", "0 Scorecard", None,
     # forecast evaluated ONCE (VAR): ISBLANK([KPI Predicted]) + a second [KPI Predicted] doubled the cost of every forecast cell
     'VAR p = [KPI Predicted]\nRETURN IF(ISBLANK(p), BLANK(), ' + _eval("p") + ')'),
    ("KPI Actual Text", "0 Scorecard", None,
     'VAR v = [KPI Actual] RETURN IF(NOT [KPI Applicable], "N/A - not run at this site", ' + _fmt("v") + ')'),
    ("KPI Predicted Text", "0 Scorecard", None, 'VAR v = [KPI Predicted] RETURN IF(ISBLANK(v), "", ' + _fmt("v") + ')'),
    ("KPI Target Text", "0 Scorecard", None,
     'VAR dir = SELECTEDVALUE(Cfg_Threshold[Direction])\nVAR f = SELECTEDVALUE(Cfg_Threshold[Format], "0.0")\n'
     'VAR t = [Thr Eff Target]\nVAR w = [Thr Eff Warn]\nVAR c = [Thr Eff Crit]\n'
     'VAR u = [KPI Unit Suffix]\n'
     'RETURN SWITCH(dir,\n'
     '    "Higher", ">= " & FORMAT(t, f) & u & "  (warn < " & FORMAT(w, f) & ", crit < " & FORMAT(c, f) & ")",\n'
     '    "Lower", "<= " & FORMAT(t, f) & u & "  (warn > " & FORMAT(w, f) & ", crit > " & FORMAT(c, f) & ")",\n'
     '    "Band", FORMAT(t, f) & u & " +/- " & FORMAT(w, f) & "  (crit +/- " & FORMAT(c, f) & ")",\n'
     '    "Info", FORMAT(t, f) & u, "")'),
    ("KPI Target Short", "0 Scorecard", None,
     'VAR dir = SELECTEDVALUE(Cfg_Threshold[Direction])\nVAR f = SELECTEDVALUE(Cfg_Threshold[Format], "0.0")\n'
     'VAR t = [Thr Eff Target]\nVAR u = [KPI Unit Suffix]\n'
     'RETURN SWITCH(dir, "Higher", "≥ ", "Lower", "≤ ", "") & FORMAT(t, f) & u'),
    ("KPI Limits Short", "0 Scorecard", None,
     'VAR dir = SELECTEDVALUE(Cfg_Threshold[Direction])\nVAR f = SELECTEDVALUE(Cfg_Threshold[Format], "0.0")\n'
     'VAR w = [Thr Eff Warn]\nVAR c = [Thr Eff Crit]\n'
     'RETURN SWITCH(dir,\n'
     '    "Higher", "warn < " & FORMAT(w, f) & " · crit < " & FORMAT(c, f),\n'
     '    "Lower", "warn > " & FORMAT(w, f) & " · crit > " & FORMAT(c, f),\n'
     '    "Band", "warn ± " & FORMAT(w, f) & " · crit ± " & FORMAT(c, f), "")'),
    ("Daily Value", "0 Scorecard\\Daily report", None, 'IF([KPI Show] = 1, [KPI Actual Text])'),
    ("Daily Target", "0 Scorecard\\Daily report", None, 'IF([KPI Show] = 1, [KPI Target Text])'),
    ("Daily Status", "0 Scorecard\\Daily report", None, 'IF([KPI Show] = 1, [KPI Status Label])'),
    ("Daily Predicted", "0 Scorecard\\Daily report", None, 'IF([KPI Show] = 1, [KPI Predicted Text])'),
    ("KPI Status Label", "0 Scorecard", None, 'VAR s = [KPI Status] RETURN ' + ICON.format(s="s") + ' & s'),
    ("KPI Predicted Status Label", "0 Scorecard", None, 'VAR s = [KPI Predicted Status] RETURN IF(ISBLANK(s), "", ' + ICON.format(s="s") + ' & s)'),
    ("KPI Status Color", "0 Scorecard", None, 'VAR s = [KPI Status] RETURN ' + COLOR.format(s="s")),
    ("KPI Predicted Status Color", "0 Scorecard", None, 'VAR s = [KPI Predicted Status] RETURN ' + COLOR.format(s="s")),
    ("KPI Predicted Summary", "0 Scorecard", None,
     # "<forecast value>  <icon> <status>" from ONE forecast evaluation (cards + alert tower); blank = no forecast for this KPI
     'VAR v = [KPI Predicted]\nRETURN IF(ISBLANK(v), BLANK(),\n    VAR s = (' + _eval("v") + ')\n    RETURN ' + _fmt("v") + ' & "  " & ' + ICON.format(s="s") + ' & s)'),
]

for k in CARD_KEYS:
    flt = f'Cfg_Threshold[KPI_Key] = "{k}"'
    SCORECARD += [
        (f"Card {k} Value", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Actual Text], {flt})'),
        (f"Card {k} Status", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Status Label], {flt})'),
        (f"Card {k} Target", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Target Short], {flt})'),
        (f"Card {k} Limits", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Limits Short], {flt})'),
        (f"Card {k} Predicted", "0 Scorecard\\Cards", None,
         f'CALCULATE(COALESCE([KPI Predicted Summary], "no forecast"), {flt})'),
        (f"Card {k} Color", "0 Scorecard\\Cards", None, f'CALCULATE([KPI Status Color], {flt})'),
        (f"Card {k} Name", "0 Scorecard\\Cards", None,
         f'CALCULATE(SELECTEDVALUE(Cfg_Threshold[KPI_Name]), {flt})'),
    ]

ALERT_CTX = 'TREATAS({SELECTEDVALUE(Cfg_AlertRule[KPI_Key])}, Cfg_Threshold[KPI_Key])'


def _rule_ctx(expr):
    """Evaluate expr in the KPI context of the ONE alert rule in context: iterate the rule's key in Cfg_Threshold (context transition).
    Same values as CALCULATE(expr, ALERT_CTX) (checked per rule), measured 1.7 s vs 2.9 s per control-tower column at Jakarta."""
    return ('IF(HASONEVALUE(Cfg_AlertRule[Rule_No]), MAXX(FILTER(ALL(Cfg_Threshold[KPI_Key]), '
            f'Cfg_Threshold[KPI_Key] = SELECTEDVALUE(Cfg_AlertRule[KPI_Key])), CALCULATE({expr})))')


ALERTS = [
    ("Alert Status", "7 Alerts", None, _rule_ctx("[KPI Status]")),
    ("Alert Status Label", "7 Alerts", None, 'VAR s = [Alert Status] RETURN IF(ISBLANK(s), BLANK(), ' + ICON.format(s="s") + ' & s)'),
    ("Alert Status Color", "7 Alerts", None, 'VAR s = [Alert Status] RETURN ' + COLOR.format(s="s")),
    ("Alert Actual", "7 Alerts", None, _rule_ctx("[KPI Actual Text]")),
    ("Alert Threshold", "7 Alerts", None, f'IF(HASONEVALUE(Cfg_AlertRule[Rule_No]), CALCULATE([KPI Target Text], {ALERT_CTX}))'),
    ("Alert Predicted", "7 Alerts", None,
     # rules whose KPI has no forecast exit before the KPI chain (17 of 23 rules: 16.9 s -> ~1 s for the control tower column)
     'VAR k = SELECTEDVALUE(Cfg_AlertRule[KPI_Key])\n'
     'RETURN IF(HASONEVALUE(Cfg_AlertRule[Rule_No]) && k IN {' + ", ".join(f'"{k}"' for k in PREDICTED) + '}, '
     'CALCULATE([KPI Predicted Summary], TREATAS({k}, Cfg_Threshold[KPI_Key])))'),
    ("Alert Insight", "7 Alerts", None,
     'IF([Alert Status] IN {"WARNING", "CRITICAL"}, SELECTEDVALUE(Cfg_AlertRule[Insight_If_Breached]), "")'),
    ("Alert Action", "7 Alerts", None,
     'SWITCH([Alert Status], "WARNING", SELECTEDVALUE(Cfg_AlertRule[Recommended_Action]), "CRITICAL", SELECTEDVALUE(Cfg_AlertRule[Recommended_Action]), '
     '"N/A", "Not applicable for this site", "NO DATA", "Check the feed on the Health page", "No action")'),
    ("Alerts Critical", "7 Alerts", "0", 'SUMX(ALL(Cfg_AlertRule), IF([Alert Status] = "CRITICAL", 1, 0))'),
    ("Alerts Warning", "7 Alerts", "0", 'SUMX(ALL(Cfg_AlertRule), IF([Alert Status] = "WARNING", 1, 0))'),
    # "What to do now" table: one row per breached rule (blank = row hidden), critical first. [Alert Status] evaluates the
    # whole KPI chain -> computed ONCE per measure (VAR), never twice through a helper measure
    ("Open Alert Status", "7 Alerts", None,
     'VAR s = [Alert Status]\nRETURN IF(s IN {"WARNING", "CRITICAL"}, ' + ICON.format(s="s") + ' & s)'),
    ("Open Alert Action", "7 Alerts", None,
     'VAR s = [Alert Status]\nRETURN IF(s IN {"WARNING", "CRITICAL"}, SELECTEDVALUE(Cfg_AlertRule[Recommended_Action]))'),
    ("Open Alert Actual", "7 Alerts", None,
     # status AND value from ONE [KPI Actual] evaluation (VARs); [Alert Status] + [Alert Actual] ran the KPI chain twice per rule.
     # A breached status implies an applicable KPI with a value, so the text is the formatted value
     'VAR k = SELECTEDVALUE(Cfg_AlertRule[KPI_Key])\nRETURN IF(HASONEVALUE(Cfg_AlertRule[Rule_No]), CALCULATE(\n'
     '    VAR a = [KPI Actual]\n    VAR s = (' + _eval("a") + ')\n    RETURN IF(s IN {"WARNING", "CRITICAL"}, ' + _fmt("a") + '),\n'
     '    TREATAS({k}, Cfg_Threshold[KPI_Key])))'),
    ("Open Alert Rank", "7 Alerts", "0", 'SWITCH([Alert Status], "CRITICAL", 1, "WARNING", 2)'),
    ("Open Alert Text", "7 Alerts", None,
     # cockpit "What to do now": status + actual vs target + action of a BREACHED rule from ONE KPI evaluation (blank = row hidden).
     # Separate status / colour / actual / action columns ran the KPI chain 4x per rule (22 s on the landing page)
     'VAR act = SELECTEDVALUE(Cfg_AlertRule[Recommended_Action])\nRETURN ' +
     _rule_ctx('\n    VAR x = [KPI Actual]\n    VAR s = (' + _eval("x") + ')\n'
               '    RETURN IF(s IN {"WARNING", "CRITICAL"}, ' + ICON.format(s="s") + ' & s & "  ·  " & ' + _fmt("x") +
               ' & " (target " & [KPI Target Short] & ")  ->  " & act)\n')),
    ("Overall Alert State", "7 Alerts", None,
     # every rule's status ONCE (table VAR) for both counts - [Alerts Critical] + [Alerts Warning] ran the KPI chain twice
     'VAR st = ADDCOLUMNS(ALL(Cfg_AlertRule), "@s", [Alert Status])\n'
     'VAR c = COUNTROWS(FILTER(st, [@s] = "CRITICAL")) + 0\nVAR w = COUNTROWS(FILTER(st, [@s] = "WARNING")) + 0\n'
     'RETURN IF(c + w = 0, "✅ " & ' + rca("NARRATIVE", '"ALL_CLEAR"') + ', IF(c > 0, "🔴 " & ' +
     fill(rca("NARRATIVE", '"STATE_CRIT"'), {"crit": "c", "warn": "w"}) + ', "🟠 " & ' + fill(rca("NARRATIVE", '"STATE_WARN"'), {"warn": "w"}) + '))'),
    ("Narrative Production Outlook", "7 Alerts", None,
     'VAR k = IF([Feature Production] <> 1, "PROD_OFF", IF([Prod Pallets Day] = 0, "PROD_NONE", '
     'IF([Prod Projected EOD] < [Prod Ramp Plan Day], "PROD_BEHIND", "PROD_ONTRACK")))\n'
     'VAR t = ' + rca("NARRATIVE", "k") + '\nRETURN ' +
     fill("t", {"rate": 'FORMAT(COALESCE([Prod Run Rate 3h], [KPI PPH], 0), "0.0")', "proj": 'FORMAT(COALESCE([Prod Projected EOD], 0), "#,##0")',
                "plan": 'FORMAT([Prod Ramp Plan Day], "#,##0")', "req": 'FORMAT(COALESCE([Prod Required Rate], 0), "0")',
                "last": 'IF(ISBLANK([Prod Last Pallet Time]), "never in the loaded window", FORMAT([Prod Last Pallet Time], "ddd dd-mmm hh:00"))',
                "hours": 'FORMAT([Elapsed Hours], "0.0")'})),
    ("Verdict Key", "7 Alerts", None,
     'SWITCH(TRUE(),\n'
     f'  [Feature LevelA] = 1 && [KPI Idle A] > {thr("IDLE_A", "Warn_At")} && [KPI Free Short] >= {thr("MIN_SHORT")} && [KPI Free Tall] >= {thr("MIN_TALL")}, "SPACE_ALLOC",\n'
     f'  [Feature LevelA] = 1 && ([KPI Free Short] < {thr("MIN_SHORT")} || [KPI Free Tall] < {thr("MIN_TALL")}), "RACKING",\n'
     f'  [KPI Loc Util] > {thr("LOC_UTIL", "Warn_At")}, "WH_FULL",\n'
     '  [KPI Lines In Alert] > 0, "LINE", "NONE")'),
    ("Narrative Verdict", "7 Alerts", None,
     'VAR t = ' + rca("VERDICT", "[Verdict Key]") + '\nRETURN ' +
     fill("t", {"free_short": 'FORMAT([KPI Free Short], "0")', "free_tall": 'FORMAT([KPI Free Tall], "0")', "idle_locs": 'FORMAT([LevelA Idle Locations], "0")',
                "loc_util": 'FORMAT([KPI Loc Util], "0.0%")', "lines": 'FORMAT([KPI Lines In Alert], "0")',
                "runway": 'IF(ISBLANK([Space Runway Hours]), "", ", ~" & FORMAT([Space Runway Hours], "0") & " h until critical")'})),
    ("Narrative Fix Order", "7 Alerts", None,
     'VAR st = ADDCOLUMNS(ALL(Cfg_AlertRule), "@s", [Alert Status])\n'
     'VAR useCrit = NOT ISEMPTY(FILTER(st, [@s] = "CRITICAL"))\n'
     'VAR lst = FILTER(st, [@s] = IF(useCrit, "CRITICAL", "WARNING"))\n'
     'RETURN IF(COUNTROWS(lst) = 0, ' + rca("NARRATIVE", '"FIX_NONE"') + ', ' + rca("NARRATIVE", '"FIX_ORDER"') + ' & " " & '
     'CONCATENATEX(lst, "#" & Cfg_AlertRule[Rule_No] & " " & Cfg_AlertRule[Recommended_Action], "   |   ", Cfg_AlertRule[Rule_No], ASC))'),
]

ALL_SCORECARD = SCORECARD + ALERTS

# ---------------------------------------------------------------- why it is an alert / numbers / how calculated / prediction / diagnosis
# One [KPI Actual] evaluation per cell; names differ from _eval's inner a / dir / tgt / w / c (nested VAR blocks).
WHY_BODY = (
    'VAR x = [KPI Actual]\n'
    'VAR s = (' + _eval("x") + ')\n'
    'VAR fm = SELECTEDVALUE(Cfg_Threshold[Format], "0.0")\nVAR un = [KPI Unit Suffix]\nVAR dr = SELECTEDVALUE(Cfg_Threshold[Direction])\n'
    'VAR tg = [Thr Eff Target]\nVAR wn = [Thr Eff Warn]\nVAR cr = [Thr Eff Crit]\n'
    'VAR xv = FORMAT(x, fm) & un\nVAR tv = FORMAT(tg, fm) & un\n'
    'VAR lim = IF(s = "CRITICAL", "critical limit " & FORMAT(cr, fm) & un, "warning limit " & FORMAT(wn, fm) & un)\n'
    'VAR breach = SWITCH(dr,\n'
    '    "Higher", "actual " & xv & " is below the " & lim & " (target >= " & tv & ")",\n'
    '    "Lower", "actual " & xv & " is above the " & lim & " (target <= " & tv & ")",\n'
    '    "Band", "actual " & xv & " is " & FORMAT(ABS(x - tg), fm) & un & " away from the target " & tv & " (" & IF(s = "CRITICAL", "critical", "warning") '
    '& " band +/- " & FORMAT(IF(s = "CRITICAL", cr, wn), fm) & un & ")",\n'
    '    "actual " & xv)\n'
    'VAR why = SWITCH(s,\n'
    '    "CRITICAL", "CRITICAL: " & breach, "WARNING", "WARNING: " & breach,\n'
    '    "OK", "OK: actual " & xv & " meets the target " & IF(dr = "Higher", ">= ", IF(dr = "Lower", "<= ", "")) & tv,\n'
    '    "NO DATA", "No data: " & COALESCE(SELECTEDVALUE(Cfg_Threshold[No_Activity_Text]), "no activity in the report day"),\n'
    '    "N/A", "Not used at this site", "INFO", "Info: " & xv, BLANK())\n')
EXPLAIN_LOOKUP = 'LOOKUPVALUE(Cfg_KpiExplain[{col}], Cfg_KpiExplain[KPI_Key], {key})'

WHY = [
    ("KPI Why Text", "0 Scorecard", None, WHY_BODY + 'RETURN why'),
    ("KPI Numbers Text", "0 Scorecard", None,
     '-- the numbers behind the KPI (config/kpi_explain.csv Numbers template) - only the selected KPI branch runs\n'
     'SWITCH(SELECTEDVALUE(Cfg_Threshold[KPI_Key]),\n    '
     + ",\n    ".join(f'"{r["KPI_Key"]}", {numbers_dax(r["Numbers"])}' for r in EXPLAIN if r["Numbers"].strip()) + ',\n    BLANK())'),
    ("KPI How Text", "0 Scorecard", None, EXPLAIN_LOOKUP.format(col="How_Calculated", key="SELECTEDVALUE(Cfg_Threshold[KPI_Key])")),
    ("KPI Prediction Method", "0 Scorecard", None, EXPLAIN_LOOKUP.format(col="Prediction_Method", key="SELECTEDVALUE(Cfg_Threshold[KPI_Key])")),
    ("KPI Diagnosis", "0 Scorecard", None, EXPLAIN_LOOKUP.format(col="Diagnosis", key="SELECTEDVALUE(Cfg_Threshold[KPI_Key])")),
    ("Alert Why", "7 Alerts", None,
     '-- status icon + why the rule is (not) an alert: actual vs the breached limit and the target, + the probable cause when breached.\n'
     '-- ONE KPI evaluation per rule carries status, actual and limit (the control tower has no separate status / actual columns)\n'
     'VAR cause = SELECTEDVALUE(Cfg_AlertRule[Insight_If_Breached])\n'
     'RETURN ' + _rule_ctx('\n' + WHY_BODY +
                           'RETURN IF(ISBLANK(why), BLANK(), ' + ICON.format(s="s") + ' & why & '
                           'IF(s IN {"WARNING", "CRITICAL"} && NOT ISBLANK(cause) && cause <> "", " -> probable cause: " & cause))\n')),
    ("Alert Numbers", "7 Alerts", None, _rule_ctx("[KPI Numbers Text]")),
    ("Alert Detail Text", "7 Alerts", None,
     '-- detail panel of the rule clicked in the control tower (cross-filter); one rule = one evaluation\n'
     'VAR k = SELECTEDVALUE(Cfg_AlertRule[KPI_Key])\n'
     'RETURN IF(NOT HASONEVALUE(Cfg_AlertRule[Rule_No]),\n'
     '    "Click a rule in the control tower: this panel shows why it is an alert, the numbers behind it, how it is calculated, '
     'how the prediction is made and what to check.   " & [Narrative Fix Order],\n'
     '    "#" & SELECTEDVALUE(Cfg_AlertRule[Rule_No]) & " " & SELECTEDVALUE(Cfg_AlertRule[Rule]) & "   |   WHY: " & [Alert Why]\n'
     '    & "   |   NUMBERS: " & COALESCE([Alert Numbers], "-")\n'
     '    & "   |   HOW IT IS CALCULATED: " & ' + EXPLAIN_LOOKUP.format(col="How_Calculated", key="k") + '\n'
     '    & "   |   PREDICTION: " & COALESCE([Alert Predicted], "no forecast") & " - " & ' + EXPLAIN_LOOKUP.format(col="Prediction_Method", key="k") + '\n'
     '    & "   |   DIAGNOSIS: " & ' + EXPLAIN_LOOKUP.format(col="Diagnosis", key="k") + '\n'
     '    & "   |   ACTION: " & SELECTEDVALUE(Cfg_AlertRule[Recommended_Action]))'),
]
ALL_SCORECARD += WHY
