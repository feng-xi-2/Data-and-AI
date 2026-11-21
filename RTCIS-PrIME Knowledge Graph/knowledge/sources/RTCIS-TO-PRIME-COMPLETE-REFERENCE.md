# RTCIS → PrIME 2022 SQL Translation — Complete Reference
# ═══════════════════════════════════════════════════════════════════
# Last updated: 2026-07-06
# Status: 34/34 Pomezia PASS + 3 vendor queries PASS + ORDNUM validated
# Latest outputs: pomezia_20260330_184323.html (34 queries), vendor_queries_validated_20260408.html (vendor) — both archived 2026-06-26 (see advisory)
# Pipeline: Single-auth retry architecture (1 login prompt per run)
# ══════════════════════════════════════════════════════════════════

---

> **⚠️ Reorg advisory (2026-06-26):** The legacy regex-pipeline scripts (`_translate_universal.py`, `_prime_validate.ps1`, `_auto_fix_between_retries.py`), their inputs (`_validate_input_all20.json`), and the golden/vendor output HTMLs (`pomezia_20260330_184323.html`, `vendor_queries_validated_20260408.html`) were **archived** under `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/` during the workspace reorg. They remain valid reference knowledge and the Files table (§15) points to their archived paths. `_batch_translate_pomezia.py` was **removed** entirely. The **active translation path is the agent + Layer-1 knowledge + live Athens validation**, not the old scripts. `_athens_view_definitions.py` and `_validate_athens_vs_neo4j.py` remain live in `SQL_Translations/`.

---

## 1. THREE DISTINCT WMS SYSTEMS

| System | Schema | Table Case | Example | Era |
|---|---|---|---|---|
| **RTCIS** | `esiliv1` | UPPERCASE | `esiliv1.LOCATN` | Legacy — being decommissioned |
| **PrIME 2014** | `dbo` | lowercase | `dbo.locmst` | Older PrIME — being upgraded |
| **PrIME 2022** | `dbo` | lowercase | `dbo.locmst` | Target — current version |

**CRITICAL:** RTCIS ≠ PrIME 2014. They are completely separate WMS platforms.
- `Pomezia RTCIS DR 2014.xlsx` = RTCIS schema (the "2014" is a date, NOT PrIME 2014)
- Data Model "Available - 2014" columns = PrIME 2014, NOT RTCIS

### System Names
- **PrIME** = Blue Yonder WMS (BY WMS). PrIME 2022 = BY2022 = **Puma**
- **RTCIS** = Real Time Control Information System (older custom-built P&G WMS)

---

## 2. CRITICAL CORRECTIONS (Expert-Verified, March 30, 2026)

⚠️ **These override any older information in other files:**

| Fact | Correct | Wrong (outdated) |
|---|---|---|
| TRUKIO maps to | **trlr** | ~~trlract~~ (trlract is a different table) |
| ITMCLS maps to | **prtmst.typcod** (FERT/ROH/HALB) | ~~prt_class_name~~ (empty at Athens) |
| Activity codes CASPIK/CASXFR | **Keep in translated SQL** but flag for site verification (see §4 Value Mappings) | ~~Don't exist, use CASPCKMOV/CS_XFR~~ |
| Table name suffix | **No __b suffix** (use `ord_line` not `ord_line__b`) | ~~__b suffix~~ (physical names) |
| APTDAT maps to | **appt.start_dte** (via trlr.appt_id → appt) | ~~stop.appt_dte~~ |

---

## 3. TABLE MAPPINGS (52 verified)

### HIGH Confidence (use directly)

| RTCIS | PrIME | Notes |
|---|---|---|
| AGV_INVENTORY_VIEW | inventory_view | No PrIME equivalent — use inventory_view + locmst + aremst JOINs |
| AS_RTCIS_CTLGRP | inventory_view | Inventory status filter (no separate table) |
| AS_RTCIS_UNITLD | invlod | Inventory Load (pallet) |
| AS_RTCIS_UNTDTL | invdtl | Inventory Detail (items on load) |
| CARRIER | car | Carrier master |
| CUSTMR | cstmst | Customer master |
| DLYTRN | dlytrn | Daily Transaction (PrIME native, 104 cols) |
| HOLD | invhld | Inventory Hold records |
| INVACT | invmov | Core movement log |
| INVDTL | invdtl | Inventory Detail (PrIME native) |
| INVENTORY_VIEW | inventory_view | Inventory summary view (PrIME native, 120+ cols) |
| INVHLD | invhld | Inventory Hold (PrIME native) |
| INVLOD | invlod | Inventory Load / pallet (PrIME native) |
| INVSUB | invsub | Inventory Sub-load (PrIME native) |
| ITEM_CONFIG | prtmst | Item Master (164 fields). PK: prtnum+prt_client_id+wh_id_tmpl |
| ITEM_UOM | prtftp_dtl | Item Footprint Detail (29 fields) |
| I_INVACT | invmov | Same as INVACT, extra cols CASQTY/EVT_ID available in PrIME |
| LOCATN | locmst | Primary location table, 76→5 columns |
| LOCMST | locmst | Location Master (PrIME native) |
| ORDDTL | ord_line | Order line detail |
| ORDHDR | ord | Order header |
| PRTFTP | prtftp | Item Footprint (PrIME native) |
| PRTFTP_DTL | prtftp_dtl | Footprint Detail / UOM (PrIME native) |
| PRTMST | prtmst | Primary item/part master |
| RCPDTL | rcvlin | Receipt line detail |
| SHPHDR | shipment | Shipment header |
| SHPORD | shipment_line | Shipment/order link |
| SYSDTL | dlytrn | Merged into dlytrn (SYSTRN+SYSDTL denormalized in PrIME) |
| SYSTRN | dlytrn | System Transaction → Daily Transaction (104 fields) |
| TRAILER | rcvtrk | Trailer master |
| TRLREQ | rcvtrk | Trailer assignment requests |
| TRUKIO | **trlr** | Trailer table. APTDAT via appt JOIN (trlr.appt_id=appt.appt_id) |
| WAVHDR | pckbat | Wave → Batch in PrIME |
| WH | wh | Warehouse |

### MED Confidence (verify on target)

| RTCIS | PrIME | Notes |
|---|---|---|
| AP3_CASPIK | pckwrk_dtl/pckwrk_hdr | Carrier-integrated case picks |
| BLDING | wh | Building/facility → site config or wh |
| CASPIK | pckwrk_dtl/pckwrk_hdr/pckbat | Case pick work records |
| CGHOLD | inv_asset | QA hold records via hold flag |
| ITMMST | prtmst/prtdsc | Split across two PrIME tables |
| MVT_MVTTYP | POLDAT | polcod='MVT_TYPE'; verify on target |
| PICK_METHOD | pck_mthd | Pick method definitions |
| PWZON | ptwy_last_loc/ALLOC_SEARCH_PATH_VIEW | Check view first |
| RCPHDR | rcvinv/rcvtrk | Split header/trailer in PrIME |
| REPLEN | wrkque | Filter by work type for replenishment |
| TRLMOV | invmov | Filter invmov by trailer for movement history |
| TSKTYP | wkohdr/wrkque | Task type master |
| WRKZON | mov_zone/wrkque | Work/movement zone |
| ZONCOD | pck_zone/sto_zone/mov_zone | Disambiguate by ZONE_TYPE |

---

## 4. COLUMN MAPPINGS (64 verified)

### Key RTCIS → PrIME Column Maps

