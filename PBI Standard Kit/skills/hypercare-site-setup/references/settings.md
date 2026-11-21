# Site settings reference (config/site_config.csv)

Columns marked **input** come from the Sites tab of the inputs file. **profiled** columns come from `tools/profile_site.py` (rule + evidence). **site** columns need site knowledge (LOW confidence; a safe default is used).

| Setting | Source | Meaning | Evidence / probe (S = schema, last 14 d) |
|---|---|---|---|
| WMS_Version | profiled | PrIME 2014 (`prodwms`) or 2022 (`dbo`) | `sys.objects` schema of `dlytrn` |
| WH_ID | input / profiled | warehouse id | `SELECT wh_id, COUNT(*) FROM S.dlytrn ... GROUP BY wh_id` → the busiest. A replica can hold 2 warehouses (Jakarta ID01 / ID12) |
| UTC_Offset_h, Shift*_Start, Hypercare_Start | input | site clock and report day | site |
| ShiftDay_Start_Min | site | minute the report day starts (BD 390 = 06:30) | default Shift1_Start × 60 |
| Has_Production + PROD_* + Prod_Model + OPR_LTA_STORE | profiled | how a produced pallet is counted | work-order receipts `actcod='RCV' AND oprcod='UID'` with a `wkohdr.wkonum = frstol` (**WO** model) vs pallets leaving `LT%` / `LTA%` locations (**LTA** model). Token templates: `config/production_models.csv` |
| LOC_LTA | profiled | line take-away lanes | `locmst stoloc LIKE 'LT%'`; LTA% when every LT location starts with LTA |
| LOC_PROD_SUPPLY | profiled | line supply locations | moves to `PL%` / PL% locations in `locmst` |
| Has_LevelA, AREA_LEVEL_A_PICK, LOC_LEVEL_A | profiled | ground-level pick faces (locations ending in A) | `pckwrk_view` srcare with the most picks from `RIGHT(srcloc,1)='A'` (at least 20 picks and 5%); pattern = the dominant first 2 characters + `%A` |
| AREA_RDTS | profiled | RF / forklift "in transit" area, a **LIKE pattern** | `fr_arecod LIKE 'RDT%'`: one area → exact; several areas (each at least 1%) → prefix + `%` (Jakarta `RDTS%`) |
| Has_HOFF, LOC_HOFF_IN / OUT | profiled | production hand-off lanes | moves into `HO%IN` / out of `HO%OUT`, else a used `X-IN` / `X-OUT` pair (Akashi CSTCO-IN/OUT) |
| LOC_PROBLEM | profiled | problem locations | moves / `locmst` for `PROB%`, `PRBL%` |
| LOC_RETURN | profiled | return locations | `RTN%`, `RER%`, `%RET%` |
| AREA_RCV_STAGE, AREA_RCV_DOCK | profiled | where received pallets land | `to_arecod` of `RCV` / `ASN_*` (RCST% preferred, RDT areas ignored) |
| LOC_DOOR_PATTERN | profiled | door locations pallets are moved to before loading (Shipped Pallet LOAD step) | moves / `locmst` for `C[0-9][0-9][0-9]`, `DOOR%` |
| FG_PRTNUM_LIKE | profiled | finished-goods part numbers | first characters of the parts loaded on trailers (`tostol LIKE 'TRL%'`), then `wkohdr` parts, then inventory (LOW) |
| PRTDSC_LOCALE | profiled | part description language | `prtdsc` rows by locale; US_ENGLISH when it covers at least 90% |
| USR_EXCLUDE | profiled + site | users kept out of productivity | SUPER, NOUSER + users above 5 × ROBOT_TXN_PER_HOUR pallet transactions per hour (interfaces); ask the site about users above 1 × |
| ZONES_EXCL_PICK / BIN | site | storage zones not counted (RPM, QA) | site; default `'~NA~'` (none) |
| SAP_Plant, Has_SAP_Prod, SAP_PALLET_UOM | input / site | SAP production from CDL | plant from the inputs file; UoM A1 for most sites (Minhang P2) |
| Has_SAP_Plan, Has_RPM_Master, LOC_PROD_CHECKIN, CTMZ_LINE, LOC_EOL* | site | BD-only line features | OFF until the site provides them |
| Gateway_Connection | rule | gateway data source name | `MI-<database>-PROD-FULL-PaaS-ADHOC` |
| Config_Status | tool | NEW → AUTO-PROFILED → VALIDATED (after the site confirms) | |

## Freshness / history checks
- `SELECT MIN(trndte), MAX(trndte) FROM S.dlytrn WHERE wh_id = '<WH>' AND trndte >= <14 d before the newest>`
  - under 72 h of activity → the site is not live; absent features are "confirm", not OFF.
- Replica lag: see the `data-replica-latency` skill (HVR watermark per engine).

## Known site facts (31-Oct-2026)
- **Akashi:** `dlytrn` holds only 30-Oct 08:47–18:05 (inventory load `IDNTFY` into ASRS). No production yet → re-profile after go-live.
- **Jakarta:** the PROD replica runs only DC ID01 (no production); production ID12 is on NON-PROD only. Its RF areas are RDTS000005/3/1, so the setting is `RDTS%`.
- **Minhang:** very low volume (about 19.5k `dlytrn` rows since May 2025); the replica was **emptied on 31-Oct between 20:25 and 21:20** (`dlytrn` 12 rows, `wkohdr` 0) - ask the replica owner. For the site to confirm: FG pattern, doors (yard P1DCK1-4, no C### locations), and user FE2462 (9.6k pallet transactions/h).
- **Xiqing:** for the site to confirm: Level A also includes the 40… / 61… / 50… pick faces ending in A (config `A0%A` covers 61%); FG = 8% on trailers.
