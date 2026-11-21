"""Process-diagnosis pages (PBIR) - follow the site process left to right and answer 'where is it stuck, since when, what to do'.

Pages: Process Flow (stage board + stuck list + heat map), Trucks & TTAT, Pallet Flow, Orders & Shipments,
Production SAP vs WMS, Field Guide. Every colour / limit / text comes from config (process_stages, movement_classes, time_bands,
kpi_thresholds, rca_rules, field_guide) through the model; this module only lays the visuals out on the standard grid."""
import csv
import json
from pathlib import Path

from report_pages import (K, AR, BANNER_H, BODY_H, GUIDE_H, NAVY, W, banner, card, container, fld, hid, lit, page_filter, measure_filter, proj, slicer, subtitle, table)
from kpi_strips import strip

CFG = Path(__file__).resolve().parents[1] / "config"
UA, ST, FI, TB = "User Activity", "Cfg_Stage", "Flow Items", "Cfg_TimeBand"
Y0 = BANNER_H + 6
BOTTOM = BANNER_H + BODY_H - 6
# tall scrollable pages (page height in px; the page guide sits at the bottom) - long charts such as the truck Gantt get full height
TALL = {"truck_diagnosis": 1800, "user_productivity": 1500}


def tall_bottom(pid):
    return TALL[pid] - GUIDE_H - 6
GAP = 8
# colours: theme/palette.json "diagnosis" (same file as the theme) - comparison series and truck-time segments
PAL = json.load(open(Path(__file__).resolve().parents[1] / "theme" / "palette.json", encoding="utf-8"))["diagnosis"]
IN_C, OUT_C, SAP_C, WMS_C = PAL["inbound"], PAL["outbound"], PAL["sap"], PAL["wms"]
SEG_WAIT, SEG_WORK, SEG_REST = PAL["seg_wait"], PAL["seg_work"], PAL["seg_rest"]


# legend + visual title name every series / axis -> axis titles only repeat them (and get truncated)
NO_AXIS_TITLES = {"valueAxis": [{"properties": {"showAxisTitle": lit("false")}}], "categoryAxis": [{"properties": {"showAxisTitle": lit("false")}}]}


def move_class_colors():
    return {r["Move_Class"]: r["Color"] for r in csv.DictReader(open(CFG / "movement_classes.csv", encoding="utf-8-sig")) if r["Counts_As_Move"] == "1"}


def merge_filters(*fcs):
    return {"filters": [f for fc in fcs if fc for f in fc["filters"]]}


