"""Add the Hypercare pages (PBIR) to the copied BD Throughput report. Existing pages are kept untouched."""
import json
import hashlib
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from measures_core import INPUTS, INPUT_LEVELS, input_table  # noqa: E402
from kpi_strips import strip  # noqa: E402
from pbi_common import read_csv, sap_included, SAP_PAGES  # noqa: E402

_OPTS = {r["Setting"]: r["Value"].strip() for r in read_csv("build_options.csv")} if (Path(__file__).resolve().parents[1] / "config" / "build_options.csv").exists() else {}
INPUTS_WHEN = ("copied into this file when it is built (change = edit the workbook, then rebuild)" if _OPTS.get("Embed_Inputs", "1") == "1"
               else "read at every refresh")

VSCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
PSCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
K = "_KPI"
NAVY, GREY, LIGHT = "#0B2A4A", "#605E5C", "#F3F6FA"


def hid(*p):
    return hashlib.sha1("|".join(p).encode()).hexdigest()[:20]


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def fld(entity, prop, measure):
    return {("Measure" if measure else "Column"): {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(entity, prop, measure=True, label=None):
    p = {"field": fld(entity, prop, measure), "queryRef": f"{entity}.{prop}", "nativeQueryRef": label or prop}
    if label:
        p["displayName"] = label
    return p


def container(page, key, vtype, x, y, w, h, z, visual_extra, title=None, border=True):
    """Border / shadow / background come from the theme (PRIME_ELS_Theme.json) so every tab looks the same; border=False = bare."""
    vco = {"title": [{"properties": {"show": lit("true" if title else "false"), **({"text": lit(f"'{title}'")} if title else {})}}]}
    if not border:
        vco["border"] = [{"properties": {"show": lit("false")}}]
        vco["dropShadow"] = [{"properties": {"show": lit("false")}}]
    v = {"visualType": vtype, **visual_extra, "visualContainerObjects": vco, "drillFilterOtherVisuals": True}
    return {"$schema": VSCHEMA, "name": hid(page, key), "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
            "visual": v}


def subtitle(c, measure, size=8):
    """Dynamic subtitle from a text measure (e.g. which day a chart shows and why); the literal title stays for the test tools."""
    c["visual"]["visualContainerObjects"]["subTitle"] = [{"properties": {"show": lit("true"), "text": {"expr": fld(K, measure, True)},
                                                                         "fontSize": lit(f"{size}D"), "titleWrap": lit("true")}}]
    return c


def textbox(page, key, x, y, w, h, z, runs, align="left", bg=None):
    paras = [{"textRuns": [{"value": t, "textStyle": st}], "horizontalTextAlignment": align} for t, st in runs]
    c = container(page, key, "textbox", x, y, w, h, z, {"objects": {"general": [{"properties": {"paragraphs": paras}}]}}, border=False)
    if bg:
        c["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit(f"'{bg}'")}}}}]
    return c


def card(page, key, x, y, w, h, z, measures, title=None, value_size=18, cols=1, color_measure=None):
    """Classic multi-row card (robust with text measures). cols kept for call compatibility (multi-row card wraps by width)."""
    objects = {"dataLabels": [{"properties": {"fontSize": lit(f"{value_size}D"), "fontFamily": lit("'Segoe UI Semibold'")}}],
               "categoryLabels": [{"properties": {"show": lit("true"), "fontSize": lit("9D"), "color": {"solid": {"color": lit(f"'{GREY}'")}}}}],
               "card": [{"properties": {"outlineStyle": lit("0D"), "barShow": lit("false"), "cardPadding": lit("4D")}}],
               "wordWrap": [{"properties": {"show": lit("true")}}]}
    if color_measure:
        objects["dataLabels"][0]["properties"]["color"] = {"solid": {"color": {"expr": fld(K, color_measure, True)}}}
    q = {"queryState": {"Values": {"projections": [proj(K, m, True, lbl) for m, lbl in measures]}}}
    return container(page, key, "multiRowCard", x, y, w, h, z, {"query": q, "objects": objects}, title)


def single_card(page, key, x, y, w, h, z, measure, size, color, bold=True, align="left"):
    """Classic card for one text value (banner title / context)."""
    objects = {"labels": [{"properties": {"fontSize": lit(f"{size}D"), "color": {"solid": {"color": lit(f"'{color}'")}},
                                          "fontFamily": lit("'Segoe UI Semibold'" if bold else "'Segoe UI'")}}],
               "categoryLabels": [{"properties": {"show": lit("false")}}],
               "wordWrap": [{"properties": {"show": lit("true")}}]}
    q = {"queryState": {"Values": {"projections": [proj(K, measure, True, measure)]}}}
    c = container(page, key, "card", x, y, w, h, z, {"query": q, "objects": objects}, border=False)
    vco = c["visual"]["visualContainerObjects"]
    vco["background"] = [{"properties": {"show": lit("false")}}]
    vco["dropShadow"] = [{"properties": {"show": lit("false")}}]
    return c

def text_card(page, key, x, y, w, h, z, measure, title, size=11):
    """Classic card with word wrap - for long narrative sentences (multi-row cards cut them to one line)."""
    c = single_card(page, key, x, y, w, h, z, measure, size, "#1F2D3D", bold=False)
    vco = c["visual"]["visualContainerObjects"]
    vco["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}]
    for k in ("border", "background", "dropShadow"):
        vco.pop(k, None)
    return c


def table(page, key, x, y, w, h, z, fields, title, color_rules=(), sort=None, widths=None):
    """fields: (entity, prop, is_measure, label). color_rules: (status_field_prop, color_measure_prop). widths: {prop: px}."""
    q = {"queryState": {"Values": {"projections": [proj(e, p, m, lbl) for e, p, m, lbl in fields]}}}
    if sort:
        e, p, m, d = sort
        q["sortDefinition"] = {"sort": [{"field": fld(e, p, m), "direction": d}], "isDefaultSort": True}
    vals = [{"properties": {"fontSize": lit("9D"), "wordWrap": lit("true")}}]
    for status_prop, color_prop in color_rules:
        ent = next(e for e, p, m, lbl in fields if p == status_prop)
        vals.append({"properties": {"fontColor": {"solid": {"color": {"expr": fld(K, color_prop, True)}}}},
                     "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{ent}.{status_prop}"}})
    objects = {"values": vals, "columnHeaders": [{"properties": {"fontSize": lit("9D"), "bold": lit("true"), "wordWrap": lit("true")}}],
               "total": [{"properties": {"totals": lit("false")}}]}
    if widths:
        objects["columnWidth"] = [{"properties": {"value": lit(f"{px}D")}, "selector": {"metadata": f"{e}.{p}"}}
                                  for e, p, m, lbl in fields if p in widths for px in [widths[p]]]
    return container(page, key, "tableEx", x, y, w, h, z, {"query": q, "objects": objects}, title)


def slicer(page, key, x, y, w, h, z, entity, prop, title):
    q = {"queryState": {"Values": {"projections": [dict(proj(entity, prop, False), active=True)]}},
         "sortDefinition": {"sort": [{"field": fld(entity, prop, False), "direction": "Descending"}]}}
    objects = {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
               "selection": [{"properties": {"singleSelect": lit("true")}}],
               "header": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}]}
    return container(page, key, "slicer", x, y, w, h, z, {"query": q, "objects": objects})


def column_chart(page, key, x, y, w, h, z, cat, values, title, vtype="clusteredColumnChart"):
    q = {"queryState": {"Category": {"projections": [dict(proj(*cat[:2], False), active=True)]},
                        "Y": {"projections": [proj(K, m, True, lbl) for m, lbl in values]}}}
    return container(page, key, vtype, x, y, w, h, z, {"query": q}, title)



# ============================================================== layout (best practice: banner -> filters -> KPIs -> detail -> guide)
# header = navy strip (title, page, refresh info) + filter bar (Site | Day | Shift | report window) - the same on every page
W, TOP_H, FILTER_H, GUIDE_H, BODY_H = 1280, 50, 58, 86, 720
BANNER_H = TOP_H + FILTER_H
FILTER_BG = "#E6EDF6"
PAGE_H = BANNER_H + BODY_H + GUIDE_H
TH, AR, HC, PG = "Cfg_Threshold", "Cfg_AlertRule", "Cfg_HealthCheck", "Cfg_PageGuide"

# existing BD pages: page id -> (new display name or None, guide key)
EXISTING = {
    "d6eb503d1ea76336e4a5": ("Home", "HOME"), "674fce0b066e4467e9a1": (None, "SYNC"), "c93d18fb38fce051a7c5": (None, "INV"),
    "9a232c2895c5641345d0": (None, "PROD"), "e37cebb31ef2cae44098": (None, "PRED"), "c50d611119e594ca0481": (None, "TTAT"),
    "eb9511b96faae5d9e3c1": (None, "SHORTPO"), "03deab134c26e7230826": ("RPM Material Readiness", "RPM"),
    "06950963f1b0d511e685": (None, "ACTIVITY"),
}
REMOVE = {"3c1bff86cb3f5f44dcd0": "empty hidden 'Page 1'", "ae97b9824a3091f896fe": "'Duplicate of Inv Status' (duplicates Activity Tracking + Produced Plt/h)"}
REMOVE_VISUALS = {"067a4bc103ddd7d88183": "hard-coded market colour legend -> Cfg_Market table on Home"}
STRIP_TEXT = ["Binh Duong "]


def page_filter(entity, prop, value):
    return {"filters": [{"name": hid(entity, prop, value), "field": fld(entity, prop, False), "type": "Categorical",
                         "filter": {"Version": 2, "From": [{"Name": "c", "Entity": entity, "Type": 0}],
                                    "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": prop}}],
                                                                    "Values": [[{"Literal": {"Value": f"'{value}'"}}]]}}}]}}]}


