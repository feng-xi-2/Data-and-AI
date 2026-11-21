"""The ONE inputs file (config/inputs_source.csv): Hypercare_KPI_Inputs.xlsx in the PRIME ELS SharePoint folder (Data Projects/PRIME ELS/Hypercare KPI), synced by OneDrive.

Tabs (Excel tables, so a user can add rows without breaking the layout):
  Sites          table 'Sites'         one row per site in the report (max Max_Sites): business settings only
  Alert targets  table 'AlertTargets'  Site = 'All sites' (every site, = BD thresholds) or a SiteCode (override one KPI of one site)
The model reads 'Alert targets' at every refresh (no rebuild); 'Sites' is structural (a site = replica partitions) -> tools/apply_inputs.py.
Tools only READ the SharePoint file (make_inputs_template.py creates it once when it does not exist)."""
import csv
import re
import os
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
ALL_SITES = "All sites"
SITE_COLS = [("SiteCode", "Short code, capitals, no spaces (e.g. JAKARTA)"), ("SiteName", "Name shown in the Site slicer, e.g. 'Jakarta (ID01)'"),
             ("Region", "APAC / Greater China / Europe ..."), ("WMS_Version", "PrIME 2014 or PrIME 2022"),
             ("ReplicaServer", "Data replica server, e.g. <replica-server>"), ("ReplicaDatabase", "Replica database name"),
             ("WH_ID", "Warehouse id in PrIME (blank = profiled from the replica)"), ("UTC_Offset_h", "Site time vs UTC in hours (e.g. 7, 8, 2)"),
             ("Shift1_Start", "Hour the first shift starts (0-23) = start of the report day"), ("Shift2_Start", "Hour shift 2 starts"),
             ("Shift3_Start", "Hour shift 3 starts (= Shift2_Start when the site runs 2 shifts)"), ("Hypercare_Start", "Go-live / hypercare start date (yyyy-mm-dd)"),
             ("SAP_Plant", "SAP plant code for SAP production receipts (blank = none)"), ("Has_Production", "1 = production lines received in PrIME, 0 = distribution centre"),
             ("Is_Default", "1 = the site shown when the report opens (exactly one row)")]
TARGET_COLS = [("Site", f"'{ALL_SITES}' or a SiteCode of the Sites tab"), ("KPI_Key", "KPI code (dropdown)"), ("KPI_Name", "for reading only"),
               ("Unit", "for reading only"), ("Direction", "Higher = bigger is better, Lower = smaller is better, Band = stay near Target (Warning_At / Critical_At = allowed +/- deviation)"),
               ("Target", "Target in the KPI unit (% as 0.85)"), ("Warning_At", "Warning limit in the KPI unit"), ("Critical_At", "Critical limit in the KPI unit"),
               ("Changed_By", "Who changed it"), ("Reason", "Why")]


def source():
    src = {r["Key"]: r["Value"] for r in csv.DictReader(open(CFG / "inputs_source.csv", encoding="utf-8-sig"))}
    # PRIME ELS and PRISM 2 ELS are different projects: the PRIME ELS inputs never live in a PRISM 2 folder
    bad = [k for k in ("SharePoint_Url", "Local_Path") if re.search(r"PRISM", src.get(k, ""), re.I)]
    if bad:
        raise SystemExit(f"config/inputs_source.csv {bad} points into a PRISM 2 folder - PRIME ELS inputs belong in Data Projects/PRIME ELS")
    return src


def local_path():
    return Path(os.path.expandvars(source()["Local_Path"]))


def max_sites():
    return int(source()["Max_Sites"])


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return "BAD"


def _table_rows(wb, table_name):
    for ws in wb.worksheets:
        if table_name in ws.tables:
            ref = ws.tables[table_name].ref
            rows = [[c.value for c in r] for r in ws[ref]]
            head = [str(h).strip() if h is not None else "" for h in rows[0]]
            return [dict(zip(head, r)) for r in rows[1:] if any(v not in (None, "") for v in r)]
    raise SystemExit(f"inputs file: Excel table '{table_name}' not found - recreate the file with py tools/make_inputs_template.py")