def matrix(page, key, x, y, w, h, z, rows, cols, value, title, back_color=None, filters=None, sort=None):
    """Heat map = matrix with a measure-driven cell background (colour rule from config limits). rows / cols: (entity, prop, label)."""
    q = {"queryState": {"Rows": {"projections": [dict(proj(e, p, False, lbl), active=True) for e, p, lbl in rows]},
                        "Columns": {"projections": [dict(proj(e, p, False, lbl), active=True) for e, p, lbl in cols]},
                        "Values": {"projections": [proj(K, value[0], True, value[1])]}}}
    if sort:
        e, p, m, d = sort
        q["sortDefinition"] = {"sort": [{"field": fld(e, p, m), "direction": d}], "isDefaultSort": True}
    vals = [{"properties": {"fontSize": lit("9D")}}]
    if back_color:
        vals.append({"properties": {"backColor": {"solid": {"color": {"expr": fld(K, back_color, True)}}}},
                     "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"{K}.{value[0]}"}})
    objects = {"values": vals,
               "subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}],
               "columnHeaders": [{"properties": {"fontSize": lit("9D"), "bold": lit("true"), "wordWrap": lit("true")}}],
               "rowHeaders": [{"properties": {"fontSize": lit("9D"), "wordWrap": lit("true")}}]}
    c = container(page, key, "pivotTable", x, y, w, h, z, {"query": q, "objects": objects}, title)
    if filters:
        c["filterConfig"] = filters
    return c


def series_chart(page, key, x, y, w, h, z, cat, series, value, title, colors, vtype="columnChart"):
    """Stacked chart with a legend column; every legend value gets its configured colour (stable across sites)."""
    q = {"queryState": {"Category": {"projections": [dict(proj(cat[0], cat[1], False, cat[2]), active=True)]},
                        "Series": {"projections": [proj(series[0], series[1], False, series[2])]},
                        "Y": {"projections": [proj(K, value[0], True, value[1])]}}}
    dp = [{"properties": {"fill": {"solid": {"color": lit(f"'{c}'")}}},
           "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0,
                                                              "Left": {"Column": {"Expression": {"SourceRef": {"Entity": series[0]}}, "Property": series[1]}},
                                                              "Right": {"Literal": {"Value": f"'{v}'"}}}}}]}} for v, c in colors.items()]
    objects = {"dataPoint": dp, "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}], **NO_AXIS_TITLES}
    return container(page, key, vtype, x, y, w, h, z, {"query": q, "objects": objects}, title)


def measures_chart(page, key, x, y, w, h, z, cat, values, title, colors, vtype="clusteredColumnChart", sort=None, tooltips=(), labels=False):
    """Chart with one series per measure, each with its own fixed colour; optional sort / tooltip measures."""
    q = {"queryState": {"Category": {"projections": [dict(proj(cat[0], cat[1], False, cat[2]), active=True)]},
                        "Y": {"projections": [proj(K, m, True, lbl) for m, lbl in values]}}}
    if tooltips:
        q["queryState"]["Tooltips"] = {"projections": [proj(K, m, True, lbl) for m, lbl in tooltips]}
    if sort:
        e, p, m, d = sort
        q["sortDefinition"] = {"sort": [{"field": fld(e, p, m), "direction": d}], "isDefaultSort": False}
    dp = [{"properties": {"fill": {"solid": {"color": lit(f"'{c}'")}}}, "selector": {"metadata": f"{K}.{m}"}} for (m, _), c in zip(values, colors)]
    objects = {"dataPoint": dp, "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}], **NO_AXIS_TITLES}
    if labels:
        objects["labels"] = [{"properties": {"show": lit("true"), "fontSize": lit("8D")}}]
    return container(page, key, vtype, x, y, w, h, z, {"query": q, "objects": objects}, title)


def combo_chart(page, key, x, y, w, h, z, cat, cols, lines, title, colors):
    q = {"queryState": {"Category": {"projections": [dict(proj(cat[0], cat[1], False, cat[2]), active=True)]},
                        "Y": {"projections": [proj(K, m, True, lbl) for m, lbl in cols]},
                        "Y2": {"projections": [proj(K, m, True, lbl) for m, lbl in lines]}}}
    dp = [{"properties": {"fill": {"solid": {"color": lit(f"'{c}'")}}}, "selector": {"metadata": f"{K}.{m}"}}
          for (m, _), c in zip(list(cols) + list(lines), colors)]
    objects = {"dataPoint": dp, "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]}
    return container(page, key, "lineClusteredColumnComboChart", x, y, w, h, z, {"query": q, "objects": objects}, title)


def note(page, key, x, y, w, h, z, measure, label, size=10):
    """Narrative / explanation measure shown as a one-column table: the header is the caption, the cell wraps any length."""
    if h < 58:
        # caption + padding take ~40 px: below 58 px the text row is pushed behind a scrollbar and the note looks empty
        raise ValueError(f"note '{key}' on page '{page}': height {h} px < 58 px - its text would be hidden behind the caption")
    t = table(page, key, x, y, w, h, z, [(K, measure, True, label)], None, widths={measure: w - 40})
    o = t["visual"]["objects"]
    o["values"][0]["properties"].update({"fontSize": lit(f"{size}D"), "backColorPrimary": {"solid": {"color": lit("'#FFFFFF'")}},
                                         "backColorSecondary": {"solid": {"color": lit("'#FFFFFF'")}}})
    # caption look instead of the theme's dark table header
    o["columnHeaders"][0]["properties"].update({"backColor": {"solid": {"color": lit("'#FFFFFF'")}}, "fontColor": {"solid": {"color": lit(f"'{NAVY}'")}}})
    return t


def date_slicer(p, h=56):
    return slicer(p, "date", 10, Y0, 170, h, 2, "DimDate", "Date", "Shift day (blank = today or last active day)")


def stuck_table(p, key, x, y, w, h, z, obj, title, extra_filter=None, stale=False):
    """Waiting items of one object type (Truck / Pallet / Shipment, or all when obj is None), oldest first.
    stale=False: LIVE items past their stage warning age; stale=True: records older than STALE_HOURS (inventory accuracy)."""
    flt = merge_filters(page_filter(FI, "Object", obj) if obj else None, measure_filter("Item Stale" if stale else "Item Over Warn", "1L"), extra_filter)
    cols = [(ST, "Stage", False, "Stage"), (FI, "Item", False, "Truck / pallet / shipment"), (FI, "Where", False, "Where")]
    if w >= 1000:
        cols.append((FI, "Detail", False, "Detail"))
    cols += [(K, "Item Age", True, "In stage"), (K, "Item Status Label", True, "Status"), (K, "Item Action", True, "What to do")]
    fixed = {"Item Age": 58, "Item Status Label": 92, "Item Age Min": 8}
    share = {"Stage": 0.24, "Item": 0.22, "Where": 0.17, "Detail": 0.22, "Item Action": 0.37}
    names = [c[1] for c in cols if c[1] in share]
    free = w - 40 - sum(fixed.values())
    tot = sum(share[n] for n in names)
    widths = {**{n: int(free * share[n] / tot) for n in names}, **fixed}
    t = table(p, key, x, y, w, h, z, cols, title, color_rules=[("Item Status Label", "Item Status Color")], sort=(K, "Item Age Min", True, "Descending"),
              widths=widths)
    # sort key only (8 px): a one-character header - a word header wraps letter by letter and stretches the whole header row
    t["visual"]["query"]["queryState"]["Values"]["projections"].append(proj(K, "Item Age Min", True, "↓"))
    t["visual"]["objects"]["columnWidth"].append({"properties": {"value": lit("8D")}, "selector": {"metadata": f"{K}.Item Age Min"}})
    t["filterConfig"] = flt
    return t


# =================================================================== pages
def page_process_flow():
    p = "process_flow"
    v = [*banner(p, "FLOW", "Process Flow (stuck now)"),
         note(p, "verdict", 10, Y0, 860, 84, 2, "Flow Verdict", "Biggest blockage now (live) and stale records", 10),
         note(p, "snap", 878, Y0, 392, 84, 3, "Flow Snapshot Label", "How to read this page", 8)]
    y1 = Y0 + 90
    v.append(card(p, "kpis", 10, y1, 760, 58, 4, strip("FLOW"), value_size=14, cols=7))
    v.append(note(p, "last", 778, y1, 492, 58, 5, "Last Activity Text", "Last activity (why a day can be empty)", 8))
    y2 = y1 + 64
    hb = 270
    v.append(table(p, "board", 10, y2, 1260, hb, 10,
                   [(ST, "Flow", False, "Flow"), (ST, "Stage", False, "Process stage (in process order)"), (ST, "Unit", False, "Unit"),
                    (K, "Stage Items", True, "Now"), (K, "Stage Over Warn", True, "Past warn"), (K, "Stage Over Crit", True, "Past crit"),
                    (K, "Stage Stale", True, "Stale"), (K, "Stage Oldest", True, "Oldest live"), (K, "Stage Limits", True, "Limits"),
                    (K, "Stage Status Label", True, "Status"), (K, "Stage Action Now", True, "What to do now")],
                   "Process stage board - every stage of the site process, inbound (top) to outbound (bottom)",
                   color_rules=[("Stage Status Label", "Stage Status Color")], sort=(ST, "Stage", False, "Ascending"),
                   widths={"Flow": 76, "Stage": 250, "Unit": 62, "Stage Items": 72, "Stage Over Warn": 72, "Stage Over Crit": 72, "Stage Stale": 72,
                           "Stage Oldest": 74, "Stage Limits": 128, "Stage Status Label": 96, "Stage Action Now": 260}))
    y3 = y2 + hb + GAP
    half = (1260 - GAP) // 2
    v.append(stuck_table(p, "stuck", 10, y3, half, BOTTOM - y3, 11, "Pallet",
                         "Pallets stuck now (live) - oldest first (trucks: Trucks & TTAT, shipments: Orders & Shipments)"))
    v.append(subtitle(stuck_table(p, "stale", 10 + half + GAP, y3, half, BOTTOM - y3, 12, None,
                                  "Stale records - verify physically and correct WMS", stale=True), "Stale Rule Text"))
    return p, "Process Flow", "FLOW", v


def gantt(p, key, x, y, w, h, z, prefix=""):
    """Truck Gantt - completed trucks on one timeline (minutes after the first check-in); segments wait / work / close-out."""
    g = measures_chart(p, key, x, y, w, h, z, ("TTAT", "TrailerID", "Truck"),
                       [("Gantt Start Min", "start (min after the first check-in)"), ("Truck Wait Min", "1 wait: check-in -> first scan"),
                        ("Truck Work Min", "2 unload / load"), ("Truck Rest Min", "3 close-out")],
                       prefix + "Truck Gantt - completed trucks on one timeline (minutes after the first check-in); the longest segment = where the truck lost time",
                       [PAL["gantt_offset"], SEG_WAIT, SEG_WORK, SEG_REST], vtype="barChart",
                       sort=(K, "Gantt Start Min", True, "Ascending"), tooltips=[("Truck TTAT Min", "TTAT (min)")], labels=True)
    # the start offset is only the invisible lead-in of the bar: no label
    g["visual"]["objects"]["labels"].append({"properties": {"show": lit("false")}, "selector": {"metadata": f"{K}.Gantt Start Min"}})
    return subtitle(g, "Truck Day Label")


def page_trucks():
    """Inbound & outbound trucks: direction + KPIs -> where the truck time goes -> dock / staging allocation -> every truck (Gantt) -> now."""
    p = "truck_diagnosis"
    bottom = tall_bottom(p)
    ts = "Truck Staging"
    v = [*banner(p, "TRUCKS", "Trucks & TTAT diagnosis"),
         slicer(p, "direction", 10, Y0, 190, 92, 2, "TTAT", "Direction", "Direction (blank = in + out)"),
         # 11 values: two rows (one row of 56 px hid the last three behind a scrollbar)
         card(p, "kpis", 208, Y0, 1062, 92, 3, strip("TRUCKS"), value_size=12, cols=6)]
    # 1. where the truck time goes
    y1 = Y0 + 98
    h1 = 250
    v.append(subtitle(measures_chart(p, "segments", 10, y1, 700, h1, 10, ("TTAT", "TrailerID", "Truck"),
                            [("Truck Wait Min", "1 Check-in to first scan (wait)"), ("Truck Work Min", "2 Unload / load (work)"),
                             ("Truck Rest Min", "3 After loading to close (close-out)")],
                            "1. Where the truck time goes - completed trucks, longest TTAT first (min)",
                            [SEG_WAIT, SEG_WORK, SEG_REST], vtype="barChart",
                            sort=(K, "Truck TTAT Min", True, "Descending"), tooltips=[("Truck TTAT Min", "TTAT (min)")]), "Truck Day Label"))
    v.append(subtitle(measures_chart(p, "dist", 718, y1, 552, h1, 11, (TB, "Band", "TTAT band"),
                            [("Band Trucks In", "Inbound trucks"), ("Band Trucks Out", "Outbound trucks")],
                            "TTAT distribution - completed trucks per TTAT band", [IN_C, OUT_C],
                            sort=(TB, "Band", False, "Ascending"), labels=True), "Truck Day Label"))
    # 2. dock + staging allocation (which doors and lanes carry the pallets)
    y2 = y1 + h1 + GAP
    h2 = 230
    v.append(card(p, "stg_kpis", 10, y2, 200, h2, 12,
                  [("Staging Trucks", "Trucks (window)"), ("Staging Pallets", "Pallets"), ("Staging Pallets Per Truck", "Pallets / truck"),
                   ("Staging Lanes Used", "Lanes used"), ("Staging Lane Dwell h", "Outbound lane dwell (h)")],
                  title="2. Dock & staging", value_size=10))
    v.append(measures_chart(p, "docks", 218, y2, 520, h2, 13, (ts, "Dock", "Dock"), [("Staging Pallets", "Pallets")],
                            "Pallets per dock (door) - trucks of the window", [PAL["dock"]], vtype="barChart",
                            sort=(K, "Staging Pallets", True, "Descending"), tooltips=[("Staging Trucks", "Trucks")], labels=True))
    v.append(measures_chart(p, "lanes", 746, y2, 524, h2, 14, (ts, "Staging Lane", "Staging / receiving lane"), [("Staging Pallets", "Pallets")],
                            "Pallets per staging lane (outbound: loaded from; inbound: received into)", [PAL["lane"]], vtype="barChart",
                            sort=(K, "Staging Pallets", True, "Descending"), tooltips=[("Staging Trucks", "Trucks")], labels=True))
    # 3. every truck: dock, lanes, pallets, times
    y3 = y2 + h2 + GAP
    h3 = 280
    v.append(subtitle(table(p, "alloc", 10, y3, 1260, h3, 15,
                   [(ts, "Direction", False, "Dir"), (ts, "TrailerID", False, "Truck"), (ts, "Dock", False, "Dock"),
                    (ts, "Staging Lane", False, "Staging / receiving lane"), (ts, "Lane Area", False, "Lane area"), (K, "Staging Pallets", True, "Pallets"),
                    (ts, "First Pallet", False, "First pallet"), (ts, "Last Pallet", False, "Last pallet"), (ts, "Check-in", False, "Check-in"),
                    (ts, "Close", False, "Close"), (ts, "Dispatch", False, "Dispatch"), (K, "Staging Truck TTAT", True, "TTAT (min)")],
                   "3. Truck allocation - dock, staging lanes and pallets per truck",
                   sort=(ts, "Close", False, "Descending"),
                   widths={"Direction": 64, "TrailerID": 110, "Dock": 90, "Staging Lane": 150, "Lane Area": 90, "Staging Pallets": 60,
                           "First Pallet": 110, "Last Pallet": 110, "Check-in": 110, "Close": 110, "Dispatch": 110, "Staging Truck TTAT": 66}),
                      "Staging Rule Text"))
    # 4. every truck on one timeline (full width, tall: scroll the page)
    y4 = y3 + h3 + GAP
    h4 = 520
    v.append(gantt(p, "gantt", 10, y4, 1260, h4, 16, prefix="4. "))
    # 5. today by hour + trucks on site now
    y5 = y4 + h4 + GAP
    v.append(subtitle(combo_chart(p, "hours", 10, y5, 620, bottom - y5, 17, ("DimHour", "Hour Label", "Hour"),
                         [("Hour Inbound Done", "Inbound trucks dispatched"), ("Hour Outbound Loads", "Outbound trucks closed")],
                         [("Hour Inbound Done TTAT", "Inbound TTAT (min)"), ("Hour Outbound TTAT", "Outbound TTAT (min)")],
                         "5. Trucks completed per hour of the report window and their TTAT (inbound at dispatch, outbound at close)",
                         [IN_C, OUT_C, PAL["in_ttat_line"], PAL["out_ttat_line"]]), "Truck Report Day Label"))
    v.append(stuck_table(p, "onsite", 638, y5, 632, bottom - y5, 18, "Truck", "Trucks on site now past the stage warning age (snapshot)"))
    return p, "Trucks & TTAT", "TRUCKS", v


def page_pallet_flow():
    p = "pallet_flow"
    v = [*banner(p, "PALLETS", "Pallet Flow"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("PALLETS"), value_size=14, cols=6)]
    y1 = Y0 + 62
    h1 = 320
    colors = move_class_colors()
    v.append(series_chart(p, "byhour", 10, y1, 760, h1, 10, ("DimHour", "Hour Label", "Hour"), (UA, "Move_Class", "Process step"),
                          ("Moves Hour", "Pallets moved"), "Pallets moved by hour and process step (report day; pallet counted once per user-hour)", colors))
    v.append(subtitle(series_chart(p, "byday", 778, y1, 492, h1, 11, (UA, "Shift_Date", "Shift day"), (UA, "Move_Class", "Process step"),
                                   ("Moves Day Trend", "Pallets moved"), "Pallets moved per shift day by process step", colors), "Lookback Text"))
    y2 = y1 + h1 + GAP
    v.append(matrix(p, "heat", 10, y2, 640, BOTTOM - y2, 12, [(ST, "Stage", "Stage")], [(TB, "Band", "Time in location")],
                    ("Band Items", "Pallets"), "Pallets waiting now by stage and time in location (green / amber / red = stage limits)",
                    back_color="Band Cell Color", filters=page_filter(ST, "Object", "Pallet")))
    v.append(table(p, "areas", 658, y2, 612, BOTTOM - y2, 13,
                   [("Pallets Movement", "from_area", False, "From area"), ("Pallets Movement", "to_area", False, "To area"),
                    (K, "Area Moves Day", True, "Pallets (report day)")],
                   "Top area-to-area pallet flows of the report day", sort=(K, "Area Moves Day", True, "Descending"),
                   widths={"from_area": 200, "to_area": 200, "Area Moves Day": 120}))
    return p, "Pallet Flow", "PALLETS", v


def page_orders():
    p = "orders_flow"
    v = [*banner(p, "ORDERS", "Orders & Shipments"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("ORDERS"), value_size=14, cols=6)]
    y1 = Y0 + 62
    v.append(note(p, "used", 10, y1, 1260, 60, 4, "Orders Flow Text", "Order flow at this site (from the live WMS shipment statuses)", 9))
    y2 = y1 + 66
    h2 = 240
    flt = page_filter(ST, "Object", "Shipment")
    bar = measures_chart(p, "stages", 10, y2, 500, h2, 10, (ST, "Stage", "Stage"), [("Stage Items", "Open shipments")],
                         "Open shipments by order stage (now)", [PAL["orders"]], vtype="clusteredBarChart", sort=(ST, "Stage", False, "Ascending"), labels=True)
    bar["filterConfig"] = flt
    v.append(bar)
    v.append(matrix(p, "heat", 518, y2, 752, h2, 11, [(ST, "Stage", "Stage")], [(TB, "Band", "Time in status")],
                    ("Band Items", "Shipments"), "Open shipments by stage and time in the current status", back_color="Band Cell Color", filters=flt))
    y3 = y2 + h2 + GAP
    v.append(stuck_table(p, "late", 10, y3, 1260, BOTTOM - y3, 12, "Shipment", "Open shipments past the stage warning age - oldest first"))
    return p, "Orders & Shipments", "ORDERS", v


def page_sap_prod():
    p = "production_sap"
    sp = "SAP Production"
    v = [*banner(p, "SAPPROD", "Production - SAP vs PrIME"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("SAPPROD"), value_size=14, cols=5)]
    y1 = Y0 + 62
    v.append(note(p, "why", 10, y1, 840, 66, 4, "Production Explanation", "Why PrIME production looks the way it does", 9))
    v.append(note(p, "act", 858, y1, 412, 66, 5, "Production Explanation Action", "What to do", 9))
    y2 = y1 + 72
    h2 = 330
    v.append(subtitle(measures_chart(p, "days", 10, y2, 760, h2, 10, (sp, "Posting_Date", "Day"),
                                     [("SAP Pallets By Day", "SAP FG pallets (GR 101)"), ("WMS Pallets By Day", "PrIME produced pallets")],
                                     "Finished-goods pallets per day - SAP goods receipts vs PrIME production", [SAP_C, WMS_C], labels=True), "Lookback Text"))
    v.append(table(p, "daytbl", 778, y2, 492, h2, 11,
                   [(sp, "Posting_Date", False, "Day"), (K, "SAP GR Lines By Day", True, "SAP GR lines"), (K, "SAP Pallets By Day", True, "SAP pallets"),
                    (K, "WMS Pallets By Day", True, "PrIME pallets"), (K, "WMS Coverage By Day", True, "PrIME / SAP")],
                   "Per day", sort=(sp, "Posting_Date", False, "Descending"),
                   widths={"Posting_Date": 90, "SAP GR Lines By Day": 80, "SAP Pallets By Day": 80, "WMS Pallets By Day": 80, "WMS Coverage By Day": 80}))
    y3 = y2 + h2 + GAP
    v.append(table(p, "mats", 10, y3, 1260, BOTTOM - y3, 12,
                   [(sp, "MatNr", False, "Material"), (sp, "MatDesc", False, "Description"), (sp, "BUoM", False, "Base unit"),
                    (K, "SAP Material Qty Day", True, "Quantity (base unit)"), (K, "SAP Material Pallets Day", True, "Pallets"),
                    (sp, "Pallet_Basis", False, "Pallet basis")],
                   "SAP finished-goods receipts of the report day by material", sort=(K, "SAP Material Pallets Day", True, "Descending"),
                   widths={"MatNr": 90, "MatDesc": 420, "BUoM": 70, "SAP Material Qty Day": 130, "SAP Material Pallets Day": 90, "Pallet_Basis": 160}))
    return p, "Production SAP vs PrIME", "SAPPROD", v


def page_field_guide():
    p = "field_guide"
    fg = "Cfg_FieldGuide"
    v = [*banner(p, "FIELDS", "Field Guide")]
    h1 = int((BOTTOM - Y0) * 0.62)
    v.append(table(p, "fields", 10, Y0, 1260, h1, 10,
                   [(fg, "Order", False, "#"), (fg, "Page", False, "Page"), (fg, "Visual", False, "Visual"), (fg, "Field", False, "Field"),
                    (fg, "Unit", False, "Unit"), (fg, "Meaning", False, "Meaning / calculation"), (fg, "Grouping_Colour", False, "Grouping & colour"),
                    (fg, "Source", False, "Source")],
                   "Every field of the report: meaning, unit of measure, grouping / colour rule and source",
                   sort=(fg, "Order", False, "Ascending"),
                   widths={"Order": 30, "Page": 90, "Visual": 130, "Field": 130, "Unit": 70, "Meaning": 420, "Grouping_Colour": 220, "Source": 140}))
    pg = "Cfg_PageGuide"
    v.append(table(p, "page_tech", 10, Y0 + h1 + 8, 1260, BOTTOM - Y0 - h1 - 8, 11,
                   [(pg, "Page", False, "Page"), (pg, "How_Calculated", False, "How it is calculated (data sources, rules)"),
                    (pg, "How_To_Configure", False, "How to configure (report owner)")],
                   "For the report owner: how each page is calculated and configured",
                   widths={"Page": 150, "How_Calculated": 640, "How_To_Configure": 440}))
    return p, "Field Guide", "FIELDS", v


def page_ask_copilot():
    p = "ask_copilot"
    cq = "Cfg_CopilotQuestions"
    v = [*banner(p, "COPILOT", "Ask Copilot")]
    v.append(table(p, "questions", 10, Y0, 1260, BOTTOM - Y0, 11,
                   [(cq, "Order", False, "#"), (cq, "Group", False, "Topic"), (cq, "Template", False, "Question template"),
                    (cq, "Example", False, "Example to copy"), (cq, "Answer", False, "What you get")],
                   "Question templates for Copilot - open Copilot (top right), copy an example, change <SITE>, <KPI> or <OWNER>",
                   sort=(cq, "Order", False, "Ascending"),
                   widths={"Order": 30, "Group": 110, "Template": 360, "Example": 380, "Answer": 360}))
    return p, "Ask Copilot", "COPILOT", v


def page_lines_shifts():
    """Excel LTA_MONITOR (line x hour grid) + LTA_RCA (root cause + action per line) + the ALERTS 'TTAT diagnostic' (waiting vs unloading per shift)."""
    p = "lines_shifts"
    pt = "Produced Pallet"
    v = [*banner(p, "LINES", "Line RCA & truck shifts"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("LINES"), value_size=12, cols=8)]
    y1 = Y0 + 62
    h1 = 300
    v.append(table(p, "rca", 10, y1, 1260, h1, 10,
                   [(pt, "WORKSTATION_LTA", False, "Line source"), (pt, "PRODUCT_LINE", False, "Line"), (K, "Line Day Pallets", True, "Pallets (day)"),
                    (K, "Line Day vs Baseline", True, "Day vs baseline"), (K, "Line Latest Hr Pallets", True, "Latest hour"),
                    (K, "Line Baseline Same Hr", True, "Baseline same hour"), (K, "Line Variance", True, "vs baseline"),
                    (K, "Line Status", True, "Status"), (K, "Line Hours Idle", True, "Hours idle"), (K, "Line Root Cause", True, "Root cause"),
                    (K, "Line Action", True, "Action")],
                   "Production lines - latest hour vs the baseline of the same hour over the look-back days, root cause and action (Excel LTA_RCA)",
                   sort=(K, "Line Variance", True, "Ascending"),
                   widths={"WORKSTATION_LTA": 80, "PRODUCT_LINE": 90, "Line Day Pallets": 64, "Line Day vs Baseline": 64, "Line Latest Hr Pallets": 58,
                           "Line Baseline Same Hr": 64, "Line Variance": 58, "Line Status": 80, "Line Hours Idle": 50, "Line Root Cause": 330,
                           "Line Action": 250}))
    v[-1] = subtitle(v[-1], "Lookback Text")
    y2 = y1 + h1 + GAP
    v.append(matrix(p, "grid", 10, y2, 700, BOTTOM - y2, 11, [(pt, "PRODUCT_LINE", "Line")], [(pt, "ReportHour", "Hour")],
                    ("Line Hour Pallets", "Pallets"), "Pallets produced per line and hour of the report shift day (Excel LTA_MONITOR)"))
    v.append(subtitle(table(p, "shifts", 718, y2, 552, BOTTOM - y2, 12,
                            [("TTAT", "Direction", False, "Direction"), ("Cfg_Shift", "Shift", False, "Shift"), (K, "Shift Label", True, "Hours"),
                             (K, "Shift Trucks", True, "Trucks"), (K, "Shift Avg Wait Min", True, "Avg wait"), (K, "Shift Avg Work Min", True, "Avg (un)load"),
                             (K, "Shift Avg TTAT Min", True, "Avg TTAT"), (K, "Shift Verdict", True, "Read")],
                            "TTAT by shift - is the delay waiting or (un)loading? (Excel ALERTS TTAT diagnostic)",
                            sort=("Cfg_Shift", "Shift", False, "Ascending"),
                            widths={"Direction": 58, "Shift": 50, "Shift Label": 80, "Shift Trucks": 46, "Shift Avg Wait Min": 52, "Shift Avg Work Min": 56,
                                    "Shift Avg TTAT Min": 52, "Shift Verdict": 180}), "Shift Window Text"))
    return p, "Line RCA & Shifts", "LINES", v


def diag_pages():
    from pbi_common import sap_included
    return [page_process_flow(), page_process_mining(), page_trucks(), page_lines_shifts(), page_pallet_flow(), page_inventory(), page_orders(),
            *([page_sap_prod()] if sap_included() else []), page_field_guide(), page_ask_copilot()]


# =================================================================== process mining + inventory
SANKEY = "sankey02300D1BE6F5427989F3DE31CCA9E0F32020"     # Microsoft certified Sankey (AppSource) - registered in report.json
PET = "Process Edges"


def sankey(p, key, x, y, w, h, z, flow, title):
    """Microsoft Sankey: Source = From step, Destination = To step, Weight = distinct cases of the main flow (Forward + Open hand-offs);
    node and link labels show the numbers."""
    q = {"queryState": {"Source": {"projections": [dict(proj(PET, "From_Step", False, "From step"), active=True)]},
                        "Destination": {"projections": [proj(PET, "To_Step", False, "To step")]},
                        "Weight": {"projections": [proj(K, "PM Flow Cases", True, "Cases")]}}}
    objects = {"labels": [{"properties": {"show": lit("true"), "fontSize": lit("9D")}}],
               "linkLabels": [{"properties": {"show": lit("true"), "fontSize": lit("8D")}}]}
    c = container(p, key, SANKEY, x, y, w, h, z, {"query": q, "objects": objects}, title)
    c["filterConfig"] = page_filter(PET, "Flow", flow)
    return c


def in_values_filter(entity, prop, values):
    return {"filters": [{"name": hid(entity, prop, *values), "field": fld(entity, prop, False), "type": "Categorical",
                         "filter": {"Version": 2, "From": [{"Name": "c", "Entity": entity, "Type": 0}],
                                    "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": prop}}],
                                                                    "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values]}}}]}}]}


def page_process_mining():
    """Order -> pick -> load -> truck process mined from the event logs (directly-follows graph), where it is stuck now and the flow alerts."""
    p = "process_mining"
    v = [*banner(p, "PROCMINING", "Process Mining - order to truck"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("PM"), value_size=13, cols=7)]
    y1 = Y0 + 62
    h1 = 150     # the verdict carries up to 5 sentences (orders, pallets, trucks, storage, stuck now)
    # one home per item: the truck Gantt is on Trucks & TTAT, the inbound / outbound alert list on Alerts
    v.append(note(p, "verdict", 10, y1, 1260, h1, 4, "PM Verdict",
                  "Where the flow loses most time and where it is stuck now (measured) - truck timeline: Trucks & TTAT; alert status: Alerts", 9))
    y2 = y1 + h1 + GAP
    h2 = 260
    v.append(subtitle(sankey(p, "orders", 10, y2, 626, h2, 6, "Order",
                             "Order flow: created -> pick released -> picked & staged -> loaded -> truck dispatched (orders; 'Open' = stuck now)"),
                      "PM Order Flow Note"))
    v.append(subtitle(sankey(p, "pallets", 644, y2, 626, h2, 7, "Pallet",
                             "Pallet flow through the main process steps (distinct pallets per forward hand-off; transfers / other moves / rework: table below)"),
                      "PM Pallet Flow Note"))
    y3 = y2 + h2 + GAP
    v.append(subtitle(table(p, "handoffs", 10, y3, 1260, BOTTOM - y3, 9,
                   [(PET, "Flow", False, "Flow"), (PET, "From_Step", False, "From"), (PET, "To_Step", False, "To"), (K, "PM Cases", True, "Cases"),
                    (K, "PM Median Text", True, "Median"), (K, "PM P95 Text", True, "p95"), (K, "PM Case Hours", True, "Case-hours"),
                    (K, "PM Edge Verdict", True, "Verdict")],
                   "Hand-offs ranked by total waiting time (cases x median) - the top forward hand-off is the bottleneck",
                   sort=(K, "PM Case Hours", True, "Descending"),
                   widths={"Flow": 70, "From_Step": 200, "To_Step": 220, "PM Cases": 70, "PM Median Text": 80, "PM P95 Text": 80,
                           "PM Case Hours": 80, "PM Edge Verdict": 420}), "PM Window Text"))
    return p, "Process Mining", "PROCMINING", v


def page_inventory():
    """All pallets (finished goods + materials) and storage space now - works at every site (Inv KPIs is the Level A view)."""
    p = "inventory_now"
    lu = "Location Utilisation"
    v = [*banner(p, "INVENTORY", "Inventory - stock & space now"),
         card(p, "kpis", 10, Y0, 1260, 56, 3, strip("INVENTORY"), value_size=14, cols=7)]
    y1 = Y0 + 62
    h1 = 320
    v.append(measures_chart(p, "space", 10, y1, 620, h1, 10, (lu, "Area", "Area"),
                            [("Loc Area Occupied", "Occupied locations"), ("Loc Free", "Free locations")],
                            "Storage space by area now - occupied vs free locations (utilisation in the tooltip)",
                            [PAL["occupied"], PAL["free"]], vtype="barChart", sort=(K, "Loc Area Occupied", True, "Descending"),
                            tooltips=[("Loc Area Util", "Utilisation")], labels=True))
    v.append(measures_chart(p, "age", 638, y1, 632, h1, 11, ("Cfg_StockAge", "Band", "Age band"),
                            [("Inv Band FG Pallets", "Finished goods"), ("Inv Band Material Pallets", "Materials")],
                            "Pallets in stock by age band now (days since receipt; FIFO date when no receipt date)",
                            [PAL["fg"], PAL["material"]], vtype="columnChart", sort=("Cfg_StockAge", "Band", False, "Ascending"), labels=True))
    y2 = y1 + h1 + GAP
    v.append(matrix(p, "status", 10, y2, 400, BOTTOM - y2, 12, [(IVT, "Area", "Area")], [(IVT, "Status", "WMS status")],
                    ("Inv Pallets Cell", "Pallets"), "Pallets by area and WMS status now"))
    v.append(subtitle(table(p, "old", 418, y2, 420, BOTTOM - y2, 13,
                   [(IVT, "Area", False, "Area"), (IVT, "Location Class", False, "Location class"), (IVT, "Material", False, "Material"),
                    (K, "Inv Old Pallets Row", True, "Old pallets"), (K, "Inv Old Row All Pallets", True, "All pallets"),
                    (K, "Inv Old Row Max Age", True, "Oldest (days)")],
                   "Old stock by area - largest first",
                   sort=(K, "Inv Old Pallets Row", True, "Descending"),
                   widths={"Area": 76, "Location Class": 82, "Material": 74, "Inv Old Pallets Row": 56, "Inv Old Row All Pallets": 56,
                           "Inv Old Row Max Age": 56}), "Inv Old Rule Text"))
    v.append(table(p, "old_cause", 846, y2, 424, BOTTOM - y2, 14,
                   [(IVT, "Location Class", False, "Location class"), (K, "Inv Old Pallets Row", True, "Old pallets"),
                    (K, "Inv Old Cause", True, "Likely cause"), (K, "Inv Old Action", True, "Action")],
                   "Old stock - likely cause and action per location class",
                   sort=(K, "Inv Old Pallets Row", True, "Descending"),
                   widths={"Location Class": 70, "Inv Old Pallets Row": 50, "Inv Old Cause": 145, "Inv Old Action": 145}))
    return p, "Inventory", "INVENTORY", v


IVT = "Inventory"