def measure_filter(measure, value_literal):
    return {"filters": [{"name": hid(measure, value_literal), "field": fld(K, measure, True), "type": "Advanced",
                         "filter": {"Version": 2, "From": [{"Name": "k", "Entity": K, "Type": 0}],
                                    "Where": [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                                                            "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "k"}}, "Property": measure}},
                                                                            "Right": {"Literal": {"Value": value_literal}}}}}]}}]}


def in_filter(entity, prop, value):
    return {"Version": 2, "From": [{"Name": "c", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": prop}}],
                                            "Values": [[{"Literal": {"Value": f"'{value}'"}}]]}}}]}


# process sections (config/page_guide.csv Section): tab order, banner label and the grouped Home index
_GUIDE = read_csv("page_guide.csv")
SECTION = {r["Page_Key"]: r["Section"] for r in _GUIDE}
GUIDE_ORDER = [r["Page_Key"] for r in _GUIDE]

SITE_ENT, SITE_PROP = "Cfg_Site", "SiteName"
DEFAULT_SITE = {"name": ""}          # set by add_pages (Cfg_Site row with Is_Default = 1)


def site_slicer(page, x, y, w, h, z):
    """Site picker: dropdown, single select + force selection, synced on every page (sync group 'Site') - in the filter bar."""
    q = {"queryState": {"Values": {"projections": [dict(proj(SITE_ENT, SITE_PROP, False, "Site"), active=True)]}},
         "sortDefinition": {"sort": [{"field": fld(SITE_ENT, SITE_PROP, False), "direction": "Ascending"}]}}
    objects = {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
               "selection": [{"properties": {"singleSelect": lit("true"), "strictSingleSelect": lit("true")}}],
               "header": [{"properties": {"show": lit("true"), "text": lit("'Site'"), "fontColor": {"solid": {"color": lit(f"'{NAVY}'")}},
                                          "textSize": lit("8D")}}],
               "items": [{"properties": {"textSize": lit("11D")}}]}
    if DEFAULT_SITE["name"]:
        objects["general"] = [{"properties": {"filter": {"filter": in_filter(SITE_ENT, SITE_PROP, DEFAULT_SITE["name"])}}}]
    c = container(page, "site_slicer", "slicer", x, y, w, h, z,
                  {"query": q, "objects": objects, "syncGroup": {"groupName": "Site", "fieldChanges": True, "filterChanges": True}}, border=False)
    c["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": lit("false")}}]
    c["visual"]["visualContainerObjects"]["padding"] = [{"properties": {"top": lit("0D"), "bottom": lit("0D"), "left": lit("4D"), "right": lit("4D")}}]
    return c


def input_slicer(page, kpi, lvl, x, y, w, h, z, hidden=False):
    """What-if input box (single value) for one KPI threshold level; synced on every page so all tabs use the typed value."""
    ent = input_table(kpi, lvl)
    q = {"queryState": {"Values": {"projections": [dict(proj(ent, "Value", False, "Value"), active=True)]}}}
    objects = {"data": [{"properties": {"mode": lit("'Single'")}}], "header": [{"properties": {"show": lit("false")}}],
               "numericInputStyle": [{"properties": {"textSize": lit("11D")}}]}
    c = container(page, f"in_{kpi}_{lvl}", "slicer", x, y, w, h, z,
                  {"query": q, "objects": objects, "syncGroup": {"groupName": ent, "fieldChanges": True, "filterChanges": True}}, border=not hidden)
    if hidden:
        c["isHidden"] = True
    return c


def synced_inputs(page):
    """Hidden copies of every threshold input box (sync slicers need one copy per page)."""
    return [input_slicer(page, r["KPI_Key"], lvl, 0, 0, 40, 20, 8000 + i, hidden=True)
            for i, (r, (lvl, _)) in enumerate((r, l) for r in INPUTS for l in INPUT_LEVELS)]


def global_slicer(page, key, x, y, w, h, z, entity, prop, title, group, descending=False):
    """Dropdown, single select, synced on EVERY page (sync group) - one Day / Shift choice drives the whole report."""
    q = {"queryState": {"Values": {"projections": [dict(proj(entity, prop, False), active=True)]}},
         "sortDefinition": {"sort": [{"field": fld(entity, prop, False), "direction": "Descending" if descending else "Ascending"}]}}
    objects = {"data": [{"properties": {"mode": lit("'Dropdown'")}}],
               "selection": [{"properties": {"singleSelect": lit("true")}}],
               "header": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'"), "fontColor": {"solid": {"color": lit(f"'{NAVY}'")}},
                                          "textSize": lit("8D")}}],
               "items": [{"properties": {"textSize": lit("10D")}}]}
    c = container(page, key, "slicer", x, y, w, h, z,
                  {"query": q, "objects": objects, "syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True}}, border=False)
    c["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": lit("false")}}]
    return c


def banner(page, key, page_title):
    """Navy strip: Home | '<Site> PRIME ELS Dashboard' | page name | refresh context.
    Filter bar below: Site | Day | Shift (synced on every page, blank = today's shift day / whole day) | report window in words."""
    bg = band(page, "banner_bg", 0, 0, W, TOP_H, 0, NAVY)
    fb = band(page, "filter_bg", 0, TOP_H, W, FILTER_H, 0, FILTER_BG)
    sec = SECTION.get(key, "")
    name = textbox(page, "banner_page", 470, 0, 250, TOP_H, 2,
                   ([(sec.split(" ", 1)[-1].upper(), {"fontSize": "7pt", "color": "#7FA7D1", "fontFamily": "Segoe UI Semibold"})] if sec else []) +
                   [(page_title, {"fontSize": "11pt", "color": "#9FC3E7", "fontFamily": "Segoe UI Semibold"})])
    name["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": lit("false")}}]
    # context line (WMS | shift day | elapsed | refreshed / next / now in site time)
    ctx = single_card(page, "banner_ctx", 726, 1, 548, TOP_H - 2, 3, "Report Label", 8, "#DCE6F2", bold=False)
    ctx["filterConfig"] = page_filter(PG, "Page_Key", key)
    title = single_card(page, "banner_title", 66, 3, 400, TOP_H - 6, 1, "Dashboard Title", 16, "#FFFFFF")
    home = [] if key == "HOME" else [nav_button(page, "home_btn", 8, 10, 52, 30, 5, HOME_ID, "⌂ Home", fill=HOME_BLUE, size=9)]
    if key == "HOME":
        title = single_card(page, "banner_title", 10, 3, 456, TOP_H - 6, 1, "Dashboard Title", 16, "#FFFFFF")
    y = TOP_H + 2
    hh = FILTER_H - 4
    day = global_slicer(page, "day_slicer", 248, y, 200, hh, 6, "DimDate", "Date", "Day (blank = today)", "Day", descending=True)
    shf = global_slicer(page, "shift_slicer", 456, y, 190, hh, 7, "Cfg_Shift", "Shift", "Shift (blank = whole day)", "Shift")
    win = single_card(page, "window_label", 656, y + 8, 618, hh - 12, 8, "Window Label", 10, NAVY)
    return [bg, fb, title, name, ctx, site_slicer(page, 10, y, 230, hh, 4), day, shf, win] + home + synced_inputs(page)

