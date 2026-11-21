"""Tokenise the BD-only literals inside the original pbix M queries -> {TOKENS} resolved per site by fnSiteSql.

Every rule is literal-for-literal so the Binh Duong SQL renders back byte-identical (except the schema prefix
and the additional START_DT bound on TTAT / Shipped Pallet that keeps PrIME 2014 history scans bounded).
"""
import re

WMS_TABLES = ("dlytrn locmst sto_zone inventory_view invsum pckwrk_view prtftp_view prtftp_dtl prtmst prtdsc wkohdr "
              "wkodtl trlr trlract car_move stop shipment shipment_line ord ord_line adrmst dscmst").split()

LITERALS = [
    # (regex, replacement)  - applied in order, case-sensitive unless (?i)
    (r"\(\s*'10146'\s*,\s*'10112'\s*,\s*'10148'\s*,\s*'10086'\s*\)", "({ZONES_EXCL_PICK})"),
    (r"\(\s*'10148'\s*,\s*'10153'\s*,\s*'10040'\s*\)", "({ZONES_EXCL_BIN})"),
    (r"\(\s*'LTASTO_SM'\s*,\s*'LTASTO_FM'\s*,\s*'LTASTO_MM'\s*\)", "({OPR_LTA_STORE})"),
    (r"'F0%A'", "'{LOC_LEVEL_A}'"),
    (r"'LOAPW2F0'", "'{AREA_LEVEL_A_PICK}'"),
    (r"'HO%IN'", "'{LOC_HOFF_IN}'"),
    (r"'HO%OUT'", "'{LOC_HOFF_OUT}'"),
    (r"'PROB%'", "'{LOC_PROBLEM}'"),
    (r"'LT%'", "'{LOC_LTA}'"),
    (r"'8%'", "'{FG_PRTNUM_LIKE}'"),
    (r"'%VN07%'", "'%{WH_ID}%'"),
    (r"'VN07'", "'{WH_ID}'"),
    (r"'RDTS'", "'{AREA_RDTS}'"),
    (r"\s*=\s*'\{AREA_RDTS\}'", " LIKE '{AREA_RDTS}'"),          # AREA_RDTS is a LIKE pattern (sites with several RF areas, e.g. RDTS%)
    (r"'PL%'", "'{LOC_PROD_SUPPLY}'"),
    (r"'BD%'", "'{LOC_PROD_CHECKIN}'"),
    (r"'RTN%'", "'{LOC_RETURN}'"),
    (r"'TRL%'", "'{LOC_TRAILER}'"),
    (r"'RCST%'", "'{AREA_RCV_STAGE}'"),
    (r"'C\[0-9\]\[0-9\]\[0-9\]'", "'{LOC_DOOR_PATTERN}'"),
    (r"'ES-ES'", "'{PRTDSC_LOCALE}'"),
    (r"'US_ENGLISH'", "'{DSC_LOCALE}'"),
    (r"'\|VN07'", "'|{WH_ID}'"),
    (r"'BDD%'", "'{LOC_EOL}'"),
    (r"<>\s*'PLDN'", "<> '{LOC_EOL_EXACT}'"),
    (r"=\s*'PLDN'", "= '{LOC_EOL_EXACT}'"),
    (r"DATEADD\(\s*HOUR\s*,\s*7\s*,\s*GETUTCDATE\(\)\s*\)", "DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())"),
    (r"DATEADD\(DAY,\s*-30,", "DATEADD(DAY, -{WO_WINDOW_DAYS},"),
    (r"DATEADD\(DAY,\s*30,", "DATEADD(DAY, {WO_WINDOW_DAYS},"),
    (r"(?i)\b(?:binhduong_replica\.)?footprint_md\b(?!\})", "{T_FOOTPRINT}"),
    (r"'9772'", "'{SAP_Plant}'"),
    (r"'20260701'", "'{START_YYYYMMDD}'"),
    (r"'2026-07-2[26] 0[06]:00:00'", "'{START_DT}'"),
    (r"'7/26/2026 06:00:00 AM'", "'{START_DT}'"),
    (r"\b(lochgt|hgt)\s*(>|<=)\s*150\b", r"\1 \2 {TALL_HEIGHT_CM}"),
    (r"(?i)\bFROM\s+footprint_md\b", "FROM {T_FOOTPRINT}"),
    (r"(?i)\bdbo\.", "{S}."),
]

