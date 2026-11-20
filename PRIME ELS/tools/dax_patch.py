"""Replace the BD-only constants inside the ORIGINAL DAX (measures, calculated tables, calculated columns) with Cfg_* lookups.

Every rule must hit (assert) - if the source pbix changes, the build fails loudly instead of silently leaving a BD value.
"""
import re

# shared calendar tables (DimDate / DimBucket / DimHour ...) are built once for all sites -> Cfg_Site row with Is_Default = 1
ACT = "FILTER(Cfg_Site, Cfg_Site[Is_Default] = 1)"


def cfg(col, default):
    # single-site file without an Is_Default row: its own (only) site
    return f"COALESCE(MAXX({ACT}, Cfg_Site[{col}]), IF(COUNTROWS(Cfg_Site) = 1, MAXX(Cfg_Site, Cfg_Site[{col}])), {default})"


def row_cfg(table, col, default):
    """Calculated column of a site table: value of the row's own site."""
    return f"COALESCE(LOOKUPVALUE(Cfg_Site[{col}], Cfg_Site[SiteCode], {table}[SiteCode]), {default})"


S1 = cfg("Shift1_Start", 0)
OB_S1 = row_cfg("'Outbound Pallet from Inv'", "Shift1_Start", 0)
SDS_MIN = cfg("ShiftDay_Start_Min", 0)

MARKET_COLOR = "\n\t\t\t[Market Color]\n"
MARKET_FLAG = ("\n\t\t\tVAR MarketNb  = [Market Count]\n\t\t\tVAR TheMarket = SELECTEDVALUE ( 'Shipping Market'[MarketCode] )\n"
               "\t\t\tRETURN\n\t\t\t    SWITCH (\n\t\t\t        TRUE (),\n\t\t\t        MarketNb = 0, BLANK (),\n\t\t\t        MarketNb > 1, \"❓\",\n"
               "\t\t\t        ISBLANK ( LOOKUPVALUE ( Cfg_Market[Color], Cfg_Market[Market], TheMarket ) ), \"🚨\",\n\t\t\t        BLANK ()\n\t\t\t    )\n")


def _measure_body(name):
    return re.compile(r"(\tmeasure '" + re.escape(name) + r"' =)(.*?)(?=\n\t\t(?:formatString|lineageTag|displayFolder))", re.S)