def guide(page, key, y):
    c = card(page, "guide", 0, y, W, GUIDE_H, 9000, [("Page Guide Calc", "How it is calculated"), ("Page Guide Config", "How to configure")],
             value_size=9, cols=2)
    c["visual"]["visualContainerObjects"]["background"] = [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit(f"'{LIGHT}'")}}}}]
    c["filterConfig"] = page_filter(PG, "Page_Key", key)
    return c


def page_cockpit():
    p = "hypercare_cockpit"
    y0 = BANNER_H + 6
    v = [*banner(p, "COCKPIT", "Hypercare Cockpit"),
         card(p, "state", 10, y0, 1260, 56, 3, [("Overall Alert State", "Alert state"), ("Health Banner", "Data trust")], value_size=11, cols=2)]
    tiles = [("PPH", "1 Production - pallets / h"), ("TTAT_IN", "2 Inbound TTAT"), ("TTAT_OUT", "3 Outbound TTAT"),
             ("LOC_UTIL", "4 Location utilisation"), ("USER_PROD", "5 User productivity"), ("HEALTH_FAILS", "6 Daily health checks")]
    for i, (k, t) in enumerate(tiles):
        v.append(card(p, f"tile_{k}", 10 + i * 211, y0 + 66, 203, 262, 10 + i,
                      [(f"Card {k} Value", "Actual (report day)"), (f"Card {k} Status", "Status"), (f"Card {k} Prev", "Previous day"),
                       (f"Card {k} Avg Prior", "Prior-days average"), (f"Card {k} Target", "Target"),
                       (f"Card {k} Limits", "Warning / critical at"), (f"Card {k} Predicted", "Prediction")],
                      title=t, value_size=11, color_measure=f"Card {k} Color"))
    yn = y0 + 66 + 270
    hn = BANNER_H + BODY_H - yn - 6
    for i, (m, t) in enumerate([("Narrative Verdict", "Where is the constraint?"), ("Narrative Production Outlook", "Production outlook")]):
        v.append(text_card(p, f"narr{i}", 10 + i * 338, yn, 330, hn, 20 + i, m, t, 12))
    # every measure column re-runs the KPI chain for all rules: ONE measure carries status, actual vs target and the action
    # ("🔴 CRITICAL" sorts before "🟠 WARNING"); blank for rules that are not breached -> only open alerts are listed
    v.append(table(p, "todo", 686, yn, 584, hn, 22,
                   [(K, "Open Alert Text", True, "Status · actual (target) -> what to do"), (AR, "Rule", False, "Breached rule"),
                    (AR, "Owner", False, "Owner")],
                   "What to do now (open alerts, critical first)",
                   sort=(K, "Open Alert Text", True, "Ascending"),
                   widths={"Open Alert Text": 340, "Rule": 150, "Owner": 74}))
    return p, "Hypercare Cockpit", "COCKPIT", v


def page_alerts():
    """Excel ALERTS sheet: every rule, status vs threshold, why it is an alert, the numbers behind it, prediction, action, owner;
    clicking a rule fills the detail panel (how it is calculated, prediction method, diagnosis)."""
    from report_diag import note        # late import: report_diag builds on this module
    p = "alerts_rca"
    y0 = BANNER_H + 6
    v = [*banner(p, "ALERTS", "Alerts"),
         # the state text already carries both counts; separate count measures re-ran all 23 rule statuses twice (7.8 s -> 2.4 s)
         card(p, "state", 10, y0, 1260, 56, 3, [("Overall Alert State", "Alert state")], value_size=11, cols=1)]
    detail_h = 130
    th = BANNER_H + BODY_H - (y0 + 64) - 6 - detail_h - 8
    # every measure column re-runs the KPI chain for each of the 23 rules: ONE heavy column (status icon + actual vs limit + probable cause),
    # the target is a cheap threshold lookup, and numbers / prediction / action of the clicked rule are in the detail panel (34 s -> ~5 s)
    v.append(table(p, "rules", 10, y0 + 64, 1260, th, 10,
                   [(AR, "Rule_No", False, "#"), (AR, "Pillar", False, "Pillar"), (AR, "Rule", False, "Alert rule"),
                    (K, "Alert Why", True, "Status - why it is (not) an alert: actual vs limit / probable cause"),
                    (K, "Alert Threshold", True, "Target (warn / crit)"), (AR, "Owner", False, "Owner")],
                   "Alert control tower - click a rule: the numbers behind it, how it is calculated, prediction, diagnosis and action appear below",
                   sort=(AR, "Rule_No", False, "Ascending"),
                   widths={"Rule_No": 24, "Pillar": 70, "Rule": 210, "Alert Why": 680, "Alert Threshold": 160, "Owner": 90}))
    v.append(note(p, "detail", 10, y0 + 64 + th + 8, 1260, detail_h, 11, "Alert Detail Text",
                  "Selected rule: why, numbers behind it, how it is calculated, prediction and method, diagnosis, action", 9))
    return p, "Alerts", "ALERTS", v


def page_daily_hourly():
    """Excel DAILY_REPORT (left) + HOURLY_ALERT (right) - generic for every site (no LTA dependency)."""
    p = "daily_hourly"
    y0 = BANNER_H + 6
    v = [*banner(p, "DAILY", "Daily & Hourly Report"),
         card(p, "state", 10, y0, 1260, 56, 3, [("Health Banner", "Data trust"), ("Hourly Scan Summary", "Hour-by-hour scan")],
              value_size=11, cols=2)]
    yt = y0 + 64
    hb = BANNER_H + BODY_H - yt - 6
    v.append(table(p, "daily", 10, yt, 520, hb, 10,
                   [(TH, "Pillar", False, "Pillar"), (TH, "KPI_Name", False, "Metric"), (K, "Daily Value", True, "Value"),
                    (K, "Daily Target", True, "Target (warn / crit)"), (K, "Daily Status", True, "Status"),
                    (K, "Daily Predicted", True, "Predicted")],
                   "Daily report (Excel DAILY_REPORT)", color_rules=[("Daily Status", "KPI Status Color")],
                   sort=(TH, "Pillar", False, "Ascending")))
    v.append(table(p, "hourly", 538, yt, 732, hb, 11,
                   [("DimHour", "Hour Label", False, "Hour"), (K, "Hour Pallets Moved", True, "Pallets moved"),
                    (K, "Hour Moves Baseline", True, "Baseline"), (K, "Hour Moves vs Baseline", True, "vs base"),
                    (K, "Hour Status Label", True, "Status"), (K, "Hour Active Users", True, "Users"),
                    (K, "Hour Inbound Trucks", True, "In trucks"), (K, "Hour Inbound TTAT", True, "In TTAT"),
                    (K, "Hour Outbound Loads", True, "Out loads"), (K, "Hour Outbound TTAT", True, "Out TTAT"),
                    (K, "Hour Pallets", True, "Produced"), (K, "Hour Verdict", True, "Hourly verdict")],
                   "Hour-by-hour report (Excel HOURLY_ALERT)", color_rules=[("Hour Status Label", "Hour Status Color")],
                   sort=("DimHour", "Hour Sort", False, "Ascending")))
    return p, "Daily & Hourly Report", "DAILY", v