| RTCIS | PrIME | Conf | Notes |
|---|---|---|---|
| ORDDTL.ORDNUM | ord_line.ordnum | HIGH | |
| ORDDTL.ITMCOD | ord_line.prtnum | HIGH | |
| ORDDTL.CASPAL | *CALCULATED* | — | `COALESCE(NULLIF(untpal,0)/NULLIF(untcas,0), 0)` |
| ORDHDR.ORDNUM | ord.ordnum | HIGH | |
| ORDHDR.SHIPID | ord.ship_id | HIGH | |
| TRUKIO.APTDAT | appt.start_dte | HIGH | Via JOIN: trlr.appt_id = appt.appt_id |
| TRUKIO.ORDNUM | **ABSENT** | — | trlr has NO ordnum. Use 5-hop join path |
| ITEM_CONFIG.ITMCOD | prtmst.prtnum | HIGH | |
| ITEM_UOM.ITMCOD | prtftp_dtl.prtnum | HIGH | |
| ITEM_UOM.WHSFLG | prtftp_dtl.stk_flg | HIGH | Binary flag: 0/1 |
| SYSTRN.TRNTYP | dlytrn.actcod | HIGH | Values NOT 1-1 mapped! Site must verify |
| SYSTRN.TRNSEQ | dlytrn.dlytrn_id | HIGH | PK of dlytrn |
| SYSDTL.ITMCLS | **prtmst.typcod** | HIGH | 'F'→'FERT', 'P'→'ROH'/'HALB'. NOT prt_class_name |
| SYSDTL.ITMCOD | dlytrn.prtnum | HIGH | |
| SYSDTL.LOCATN | dlytrn.frstol | HIGH | frstol=from, tostol=to. Use both for complete picture |
| SYSDTL.ORDNUM | dlytrn.ordnum | HIGH | |
| SYSDTL.TRNSEQ | dlytrn.dlytrn_id | HIGH | Denormalized into single table |
| LOCATN.LOCATN | locmst.stoloc | HIGH | NOT loc_id |
| LOCATN.ARECOD | locmst.arecod | HIGH | NOT area_id |
| LOCATN.RPLFLG | locmst.repflg | HIGH | NOT replen_flg |
| LOCATN.LOCTYPE | locmst.loc_typ_id | HIGH | |
| LOCATN.PIKZON | locmst.pck_zone_id | HIGH | |
| LOCATN.WRKZON | locmst.mov_zone_id | HIGH | |
| PRTMST.UNTPAL | prtftp_dtl.untqty | HIGH | WHERE uomcod='PL'. NOT on prtmst! |
| PRTMST.UNTCAS | prtftp_dtl.untqty | HIGH | WHERE uomcod='CS'. NOT on prtmst! |
| PRTMST.UNTINP | prtftp_dtl.untqty | HIGH | WHERE uomcod='LY'. untinp removed in 2022 → use untlay |

### SYSDTL Detail Fields → dlytrn

| RTCIS | PrIME | Notes |
|---|---|---|
| ULID | lodnum | Load number |
| ITMCOD | prtnum | Part number |
| CTLGRP | lotnum | Lot number |
| SUBSIT | wh_id | Replace with site's warehouse ID |
| LOCATN | frstol/tostol | Source or destination location |
| LNGCOM | cmnt | Long comment → comment field |

### Value Mappings (RTCIS Filter Constants → PrIME Equivalents)

RTCIS queries use hardcoded filter values (e.g. `WHERE TRNTYP IN ('CASPIK','CASXFR')`).
The **column** maps correctly (`TRNTYP` → `actcod`), but the **values inside** are RTCIS-specific and may not exist in PrIME.

#### SYSTRN.TRNTYP → dlytrn.actcod (Transaction Type → Activity Code)

`TRNTYP` is a lookup table in RTCIS schema (`_rtcis_tables.txt` line 368). Values are abbreviations of warehouse operations defined in the RTCIS Training Modules.

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | Best-Estimate PrIME actcod | Confidence | Evidence |
|---|---|---|---|---|---|
| CASPIK | Case Pick — picking cases from bulk storage | SYSTRN.TRNTYP; Training Module `161. RTCIS Case Picking.ppt` | CASPCKMOV (6,634 rows at Athens) | MED | Name similarity + `_batch_translate_pomezia.py` mapping. LSTPCK (79K rows) also possible |
| CASXFR | Case Transfer — moving cases between locations | SYSTRN.TRNTYP; Training Module `170. Shuttle and Transfer.ppt` | CS_XFR (in Athens actcod list) | MED | Name match (CAS→CS, XFR→XFR). Also FL_XFR, PL_XFR for other UOMs |
| STKCOR | Stock Correction — inventory adjustment after discrepancy | SYSTRN.TRNTYP; Training Module `200. Stock Counting.ppt` context | INVSTSCHG (7,705 rows at Athens) | MED | Business meaning match: stock correction ≈ inventory status change |
| STKCNT | Stock Count — physical cycle count transaction | SYSTRN.TRNTYP; Training Module `200. Stock Counting.ppt` | CNTBCKD or count-related code | LOW | No exact match at Athens. CNTBCKD = count back (batch translate guess) |
| OVRPND | Override Pending — supervisor override awaiting approval | SYSTRN.TRNTYP; Q18 RTCIS SQL filter | No match at Athens | LOW | `open-questions.json` Q#1. Closest: LOCOVRRID (location override) |
| OVRRID | Override — supervisor override executed | SYSTRN.TRNTYP; Q18 RTCIS SQL filter | LOCOVRRID (partial) | LOW | Learning #6: doesn't exist at Athens. LOCOVRRID is closest |
| DEPSUL | Deposit/Putaway — placing stock into storage location | SYSTRN.TRNTYP; Q18 RTCIS SQL filter | PUT_DRCT (3,686 rows) or GENMOV | LOW | Business meaning: deposit ≈ putaway. Learning #6: no match at Athens |

**⚠️ All MED/LOW estimates must be verified by the Pomezia WMS team before production use.**

#### SYSDTL.ITMCLS → prtmst.typcod (Item Classification)

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | PrIME Value | Confidence | Evidence |
|---|---|---|---|---|---|
| F | Finished Goods | SYSDTL.ITMCLS; RTCIS schema convention (SAP FERT) | FERT | HIGH | Expert-verified. Learning #5, #44. Training Module `121. Master Data.ppt` |
| P | Raw/Packaging Material | SYSDTL.ITMCLS; SAP material type ROH/HALB | ROH or HALB | MED | Inferred from SAP type mapping (§6 Product/Material Types) |

#### SYSDTL.DTLTYP → dlytrn.oprcod (Detail Type → Operation Code)

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | PrIME Value | Confidence | Evidence |
|---|---|---|---|---|---|
| F | Operation type filter | SYSDTL.DTLTYP; Q1/Q2 RTCIS SQL | F (same value) | HIGH | Learning #58. No remapping needed. ⚠️ Do NOT confuse with ITMCLS='F'→typcod='FERT' |

#### AS_RTCIS_CTLGRP.QASTAT → inventory_view.invsts (Quality Status → Inventory Status)

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | PrIME Value | Confidence | Evidence |
|---|---|---|---|---|---|
| RL | Released (quality approved) | AS_RTCIS_CTLGRP.QASTAT; Q28/Q29 RTCIS SQL | U (Unrestricted) | HIGH | Learning #49, #56. Value 'RL' does NOT exist in PrIME. ⚠️ Bug found and fixed 2026-04-10 |

