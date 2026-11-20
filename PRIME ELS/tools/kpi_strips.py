"""KPI strips (multi-row cards) of the generated pages: (measure, label) per strip.

Every strip shows the display twin '<measure> (strip)' = [measure] + 0 (measures_diag.strip_twins) with the base measure's unit
format plus a zero section '–' (build_pbip.apply_strip_formats) - a strip never shows '(Blank)'. One registry for report_pages,
report_diag and the model build: a field added here gets its twin automatically.
"""
STRIP_SUFFIX = " (strip)"
STRIPS = {
    "USERS": [("KPI Active Users", "Active users"), ("Active Users Prev", "Users prev day"), ("User Pallets Moved", "Pallets moved"),
              ("User Pallets Prev", "Pallets prev day"), ("KPI User Productivity", "Pallets / user-hour"), ("User Productivity Prev", "Pallets / user-h prev day"),
              ("User Active Hours", "User-hours"), ("User Productivity 7d", "Trend avg")],
    "FLOW": [("Flow Items Waiting", "Waiting in a stage now"), ("Flow Items Warning", "Past warning (live)"), ("Flow Items Critical", "Past critical (live)"),
             ("Flow Items Stale", "Stale records"), ("Trucks On Site", "Trucks on site"), ("Pallets In Flow Now", "Pallets in flow"),
             ("Shipments Open", "Open shipments")],
    "TRUCKS": [("Inbound Trucks", "Inbound trucks (day)"), ("Inbound Trucks Prev", "Inbound prev day"), ("KPI TTAT In", "Inbound TTAT"),
               ("KPI TTAT In Prev", "In TTAT prev day"), ("Outbound Trucks", "Outbound trucks (day)"), ("Outbound Trucks Prev", "Outbound prev day"),
               ("KPI TTAT Out", "Outbound TTAT"), ("KPI TTAT Out Prev", "Out TTAT prev day"), ("Trucks On Site", "On site now"),
               ("Trucks Over Crit", "Past critical now"), ("Trucks Stale", "Stale (> STALE_HOURS)")],
    "PALLETS": [("User Pallets Moved", "Pallets moved (day)"), ("Pallets Moved Prev", "prev day"), ("Pallets Moved Prior Avg", "prior-days avg"),
                ("Pallets In Flow Now", "In flow stages now"), ("Pallets Over Crit", "Past critical now (live)"), ("Pallets Stale", "Stale records")],
    "ORDERS": [("Shipments Open", "Open shipments now"), ("Shipments Late", "Past late ship date"), ("Shipments Created Day", "Created (day)"),
               ("Shipments Created Prev", "Created prev day"), ("Shipments Loaded Day", "Loaded (day)"), ("Shipments Loaded Prev", "Loaded prev day")],
    "SAPPROD": [("SAP Pallets Day", "SAP FG pallets (day)"), ("SAP Pallets Prev", "prev day"), ("SAP Pallets Prior Avg", "prior-days avg"),
                ("Prod Pallets Day", "PrIME produced (day)"), ("KPI WMS Coverage", "PrIME / SAP (window)")],
    "PM": [("PM Orders Traced", "Orders traced (7 d)"), ("PM Orders Waiting", "Orders open now"), ("PM Trucks Traced", "Trucks traced (7 d)"),
           ("PM Trucks Waiting", "Trucks open now"), ("PM Pallet Handoffs", "Pallet hand-offs (7 d)"), ("KPI TTAT In", "Inbound TTAT (day)"),
           ("KPI TTAT Out", "Outbound TTAT (day)")],
    "INVENTORY": [("Inv Pallets", "Pallets in stock now"), ("Inv FG Pallets", "Finished goods"), ("Inv Material Pallets", "Materials"),
                  ("Inv Old Pallets", "Old stock (> STOCK_OLD_DAYS)"), ("Inv Old Share", "Old stock share"), ("KPI Loc Util", "Location utilisation"),
                  ("Loc Free", "Free locations")],
    "LINES": [("Prod Pallets Day", "Pallets produced (day)"), ("KPI PPH", "Pallets / h (day)"), ("KPI Lines In Alert", "Lines in alert"),
              ("Prod Run Rate 3h", "Run rate last hours"), ("Prod Projected EOD", "Projected end of day"), ("Prod Required Rate", "Rate needed for plan"),
              ("Inbound Trucks", "Inbound trucks (day)"), ("Outbound Trucks", "Outbound trucks (day)")],
}


def strip(key):
    return [(m + STRIP_SUFFIX, lbl) for m, lbl in STRIPS[key]]