def page_users():
    """User productivity: KPIs -> 1. by hour (pallets, users, pallets per user-hour vs target, users below) -> 2. per user -> 3. user x hour."""
    from report_diag import GAP, PAL, combo_chart, matrix, subtitle as _sub, tall_bottom   # late import: report_diag builds on this module
    p = "user_productivity"
    ua = "User Activity"
    y0 = BANNER_H + 6
    bottom = tall_bottom(p)
    v = [*banner(p, "USERS", "User Productivity"),
         card(p, "kpis", 10, y0, 1260, 92, 3, strip("USERS"), value_size=14, cols=8)]
    y1 = y0 + 100
    h1 = 340
    v.append(_sub(combo_chart(p, "byhour", 10, y1, 700, h1, 10, ("DimHour", "Hour Label", "Hour"),
                              [("Hour Pallets Moved", "Pallets moved")], [("Hour Pallets Per User", "Pallets per user-hour"), ("Hour Productivity Target", "Target")],
                              "1. Productivity by hour - pallets moved and pallets per active user-hour vs target",
                              [PAL["users"], PAL["per_user"], PAL["target"]]), "User Hour Rule Text"))
    v.append(table(p, "hourly", 718, y1, 552, h1, 11,
                   [("DimHour", "Hour Label", False, "Hour"), (K, "Hour Pallets Moved", True, "Pallets"), (K, "Hour Active Users", True, "Users"),
                    (K, "Hour Pallets Per User", True, "Plt / user-h"), (K, "Hour Productivity Target", True, "Target"),
                    (K, "Hour Users Below", True, "Users below"), (K, "Hour Productivity Status", True, "Status")],
                   "By hour - report window (completed hours)", color_rules=[("Hour Productivity Status", "Hour Productivity Font")],
                   sort=("DimHour", "Hour Sort", False, "Ascending"),
                   widths={"Hour Label": 50, "Hour Pallets Moved": 60, "Hour Active Users": 50, "Hour Pallets Per User": 70,
                           "Hour Productivity Target": 56, "Hour Users Below": 70, "Hour Productivity Status": 100}))
    y2 = y1 + h1 + GAP
    h2 = 420
    v.append(table(p, "users", 10, y2, 700, h2, 12,
                   [(ua, "User_Id", False, "User"), (K, "User Pallets Moved", True, "Pallets"), (K, "User Transactions", True, "Txns"),
                    (K, "User Active Hours", True, "Active h"), (K, "KPI User Productivity", True, "Pallets / h"),
                    (K, "User Status", True, "Status"), (K, "User Productivity 7d", True, "Trend"), (K, "User Main Step", True, "Main process step")],
                   "2. Per RF user (report window)", sort=(K, "KPI User Productivity", True, "Descending")))
    v.append(column_chart(p, "ops", 718, y2, 552, h2, 13, (ua, "Operation"),
                          [("User Pallets Moved", "Pallets moved")], "Pallets moved by operation code", "clusteredBarChart"))
    y3 = y2 + h2 + GAP
    v.append(_sub(matrix(p, "heat", 10, y3, 1260, bottom - y3, 14, [(ua, "User_Id", "User")], [("DimHour", "Hour Label", "Hour")],
                         ("Moves Hour", "Pallets"), "3. Pallets moved per user and hour (colour = productivity limits)", back_color="User Hour Color"),
                  "User Hour Rule Text"))
    return p, "User Productivity", "USERS", v


def page_config_health():
    p = "config_health"
    y0 = BANNER_H + 6
    bottom = BANNER_H + BODY_H - 6
    v = [*banner(p, "CONFIG", "Config & Health"),
         card(p, "banner2", 10, y0, 560, 56, 2, [("Health Banner", "Data trust")], value_size=11),
         card(p, "fresh", 578, y0, 692, 56, 3,
              [("Data Last Txn", "Newest dlytrn (site time)"), ("KPI Data Lag Min", "Replica lag at refresh"),
               ("Data Snapshot UTC", "Refreshed (UTC)"), ("KPI Refresh Age h", "Refresh age"), ("Site WMS", "WMS engine")],
              value_size=11, cols=5)]
    yt = y0 + 64
    v.append(table(p, "checks", 10, yt, 560, 296, 10,
                   [(HC, "Check_No", False, "#"), (HC, "Check", False, "Daily health check"), (K, "Health Check Value Text", True, "Actual"),
                    (K, "Health Check Rule", True, "Rule"), (K, "Health Check Status", True, "Status"),
                    (HC, "Why", False, "If it fails")],
                   "1. Data health of the selected site (Excel VALIDATION)", sort=(HC, "Check_No", False, "Ascending"),
                   widths={"Check_No": 24, "Check": 190, "Health Check Value Text": 70, "Health Check Rule": 70, "Health Check Status": 50, "Why": 120}))
    # every site side by side (not filtered by the Site slicer - see visualInteractions): empty sources show red = where a page will be empty
    from report_diag import matrix          # late import: report_diag builds on this module
    v.append(matrix(p, "feeds", 10, yt + 304, 560, 180, 11, [("Data Health", "Source_Object", "Replica source")],
                    [("Cfg_Site", "SiteCode", "Site")], ("Feed Rows 24h", "Rows (24 h)"),
                    "4. Feed completeness - rows per replica source in the last 24 h, every site (red = empty -> the pages using it are empty)",
                    back_color="Feed Fill"))
    v.append(table(p, "issues", 10, yt + 492, 560, bottom - (yt + 492), 12,
                   [("Cfg_InputIssues", "Row", False, "Row"), ("Cfg_InputIssues", "Site", False, "Site"), ("Cfg_InputIssues", "KPI_Key", False, "KPI"),
                    ("Cfg_InputIssues", "Issue", False, "Problem (row ignored - fix it in the inputs file)")],
                   "5. Inputs file problems (Hypercare_KPI_Inputs.xlsx, tab Alert targets) - " + INPUTS_WHEN.split(" (")[0],
                   sort=("Cfg_InputIssues", "Row", False, "Ascending"),
                   widths={"Row": 36, "Site": 80, "KPI_Key": 110, "Issue": 300}))
    # ---- threshold input grid: one row per KPI, Target / Warning / Critical boxes (what-if single-value slicers, synced on all pages)
    gx, gw = 578, 692
    head = {"fontSize": "10pt", "fontWeight": "bold", "color": NAVY}
    small = {"fontSize": "9pt", "color": GREY}
    v.append(textbox(p, "in_title", gx, yt, gw, 70, 20,
                     [("2. Alert threshold inputs (applies to every page of this report)", head),
                      ("Try a value: type a number + Enter - only for you, NOT saved. To save a target for everyone: inputs file, tab Alert targets. Eraser = clear.", small)]))
    cx = [gx, gx + 230, gx + 384, gx + 538]
    for i, lbl in enumerate(["KPI (unit)", "Target", "Warning at", "Critical at"]):
        v.append(textbox(p, f"in_h{i}", cx[i], yt + 72, 150 if i else 226, 34, 21 + i, [(lbl, head)]))
    for r_i, r in enumerate(INPUTS):
        y = yt + 108 + r_i * 50
        v.append(textbox(p, f"in_l{r_i}", gx, y, 226, 50, 30 + r_i, [(f"{r['Label']} ({r['Input_Unit']})", {"fontSize": "9pt", "color": "#1F2D3D"})]))
        for l_i, (lvl, _) in enumerate(INPUT_LEVELS):
            v.append(input_slicer(p, r["KPI_Key"], lvl, cx[l_i + 1], y, 150, 40, 40 + r_i * 3 + l_i))
    yth = yt + 108 + len(INPUTS) * 50 + 6
    v.append(table(p, "thr", gx, yth, gw, bottom - yth, 12,
                   [(TH, "Pillar", False, "Pillar"), (TH, "KPI_Name", False, "KPI / setting"), (TH, "Direction", False, "Dir"),
                    (K, "Thr Target Text", True, "Target"), (K, "Thr Warn Text", True, "Warn at"), (K, "Thr Crit Text", True, "Crit at"),
                    (K, "Thr Source", True, "Source")],
                   "3. Thresholds in use for the selected site", sort=(TH, "Pillar", False, "Ascending"),
                   widths={"Pillar": 76, "KPI_Name": 236, "Direction": 44, "Thr Target Text": 80, "Thr Warn Text": 76, "Thr Crit Text": 76, "Thr Source": 84}))
    visible = {x["name"] for x in v if not x.get("isHidden")}
    v = [x for x in v if not (x.get("isHidden") and x["name"] in visible)]
    return p, "Config & Health", "CONFIG", v


HOWTO_SRC = ["howto_change_site.png", "howto_add_site.png"]
HOWTO_DIR = Path(__file__).resolve().parents[1] / "theme" / "howto"


def _versioned(img):
    """Resource name carries a content hash - Desktop caches images by name, so a re-rendered guide gets a new name."""
    digest = hashlib.sha1((HOWTO_DIR / img).read_bytes()).hexdigest()[:8]
    return f"{Path(img).stem}_{digest}.png"