def read(path=None):
    """-> (sites, targets, issues). Never raises on content errors: every bad row becomes an issue and is skipped."""
    p = Path(path) if path else local_path()
    if not p.exists():
        raise SystemExit(f"inputs file not found: {p}\n   create it: py tools/make_inputs_template.py  (OneDrive must sync the ELS shortcut)")
    wb = openpyxl.load_workbook(p, data_only=True)
    issues, sites, targets = [], [], []
    for i, r in enumerate(_table_rows(wb, "Sites"), start=2):
        code = str(r.get("SiteCode") or "").strip().upper()
        if not code:
            continue
        row = {c: ("" if r.get(c) is None else str(r.get(c)).strip()) for c, _ in SITE_COLS}
        row["SiteCode"] = code
        for c in ("UTC_Offset_h", "Shift1_Start", "Shift2_Start", "Shift3_Start"):
            if _num(row[c]) in (None, "BAD"):
                issues.append(("Sites", i, code, f"{c} must be a number (got '{row[c]}')"))
        if row["WMS_Version"] not in ("PrIME 2014", "PrIME 2022"):
            issues.append(("Sites", i, code, f"WMS_Version must be 'PrIME 2014' or 'PrIME 2022' (got '{row['WMS_Version']}')"))
        if not row["ReplicaServer"] or not row["ReplicaDatabase"]:
            issues.append(("Sites", i, code, "ReplicaServer and ReplicaDatabase are required"))
        if row["Hypercare_Start"] and len(row["Hypercare_Start"]) >= 10:
            row["Hypercare_Start"] = row["Hypercare_Start"][:10] + " 00:00:00"
        for c in ("UTC_Offset_h", "Shift1_Start", "Shift2_Start", "Shift3_Start", "Has_Production", "Is_Default"):
            n = _num(row[c])
            if isinstance(n, float):
                row[c] = str(int(n)) if n.is_integer() else f"{n:g}"
        if code in {s["SiteCode"] for s in sites}:
            issues.append(("Sites", i, code, "duplicate SiteCode"))
            continue
        sites.append(row)
    if len(sites) > max_sites():
        issues.append(("Sites", 0, "*", f"{len(sites)} sites - the report holds at most {max_sites()} (config/inputs_source.csv Max_Sites)"))
    if sites and sum(1 for s in sites if s["Is_Default"] == "1") != 1:
        issues.append(("Sites", 0, "*", "exactly one site must have Is_Default = 1"))
    codes = {s["SiteCode"] for s in sites}
    keys = {r["KPI_Key"]: r for r in csv.DictReader(open(CFG / "kpi_thresholds.csv", encoding="utf-8-sig")) if r["Site"] == "*"}
    for i, r in enumerate(_table_rows(wb, "AlertTargets"), start=2):
        site = str(r.get("Site") or "").strip()
        key = str(r.get("KPI_Key") or "").strip().upper()
        if not key:
            continue
        site = ALL_SITES if site.lower() in ("", "all sites", "*") else site.upper()
        bad = None
        if key not in keys:
            bad = f"unknown KPI_Key '{key}'"
        elif site != ALL_SITES and codes and site not in codes:
            bad = f"site '{site}' is not in the Sites tab"
        vals = {c: _num(r.get(c)) for c in ("Target", "Warning_At", "Critical_At")}
        if not bad and any(v == "BAD" for v in vals.values()):
            bad = "Target / Warning_At / Critical_At must be numbers"
        if not bad:
            d = keys[key]["Direction"]
            w, c = vals["Warning_At"], vals["Critical_At"]
            if w is not None and c is not None and ((d == "Higher" and w < c) or (d in ("Lower", "Band") and w > c)):
                bad = f"Warning_At {w:g} is beyond Critical_At {c:g} for a '{d}' KPI"
        if bad:
            issues.append(("Alert targets", i, f"{site}/{key}", bad))
            continue
        targets.append({"Site": site, "KPI_Key": key, **vals, "Changed_By": str(r.get("Changed_By") or ""), "Reason": str(r.get("Reason") or "")})
    return sites, targets, issues

