---
title: "Source: CL (countable location) and IRA reference queries"
type: source
status: documented
sources: [raw/queries/cl-ira/CL_LATEST_RTCIS.sql, raw/queries/cl-ira/CL_LATEST_PRIME2022.sql, raw/queries/cl-ira/CL_LATEST_PRIME2014.sql, raw/queries/cl-ira/COUNT_COVERAGE_KRI_3VERSIONS.sql, raw/memories/prime_ira_london_aligned.md, raw/memories/ira_column_standard.md]
evidence: [results/compare.json]
updated: 2026-10-20
---
# Source: CL and IRA reference queries

Production inventory-accuracy queries maintained per WMS engine (copied from `SQL_Translations/CL_latest/`). They are
the house reference for **location** and **count** logic on all three engines.

| Reference rule | RTCIS | PrIME 2022 | Used in this wiki |
|---|---|---|---|
| Countable locations | `locatn.arecod IN ('CP','RA','RO')`, not `AL%`, zone in `zondtl` | `loc_typ.LOC_TYP_CAT='STORAGE' AND LOC_TYP<>'ASRS'` (2022 replaced aremst flags) | [R17](../queries/R17.md) `RSTO` covers the same 25,580 RTCIS locations |
| Last count date | `greatest(STKCNT/STKMIS systrn date, locatn.cycdat)` | `locmst.CNTDTE` | R17 keeps the original (cycdat only) |
| Item class of a location | `count_itmcls`, else dominant class of the zone | stock class of the location (`invsum`), else dominant `TYPCOD` of the area; FERT→F, ROH/HALB→P | R17 fallback → 98.8% where RTCIS set |
| Plant | `subsit.plant_code`, default plant | `prt_client_id`, else POLDAT `VC-PRIME-SAP / PLANT_CD` (LEN 4) | — |

IRA learnings (raw/memories/prime_ira_london_aligned.md): one row per count transaction (no rn=1 over history);
`row_number()` + tie-breaker instead of `rank()` (hidden ties under DISTINCT); POLDAT correlated on wh_id (3-plant
fan-out at Lima); AREA CODE = `dscmst` SHORT_DSC; POSTCNT = NULL in PrIME. R17 already follows the area-code and
NULL-flag rules; its new ranking uses `ROW_NUMBER` with a tie-breaker per the IRA fix D.