#### SYSDTL.SUBSIT / AGV_INVENTORY_VIEW.SUBSIT → dlytrn.wh_id (Subsite → Warehouse ID)

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | PrIME Value | Confidence | Evidence |
|---|---|---|---|---|---|
| 0 | Pomezia default subsite | Q19/Q20 RTCIS SQL: `WHERE SUBSIT = '0'` | WMD1 (Athens) / **TBD** (Pomezia) | MED | Athens DBA discovery: only wh_id='WMD1' exists. Pomezia ID unknown |

#### AGV_INVENTORY_VIEW.BLDING → wh.bldg_id (Building)

| RTCIS Value | RTCIS Meaning | Source (RTCIS) | PrIME Value | Confidence | Evidence |
|---|---|---|---|---|---|
| POME | Pomezia warehouse building | Q19 RTCIS SQL: `WHERE BLDING = 'POME'` | POME (likely same) | MED | Building IDs often carry over. Verify at Pomezia site |

#### ORDDTL.ITMCOD exclusion list (Service Items)

| RTCIS Values | RTCIS Meaning | Source (RTCIS) | PrIME Equivalent | Confidence |
|---|---|---|---|---|
| 00070000, 00070005, 00070006, 00070009, 00070010 | Service/non-stock item codes | Q1/Q2 RTCIS SQL: `ITMCOD NOT IN (...)` | Same part numbers (prtnum) | HIGH — part numbers are master data, not system codes |

#### Queries Affected by Unmapped Values

| Query | Unmapped Values | Impact |
|---|---|---|
| Q1 | appt_id IS NOT NULL filter | 0 rows — no appointments in Athens test data |
| Q5, Q6, Q7, Q8 | CASPIK, CASXFR | 0 rows — actcod values don't exist at Athens |
| Q9, Q11, Q12 | CASPIK, CASXFR + typcod='FERT' | 0 rows — same actcod issue |
| Q17 | CASXFR, STKCOR, STKCNT | 0 rows — actcod values don't exist at Athens |
| Q18 | OVRPND, OVRRID, DEPSUL | 0 rows — actcod values don't exist at Athens |
| Q19 | bldg_id='POME' + arecod LIKE '%AGV%' | 0 rows — Athens is not Pomezia |
| Q20 | typcod='FERT' + HOLD_ULID LIKE '00%' | 0 rows — no matching hold records at Athens |

---

## 5. JOIN PATHS

### ORDDTL → TRUKIO (5-hop shipment bridge)
```
ord_line → shipment_line (ordnum+ordlin+client_id)
  → shipment (ship_id)
    → stop (stop_id)
      → car_move (car_move_id)
        → trlr (trlr_id)
```
**NOTE:** Direct join impossible — trlr has no ordnum column.

### SYSTRN + SYSDTL → dlytrn
Both RTCIS tables merge into single `dlytrn` table. No JOIN needed in PrIME.

### TRUKIO.APTDAT → appt.start_dte
```
trlr (appt_id) → appt (appt_id) → appt.start_dte
```

### Footprint (ITEM_CONFIG/ITEM_UOM → prtftp/prtftp_dtl)
Triple LEFT JOIN with UOM-specific aliases:
```sql
LEFT JOIN dbo.prtftp_dtl fp_cs ON item.prtnum = fp_cs.prtnum 
    AND fp_cs.uomcod = 'CS' AND fp_cs.wh_id = item.wh_id AND fp_cs.ftpcod = item.ftpcod
LEFT JOIN dbo.prtftp_dtl fp_ly ON ... AND fp_ly.uomcod = 'LY' ...
LEFT JOIN dbo.prtftp_dtl fp_pl ON ... AND fp_pl.uomcod = 'PL' ...
```

---

## 6. CONCEPT MAPPINGS

| RTCIS Concept | PrIME Replacement | Notes |
|---|---|---|
| Subsite (subsit / *sit fields) | wh_id | Always tell user to replace with their warehouse ID |
| Item Group (itmgrp) | prtfam | Item family |
| Zone Code (ZONCOD) | arecod | Area code (may need sto_zone_id depending on context) |
| Pallet Type (ULPALL) | `isnull(asset_typ, ftpcod)` | Asset type if site uses tracking, else footprint code |
| Item Class (ITMCLS) | prtmst.typcod | 'F'→'FERT', 'P'→'ROH/HALB'. NOT prt_class_name |
| UNTDTL.ORDNUM | ship_line_id or shipment_line join | Null check: ship_line_id. Actual order#: join shipment_line |

### Product/Material Types
| Abbreviation | Meaning | SAP Type |
|---|---|---|
| FG/FP/SKU | Finished Goods/Products | FERT |
| RM/PM/RPM | Raw/Packaging Materials | ROH (sometimes HALB) |

### Footprint Hierarchy (Units of Measure)
```
Pallet(PL) > Layer(LY) > Case(CS) > [Shrink-Wrap(SW)/Shelf-Pack(SP) >] Item(IT)
```
- Case is lowest tracked UOM for most legacy products
- All untqty fields are in **units** (smallest UOM) — convert: qty / untcas

---

## 7. SQL TRANSLATION RULES

### Mandatory Rules
1. **Division safety (ALWAYS):** `CASE WHEN ISNULL(divisor, 0) = 0 THEN dividend ELSE dividend/divisor END`
2. **untinp removed in 2022** — use `untlay` instead
3. **Schema prefixes:** PrIME 2022 = `dbo.`, RTCIS = `live3.`, PrIME 2014 = `prodwms.`
4. **HAVING without aggregate** → move to WHERE
5. **WHERE duplicating JOIN ON** → remove from WHERE
6. **Subsite → wh_id** — always alert user to replace
7. **No __b suffix** on table names (use logical/view names)
8. **No AS keyword** on table aliases (enterprise convention: `dbo.ord_line d` not `dbo.ord_line AS d`)
9. **Block comments** `/* */` not `--` for inline annotations (single-line SQL safety)

### Output Equivalence Rules (RULE #2 — April 2026)
10. **NOT a 1:1 translation** — RTCIS and PrIME are different WMS products. The goal is semantic equivalence of OUTPUT, not syntactic similarity of SQL. A correct PrIME query may look structurally different.
11. **JOIN paths are valid** — When an RTCIS column is split across multiple PrIME tables, use JOINs / correlated subqueries / CROSS APPLY to retrieve it. Do not leave it as NULL unless the data truly does not exist in PrIME. Mark every JOIN resolution in the "What Changed" section.
12. **Same output column sequence & meaning** — Downstream consumers (PBI, RPA, etc.) must receive the same columns in the same order with the same meaning. PrIME columns must be aliased to RTCIS names. Extra PrIME columns may be appended at end.
13. **Highlight uncertain filter values** — Any hardcoded filter value (area codes, location names, actcod constants, zone patterns) that may not exist at target site must have an inline `/* VERIFY: ... */` comment.
14. **SELECT * handling** — RTCIS and PrIME tables have completely different column sets (names, count, order). SELECT * cannot be blindly transformed. Best: expand to explicit column list with RTCIS aliases. Acceptable: wrap in outer query. Last resort: use SELECT * with a WARNING comment.

### Iterative Best-Effort Column Matching (RULE #3 — April 2026)
15. **Never leave a column unmapped** without exhausting all 9 matching passes: (1) exact name, (2) dictionary, (3) reverse dict, (4) suffix/compound, (5) partial tail, (6) substring, (7) semantic keyword, (8) domain analysis, (9) mark NO EQUIVALENT only as last resort.
16. **Confidence labeling** — Every mapped column must show HIGH (verified), MED (likely), or LOW (guess). MED/LOW mappings get `/* BEST-ESTIMATE */` comments.
17. **Iterate, don't stop early** — If pass 2 gives a LOW-confidence match, continue to pass 3-8 to see if a better match exists. Pick the highest-confidence result.