LTA_MAP = re.compile(r"SELECT \* FROM \(VALUES\s*\(.*?\)\s*\) AS m\(lta_source, prod_line, category\)", re.S)
BARE = re.compile(r"(?i)(\b(?:FROM|JOIN)\s+|,\s*(?:\r?\n)?\s*)(" + "|".join(WMS_TABLES) + r")\b(?![._(])")

# bounded history scans (TTAT had none; Shipped Pallet filtered only after the CTE) - safe for PrIME 2014 sites
EXTRA = {
    # idle Level A = only the usable storage locations the Level A denominator counts (Location Utilisation: useflg = 1, stoflg = 1,
    # maxqvl > 0). Xiqing: 808 of 911 A0%A locations are CP1 pick faces with stoflg = 0 -> 261 idle of 103 locations = 253% (18-Nov).
    "Pallet in Level A not active shipment": [
        ("AND i.comqty < i.untqty\n", "AND i.comqty < i.untqty\n          AND EXISTS (SELECT 1 FROM {S}.locmst AS l WHERE l.wh_id = i.wh_id "
                                     "AND l.stoloc = i.stoloc AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0)\n"),
    ],
    # put-away of produced pallets RDT -> Level A / other storage: the source counted only oprcod LTASTO_* and work orders 'LIKE 00%'
    # (BD-specific; BD has put away with UTR / FL_XFR since go-live). The wkohdr join already restricts to work-order pallets.
    "Pallet From LTA To Level A": [
        ("AND a.oprcod IN ({OPR_LTA_STORE})", "AND a.to_arecod NOT LIKE '{AREA_RDTS}'"),
        ("AND b.frstol LIKE '00%'", "AND b.trndte <= a.trndte"),
    ],
    "TTAT": [
        ("WHERE t.TRLR_COD LIKE 'RCV%'\n", "WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= '{START_DT}'\n"),
        ("WHERE (\n", "WHERE t.TRNDTE >= '{START_DT}' AND (\n"),
        ("WHERE d.lodnum IS NOT NULL\n", "WHERE d.lodnum IS NOT NULL AND d.trndte >= '{START_DT}'\n"),
        # inbound truck key + receipt link per site (BD: TRKNUM on every trailer action; Minhang: truck per trailer via rcvtrk)
        ("FROM {S}.TRLRACT t\n    LEFT JOIN {S}.DLYTRN d ON t.TRKNUM = d.FRSTOL", "FROM {TTAT_IN_SRC} t\n    LEFT JOIN {S}.DLYTRN d ON {TTAT_IN_RCPT_COND}"),
        ("FROM {S}.TRLRACT t\n    JOIN {S}.dlytrn d ON t.TRKNUM = d.FRSTOL", "FROM {TTAT_IN_SRC} t\n    JOIN {S}.dlytrn d ON {TTAT_IN_RCPT_COND}"),
        # one row per TRAILER: the trailer number / carrier move / route can change during the visit (BD yard placeholder
        # 'SDC_02' at check-in -> container 'CTCU 2020003SD5' at close) and grouping by them split the trailer in two rows that
        # both failed the HAVING (99 BD outbound trailers since 1-Oct were dropped)
        ("        t.TRLR_NUM      AS [Trailer Number],", "        MAX(t.TRLR_NUM) AS [Trailer Number],"),
        ("        t.TRKNUM        AS [Truck Number],", "        MAX(t.TRKNUM)   AS [Truck Number],"),
        ("        t.CAR_MOVE_ID   AS [Load],", "        MAX(t.CAR_MOVE_ID) AS [Load],"),
        ("        adrmst.ctry_name AS [Route To],", "        MAX(adrmst.ctry_name) AS [Route To],"),
        ("WHEN t.TRLR_COD LIKE 'STO' THEN 'Fast Lanes'", "WHEN MAX(t.TRLR_COD) LIKE 'STO' THEN 'Fast Lanes'"),
        ("    GROUP BY t.TRLR_ID, t.TRLR_NUM, t.TRKNUM\n", "    GROUP BY t.TRLR_ID\n"),
        ("    GROUP BY t.TRLR_ID, t.TRLR_NUM, t.CAR_MOVE_ID, t.TRLR_COD, adrmst.ctry_name\n", "    GROUP BY t.TRLR_ID\n"),
        # the trailer (not the truck number - absent on ~40-70 % of BD / Xiqing inbound trailers) is the unit; receipts are linked
        # through rcvtrk in TTAT_IN_SRC / TTAT_IN_RCPT_COND (config/engine_profiles.csv)
        ("      AND t.TRKNUM IS NOT NULL\n", ""),
    ],
    "Shipped Pallet": [
        ("FROM {S}.dlytrn\n    WHERE (", "FROM {S}.dlytrn\n    WHERE TRNDTE >= DATEADD(DAY, -1, '{START_DT}') AND ((") ,
        ("TO_ARECOD LIKE '{AREA_RCV_STAGE}')\n),", "TO_ARECOD LIKE '{AREA_RCV_STAGE}'))\n),"),
    ],
    "Pallets Location": [
        ("lm.arecod, lm.{ZONE_COL},", "lm.arecod, lm.{ZONE_COL} AS sto_zone_id,"),
        ("LEFT JOIN {S}.loc_typ lt ON lt.loc_typ_id=lm.loc_typ_id AND lt.wh_id='{WH_ID}'", "{LOC_TYP_JOIN}"),
        ("lt.prod_flg=1 OR lt.prd_stgflg=1", "{LT_LINE_COND}"),
        ("lt.rcv_stgflg=1", "{LT_RCV_COND}"),
        ("lt.shp_dck_flg=1 OR lt.stgflg=1", "{LT_SHIP_COND}"),
        # FIFO override dates > 1 year ahead are keying errors (BD had year 6026); aging only from dates already passed
        ("MIN(iv.fifdte) AS fifo_dte", "MIN(CASE WHEN iv.fifdte < DATEADD(YEAR, 1, GETDATE()) THEN iv.fifdte END) AS fifo_dte"),
        ("COALESCE(p.received_dte,p.fifo_dte), DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))",
         "COALESCE(CASE WHEN p.received_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.received_dte END, "
         "CASE WHEN p.fifo_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.fifo_dte END), DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))"),
    ],
    # free spots = capacity - (current + pending); a location committed beyond its capacity has 0 free spots, not -1
    "Level A Available Pallet Spot": [
        ("(l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)))",
         "(CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END)"),
    ],
    # the source read every work order ever planned (Jakarta 2018, Xiqing 2022-2027) -> same +-WO_WINDOW_DAYS window as RPM Breakdown
    "Planned Pallet PO": [
        ("ORDER BY w.sch_begdte;", "AND w.sch_enddte >= DATEADD(DAY, -{WO_WINDOW_DAYS}, DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))\n"
                                   "          AND w.sch_begdte <  DATEADD(DAY, {WO_WINDOW_DAYS}, DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))\n"
                                   "        ORDER BY w.sch_begdte;"),
    ],
    "Pallets Movement": [
        ("WHERE d.wh_id  = '{WH_ID}'", "WHERE d.wh_id  = '{WH_ID}' AND d.trndte >= DATEADD(DAY, -{MOVEMENT_DAYS}, GETDATE())"),
        ("-- AND d.lodnum = '00300097720035846752'", "-- AND d.lodnum = '<LPN to trace>'"),
        # zone = int sto_zone_id on PrIME 2022 but text arecod on PrIME 2014 -> always text (model column is string)
        ("lf.{ZONE_COL}                 AS from_zone", "CAST(lf.{ZONE_COL} AS NVARCHAR(20)) AS from_zone"),
        ("lt.{ZONE_COL}                 AS to_zone", "CAST(lt.{ZONE_COL} AS NVARCHAR(20)) AS to_zone"),
    ],
    # performance: the original final join ran 208 s on BD (nested loops over the CTEs); a hash-join hint runs it in ~4 s
    "Planned PO RPM Breakdown": [
        ("LEFT JOIN fg f   ON f.prtnum=o.fg_gcas\n", "LEFT JOIN fg f   ON f.prtnum=o.fg_gcas\nOPTION (HASH JOIN)\n"),
    ],
    # performance: 116k rows since go-live (52 s) -> only the last DETAIL_DAYS days of work-line activity
    "WorkLine Activities": [
        ("WHERE d.trndte >= @StartDate", "WHERE d.trndte >= CASE WHEN @StartDate > DATEADD(DAY, -{DETAIL_DAYS}, GETDATE()) THEN @StartDate "
                                         "ELSE DATEADD(DAY, -{DETAIL_DAYS}, GETDATE()) END"),
    ],
}

