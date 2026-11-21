"""Create the ONE inputs file Hypercare_KPI_Inputs.xlsx (Read me / Sites / Alert targets) from today's config.

    py tools/make_inputs_template.py            create it in the synced SharePoint folder (config/inputs_source.csv) if it does not exist yet
    py tools/make_inputs_template.py --force    overwrite it (asks nothing - use only when the file is broken)
    py tools/make_inputs_template.py --template write the empty-structure copy to inputs/Hypercare_KPI_Inputs_TEMPLATE.xlsx (kit)

Alert targets = the alert KPIs (config/alert_rules.csv) with the BD values as 'All sites' rows - every site follows BD until a site row is added."""
import csv
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

import inputs_file as IF

ROOT = IF.ROOT
NAVY = "0B2A4A"


def read(name):
    return list(csv.DictReader(open(ROOT / "config" / name, encoding="utf-8-sig")))


def effective(r, lvl):
    def n(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    ab, pct, t = n(r.get(f"{lvl}_Abs")), n(r.get(f"{lvl}_Pct")), n(r.get("Target"))
    if ab is not None:
        return ab
    if t is None or pct is None:
        return None
    return t * pct if r["Direction"] == "Higher" else t * (1 + pct) if r["Direction"] == "Lower" else pct if r["Direction"] == "Band" else None


def sheet(wb, title, cols, rows, table, widths):
    ws = wb.create_sheet(title)
    ws.append([c for c, _ in cols])
    for r in rows:
        ws.append([r.get(c) for c, _ in cols])
    for i, (c, note) in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=i)
        cell.comment = Comment(note, "Hypercare KPI")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        ws.column_dimensions[cell.column_letter].width = widths.get(c, 16)
    last = ws.cell(row=max(2, len(rows) + 1), column=len(cols)).coordinate
    t = Table(displayName=table, ref=f"A1:{last}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(t)
    ws.freeze_panes = "B2"
    return ws


def build(path, empty=False):
    sites = [] if empty else read("site_config.csv")
    th = {r["KPI_Key"]: r for r in read("kpi_thresholds.csv") if r["Site"] == "*"}
    alert_keys = []
    for r in read("alert_rules.csv"):
        if r["KPI_Key"] not in alert_keys:
            alert_keys.append(r["KPI_Key"])
    wb = Workbook()
    rm = wb.active
    rm.title = "Read me"
    lines = [("Hypercare KPI - inputs (one file for every site)", True),
             ("", False),
             ("1  Add a site (the report holds at most %d sites)" % IF.max_sites(), True),
             ("Tab Sites: add one row - code, name, PrIME 2014 / 2022, replica server + database, UTC offset, shift start hours, hypercare start, SAP plant.", False),
             ("Then run on the kit laptop:  py tools/add_site.py <CODE>  - reads the replica, proposes every technical setting, checks every query,", False),
             ("builds and tests the site; publish with py tools/publish.py. Confirm the items of docs/ONBOARDING_<CODE>.md with the site.", False),
             ("Remove a site: delete its row, then  py tools/apply_inputs.py --confirm  and rebuild.", False),
             ("", False),
             ("2  Alert targets", True),
             ("Rows with Site = 'All sites' apply to every site (they are the Binh Duong thresholds).", False),
             ("To change one site: add a row with its SiteCode and the KPI_Key, fill Target, Warning_At, Critical_At (in the KPI unit; % as 0.85).", False),
             ("The report reads this tab at every refresh (every 30 min) - no rebuild. A wrong row is ignored and listed on Config & Health > Input issues.", False),
             ("Direction: Higher = bigger is better (warning when below Warning_At), Lower = smaller is better (warning when above), Band = stay near Target.", False),
             ("", False),
             ("Do not rename the tabs, the tables or the column headers. Hover a header for its meaning.", False)]
    for i, (t, bold) in enumerate(lines, start=1):
        c = rm.cell(row=i, column=1, value=t)
        c.font = Font(bold=bold, size=13 if i == 1 else 11, color=NAVY if bold else "252423")
        c.alignment = Alignment(wrap_text=False)
    rm.column_dimensions["A"].width = 150
    site_rows = [{c: s.get(c, "") for c, _ in IF.SITE_COLS} for s in sites]
    for s in site_rows:
        s["Hypercare_Start"] = (s.get("Hypercare_Start") or "")[:10]
        for c in ("UTC_Offset_h", "Shift1_Start", "Shift2_Start", "Shift3_Start", "Has_Production", "Is_Default"):
            try:
                v = float(s[c]); s[c] = int(v) if v.is_integer() else v
            except (TypeError, ValueError):
                pass
    ws_s = sheet(wb, "Sites", IF.SITE_COLS, site_rows, "Sites",
                 {"SiteCode": 12, "SiteName": 22, "ReplicaServer": 52, "ReplicaDatabase": 20, "Hypercare_Start": 16, "WMS_Version": 13})
    t_rows = []
    for k in alert_keys:
        r = th[k]
        t_rows.append({"Site": IF.ALL_SITES, "KPI_Key": k, "KPI_Name": r["KPI_Name"], "Unit": r["Unit"], "Direction": r["Direction"],
                       "Target": float(r["Target"]), "Warning_At": effective(r, "Warn"), "Critical_At": effective(r, "Crit"),
                       "Changed_By": "kit default (Binh Duong)", "Reason": "BD threshold - default for every site"})
    ws_t = sheet(wb, "Alert targets", IF.TARGET_COLS, t_rows, "AlertTargets",
                 {"KPI_Key": 16, "KPI_Name": 48, "Changed_By": 24, "Reason": 40})
    lists = wb.create_sheet("Lists")
    lists.sheet_state = "hidden"
    codes = [IF.ALL_SITES] + [s["SiteCode"] for s in sites]
    for i, v in enumerate(codes, start=1):
        lists.cell(row=i, column=1, value=v)
    for i, v in enumerate(alert_keys, start=1):
        lists.cell(row=i, column=2, value=v)
    for i, v in enumerate(["PrIME 2014", "PrIME 2022"], start=1):
        lists.cell(row=i, column=3, value=v)
    n = 500
    dv_site = DataValidation(type="list", formula1=f"=Lists!$A$1:$A${IF.max_sites() + 1}", allow_blank=False)
    dv_kpi = DataValidation(type="list", formula1=f"=Lists!$B$1:$B${len(alert_keys)}", allow_blank=False)
    dv_num = DataValidation(type="decimal", operator="between", formula1="-1000000", formula2="1000000", allow_blank=True,
                            error="A number in the KPI unit (% as 0.85)", errorTitle="Number expected", showErrorMessage=True)
    dv_wms = DataValidation(type="list", formula1="=Lists!$C$1:$C$2", allow_blank=False)
    dv_01 = DataValidation(type="list", formula1='"0,1"', allow_blank=False)
    dv_hour = DataValidation(type="whole", operator="between", formula1="0", formula2="23", showErrorMessage=True, error="Hour 0-23")
    for dv, rng, ws in ((dv_site, f"A2:A{n}", ws_t), (dv_kpi, f"B2:B{n}", ws_t), (dv_num, f"F2:H{n}", ws_t),
                        (dv_wms, f"D2:D{n}", ws_s), (dv_01, f"N2:O{n}", ws_s), (dv_hour, f"I2:K{n}", ws_s)):
        ws.add_data_validation(dv)
        dv.add(rng)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return len(site_rows), len(t_rows)


def main(argv):
    if "--template" in argv:
        out = ROOT / "inputs" / "Hypercare_KPI_Inputs_TEMPLATE.xlsx"
        s, t = build(out, empty=True)
        print(f"template (no sites, {t} alert KPIs at BD values) -> {out.relative_to(ROOT)}")
        return
    p = IF.local_path()
    if p.exists() and "--force" not in argv:
        print(f"exists, not touched: {p}\n   (edit it in Excel / SharePoint; --force rewrites it from the config)")
        return
    s, t = build(p)
    print(f"created {p}\n   {s} sites, {t} alert KPIs ('All sites' = BD thresholds) - OneDrive uploads it to the PRIME ELS SharePoint folder")
    IF.read(p)


if __name__ == "__main__":
    main(sys.argv[1:])