### Footprint Translation Pattern
When RTCIS queries reference PRTMST.UNTPAL/UNTCAS/UNTINP:
- Do NOT simple-rename — these columns don't exist on prtmst in PrIME
- Must add triple LEFT JOIN to prtftp_dtl with uomcod filters per UOM
- prtftp_view = VIEW from prtftp JOIN prtftp_dtl (alternative shortcut)

### Activity Code Mapping
- RTCIS TRNTYP values (CASPIK, CASXFR, etc.) → PrIME actcod
- **No 1-1 mapping** — granularity differs between systems
- See **§4 Value Mappings** for full RTCIS→PrIME value mapping table with best estimates
- Expert guidance: use RTCIS values as-is in translated queries; site must verify which actcod values exist at Pomezia

### ITMCLS → typcod Filter Pattern
```sql
-- WRONG: WHERE prt_class_name = 'F'  (empty at Athens!)
-- CORRECT:
WHERE prtnum IN (SELECT DISTINCT prtnum FROM dbo.prtmst WHERE typcod = 'FERT')
```

---

## 8. PrIME 2014 → 2022 CHANGES (from Training Transcript)

### Areas → Zones (Biggest Change)
- Area master (`aremst`) in 2014: 105 fields, central concept
- In 2022: retains ~11 fields (info only), split into 4 zone types:

| 2014 Concept | 2022 Replacement | Table |
|---|---|---|
| Area (storage) | Storage Zones | sto_zone |
| Area (movement) | Movement Zones | mov_zone |
| Area (picking) | Pick Zones | pck_zone |
| Area (general flags) | Location Types | loc_type |
| Area UOMs + Pick policies | Pick Methods | pck_mthd |

- Any query using `arecod` must assess which zone type to use
- Reports using areas for filtering will work initially but become stale

### Other 2014→2022 Changes
- Putaway strategy: single-level → 2-level hierarchy (source move zone → dest storage zone)
- Allocation/picking: single-level → 2-level hierarchy
- Database: Oracle → SQL Server
- `uc_custom_parameters` deprecated → migrating to policies table
- 138 renamed fields, 764 removed fields, 6,865 new fields between PrIME 2014 and 2022

---

## 9. SCHEMA QUIRKS (Athens Replica)

| Finding | Impact |
|---|---|
| `dlytrn` is a SYNONYM (not table/view) | INFORMATION_SCHEMA returns 0 — use sys.columns |
| `prtmst` has no `wh_id` column | Uses `wh_id_tmpl` instead |
| `prt_class_name` is EMPTY for all 41,355 items | Use `typcod` instead |
| `prtftp_dtl` has untpal/untcas but prtmst does NOT | Must JOIN to prtftp_dtl for footprint data |
| `locmst` uses short flag names | `repflg` not `replen_flg`, `arecod` not `area_id` |
| `inventory_view` has 120+ columns | Exists as dbo.inventory_view (131 cols live) |
| frstol populated in 53% of dlytrn, tostol in 48% | Use BOTH for complete location picture |

### 9.1 ATHENS REPLICA VIEW CATALOG (Live — April 2026)

Extracted from live Athens Replica (`ATHENS_REPLICA`) via `sys.sql_modules` + `sys.dm_sql_referenced_entities`. All 17 dbo views confirmed present.

| View | Cols | Base Tables | Domain | SDC Module |
|---|---|---|---|---|
| `alloc_search_path_view` | 18 | alloc_search_path, alloc_search_path_rule, pck_mthd, pck_zone | Picking Allocation | 04/05 |
| `base_assignments` | 82 | kvi_summary, jobcode, jobcode_kvi, aisle_area, emp_sched_link, schedule, shift | Labor (LMS) | — |
| `dual` | 1 | (none — literal) | Utility | — |
| `inventory_pckwrk_view` | 112 | invdtl, invlod, invsub, pckwrk_hdr, pckwrk_dtl, prtftp, prtftp_dtl | Inventory + Picking | 04/05 |
| `inventory_view` | 131 | invdtl, invlod, invsub, invdtl_hist, invlod_hist, invsub_hist | Core Inventory | 03/04 |
| `nxtloc_view` | 29 | inventory_view, invmov, locmst | Putaway / Movement | 03 |
| `pckwrk_view` | 223 | pckwrk_hdr, pckwrk_dtl, locmst | Pick Work | 05 |
| `pndinv_view` | 64 | invdtl, invlod, invsub, invmov, locmst | Pending Inventory | 03 |
| `poldat_view` | 17 | poldat, wh | Policy / Config | 02 |
| `prtftp_view` | 47 | prtftp, prtftp_dtl | Item Footprint | 04 |
| `prtmst_view` | 165 | prtmst | Item Master | 04 |
| `rplsts_view` | 30 | rplwrk, shipment_line, ord_line, shipment, stop, wkodtl, wkohdr | Replenishment | — |
| `ship_struct_view` | 102 | shipment, stop, car_move, trlr, appt | Shipping / Yard | 01/07 |
| `shipping_pckwrk_view` | 233 | pckwrk_view, ord, shipment, stop, car_move | Shipping Picks | 05/07 |
| `Statistics_Performance` | 54 | base_assignments, jobcode, kvi_adjustments, users_view, workteam, workarea, subgroup, workcategory | Labor KPI | — |
| `users_view` | 63 | les_usr_ath, adrmst | User Master | 02 |
| `wrkopr_view` | 24 | wrkopr, wh | Work Operation Rules | 02 |

**Total:** 17 views, 1,395 columns across 49 unique base tables.

### 9.2 KEY VIEW INTERNALS

- **`prtftp_view`** — JOINs prtftp + prtftp_dtl with 6 flag-specific LEFT JOINs (pal_flg, cas_flg, pak_flg, rcv_flg, stk_flg, layer_flg). Returns 47 columns including untpal, untcas, grswgt, dimensions.
- **`ship_struct_view`** — Pre-materialized 5-hop join: `shipment → stop → car_move → trlr → appt`. 102 columns — use this instead of manually building the 5-hop join path.
- **`inventory_view`** — UNION ALL of live inventory (invdtl/invlod/invsub) + history (invdtl_hist/invlod_hist/invsub_hist). 131 columns.
- **`pckwrk_view`** — Denormalized: pckwrk_hdr + pckwrk_dtl + locmst. 223 columns — largest view.
- **`rplsts_view`** — Replenishment status tracker: rplwrk + shipment_line + ord_line + shipment + stop + wkodtl + wkohdr. Not in SDC documentation.
- **`poldat_view`** — Policy data with warehouse override pattern (same as wrkopr_view): template rows UNION ALL warehouse-specific rows.
- **`base_assignments`** / **`Statistics_Performance`** — Labor Management (LMS/KVI). Not used in current RTCIS→PrIME translations but present in live DB.

### 9.3 SDC CROSS-VALIDATION (April 2026)

- All 13 SDC-documented PrIME views confirmed LIVE in Athens ✅
- 4 extra views not in SDC: `base_assignments`, `Statistics_Performance`, `dual`, `rplsts_view`
- 25 base tables discovered that were not in `_graph_export.json`: stop, car_move, appt, rplwrk, adrmst, wrkopr, kvi_summary, jobcode, alloc_search_path, alloc_search_path_rule, invdtl_hist, invlod_hist, invsub_hist, les_usr_ath, wkodtl, shift, schedule, emp_sched_link, aisle_area, jobcode_kvi, kvi_adjustments, workteam, workarea, workcategory, subgroup
- Scripts: `_athens_view_definitions.py` (extraction), `_validate_athens_vs_neo4j.py` (validation)