# shift-day anchor hour hard-coded as 6 in the BD M code -> ShiftStartH (= Cfg_Site.Shift1_Start)
SHIFT_M = [
    (r"Number\.From\(\[ReportHour\]\)\s*<\s*6\b", "Number.From([ReportHour]) < ShiftStartH"),
    (r"if h >= 6 then h - 6 else h \+ 18", "Number.Mod(h - ShiftStartH + 24, 24)"),
    (r"-\s*6\s*\+\s*24,\s*24\)", "- ShiftStartH + 24, 24)"),
    (r"\b(startH_raw|endH_raw)(\s*)=\s*6\s*\+", r"\1\2= ShiftStartH +"),
    (r"\[Hour\]\s*<\s*6\b", "[Hour] < ShiftStartH"),
    (r"#time\(6,\s*0,\s*0\)", "#time(ShiftStartH, 0, 0)"),
    (r"(Date\.Day\(\[shift_date\]\)),\s*6,\s*0,\s*0\)", r"\1, ShiftStartH, 0, 0)"),
]


def shift_m(m):
    n = 0
    for rx, rep in SHIFT_M:
        m, k = re.subn(rx, rep, m)
        n += k
    return m, n


def tokenize_sql_text(t, table=None):
    t = LTA_MAP.sub("SELECT * FROM (VALUES {LTA_MAP_VALUES}) AS m(lta_source, prod_line, category)", t)
    for rx, rep in LITERALS:
        t = re.sub(rx, rep, t)
    t = BARE.sub(lambda m: m.group(1) + "{S}." + m.group(2), t)
    # engine-specific constructs (Cfg_Engine): 2022 sto_zone vs 2014 area zoning; production txn filter per site
    t = re.sub(r"INNER JOIN \{S\}\.sto_zone AS k\s+ON k\.sto_zone_id = l\.sto_zone_id", "{STO_ZONE_JOIN}", t)
    t = re.sub(r"(?<!\")\bsto_zone_id\b(?!\")", "{ZONE_COL}", t)
    # zone exclusions compare as text: 2022 zones are int, 2014 zones varchar, and '~NA~' (no exclusion) must not break an int compare
    t = re.sub(r"(\b\w+\.)?\{ZONE_COL\}(\s+(?:NOT\s+)?IN\s*\(\{ZONES_EXCL_)", lambda m: f"CAST({m.group(1) or ''}{{ZONE_COL}} AS NVARCHAR(40)){m.group(2)}", t, flags=re.I)
    t = re.sub(r"\(d\.OPRCOD LIKE 'UTR' OR d\.OPRCOD LIKE 'RPMSTO' OR d\.OPRCOD LIKE 'LTA%'\)", "({PROD_TXN_FILTER})", t)
    # production model per site (Cfg_Site): LTA take-away sites (BD) vs work-order receipt sites (Minhang)
    for rx, rep in PROD_MODEL:
        t = re.sub(rx, rep, t)
    return t