HOWTO_IMAGES = [_versioned(i) for i in HOWTO_SRC]


def image(page, key, x, y, w, h, z, item):
    v = container(page, key, "image", x, y, w, h, z, {"objects": {"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
        "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": item}}}}}], "imageScaling": [{"properties": {"imageScalingType": lit("'Fit'")}}]}},
        border=False)
    return v


HOME_ID = "d6eb503d1ea76336e4a5"
HOME_BLUE = "#1F5FA8"


def nav_button(page, key, x, y, w, h, z, target, label, fill=HOME_BLUE, size=10):
    """Page-navigation button (works in Desktop with Ctrl+click and in the Service with a click)."""
    # Power BI writes the on / off switches without a selector and the styling per button state (default / hover) - a 'show' inside the
    # state selector is ignored and the button renders as an empty white box
    sel, hov = {"id": "default"}, {"id": "hover"}
    style = {"text": lit(f"'{label}'"), "fontSize": lit(f"{size}D"), "bold": lit("true"), "fontColor": {"solid": {"color": lit("'#FFFFFF'")}},
             "horizontalAlignment": lit("'center'"), "verticalAlignment": lit("'middle'")}
    obj = {"icon": [{"properties": {"show": lit("false")}}, {"properties": {"shapeType": lit("'blank'")}, "selector": sel}],
           "text": [{"properties": {"show": lit("true")}}, {"properties": style, "selector": sel}, {"properties": style, "selector": hov}],
           "fill": [{"properties": {"show": lit("true")}},
                    {"properties": {"fillColor": {"solid": {"color": lit(f"'{fill}'")}}, "transparency": lit("0D")}, "selector": sel},
                    {"properties": {"fillColor": {"solid": {"color": lit(f"'{NAVY}'")}}, "transparency": lit("0D")}, "selector": hov}],
           "outline": [{"properties": {"show": lit("false")}}],
           "shape": [{"properties": {"tileShape": lit("'rectangleRounded'")}}]}
    c = container(page, key, "actionButton", x, y, w, h, z, {"objects": obj}, border=False)
    c["visual"]["visualContainerObjects"]["visualLink"] = [{"properties": {"show": lit("true"), "type": lit("'PageNavigation'"),
                                                                            "navigationSection": lit(f"'{target}'")}}]
    return c


def band(page, key, x, y, w, h, z, color):
    """Coloured rectangle (banner / filter bar): fill switch without selector, colour on the default state (as Power BI writes it)."""
    obj = {"shape": [{"properties": {"tileShape": lit("'rectangle'")}}], "rotation": [{"properties": {"shapeAngle": lit("0L")}}],
           "fill": [{"properties": {"show": lit("true")}},
                    {"properties": {"fillColor": {"solid": {"color": lit(f"'{color}'")}}, "transparency": lit("0D")}, "selector": {"id": "default"}}],
           "outline": [{"properties": {"show": lit("false")}}]}
    return container(page, key, "shape", x, y, w, h, z, {"objects": obj}, border=False)


def home_extras(p):
    """Home (right part): how to add / remove a site, how to set alert targets, the sites in this report. The page index (left part) is
    written by home_index() once every page exists."""
    x0, y = 790, BANNER_H + 10
    w = W - x0 - 10
    head = {"fontSize": "12pt", "fontWeight": "bold", "color": NAVY}
    body = {"fontSize": "9.5pt", "color": "#252423"}
    note = {"fontSize": "8.5pt", "color": GREY}
    site_steps = [("1  Add or remove a site  (max 6 sites in this report)", head),
                  ("① Inputs file (SharePoint > Data Projects > PRIME ELS > Hypercare KPI > Hypercare_KPI_Inputs.xlsx), tab Sites: add one row "
                   "- code, name, PrIME 2014 / 2022, replica server + database, UTC offset, shift starts, hypercare start, SAP plant.", body),
                  ("② Run  py tools/add_site.py <CODE>  - it reads the replica, proposes every technical setting with evidence, checks every query, "
                   "builds and tests the site.", body),
                  ("③ Publish  (py tools/publish.py)  and confirm the items of docs/ONBOARDING_<CODE>.md with the site.", body),
                  ("Remove a site: delete its row in Sites, then  py tools/apply_inputs.py --confirm  and rebuild. A 7th site is refused.", note)]
    alert_steps = [("2  Set alert targets", head),
                   ("Every site follows the BD thresholds (rows 'All sites' in the Alert targets tab of the same inputs file).", body),
                   ("To change one site: add a row with its site code and the KPI - Target, Warning at, Critical at. The targets are "
                    + INPUTS_WHEN + ".", body),
                   ("Check what is in use: Config & Health > Alert targets in use (source + any input problem). Try a value without saving: the "
                    "input boxes on Config & Health (only for you, not saved).", note)]
    v = [textbox(p, "home_sites_howto", x0, y, w, 250, 902, site_steps, bg=LIGHT),
         textbox(p, "home_alerts_howto", x0, y + 258, w, 200, 903, alert_steps, bg=LIGHT)]
    t = table(p, "home_sites", x0, y + 466, w, BANNER_H + BODY_H - (y + 466) - 6, 904,
              [("Cfg_Site", "SiteCode", False, "Code"), ("Cfg_Site", "SiteName", False, "Site"), ("Cfg_Site", "WMS_Version", False, "WMS"),
               (K, "Prod Plan Short", True, "Production"), ("Cfg_Site", "Config_Status", False, "Configuration status")],
              "Sites in this report", sort=("Cfg_Site", "SiteCode", False, "Ascending"),
              widths={"SiteCode": 74, "SiteName": 100, "WMS_Version": 64, "Prod Plan Short": 120, "Config_Status": 150})
    v.append(t)
    return v


def home_index(pages_dir, order, keys):
    """Left part of Home: one navigation button per page (report order) + what the page answers (config/page_guide.csv Purpose)."""
    purpose = {r["Page_Key"]: r.get("Purpose", "") for r in read_csv("page_guide.csv")}
    names = {pid: json.loads((pages_dir / pid / "page.json").read_text(encoding="utf-8"))["displayName"] for pid in order}
    items = [pid for pid in order if pid != HOME_ID]
    p, x0, y0 = HOME_ID, 10, BANNER_H + 10
    out = [textbox(p, "home_index_head", x0, y0, 776, 54, 905,
                   [("Pages by site process - click a button to open the page (Power BI Desktop: Ctrl + click). Every page has a Home button top left.",
                     {"fontSize": "10pt", "fontWeight": "bold", "color": NAVY})])]
    # entries: a section header before the first page of every section, then one row per page; two columns balanced by height.
    # Row = button (page name, centred) + up to 3 lines of purpose text; the Home page grows to fit (Fit to width scrolls).
    RH, HH, TOP = 64, 38, y0 + 58
    entries = []
    for pid in items:
        sec = SECTION.get(keys.get(pid, ""), "")
        if not entries or entries[-1][1] != sec:
            entries.append(("H", sec, None))
        entries.append(("P", sec, pid))
    total = sum(HH if k == "H" else RH for k, _, _ in entries)
    acc, split = 0, len(entries)
    for i, (k, _, _) in enumerate(entries):
        if acc >= total / 2 and k == "H":           # second column starts with a section header
            split = i
            break
        acc += HH if k == "H" else RH
    bottom = TOP
    for col, part in enumerate((entries[:split], entries[split:])):
        y = TOP
        x = x0 + col * 392
        for i, (kind, sec, pid) in enumerate(part):
            n = 910 + 3 * (i + col * 100)
            if kind == "H":
                out.append(textbox(p, f"idx_sec_{col}_{i}", x, y + 2, 384, HH - 2, n,
                                   [(sec.split(" ", 1)[-1].upper(), {"fontSize": "9pt", "fontWeight": "bold", "color": HOME_BLUE})]))
                y += HH
                continue
            out.append(nav_button(p, f"idx_btn_{pid}", x, y + 10, 150, RH - 20, n, pid, names[pid], size=8))
            txt = purpose.get(keys.get(pid, ""), "") or "-"
            out.append(textbox(p, f"idx_txt_{pid}", x + 154, y, 232, RH - 2, n + 1, [(txt, {"fontSize": "8pt", "color": "#252423"})]))
            y += RH
        bottom = max(bottom, y)
    hp = pages_dir / HOME_ID / "page.json"
    pj = json.loads(hp.read_text(encoding="utf-8"))
    pj["height"] = max(pj.get("height", BANNER_H + BODY_H), bottom + 10)
    hp.write_text(json.dumps(pj, indent=1, ensure_ascii=False), encoding="utf-8")
    missing = [pid for pid in items if not purpose.get(keys.get(pid, ""))]
    if missing:
        raise SystemExit(f"config/page_guide.csv: Purpose missing for page(s) {[names[m] for m in missing]}")
    for vis in out:
        vd = pages_dir / HOME_ID / "visuals" / vis["name"]
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "visual.json").write_text(json.dumps(vis, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(items)


def pred_extras(p):
    return [table(p, "legend", 0, BANNER_H + 566, 746, 150, 900,
                  [("Cfg_Market", "Market", False, "Market"), ("Cfg_Market", "Market_Name", False, "Name"), ("Cfg_Market", "Color", False, "Colour")],
                  "Market colour legend (Cfg_Market)")]

def _is_header_decor(vtype, pos):
    """Old per-page header of the BD report (navy bar + P&G logo + title text) - replaced by the standard banner."""
    return ((vtype == "image" and pos["y"] < 20 and pos["width"] <= 120) or
            (vtype == "shape" and pos["y"] <= 10 and pos["height"] <= 100 and pos["width"] >= 600) or
            (vtype == "textbox" and pos["y"] <= 10 and pos["height"] <= 70 and 100 <= pos["x"] <= 120))


KEEP_SLICER_FIELDS = {"JIT"}      # generic category defaults that are valid for every site
CLEARED_FIELDS = set()


def _fields(v):
    return {(p.get("field", {}).get("Column") or p.get("field", {}).get("Measure") or {}).get("Property")
            for role in v.get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])}