---

## 10. 20 QUERY INVENTORY (Current State)

### Expert-Validated Queries (11)
| Q | Name | Tables | Notes |
|---|---|---|---|
| Q1 | Order + Trailer | ORDDTL, TRUKIO | 5-hop shipment bridge |
| Q2 | Order + Trailer + CASPAL | ORDDTL, TRUKIO | DISPLAY/CASSE classification |
| Q5 | Daily Transactions | SYSTRN | Simple actcod filter |
| Q6 | Daily Transactions (detail) | SYSDTL, SYSTRN | SYSTRN+SYSDTL → dlytrn |
| Q7 | Transactions + Item Class | SYSDTL, SYSTRN | typcod='FERT' pattern |
| Q8 | Transactions + Item Class | SYSDTL, SYSTRN | Identical to Q7 |
| Q10 | Item Config + UOM | ITEM_CONFIG, ITEM_UOM | prtftp + prtftp_dtl |
| Q13 | All Transactions | SYSDTL, SYSTRN | Full dlytrn dump |
| Q15 | Spezzature (broken pallets) | Inventory + prtmst | Expert rewrote with inventory_view |
| Q18 | Override + Details | SYSDTL, SYSTRN | TRANSFORMATION not translation |
| Q19 | Inventario HOLD | Inventory | inventory_view + locmst + aremst |

### Auto-Translated (with expert notes) (9)
| Q | Name | RTCIS Invalid | Notes |
|---|---|---|---|
| Q3 | Order + WHSFLG | Yes | stk_flg on prtftp_dtl, 5-hop join |
| Q4 | Order + Item Master | Yes | typcod in SELECT, 5-hop join |
| Q9 | Txn + Item Class + Order | Yes | typcod='FERT' pattern (aligned Q7/Q8) |
| Q11 | Txn + Item Class + Order | Yes | Same PrIME result as Q9 |
| Q12 | Txn + Item Class (complex) | Yes | Redundant re-joins collapsed |
| Q14 | Override + Deposits | No | frstol/tostol, location extraction from cmnt |
| Q16 | Locazioni compattabili | Yes | inventory_view + packaging calculation |
| Q17 | Check compattamenti | Yes | actcod kept as RTCIS originals, site verifies |
| Q20 | SYSTRN SYSDTL HOLD | Yes | typcod='FERT', HOLD→invhld |

### Cross-Query Patterns
- Q7 = Q8 (identical)
- Q9 = Q11 = Q12 (same PrIME result after translation)
- Q5 = Q6 (same PrIME result)
- Q1→Q2→Q3→Q4: incremental build-up (orders)
- Q5→Q6→Q7→Q9→Q17: incremental build-up (transactions)

---

## 11. ACTIVE LEARNINGS (29)

### Critical (9)
| # | Learning |
|---|---|
| 1 | dlytrn PK is `dlytrn_id` (not trnnum) |
| 2 | dlytrn is a SYNONYM — use sys.columns not INFORMATION_SCHEMA |
| 3 | prtmst has `wh_id_tmpl` not `wh_id` |
| 22 | Error iteration: diagnose → auto-fix → re-validate (up to 3 attempts) |
| 23 | Footprint arch change: UNTPAL/UNTCAS/UNTINP split to prtftp_dtl |
| 41 | TRUKIO → trlr (NOT trlract). 5-hop join: ord_line→shipment_line→shipment→stop→car_move→trlr |
| 42 | CASPAL calculated: `CASE WHEN ISNULL(ftp.untcas,0)=0 THEN 0 ELSE ftp.untpal/ftp.untcas END` |
| 46 | AS_RTCIS_UNITLD + AS_RTCIS_UNTDTL both → inventory_view (not invlod/invdtl) |
| 47 | CASQTY calculated: `CASE WHEN ISNULL(untcas,0)=0 THEN untqty ELSE untqty/untcas END` |
| 51 | SYSDTL detail fields: ULID→lodnum, ITMCOD→prtnum, CTLGRP→lotnum, SUBSIT→wh_id |
| 53 | Complex RTCIS queries need TRANSFORMATION not translation |
| 54 | AGV_INVENTORY_VIEW → inventory_view + locmst + aremst JOINs |

### Important (14)
| # | Learning |
|---|---|
| 4 | locmst uses short flag names: repflg, not replen_flg |
| 5 | ITMCLS → prtmst.typcod (FERT/ROH/HALB). NOT prt_class_name |
| 6 | OVRPND, OVRRID, DEPSUL don't exist in Athens — closest alternatives needed |
| 15 | untcas not on prtmst — it's on prtftp_dtl |
| 16 | ftpcod not on prtmst — it's on prtftp/prtftp_dtl |
| 19 | area_id doesn't exist on locmst — use arecod |
| 40 | AS_RTCIS_CTLGRP.QASTAT → invhld.hldsts (VERIFIED_ABSENT) |
| 43 | TRNTYP values CASPIK/CASXFR NOT 1-1 mapped to PrIME actcod. See §4 Value Mappings |
| 44 | ITMCLS concept disappears. Closest: prtmst.typcod |
| 45 | ITEM_CONFIG → prtftp (not just prtmst). ITEM_UOM → prtftp_dtl |
| 48 | ORDNUM in AS_RTCIS_UNTDTL → shipment_line.ordnum via ship_line_id JOIN |
| 49 | AS_RTCIS_CTLGRP.QASTAT='RL' → invsts='U' in PrIME |
| 50 | CASLAY/LAYPUL calcs change in PrIME — use untcas/untlay/untpal from prtftp_view |
| 52 | LNGCOM → cmnt (but logic extracting locations from comments needs rework) |

### Minor (2)
| # | Learning |
|---|---|
| 8 | inventory_view exists at Athens with 120+ columns |
| 9 | Comment stripping: be careful not to damage string literals |

---

## 12. TRANSLATION PIPELINE

### Tool: `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/temp_scripts/_translate_universal.py` *(archived 2026-06-26)*
- Full 7-phase workflow: KB → Parse → Lookup → Gate → Translate → Validate → Capture
- Run (historical, from archive): `py _translate_universal.py --json _validate_input_all20.json --validate`
- Input: JSON array with `id`, `name`, `sql`, `prime_sql`, `expert_validated`, `expert_note` fields
- Output: HTML + JSON with per-query tabs, summary, validation results

### Per-Query Tab Sections (6)
1. **Confidence Check** — gate score, syntax warnings, expert notes (TOP of tab)
2. **Original RTCIS Query** — source SQL + table list
3. **Translated PrIME 2022 Query** — copy-paste ready SQL
   - 3b. Expert vs Auto-Generated Comparison (if expert-validated)
4. **What Changed** — Table + Column mapping tables with confidence
5. **DBA Verification Required** — questions needing confirmation
6. **Live Validation Results** — Athens Replica execution results

### Summary Tab Sections
- Overview + accuracy policy
- All Queries at a Glance (table)
- DBA Verification Questions (aggregated)
- Expert Learning Log (29 active)
- Live Database Validation
- Query Insights (cross-query analysis)
- Validation Report
- Next Steps (once, not per-query)

### Validation
- Live validation against Athens Replica (ATHENS_REPLICA, wh_id='WMD1')
- ODBC Driver 18 + ActiveDirectoryInteractive auth
- Error iteration: diagnose → auto-fix → re-validate (up to 3 attempts)
- NEVER output a failed query as READY