PROD_MODEL = [
    (r"CASE\s+WHEN d\.FRSTOL LIKE '\{LOC_LTA\}' THEN LEFT\(d\.FRSTOL, 5\)\s+WHEN d\.TOSTOL LIKE '\{LOC_LTA\}' THEN LEFT\(d\.TOSTOL, 5\)\s+END",
     "{PROD_SRC_EXPR}"),
    (r"\(d\.FRSTOL LIKE '\{LOC_LTA\}' OR d\.TOSTOL LIKE '\{LOC_LTA\}'\)", "({PROD_SCOPE})"),
    (r"WHEN c\.TOSTOL LIKE '\{LOC_LTA\}' THEN c\.LODNUM", "WHEN {PROD_ARRIVED_COND} THEN c.LODNUM"),
    (r"WHEN c\.FRSTOL LIKE '\{LOC_LTA\}' THEN c\.LODNUM", "WHEN {PROD_LEFT_COND} THEN c.LODNUM"),
]


def tokenize_m(table, m):
    """Return (new_m, notes). Server/db -> parameters, SQL literals -> tokens, query text wrapped in fnSiteSql()."""
    notes = []
    m2 = re.sub(r'Sql\.Database\(\s*"<replica-server>"]*"\s*,\s*"(?i:binhduong_replica)"\s*,',
                "Sql.Database(ReplicaServer, ReplicaDatabase,", m)
    if m2 != m:
        notes.append("server/db -> ReplicaServer/ReplicaDatabase")
    m2 = re.sub(r'Databricks\.Catalogs\(\s*"adb-[^"]+"\s*,\s*"/sql/[^"]+"\s*,', "Databricks.Catalogs(DatabricksHost, DatabricksHttpPath,", m2)
    m2 = re.sub(r"\[Query\s*=\s*(SqlQuery|SQL)\s*([,\]])", r"[Query = fnSiteSql(\1)\2", m2)
    if '[Query="' in m2:
        i = m2.index('[Query="') + len("[Query=")
        j = m2.index('"]', i)
        m2 = m2[:i] + "fnSiteSql(" + m2[i:j + 1] + ")" + m2[j + 1:]
    m2 = re.sub(r"(\[Data\],\s*)SQL,", r"\1fnSiteSql(SQL),", m2)
    if re.search(r"\[Data\],\s*\"", m2):
        i = re.search(r"\[Data\],\s*\"", m2).end() - 1
        j = re.search(r'",\s*null,', m2[i + 1:]).start() + i + 1
        m2 = m2[:i] + "fnSiteSql(" + m2[i:j + 1] + ")" + m2[j + 1:]
    m2 = tokenize_sql_text(m2, table)
    for a, b in EXTRA.get(table, []):
        if a in m2:
            m2 = m2.replace(a, b)
            notes.append(f"bounded scan: {a.strip()[:40]}")
        else:
            notes.append(f"WARN extra rule not applied: {a.strip()[:40]}")
    m2 = m2.replace("DateTimeZone.SwitchZone(DateTimeZone.UtcNow(), 7)",
                    "DateTimeZone.SwitchZone(DateTimeZone.UtcNow(), Number.From(SiteTokens[UTC_Offset_h]))")
    m2, k = shift_m(m2)
    if k:
        notes.append(f"{k} shift-hour literal(s) -> ShiftStartH")
    if table == "RPM Masterdata":
        for var, tok in (("FolderPath", "RPM_Folder"), ("MasterFile", "RPM_Master_File"), ("MapFile", "RPM_Map_File"),
                         ("VendorListFile", "RPM_VendorList_File"), ("VendorListSheet", "RPM_VendorList_Sheet")):
            m2, k = re.subn(rf'(\b{var}\s*=\s*)"[^"]*"', rf'\1Text.From(Record.FieldOrDefault(SiteTokens, "{tok}", ""))', m2, count=1)
            notes.append(f"{var} -> Cfg_Site.{tok}" if k else f"WARN {var} not found")
    m2, k = scope_warehouse(m2)
    if k:
        notes.append(f"{k} WMS table read(s) scoped to WH_ID")
    m2, k = apply_incremental(table, m2)
    if k:
        notes.append(f"incremental range filter on {k} anchor(s)")
    elif k == 0:
        notes.append("WARN extra rule not applied: incremental anchor (config/incremental_policy.csv) not found")
    return m2, notes