RULES = {
    "_DaxMeasure.tmdl": [
        (r"IF\(Ratio > 1\.5, BLANK\(\), Ratio\)", "IF(Ratio > [Cfg Sync Cap], BLANK(), Ratio)", 2),
        (r"DIVIDE\(\[Daily_Produced Pallets\],4\)", "DIVIDE([Daily_Produced Pallets],[Cfg Bucket Hours])", 1),
        (r"DIVIDE\(\[Daily_Shipped Pallets\],4\)", "DIVIDE([Daily_Shipped Pallets],[Cfg Bucket Hours])", 1),
        (r"'Produced Pallet'\[PRODUCT_LINE\]\s*<>\s*\"BDCACTM1\"", "'Produced Pallet'[Is CTMZ] = \"Non-CTMZ\"", None),
        (r"'Produced Pallet'\[PRODUCT_LINE\]\s*=\s*\"BDCACTM1\"", "'Produced Pallet'[Is CTMZ] = \"CTMZ\"", None),
        (r"FORMAT\(UTCNOW\(\) \+ TIME\(7, 0, 0\), \"dd-MM-yy HH:mm:ss\", \"vi-VN\"\)",
         "FORMAT(UTCNOW() + [Site UTC Offset h] / 24, \"dd-MM-yy HH:mm:ss\")", 1),
        (_measure_body("Predicted_Market Color"), lambda m: m.group(1) + MARKET_COLOR, 1),
        (_measure_body("Market Flag"), lambda m: m.group(1) + MARKET_FLAG, 1),
        # running balance produced vs shipped: a bucket with production but no shipment (or the reverse) is a real change of the
        # balance - the source blanked it, so sites that never ship (Minhang) showed an empty chart and BD lost those buckets
        (_measure_body("Daily_Δ Ship-Prod"),
         lambda m: m.group(1) + "\n\t\t\tVAR s = [Daily_Shipped Pallets]\n\t\t\tVAR p = [Daily_Produced Pallets]\n"
                                "\t\t\tRETURN IF(COALESCE(s, 0) = 0 && COALESCE(p, 0) = 0, BLANK(), COALESCE(s, 0) - COALESCE(p, 0))\n", 1),
        # no single date / bucket in context (total rows) -> blank instead of "Cannot convert '' to Number"
        (r"RETURN VALUE\(FORMAT\(d, \"YYYYMMDD\"\) & FORMAT\(b, \"0\"\)\)",
         "RETURN IF(ISBLANK(d) || ISBLANK(b), BLANK(), VALUE(FORMAT(d, \"YYYYMMDD\") & FORMAT(b, \"0\")))", 1),
    ],
    "Produced Pallet.tmdl": [
        (r"'Produced Pallet'\[PRODUCT_LINE\] = \"BDCACTM1\"", f"'Produced Pallet'[PRODUCT_LINE] = {row_cfg(chr(39) + 'Produced Pallet' + chr(39), 'CTMZ_LINE', chr(34) * 2)}", 1),
    ],
    "Planned Pallet PO.tmdl": [
        (r"VAR TheGCAS = 'Planned Pallet PO'\[FG GCAS\]", "VAR TheGCAS = 'Planned Pallet PO'[FG GCAS]\n\t\t\t\tVAR TheSite = 'Planned Pallet PO'[SiteCode]", 1),
        (r"'Shipping Market'\[FG GCAS\] = TheGCAS", "'Shipping Market'[FG GCAS] = TheGCAS,\n\t\t\t\t        'Shipping Market'[SiteCode] = TheSite", 1),
    ],
    "SAP Plan PO.tmdl": [
        (r"VAR TheGCAS = 'SAP Plan PO'\[FG GCAS\]", "VAR TheGCAS = 'SAP Plan PO'[FG GCAS]\n\t\t\t\tVAR TheSite = 'SAP Plan PO'[SiteCode]", 1),
        (r"'Shipping Market'\[FG GCAS\] = TheGCAS", "'Shipping Market'[FG GCAS] = TheGCAS,\n\t\t\t\t        'Shipping Market'[SiteCode] = TheSite", 1),
        (r'TIMEVALUE\("06:00"\)', row_cfg("'SAP Plan PO'", "Shift1_Start", 0) + " / 24", 1),
    ],
    "Planned PO RPM Breakdown.tmdl": [
        (r"'RPM Masterdata'\[Material No\.\] = _gcas", "'RPM Masterdata'[Material No.] = _gcas && 'RPM Masterdata'[SiteCode] = 'Planned PO RPM Breakdown'[SiteCode]", 1),
    ],
    "DimDate.tmdl": [
        (r"VAR StartDate = DATE\(2026, 7, 25\)",
         f"VAR StartDate = INT(COALESCE(MINX(Cfg_Site, DATEVALUE(LEFT(Cfg_Site[Hypercare_Start], 10))), TODAY() - 90)) - 7\n\t\t\t\tVAR SDS = {SDS_MIN} / 1440", 1),
        (r"VAR EndDate\s*=\s*DATE\(2027, 7, 30\)", "VAR EndDate   = TODAY() + " + cfg("CAL_FUTURE_DAYS", 2), 1),
        (r"TIME\(6, 30, 0\)", "SDS", 2),
        (r"\" 06:30 → \"", "\" \" & FORMAT(SDS, \"hh:nn\") & \" → \"", 1),
        (r"\"MMM D\"\) & \" 06:30\"", "\"MMM D\") & \" \" & FORMAT(SDS, \"hh:nn\")", 1),
        (r"\" \(06:30–06:30\)\"", "\" (\" & FORMAT(SDS, \"hh:nn\") & \"–\" & FORMAT(SDS, \"hh:nn\") & \")\"", 1),
    ],
    "DimBucket.tmdl": [
        (re.compile(r"DATATABLE\(\s*\"Bucket\".*?\n[\t ]*\)\n", re.S),
         "VAR S = " + SDS_MIN + "\n\t\t\t\tRETURN\n\t\t\t\tSELECTCOLUMNS(\n\t\t\t\t    GENERATESERIES(1, 6, 1),\n"
         "\t\t\t\t    \"Bucket\", \"B\" & [Value],\n"
         "\t\t\t\t    \"Time Range\", FORMAT(MOD(INT(S / 60) + ([Value] - 1) * 4, 24), \"00\") & \"-\" & FORMAT(MOD(INT(S / 60) + [Value] * 4, 24), \"00\"),\n"
         "\t\t\t\t    \"Parent Shift\", \"Shift \" & ROUNDUP([Value] / 2, 0),\n\t\t\t\t    \"Sort Order\", [Value],\n"
         "\t\t\t\t    \"Start Min\", S + ([Value] - 1) * 240,\n\t\t\t\t    \"End Min\", S + [Value] * 240\n\t\t\t\t)\n", 1),
    ],
    "DimDateBucket.tmdl": [
        (r"VAR BucketEndHour = 6 \+ 'DimDateBucket'\[Sort Order\] \* 4", f"VAR BucketEndHour = {S1} + 'DimDateBucket'[Sort Order] * 4", 1),
    ],
    "DimShiftDate.tmdl": [
        (r"VAR StartDate = DATE\(2026, 7, 1\)", "VAR StartDate = MIN(DimDate[Date])", 1),
        (r"VAR EndDate\s*=\s*DATE\(2026, 9, 30\)", "VAR EndDate   = MAX(DimDate[Date])", 1),
        (re.compile(r"VAR Shifts =\s*DATATABLE\(.*?\n[\t ]*\)\n", re.S),
         "VAR s1 = " + S1 + "\n\t\t\t\tVAR s2 = " + cfg("Shift2_Start", "s1 + 8") + "\n\t\t\t\tVAR s3 = " + cfg("Shift3_Start", "s1 + 16") + "\n"
         "\t\t\t\tVAR Shifts =\n\t\t\t\t    UNION(\n"
         "\t\t\t\t        ROW(\"Shift Number\", 1, \"Shift Name\", \"Shift 1\", \"Shift Start\", FORMAT(s1, \"00\") & \":00\", \"Shift End\", FORMAT(s2, \"00\") & \":00\"),\n"
         "\t\t\t\t        ROW(\"Shift Number\", 2, \"Shift Name\", \"Shift 2\", \"Shift Start\", FORMAT(s2, \"00\") & \":00\", \"Shift End\", FORMAT(s3, \"00\") & \":00\"),\n"
         "\t\t\t\t        ROW(\"Shift Number\", 3, \"Shift Name\", \"Shift 3\", \"Shift Start\", FORMAT(s3, \"00\") & \":00\", \"Shift End\", FORMAT(s1, \"00\") & \":00\")\n"
         "\t\t\t\t    )\n", 1),
    ],
    "DimHour.tmdl": [
        (r"IF\(\[Value\] >= 6, \[Value\] - 6, \[Value\] \+ 18\)", f"MOD([Value] - {S1} + 24, 24)", 1),
    ],
    "Outbound Pallet from Inv.tmdl": [
        (r"'Outbound Pallet from Inv'\[Hour_Of_Day\] >= 6,\s*\n(\s*)'Outbound Pallet from Inv'\[Day\],",
         lambda m: f"'Outbound Pallet from Inv'[Hour_Of_Day] >= {OB_S1},\n{m.group(1)}'Outbound Pallet from Inv'[Day],", 1),
        (re.compile(r"IF \(\s*'Outbound Pallet from Inv'\[Hour_Of_Day\] >= 6,\s*'Outbound Pallet from Inv'\[Hour_Of_Day\] - 6,\s*"
                    r"'Outbound Pallet from Inv'\[Hour_Of_Day\] \+ 18\s*\)", re.S),
         f"MOD('Outbound Pallet from Inv'[Hour_Of_Day] - {OB_S1} + 24, 24)", 1),
    ],
}


def patch_dax(tables_dir):
    log = []
    for fname, rules in RULES.items():
        p = tables_dir / fname
        if not p.exists():      # table left out of this build (e.g. SAP tables with Include_SAP_CDL = 0)
            continue
        t = p.read_text(encoding="utf-8")
        for rx, rep, expect in rules:
            t, n = re.subn(rx, rep, t)
            if n == 0 or (expect is not None and n != expect):
                raise SystemExit(f"DAX patch failed: {fname} rule {getattr(rx, 'pattern', rx)[:70]!r} matched {n}, expected {expect}")
            log.append(f"{fname}: {n}x {getattr(rx, 'pattern', rx)[:50]}")
        p.write_text(t, encoding="utf-8")
    return log