### Knowledge Sources (Priority Order)
1. Schema files (`_loc_columns_extract.txt`, `_prime_tables.txt`) — ground truth
2. ER Diagrams (81 JPGs in `Data Relationship Diagrams/`) — join paths
3. Data Model (`prime-datamodel.json`, 1,661 tables, 22,867 fields) — field semantics
4. Training transcript knowledge — business context
5. Verified mappings KB (`verified-mappings.json`) — curated from past translations
6. User feedback — site-specific knowledge

---

## 13. OUTPUT FORMAT & TONE

### Audience
Users are **non-technical** (warehouse operations, business analysts). Output must be:
- **Scannable** in under 2 minutes
- **Jargon-free** — no "logical reads", "sargable", "execution plan", "index seek"
- **Actionable** — clear next steps, copy-paste ready SQL
- **Honest** — clearly flag anything uncertain with WHO to ask and WHAT to ask

### Per-Query Tab Sections (6 — current)
1. **Confidence Check** — traffic-light table, gate score, applied learnings with badges (✅ Applied / ⚙️ Built-in / ℹ️ Reference)
2. **Original RTCIS Query** — source SQL in code block + one-line plain-English summary
3. **PrIME 2022 Query** — copy-paste ready SQL. Structural changes explained in BUSINESS terms only.
   - 3b. Expert vs Auto-Generated Comparison (if expert-validated)
4. **What Changed** — Tables (old→new), Columns (old→new), Key Differences
5. **DBA Verification** — questions with: why it matters, who to ask, what to verify
6. **Live Validation Results** — Athens Replica execution: rows, columns, sample data

### Summary Tab
Overview, All Queries at a Glance, DBA Questions (aggregated), Expert Learning Log, Live Validation, Query Insights, Validation Report, Next Steps

### File Naming
**Format:** `YYYYMMDD_HHMMSS_<TableNames>.md` in `SQL_Translations/`

### Chat vs File
| Content | Chat | File |
|---|:---:|:---:|
| 6 user-facing sections | ✅ | ✅ |
| Technical Appendix (mapping tables, join evidence, validation queries) | ❌ | ✅ |

---

## 14. PRE-FLIGHT CHECKLIST

### Schema Verification (DO FIRST)
- [ ] Input mode identified: auto-translate or hybrid (sql + prime_sql)
- [ ] All RTCIS tables verified in `_rtcis_tables.txt`
- [ ] All PrIME tables verified in `_prime_tables.txt`
- [ ] For EACH column: search `_loc_columns_extract.txt` → VERIFIED / VERIFIED_ABSENT / UNVERIFIABLE
- [ ] Every JOIN has equivalent columns in PrIME tables
- [ ] If join key missing: flag STRUCTURAL CHANGE + alternative join path

### Translation Quality (DO SECOND)
- [ ] All table names use `dbo.tablename` format
- [ ] All uncertain mappings have `/* verify */` inline comments
- [ ] All business logic preserved (WHERE, JOINs, GROUP BY)
- [ ] Every table/column has confidence: HIGH / MED / ⚠️ NEED EXPERT CHECK
- [ ] No contradictions between sections

### Error Iteration (IF VALIDATION FAILS)
- [ ] Diagnose error → apply auto-fix → re-validate (up to 3 total attempts)
- [ ] Auto-fix patterns:
  - `Invalid column name 'X'` → remove from SELECT
  - `Invalid object name 'dbo.X'` → try without dbo, check spelling
  - `Ambiguous column name 'X'` → add table alias
  - `Incorrect syntax near 'NOLOCK'` → remove WITH (NOLOCK)
  - `0 rows when data expected` → review WHERE filters (known-empty fields?)
- [ ] PASS → mark READY. FAIL after 3 retries → mark BLOCK with error documented
- [ ] **NEVER output a failed query as READY**

### Post-Translation Sustainability
- [ ] New discoveries → append to `translation-learnings.json` (v2.0 with `implemented_via`)
- [ ] Check for duplicate learnings before appending
- [ ] Unresolved uncertainties → `open-questions.json` with priority + who_to_ask
- [ ] New HIGH-confidence mappings → update `verified-mappings.json`
- [ ] Translator TABLE_MAP/col_map matches KB — flag discrepancies

### Column Decision Tree
```
1. Table in _loc_columns_extract.txt? NO → MED. YES → step 2.
2. Column in list? YES → HIGH. NO → step 3.
3. Join key missing? YES → STRUCTURAL CHANGE. NO → NEED EXPERT CHECK.
4. Document in both Accuracy Report AND Schema Cross-Check with evidence.
```

---

## 15. FILES & PATHS

| File | Path | Purpose |
|---|---|---|
| Translator | `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/temp_scripts/_translate_universal.py` | Main 7-phase translation pipeline *(archived 2026-06-26)* |
| Input (20 queries) | `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/temp_outputs/_validate_input_all20.json` | All 20 RTCIS queries + PrIME translations *(archived 2026-06-26)* |
| Latest HTML | `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/pomezia_20260330_184323.html` | 20/20 PASS output *(archived 2026-06-26)* |
| Verified Mappings KB | `.github/tools/verified-mappings.json` | 52 tables, 64 columns, 9 join paths |
| Translation Learnings | `.github/tools/translation-learnings.json` | 29 active learnings |
| Knowledge Registry | `.github/tools/knowledge-registry.json` | Canonical paths for all files |
| Data Model | `.github/tools/prime-datamodel.json` | 1,661 tables, 22,867 fields |
| ERD Index | `.github/tools/erd-index.json` | Machine-readable ERD data |
| Schema Extract | `_loc_columns_extract.txt` | Raw column lists |
| PrIME Tables | `_prime_tables.txt` | PrIME 2022 table list |
| RTCIS Tables | `_rtcis_tables.txt` | RTCIS table list |
| Validation Script | `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/temp_scripts/_prime_validate.ps1` | Live query execution against Athens *(archived 2026-06-26)* |
| Agent Instructions | `.github/agents/rtcis-to-prime-sql.agent.md` | Invocable agent for Copilot |
| Complete Reference | `.github/agents/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md` | This file — all domain knowledge |

---

## 16. DBA QUESTIONS (8 Answered + 3 New)

**Database:** <replica-host> / ATHENS_REPLICA / wh_id='WMD1'

1. ✅ Activity codes: CASPIK/CASXFR — use as-is per expert (earlier "don't exist" was wrong)
2. ✅ prt_class_name EMPTY for all 41,355 items — use typcod instead
3. ✅ CASPAL = untpal ÷ untcas (confirmed by expert)
4. ✅ stk_flg values: '0' and '1' (binary flag)
5. ✅ ftpcod values: B2 (common), P2, B1, C2. uomcod: PL, CS, LY, IT, SW
6. ✅ 5-hop join path confirmed by expert
7. ✅ Both frstol (53%) and tostol (48%) populated in dlytrn
8. ✅ dlytrn is a SYNONYM — use sys.columns for metadata

### New DBA Questions (Value Mapping — from §4)
9. ❓ **actcod mapping:** What PrIME actcod values correspond to RTCIS CASPIK, CASXFR, STKCOR, STKCNT, OVRPND, OVRRID, DEPSUL? (Best estimates in §4 — need Pomezia WMS team confirmation)
10. ❓ **Pomezia wh_id:** What is Pomezia's warehouse ID in PrIME? (Currently using Athens WMD1 as placeholder)
11. ❓ **Pomezia bldg_id:** Does Pomezia use 'POME' as bldg_id in PrIME? (Q19 filter)