# ------------------------------------------------------------------ incremental refresh (config/incremental_policy.csv)
# {INC_FROM} / {INC_TO} are SQL literals; the defaults leave the query unchanged in meaning. A partition narrows them:
# Desktop  '<T> - <SITE>' = history (< boundary), '<T> - <SITE> - recent' = boundary onwards (fnIncBoundary)
# Service  RangeStart / RangeEnd of the refresh policy
INC_DEFAULTS = {"INC_FROM": "'1900-01-01'", "INC_TO": "'9999-12-31'"}
_INC_POLICY = None


def incremental_policy():
    global _INC_POLICY
    if _INC_POLICY is None:
        import csv
        from pathlib import Path
        f = Path(__file__).resolve().parent.parent / "config" / "incremental_policy.csv"
        _INC_POLICY = {r["Table"]: r for r in csv.DictReader(open(f, encoding="utf-8-sig"))} if f.exists() else {}
    return _INC_POLICY


def apply_incremental(table, sql):
    """Add 'AND <col> >= {INC_FROM} AND <col> < {INC_TO}' after every occurrence of the table's anchor.
    Returns (sql, n): n = None when the table has no policy, 0 when the anchor is missing (build fails)."""
    p = incremental_policy().get(table)
    if not p:
        return sql, None
    n = sql.count(p["Anchor"])
    col = p["Date_Column"]
    return sql.replace(p["Anchor"], f"{p['Anchor']} AND {col} >= {{INC_FROM}} AND {col} < {{INC_TO}}"), n