def _clear_site_selections(j):
    """The source report was saved on Binh Duong: its slicer selections (production line, market, dates, times) and
    date-literal visual filters are BD data values -> cleared so every site opens unfiltered. The Site slicer is not touched
    (generated pages only). Returns the fields whose saved selection was removed."""
    v = j.get("visual", {})
    if v.get("visualType") == "slicer" and not (_fields(v) & KEEP_SLICER_FIELDS):
        for g in v.get("objects", {}).get("general", []):
            if g.get("properties", {}).pop("filter", None) is not None:
                CLEARED_FIELDS.update(f for f in _fields(v) if f)
    fc = j.get("filterConfig", {})
    if fc.get("filters"):
        fc["filters"] = [f for f in fc["filters"] if "datetime'" not in json.dumps(f.get("filter", {}))]


def _clean_bookmark(o):
    """Drop bookmark filter states that hold a cleared slicer field or a date literal (BD data values)."""
    if isinstance(o, dict):
        for k in list(o):
            x = o[k]
            if k == "filter" and isinstance(x, dict):
                s = json.dumps(x)
                if "datetime'" in s or any(f'"Property": "{f}"' in s for f in CLEARED_FIELDS):
                    del o[k]
                    continue
            _clean_bookmark(x)
    elif isinstance(o, list):
        for x in o:
            _clean_bookmark(x)