### Remaining Open Questions
- **What is Pomezia's PrIME warehouse ID?** (Replace WMD1 placeholders)
- **What are the correct PrIME actcod values for CASPIK, CASXFR, STKCOR, STKCNT, OVRPND, OVRRID, DEPSUL?** See §4 Value Mappings for best estimates — 11 of 20 queries return 0 rows because these RTCIS filter values don't exist at Athens. The Pomezia WMS team must provide the site-specific actcod list.
- **Pomezia prt_client_id:** Is it '----' (same as Athens) or site-specific? (Q2 vendor footprint check)
- **DEFAULT_CONF:** Does Pomezia need the "default configuration" concept from RTCIS ITEM_CONFIG? PrIME has no equivalent flag. (Q2 vendor query gap)

---

## 17. APRIL 2026 UPDATE — Vendor Ad-Hoc Queries & Pipeline Enhancements

### New Query Set: Vendor Queries (34→37)

In addition to the 34 Pomezia queries (Q1–Q34, all PASS), 2 vendor RTCIS ad-hoc queries + 1 additional question were translated and validated:

| ID | Query | Status | Notes |
|---|---|---|---|
| Q35 | UNTDTL_VIEW Count by SSCC | ✅ PASS | `SELECT COUNT(*) FROM inventory_view WHERE lodnum = ?` |
| Q36 | ITEM_CONFIG Footprint Check (LAYPUL=1 AND CASLAY<9) | ✅ PASS | Scalar subqueries into prtftp_view, DEFAULT_CONF removed (no PrIME equiv) |
| Q37 | Multi-Batch Pallet Detail (derived from Q35) | ✅ PASS | LEFT JOIN prtftp_view for CASQTY calculation |
| — | ORDNUM answer | ✅ VALIDATED | `inventory_view.ship_line_id → shipment_line.ordnum` (68.5% population rate) |

**Input file:** `SQL_Translations/_queries_vendor_adhoc.json`
**Validation report:** `SQL_Translations/_quarantine_2026-06-26/cache_archive/_archive/vendor_queries_validated_20260408.html` *(archived 2026-06-26)*

### New Table Mappings (April 2026)

| RTCIS | PrIME | Conf | Notes |
|---|---|---|---|
| UNTDTL_VIEW | inventory_view | HIGH | Vendor view name. Same as AS_RTCIS_UNTDTL |
| VUNTDTL_VIEW | inventory_view | HIGH | 'v' prefix variant. Both map to inventory_view |
| ORACLE_RTCIS..LIVE3.* | dbo.* | HIGH | Linked-server prefix syntax → strip + replace with dbo. |

### New Column Mappings (April 2026)

| RTCIS | PrIME | Conf | Notes |
|---|---|---|---|
| UNTDTL_VIEW.UNTDTL_ULID | inventory_view.lodnum | HIGH | Vendor prefixed column name. ULID = Unit Load ID = SSCC = lodnum |
| UNTDTL_VIEW.UNTDTL_ITMCOD | inventory_view.prtnum | HIGH | Vendor prefixed. ITMCOD = item code = part number |
| VUNTDTL_VIEW.ULID | inventory_view.lodnum | HIGH | Same as UNTDTL_VIEW |
| VUNTDTL_VIEW.ITMCOD | inventory_view.prtnum | HIGH | |
| VUNTDTL_VIEW.CTLGRP | inventory_view.lotnum | HIGH | Control Group = batch/lot number |
| VUNTDTL_VIEW.CASQTY | CALCULATED | — | `CASE WHEN ISNULL(untcas,0)=0 THEN untqty ELSE untqty/untcas END` |
| ITEM_CONFIG.LAYPUL | CALCULATED | — | `untpal / untlay` (layers per pallet) via prtftp_view subquery |
| ITEM_CONFIG.CASLAY | CALCULATED | — | `untlay / untcas` (cases per layer) via prtftp_view subquery |
| ITEM_CONFIG.DEFAULT_CONF | ABSENT | — | No PrIME equivalent. Removed from translated SQL |
| UNITLD_VIEW.ORDNUM | shipment_line.ordnum | HIGH | Via: `inventory_view.ship_line_id → shipment_line.ship_line_id → ordnum` |

### New Learnings (55–62)

| # | Learning | Severity |
|---|---|---|
| 55 | ORACLE_RTCIS..LIVE3. is a linked-server prefix → strip entirely, replace table with PrIME dbo. equivalent | Critical |
| 56 | Vendor column names may have table-name prefixes (UNTDTL_ULID = ULID, UNTDTL_ITMCOD = ITMCOD) → strip prefix for column lookup | Important |
| 57 | UNTDTL_VIEW and VUNTDTL_VIEW both map to inventory_view (same as AS_RTCIS_UNTDTL) | Critical |
| 58 | DEFAULT_CONF='Y' has no PrIME equivalent (verified: 0 columns matching def*/conf*/default* on prtmst). Remove from translated SQL | Important |
| 59 | CASQTY in UNTDTL context = untqty/untcas (total units ÷ units-per-case) with LEFT JOIN to prtftp_view for untcas | Critical |
| 60 | ORDNUM on inventory_view: does NOT exist as direct column. Must JOIN: inventory_view.ship_line_id → shipment_line.ship_line_id → shipment_line.ordnum. 68.5% population rate (31.5% have NULL ship_line_id) | Critical |
| 61 | COUNT(*) needs AS cnt alias for PowerShell validation (anonymous columns cause PS OrderedDictionary conversion error) | Minor |
| 62 | Mixed Italian/SQL vendor input: interpret business intent before translating (e.g. "ITMCOD=valore UNTDTL_ITMCOD da UNTDTL_VIEW" = subquery) | Important |

### ORDNUM JOIN Path (NEW — April 2026)

```
inventory_view.ship_line_id → shipment_line.ship_line_id → shipment_line.ordnum
```
- **LEFT JOIN** required (not INNER) — only 68.5% of inventory has ship_line_id
- Items not allocated to a shipment → ordnum = NULL
- `invdtl` does NOT have ordnum either — only accessible via shipment_line

### Full Label Query Pattern with ORDNUM
```sql
SELECT lodnum, a.prtnum, b.lngdsc, c.alt_prtnum AS CSGTIN,
       a.lotnum, a.untqty, a.ftpcod,
       sl.ordnum
FROM dbo.inventory_view a
LEFT JOIN dbo.prtdsc b
  ON concat(a.prtnum,'|',a.prt_client_id,'|',a.wh_id) = b.colval
  AND b.locale_id = 'US_ENGLISH'
LEFT JOIN dbo.alt_prtmst c
  ON a.prtnum = c.prtnum AND a.prt_client_id = c.prt_client_id
  AND c.alt_prt_typ = 'GTIN' AND c.uomcod = 'CS'
LEFT JOIN dbo.shipment_line sl
  ON a.ship_line_id = sl.ship_line_id
WHERE lodnum = '<SSCC>'
```

---

## 18. PIPELINE ARCHITECTURE — Single-Auth Retry (April 2026)

### Problem Solved
Each `subprocess.run()` call to PS1 triggers a new AAD Interactive login prompt. With 3 retries, users were prompted up to 4 times.

### Solution: Retry Within PS1 Connection

```
Python (1 subprocess call) → PS1 opens ODBC connection (1 auth prompt)
                               ↓
                          Validate all queries → report failures
                               ↓
                          Call _auto_fix_between_retries.py (Python)
                               ↓
                          Re-validate failed only (same connection, no auth)
                               ↓
                          Repeat up to MaxRetries → close connection
```

**Files:**
- `SQL_Translations/_prime_validate.ps1` — Single-connection PS1 with internal retry loop
  - Parameters: `-MaxRetries 3`, `-AutoFixScript path`, `-SkipDBA` (for retry mode)
  - Opens ONE ODBC connection, keeps it open for all retries
  - Skips already-passed queries on retry
  - Calls Python auto-fixer between retries