# WMS tables that carry wh_id on PrIME 2014 (prodwms) AND 2022 (dbo) - verified on BD / Akashi / Jakarta / Xiqing replicas
WH_TABLES = ("dlytrn", "inventory_view", "invlod", "invsum", "locmst", "ord", "ord_line", "pckwrk_view", "prtftp", "prtftp_dtl",
             "prtftp_view", "prtmst_view", "rplwrk", "shipment", "shipment_line", "trlract", "wkodtl", "wkohdr")
_SQL_WORDS = {"where", "join", "inner", "left", "right", "full", "cross", "outer", "on", "group", "order", "union", "having",
              "with", "select", "from", "and", "or", "pivot", "unpivot", "option", "for", "into", "as"}
_WH_RX = re.compile(r"\{S\}\.(" + "|".join(WH_TABLES) + r")\b(\s+(?:AS\s+)?([A-Za-z_]\w*))?", re.I)


def _cfg_rows(name):
    import csv
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "config" / name
    return list(csv.DictReader(open(f, encoding="utf-8-sig")))


def _sql_in(col, items):
    vals = [v.strip() for v in (items or "").split(";") if v.strip()]
    return f"{col} IN ({', '.join(chr(39) + v + chr(39) for v in vals)})" if vals else ""


def config_blocks():
    """{{BLOCK}} -> SQL generated from config/*.csv (process model). Same text for every site; the {TOKENS} inside stay per site."""
    st = sorted((r for r in _cfg_rows("process_stages.csv") if r["Site"] == "*" and r["Object"] == "Pallet" and r["Rule"].strip()),
                key=lambda r: int(r["Rule_Priority"]))
    pallet = "CASE\n" + "".join(f"            WHEN {r['Rule'].strip()} THEN '{r['Stage_Key']}'\n" for r in st) + "        END"
    ts = _cfg_rows("trailer_status.csv")

    def tcase(direction):
        return "CASE r.TRLR_STAT " + " ".join(f"WHEN '{x['Status_Code']}' THEN '{x['Stage_Key']}'" for x in ts if x["Direction"] == direction) + " END"
    trailer = f"CASE WHEN r.TRLR_COD LIKE 'RCV%' THEN {tcase('Inbound')}\n             ELSE {tcase('Outbound')} END"
    ss = _cfg_rows("shipment_status.csv")
    age = {"Created": "s.adddte", "Allocated": "COALESCE(s.alcdte, s.adddte)", "Staged": "COALESCE(s.stgdte, s.alcdte, s.adddte)",
           "Loaded": "COALESCE(s.loddte, s.stgdte, s.alcdte, s.adddte)"}
    ship_stage = "CASE s.shpsts " + " ".join(f"WHEN '{x['Status_Code']}' THEN '{x['Stage_Key']}'" for x in ss) + " ELSE 'O_OTHER' END"
    ship_open = "CASE s.shpsts " + " ".join(f"WHEN '{x['Status_Code']}' THEN {int(x['Is_Open'])}" for x in ss) + " ELSE 1 END"
    ship_since = "CASE s.shpsts " + " ".join(f"WHEN '{x['Status_Code']}' THEN {age[x['Age_From']]}" for x in ss) + " ELSE s.adddte END"
    mc = sorted(_cfg_rows("movement_classes.csv"), key=lambda r: int(r["Priority"]))
    whens, other = [], None
    for r in mc:
        if r["Counts_As_Move"] != "1":
            continue
        conds = [c for c in (_sql_in("d.actcod", r["Actcod_List"]), _sql_in("d.oprcod", r["Oprcod_List"]),
                             f"({r['Location_Rule'].strip()})" if r["Location_Rule"].strip() else "") if c]
        if conds:
            whens.append(f"WHEN {' OR '.join(conds)} THEN '{r['Move_Class']}'")
        else:
            other = r["Move_Class"]
    move = "CASE " + "\n             ".join(whens) + f"\n             ELSE '{other or 'Other'}' END"
    excl = ", ".join(f"'{v.strip()}'" for r in mc if r["Counts_As_Move"] != "1" for v in r["Actcod_List"].split(";") if v.strip())
    # process mining roles (config/movement_classes.csv Flow_Role): IN = the pallet arrives (receipt / production take-away),
    # PUTAWAY = into storage (time to the next step = storage dwell), STEP = main sequence, SIDE = extra handling (transfer / other move).
    # A SIDE move directly after an IN step is the put-away (the first move after arrival, whatever code the site books it with)
    def _roles(*names):
        return [r for r in mc if (r.get("Flow_Role") or "STEP").strip().upper() in names]
    side = ", ".join(f"'{r['Move_Class']}'" for r in _roles("SIDE"))
    inl = ", ".join(f"'{r['Move_Class']}'" for r in _roles("IN"))
    puts = _roles("PUTAWAY")
    if len(puts) > 1:
        raise SystemExit("config/movement_classes.csv: at most one Flow_Role PUTAWAY class")
    putaway = puts[0]["Move_Class"] if puts else ""
    # stock age bands (Inventory): days since FIFO / receipt -> band of config/stock_age_bands.csv; the band without limits = no date
    ab = sorted(_cfg_rows("stock_age_bands.csv"), key=lambda r: int(r["Sort"]))
    unknown = next((r["Band"] for r in ab if not r["To_Days"].strip()), "Unknown")
    age_band = ("CASE WHEN q.age_days IS NULL THEN '" + unknown + "' "
                + " ".join(f"WHEN q.age_days < {int(r['To_Days'])} THEN '{r['Band']}'" for r in ab if r["To_Days"].strip())
                + f" ELSE '{[r for r in ab if r['To_Days'].strip()][-1]['Band']}' END")
    return {"PALLET_STAGE_CASE": pallet, "TRAILER_STAGE_CASE": trailer, "SHIPMENT_STAGE_CASE": ship_stage,
            "SHIPMENT_OPEN_CASE": ship_open, "SHIPMENT_SINCE_CASE": ship_since, "MOVE_CLASS_CASE": move,
            "MOVE_EXCLUDE_LIST": excl or "'~NA~'", "MOVE_SIDE_LIST": side or "'~NA~'", "MOVE_IN_LIST": inl or "'~NA~'",
            "MOVE_PUTAWAY_STEP": f"'{putaway or '~NA~'}'", "STOCK_AGE_CASE": age_band}