TIME_AXIS = re.compile(r"(?i)date|hour|shift|bucket|time|day|week|month")
CHART_TYPES = {"clusteredColumnChart", "stackedColumnChart", "columnChart", "lineChart", "areaChart", "stackedAreaChart",
               "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "clusteredBarChart", "barChart", "ribbonChart"}


def _sort_time_axis(j):
    """Charts whose axis is a date / hour / shift: sort along the axis (time order). Other charts: largest value first.
    Without an explicit sort a column chart sorts by the value (largest bar first), which scrambles dates and hours."""
    v = j.get("visual", {})
    if v.get("visualType") not in CHART_TYPES:
        return
    qs = v.get("query", {}).get("queryState", {})
    cat = qs.get("Category", {}).get("projections", [])
    if not cat:
        return
    fields = [p["field"] for p in cat]
    props = [(f.get("Column") or {}).get("Property", "") for f in fields]
    sd = v["query"].get("sortDefinition", {}).get("sort", [])
    if not any(TIME_AXIS.search(p) for p in props):
        ys = qs.get("Y", {}).get("projections", []) or qs.get("Values", {}).get("projections", [])
        if not sd and ys:
            v["query"]["sortDefinition"] = {"sort": [{"field": ys[0]["field"], "direction": "Descending"}], "isDefaultSort": False}
        return
    if sd and all(any(s["field"] == f for f in fields) for s in sd):
        # time reads left -> right: a saved Descending sort on the time axis (BD Inv KPIs charts) is turned Ascending
        for s in sd:
            s["direction"] = "Ascending"
        return
    v["query"]["sortDefinition"] = {"sort": [{"field": f, "direction": "Ascending"} for f in fields], "isDefaultSort": False}


def sort_all_charts(pages_dir: Path):
    """Apply the chart sort rule to every page (source and generated)."""
    for vf in pages_dir.glob("*/visuals/*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        before = json.dumps(j.get("visual", {}).get("query", {}).get("sortDefinition"))
        _sort_time_axis(j)
        if json.dumps(j.get("visual", {}).get("query", {}).get("sortDefinition")) != before:
            vf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")


LABEL_CHARTS = {"columnChart", "clusteredColumnChart", "barChart", "clusteredBarChart", "lineChart", "areaChart", "stackedAreaChart",
                "lineClusteredColumnComboChart", "lineStackedColumnComboChart", "ribbonChart", "waterfallChart", "funnel", "pieChart", "donutChart",
                "hundredPercentStackedColumnChart", "hundredPercentStackedBarChart"}
STACKED = {"columnChart", "barChart", "lineStackedColumnComboChart"}


def label_all_charts(pages_dir: Path):
    """Every chart shows its numbers: data labels on (source and generated pages); stacked charts also show the stack total unless a
    series hides its labels on purpose (Gantt start offset). Per-series label settings of a visual are kept."""
    n = 0
    for vf in pages_dir.glob("*/visuals/*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        v = j.get("visual", {})
        vt = v.get("visualType")
        if vt not in LABEL_CHARTS:
            continue
        obj = v.setdefault("objects", {})
        labels = obj.setdefault("labels", [])
        base = next((e for e in labels if not e.get("selector")), None)
        if base is None:
            labels.insert(0, {"properties": {"show": lit("true")}})
        else:
            base.setdefault("properties", {})["show"] = lit("true")
        if vt in STACKED and "totals" not in obj and not any(e.get("selector") for e in labels):
            obj["totals"] = [{"properties": {"show": lit("true")}}]
        vf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")
        n += 1
    return n


def _standardize(j):
    """Drop visual-level container styling so the theme gives every tab the same border / background / title look."""
    _clear_site_selections(j)
    _sort_time_axis(j)
    vco = j.get("visual", {}).get("visualContainerObjects", {})
    if j.get("visual", {}).get("visualType") in ("shape", "textbox", "image", "actionButton"):
        return
    for k in ("background", "border", "dropShadow", "visualHeader"):
        vco.pop(k, None)
    for t in vco.get("title", []):
        for k in ("fontColor", "fontSize", "background", "fontFamily", "alignment", "bold", "titleWrap"):
            t.get("properties", {}).pop(k, None)


def _trim_small_overlaps(vis, gone, limit=24):
    """BD original layouts: neighbouring data visuals overlapping by a few px (borders / headers cut) -> the left / upper visual is
    trimmed so they touch with a 4 px gap. Larger overlaps are intentional (bookmark-toggled visuals) and are kept."""
    deco = {"shape", "image", "textbox", "actionButton"}
    items = [(n, vf, j) for n, (vf, j) in vis.items() if n not in gone and "visual" in j and not j.get("parentGroupName")
             and not j.get("isHidden") and j["visual"].get("visualType") not in deco]
    for i, (na, fa, ja) in enumerate(items):
        for nb, fb, jb in items[i + 1:]:
            a, b = ja["position"], jb["position"]
            ox = min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
            if ox <= 4 or oy <= 4:
                continue
            if ox <= limit and ox < oy:
                left = a if a["x"] < b["x"] else b
                left["width"] -= ox + 4
            elif oy <= limit:
                upper = a if a["y"] < b["y"] else b
                upper["height"] -= oy + 4
    for n, vf, j in items:
        vf.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")


def _shift_existing(pdir, key, page_name, display):
    pj = json.loads((pdir / "page.json").read_text(encoding="utf-8"))
    old_h = pj.get("height", BODY_H)
    pj["height"] = BANNER_H + old_h + GUIDE_H
    pj["displayOption"] = "FitToWidth"
    if display:
        pj["displayName"] = display
    title = pj["displayName"]
    for k in ("pageRefresh", "background", "outspace", "outspacePane"):
        pj.get("objects", {}).pop(k, None)
    vis = {}
    for vf in (pdir / "visuals").glob("*/visual.json"):
        if vf.parent.name in REMOVE_VISUALS:
            shutil.rmtree(vf.parent)
            continue
        vis[vf.parent.name] = (vf, json.loads(vf.read_text(encoding="utf-8")))
    gone = {n for n, (vf, j) in vis.items() if "visual" in j and _is_header_decor(j["visual"].get("visualType"), j["position"])}
    groups = {n for n, (vf, j) in vis.items() if "visualGroup" in j}
    for g in groups:
        kids = [n for n, (vf, j) in vis.items() if j.get("parentGroupName") == g]
        if kids and all(k in gone for k in kids):
            gone.add(g)
    for n in gone:
        shutil.rmtree(vis[n][0].parent)
    for n, (vf, j) in vis.items():
        if n in gone:
            continue
        if not j.get("parentGroupName"):
            j["position"]["y"] = j["position"]["y"] + BANNER_H
        _standardize(j)
        sj = json.dumps(j, ensure_ascii=False)
        for t in STRIP_TEXT:
            sj = sj.replace(f'"value":"{t}', '"value":"').replace(f'"value": "{t}', '"value": "')
        vf.write_text(sj, encoding="utf-8")
    _trim_small_overlaps(vis, gone)
    pj["visualInteractions"] = [x for x in pj.get("visualInteractions", []) if x["source"] not in gone and x["target"] not in gone]
    if key == "HOME":
        for vf in list((pdir / "visuals").glob("*/visual.json")):
            shutil.rmtree(vf.parent)
        pj["height"] = BANNER_H + BODY_H
        pj["visualInteractions"] = []
        extra = banner(page_name, key, title) + home_extras(page_name)
    else:
        extra = banner(page_name, key, title) + [guide(page_name, key, BANNER_H + old_h)]
    if key == "PRED":
        extra += pred_extras(page_name)
    (pdir / "page.json").write_text(json.dumps(pj, indent=1, ensure_ascii=False), encoding="utf-8")
    for vis_ in extra:
        vd = pdir / "visuals" / vis_["name"]
        vd.mkdir(exist_ok=True)
        (vd / "visual.json").write_text(json.dumps(vis_, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(gone)


def add_pages(defn: Path, default_site_name):
    DEFAULT_SITE["name"] = default_site_name
    pages_dir = defn / "pages"
    meta = json.loads((pages_dir / "pages.json").read_text(encoding="utf-8"))
    remove = dict(REMOVE)
    if not sap_included():   # SAP left out of the file -> the SAP-only pages go too (config/build_options.csv Include_SAP_CDL)
        remove.update({pid: "SAP page - Include_SAP_CDL = 0" for pid, (_, k) in EXISTING.items() if k in SAP_PAGES})
    for pid in remove:
        if (pages_dir / pid).exists():
            shutil.rmtree(pages_dir / pid)
    meta["pageOrder"] = [p for p in meta["pageOrder"] if p not in remove]
    for pid, (display, key) in EXISTING.items():
        if (pages_dir / pid).exists():
            _shift_existing(pages_dir / pid, key, pid, display)
    new = [page_cockpit(), page_daily_hourly(), page_alerts(), page_users(), page_config_health()]
    from report_diag import diag_pages          # late import: report_diag builds on the helpers of this module
    new += diag_pages()
    from report_diag import TALL
    for pid, display, key, visuals in new:
        pdir = pages_dir / pid
        (pdir / "visuals").mkdir(parents=True, exist_ok=True)
        height = TALL.get(pid, PAGE_H)
        # FitToWidth: pages scroll vertically (tall pages show their full Gantt / tables), the width always fits the window
        page = {"$schema": PSCHEMA, "name": pid, "displayName": display, "displayOption": "FitToWidth", "height": height, "width": W}
        if pid == "config_health":
            page["visualInteractions"] = [{"source": hid(pid, "site_slicer"), "target": hid(pid, t), "type": "NoFilter"} for t in ("issues", "feeds")]
        (pdir / "page.json").write_text(json.dumps(page, indent=1), encoding="utf-8")
        for vis in visuals + [guide(pid, key, height - GUIDE_H)]:
            vd = pdir / "visuals" / vis["name"]
            vd.mkdir(exist_ok=True)
            (vd / "visual.json").write_text(json.dumps(vis, indent=1, ensure_ascii=False), encoding="utf-8")
    home = "d6eb503d1ea76336e4a5"
    keys = {pid: k for pid, (_, k) in EXISTING.items()} | {pid: k for pid, _, k, _ in new}
    # tab order follows the site process (config/page_guide.csv: Section, then row order): Overview -> Inbound & Trucks -> Production & Lines
    # -> Storage & Inventory -> Outbound & Orders -> People -> Admin
    present = [p for p in meta["pageOrder"] if p in keys] + [x[0] for x in new if x[0] not in meta["pageOrder"]]
    unknown = [p for p in present if keys[p] not in GUIDE_ORDER]
    if unknown:
        raise SystemExit(f"config/page_guide.csv has no row for page(s) {unknown}")
    meta["pageOrder"] = sorted(dict.fromkeys(present), key=lambda p: (p != home, GUIDE_ORDER.index(keys[p])))
    meta["activePageName"] = home
    (pages_dir / "pages.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    # Home: page index (one button per page, grouped by section) + 'Sites in this report' lists every site (not filtered by the Site slicer)
    home_index(pages_dir, meta["pageOrder"], keys)
    hj = json.loads((pages_dir / home / "page.json").read_text(encoding="utf-8"))
    hj["visualInteractions"] = [{"source": hid(home, "site_slicer"), "target": hid(home, "home_sites"), "type": "NoFilter"}]
    (pages_dir / home / "page.json").write_text(json.dumps(hj, indent=1, ensure_ascii=False), encoding="utf-8")
    # every page except Home must have its Home button (gate: navigation never breaks when a page is added)
    no_home = [pid for pid in meta["pageOrder"] if pid != home and not (pages_dir / pid / "visuals" / hid(pid, "home_btn")).exists()]
    if no_home:
        raise SystemExit(f"pages without a Home button: {no_home}")
    # users see numbers, never config names: no visual title / text may contain a threshold key or a site-config column name
    keys = {r["KPI_Key"] for r in read_csv("kpi_thresholds.csv")} | set(read_csv("site_config.csv")[0].keys())
    keys = sorted((k for k in keys if re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", k)), key=len, reverse=True)
    krx = re.compile(r"\b(" + "|".join(keys) + r")\b")
    shown = []

    def _texts(o, inside=False):
        if isinstance(o, dict):
            for k_, v_ in o.items():
                if k_ == "value" and inside and isinstance(v_, str):              # text box runs
                    yield v_
                elif k_ == "Value" and inside and isinstance(v_, str):            # title / subtitle literal
                    yield v_.strip("'")
                else:
                    yield from _texts(v_, inside or k_ in ("title", "subTitle", "paragraphs", "textRuns"))
        elif isinstance(o, list):
            for v_ in o:
                yield from _texts(v_, inside)
    for f in pages_dir.rglob("visual.json"):
        for lit_ in _texts(json.loads(f.read_text(encoding="utf-8"))):
            shown += [f"{f.parent.parent.parent.name}: '{k}' in '{lit_[:80]}'" for k in krx.findall(lit_)]
    if shown:
        raise SystemExit("config names visible in titles / texts (show the value through a text measure instead):\n  " + "\n  ".join(shown[:20]))
    # certified AppSource visuals used by the generated pages must be registered in report.json (gate C4)
    from report_diag import SANKEY
    rj_path = defn / "report.json"
    rj = json.loads(rj_path.read_text(encoding="utf-8"))
    pcv = rj.setdefault("publicCustomVisuals", [])
    if SANKEY not in pcv:
        pcv.append(SANKEY)
        rj_path.write_text(json.dumps(rj, indent=2, ensure_ascii=False), encoding="utf-8")
    sort_all_charts(pages_dir)
    label_all_charts(pages_dir)
    for b in (defn / "bookmarks").glob("*.bookmark.json") if (defn / "bookmarks").exists() else []:
        if any(r in b.read_text(encoding="utf-8") for r in REMOVE):
            b.unlink()
            continue
        bj = json.loads(b.read_text(encoding="utf-8"))
        _clean_bookmark(bj)
        b.write_text(json.dumps(bj, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(new)


THEME_FILE = "PRIME_ELS_Theme.json"


def scope_hour_visuals(defn: Path):
    """Global Shift slicer: every visual with a DimHour axis (rows / columns / category) keeps only the hours of the report window
    ('[Hour In Window] = 1'; without a shift selection every hour is in the window). Returns the visuals changed."""
    meas = "Hour In Window"
    cond = {"Version": 2, "From": [{"Name": "k", "Entity": K, "Type": 0}],
            "Where": [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                                    "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "k"}}, "Property": meas}},
                                                    "Right": {"Literal": {"Value": "1L"}}}}}]}
    changed = []
    for vf in (defn / "pages").glob("*/visuals/*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        v = j.get("visual", {})
        if v.get("visualType") in ("slicer", None):
            continue
        projs = [p for role in v.get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])]
        if not any(p.get("field", {}).get("Column", {}).get("Expression", {}).get("SourceRef", {}).get("Entity") == "DimHour" for p in projs):
            continue
        fc = j.setdefault("filterConfig", {}).setdefault("filters", [])
        if any(f.get("field", {}).get("Measure", {}).get("Property") == meas for f in fc):
            continue
        fc.append({"name": hid(vf.parent.name, "hour_window"), "field": fld(K, meas, True), "type": "Advanced", "filter": cond, "howCreated": "User"})
        vf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")
        changed.append(f"{vf.parent.parent.parent.name}/{vf.parent.name}")
    return changed


def scope_range_visuals(defn: Path):
    """Pages with the Start / End date-time range slicers (TTAT Details, from the BD report): the cards apply the range inside
    their measures, but row tables of trucks (TTAT columns only) did not - the GCAS / trailer-type tables listed every truck
    of every day and the range filter of the detail tables had no condition. Every such table gets '[Truck Close Time Range] = 1'.
    Returns the visuals changed."""
    ent, meas = "_DaxMeasure", "Truck Close Time Range"
    cond = {"Version": 2, "From": [{"Name": "d", "Entity": ent, "Type": 0}],
            "Where": [{"Condition": {"Comparison": {"ComparisonKind": 0,
                                                    "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": meas}},
                                                    "Right": {"Literal": {"Value": "1L"}}}}}]}
    changed = []
    for page in (defn / "pages").glob("*"):
        vis = [(vf, json.loads(vf.read_text(encoding="utf-8"))) for vf in page.glob("visuals/*/visual.json")]
        slicer_cols = {(p["field"]["Column"]["Expression"]["SourceRef"].get("Entity"), p["field"]["Column"]["Property"])
                       for _, j in vis if j.get("visual", {}).get("visualType") == "slicer"
                       for role in j["visual"].get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])
                       if "Column" in p.get("field", {})}
        if not {("StartDate", "Start Date"), ("EndDate", "End Date")} <= slicer_cols:
            continue
        for vf, j in vis:
            v = j.get("visual", {})
            if v.get("visualType") not in ("tableEx", "pivotTable"):
                continue
            projs = [p for role in v.get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])]
            ents = set()
            for p in projs:
                f = p.get("field", {})
                if "Measure" in f:                                   # measures are fine - the rows are trucks
                    continue
                col = f.get("Column") or (f.get("Aggregation") or {}).get("Expression", {}).get("Column")
                ents.add(col["Expression"]["SourceRef"].get("Entity") if col else None)
            if ents != {"TTAT"}:
                continue
            fc = j.setdefault("filterConfig", {}).setdefault("filters", [])
            fc[:] = [f for f in fc if f.get("field", {}).get("Measure", {}).get("Property") != meas]   # drop condition-less copies
            fc.append({"name": hid(vf.parent.name, "range_scope"), "field": {"Measure": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": meas}},
                       "type": "Advanced", "filter": cond, "howCreated": "User"})
            vf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")
            changed.append(f"{page.name}/{vf.parent.name}")
    return changed


def scope_column_visuals(defn: Path, site_tables):
    """A visual with ONLY columns of a site table (no measure) is not filtered through the Cfg_Site relationship (a
    column-only SUMMARIZECOLUMNS ignores cross-table filters): in the all-sites file it listed every site's rows. Such
    visuals get a visual-level filter '[Rows <table>] is not blank' (hidden helper measure), which forces the site filter.
    Returns the visuals changed (page/visual: table)."""
    changed = []
    for vf in (defn / "pages").glob("*/visuals/*/visual.json"):
        j = json.loads(vf.read_text(encoding="utf-8"))
        v = j.get("visual", {})
        if v.get("visualType") in ("slicer", "textbox", "shape", "image", "actionButton", None):
            continue
        projs = [p for role in v.get("query", {}).get("queryState", {}).values() for p in role.get("projections", [])]
        if not projs or any("Column" not in p.get("field", {}) for p in projs):
            continue
        ents = {p["field"]["Column"]["Expression"]["SourceRef"].get("Entity") for p in projs}
        if len(ents) != 1 or next(iter(ents)) not in site_tables:
            continue
        t = next(iter(ents))
        m = f"Rows {t}"
        fc = j.setdefault("filterConfig", {}).setdefault("filters", [])
        if any(f'"Property": "{m}"' in json.dumps(f) for f in fc):
            continue
        fc.append({"name": hid(t, "site_scope"), "field": fld(K, m, True), "type": "Advanced",
                   "filter": {"Version": 2, "From": [{"Name": "k", "Entity": K, "Type": 0}],
                              "Where": [{"Condition": {"Not": {"Expression": {"Comparison": {
                                  "ComparisonKind": 0, "Left": {"Measure": {"Expression": {"SourceRef": {"Source": "k"}}, "Property": m}},
                                  "Right": {"Literal": {"Value": "null"}}}}}}}]}})
        vf.write_text(json.dumps(j, indent=1, ensure_ascii=False), encoding="utf-8")
        changed.append(f"{vf.parent.parent.parent.name}/{vf.parent.name}: {t}")
    return changed


def register_resources(rep_dir: Path, root: Path):
    """Copy theme + how-to images into RegisteredResources and register them in report.json (custom theme on top of the base theme)."""
    rr = rep_dir / "StaticResources" / "RegisteredResources"
    rr.mkdir(parents=True, exist_ok=True)
    shutil.copy(root / "theme" / THEME_FILE, rr / THEME_FILE)
    for src, img in zip(HOWTO_SRC, HOWTO_IMAGES):
        shutil.copy(HOWTO_DIR / src, rr / img)
    for old in rr.glob("howto_*.png"):
        if old.name not in HOWTO_IMAGES:
            old.unlink()
    rj = rep_dir / "definition" / "report.json"
    r = json.loads(rj.read_text(encoding="utf-8"))
    base = r["themeCollection"]["baseTheme"]
    r["themeCollection"]["customTheme"] = {"name": THEME_FILE, "reportVersionAtImport": base.get("reportVersionAtImport"), "type": "RegisteredResources"}
    pk = next((x for x in r["resourcePackages"] if x["name"] == "RegisteredResources"), None)
    if pk is None:
        pk = {"name": "RegisteredResources", "type": "RegisteredResources", "items": []}
        r["resourcePackages"].append(pk)
    pk["items"] = [i for i in pk["items"] if not (i["name"].startswith("howto_") and i["name"] not in HOWTO_IMAGES)]
    have = {i["name"] for i in pk["items"]}
    for name, typ in [(THEME_FILE, "CustomTheme")] + [(i, "Image") for i in HOWTO_IMAGES]:
        if name not in have:
            pk["items"].append({"name": name, "path": name, "type": typ})
    rj.write_text(json.dumps(r, indent=1), encoding="utf-8")