- `SQL_Translations/_auto_fix_between_retries.py` — Called by PS1 between retries
  - Reads validation errors from output JSON
  - Applies `_auto_fix_sql()` fixes from _translate_universal.py
  - Writes updated SQL back to input JSON
  - Exit 0 = fixes applied, Exit 1 = nothing to fix (stops retries)
- `SQL_Translations/_translate_universal.py::run_live_validation()` — Calls PS1 exactly once
  - Passes `-MaxRetries`, `-AutoFixScript` to PS1
  - 600s timeout to accommodate all retries
  - Syncs auto-fixed SQL back into translations after completion

### Auto-Fix Patterns (in `_auto_fix_sql()`)
| Error Pattern | Fix |
|---|---|
| `Invalid column name 'X'` | Remove column or apply column mapping |
| `Invalid object name 'dbo.X'` | Check TABLE_MAP, try alternate names |
| `Ambiguous column name 'X'` | Add table alias prefix |
| `Conversion failed nvarchar→int` | Remove CAST/CONVERT wrappers |
| DEFAULT_CONF | Remove from WHERE clause entirely |
| CASQTY/LAYPUL/CASLAY in wrong context | Rewrite as calculated expression |
| COUNT(*) without alias | Add `AS cnt` |
| ORACLE_RTCIS..LIVE3. prefix | Strip linked-server prefix |

---

## 19. VALIDATION REPORT WORKFLOW (April 2026)

### HTML Validation Report for Vendor Queries
**File:** `SQL_Translations/vendor_queries_validated_20260408.html`

Structure (5 tabs):
1. **Summary** — overview, all-queries status table, live validation evidence (11 checks)
2. **Q1–Q3** — per-query tabs with:
   - Original RTCIS SQL
   - Translated PrIME 2022 SQL
   - Gap warnings (e.g. DEFAULT_CONF)
   - Placeholder values table (must-replace before use)
   - Line-by-line element validation table (RTCIS→PrIME, confidence, KB citation, live evidence)
   - Actual Athens query results (real SSCC data)
3. **ORDNUM Answer** — complete answer with JOIN path, KB citations, 7 live checks, 68.5% population explanation

### Live Query Runner
**File:** `SQL_Translations/_run_all_vendor_live.ps1`
- Runs all translated queries against Athens Replica with a real SSCC
- Single connection, all 4 queries in sequence
- Results displayed with row counts and key data

### Placeholder Convention
Translated queries use placeholders that must be replaced before production use:
- `'SSCC Letto'` → actual scanned SSCC barcode (18-digit)
- `'WMD1'` → actual Pomezia warehouse ID
- `'----'` → Pomezia prt_client_id (verify with WMS team)
- `'<SSCC rilevato>'` → same as 'SSCC Letto' (Italian variant)
- `'US_ENGLISH'` → may need Italian locale at Pomezia

---

## 20. ATHENS REPLICA — Live Data Reference (April 2026)

| Item | Value |
|---|---|
| Server | <replica-host> |
| Database | ATHENS_REPLICA |
| Auth | ActiveDirectoryInteractive, UID=<user>@<company> |
| wh_id | WMD1 |
| prt_client_id | ---- |
| Total inventory rows | 80,802 |
| Rows with ship_line_id | 55,336 (68.5%) |
| Test SSCC | 00352012768840748418 |
| Test item | 80858655 (LENOR OCEAN BREEZE 6X1722) |
| Test GTIN | 8700216751100 |
| Test ordnum | 6277923359 (as of 2026-04-08) |

---

## 21. POMEZIA RTCIS — Source Database Reference (April 2026)

| Item | Value |
|---|---|
| Server (Prod) | <replica-host> |
| Server (Non-Prod) | <replica-host> |
| Database | POMEZIA |
| Auth | ActiveDirectoryInteractive, UID=<user>@<company> |
| Schema | esiliv1 / live3 |
| Purpose | Cross-validate RTCIS filter values, verify location names, actcod existence, source row counts |

**Use cases:**
1. Verify that hardcoded filter values (location names, actcod values, user IDs) actually exist in Pomezia RTCIS
2. Compare RTCIS row counts with PrIME translated query results
3. Validate that UNMAPPED actcod values (CUTSUB, LINUSE) are real Pomezia operations
4. Check original RTCIS query results to confirm business intent before translating

---

## 22. TARGET DATABASE RULE — _REPLICA vs _RTDS (Learning #61)

**⚠️ CRITICAL:** PrIME translated queries MUST target `SITENAME_REPLICA` databases, **NEVER** `SITENAME_RTDS`.

| Database Suffix | Has inventory_view? | Use for PrIME queries? |
|---|---|---|
| `_REPLICA` (e.g. `ATHENS_REPLICA`, `POMEZIA_REPLICA`) | ✅ YES | ✅ YES — always use this |
| `_RTDS` (e.g. `ATHENS_RTDS`, `POMEZIA_RTDS`) | ❌ NO | ❌ NEVER |

**Key views only in _REPLICA:** `inventory_view`, `prtdsc`, `alt_prtmst`, `vc_hazmat`, `adrmst`, `shipment_line`, `shipment`, `stop`

**Source:** Expert confirmation 2026-04-10, validated by live queries on ATHENS_REPLICA.

---

## 23. LEARNINGS INDEX — April 2026 Session (Learnings #55–#67)

| ID | Date | Category | Summary |
|---|---|---|---|
| 55 | 2026-04-10 | actcod-mapping | Filter value consistency: ⚡ proposed values MUST match SQL |
| 56 | 2026-04-10 | actcod-mapping | QASTAT='RL' → invsts='U' (NOT 'RL'). Bug fixed in Q28/Q29 |
| 57 | 2026-04-10 | pattern | ⚡ sections must document ALL site-specific filter values (47 added) |
| 58 | 2026-04-10 | pattern | DTLTYP='F' → oprcod='F' (same value). NOT ITMCLS |
| 59 | 2026-04-10 | column-fix | Silently dropped ITMCLS='F' filter in Q28/Q29 — restored as typcod='FERT' |
| 60 | 2026-04-10 | schema-quirk | Pomezia RTCIS database now accessible for cross-validation |
| 61 | 2026-04-10 | infrastructure | **Target DB must be SITENAME_REPLICA** (not _RTDS) — inventory_view only exists in _REPLICA |
| 62 | 2026-04-10 | bug-pattern | **Self-join alias tautology**: `fv_.prtnum = fv_.prtnum` always TRUE — must reference outer alias. Fixed Q27/Q31/Q34 |
| 63 | 2026-04-10 | join-pattern | **prtdsc join key**: `concat(prtnum,'|',prt_client_id,'|',wh_id)` — NOT hardcoded `'|----'`. Fixed Q4/Q5/Q14/Q20 |
| 64 | 2026-04-10 | join-pattern | **CSTNAM path**: shipment_line → shipment (ship_id) → adrmst (rt_adr_id=adr_id) → adrnam. Fixed Q32 |
| 65 | 2026-04-10 | table-mapping | **GTIN**: alt_prtmst (alt_prt_typ='GTIN', uomcod='CS') → alt_prtnum. 14 cols confirmed |
| 66 | 2026-04-10 | table-mapping | **Hazmat/DG**: vc_hazmat.vc_unnum → CASE WHEN NULL THEN 0 ELSE 1 = PITTOGRAMMA. 15 cols confirmed |
| 67 | 2026-04-10 | table-mapping | **Address fields**: adrmst (52 cols) — adrnam, adrcty, adrstc, adrln1, adrpsz, ctry_name |