def expand_config_blocks(sql):
    if "{{" not in sql:
        return sql
    blocks = config_blocks()
    out = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: blocks[m.group(1)], sql)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        raise SystemExit(f"unknown config block(s) {left}")
    return out


def scope_warehouse(sql):
    """Every read of a WMS table is limited to the site's warehouse: {S}.dlytrn d -> (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') d.
    A replica can hold several warehouses (Jakarta ID01/ID12, Xiqing CN74/CN66/CN88); the source BD queries assumed one.
    {{BLOCKS}} generated from config/*.csv (process stages, statuses, movement classes) are expanded first."""
    sql = expand_config_blocks(sql)
    n = 0

    def rep(m):
        nonlocal n
        if "(SELECT * FROM {S}." + m.group(1) in sql[max(0, m.start() - 15):m.start()]:
            return m.group(0)
        tbl, alias = m.group(1), m.group(3)
        n += 1
        if alias and alias.lower() not in _SQL_WORDS:
            return f"(SELECT * FROM {{S}}.{tbl} WHERE wh_id = '{{WH_ID}}'){m.group(2)}"
        return f"(SELECT * FROM {{S}}.{tbl} WHERE wh_id = '{{WH_ID}}') AS {tbl}" + (m.group(2) or "")
    out = _WH_RX.sub(rep, sql)
    return out, n


BD_LEFTOVERS = re.compile(r"(?i)VN07|F0%A|9772|binhduong|adb-7620|2026-07|LOAPW2F0|'10146'|footprint_md(?!\})|\bsto_zone\b|(?<!AS )(?<!\")\bsto_zone_id\b|"
                          r"<bd-author>|P9772|'BDD%'|'PLDN'|HOUR\s*,\s*7\b|\bloc_typ\b")
