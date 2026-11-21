---
title: Data facts measured in the replicas
type: ground-truth
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/hvr_latency_prime2022.md, raw/kb/ALL_LEARNINGS.md]
evidence: [results/map_inventory_fields.json, results/compare.json, results/probe_casqty_height.json, results/probe_sap_pallet_height.json]
updated: 2026-10-20
---
# Data facts `[DB]`

| # | Fact | Consequence | Evidence |
|---|---|---|---|
| 1 | PrIME `*_REPLICA.dbo.*` and RTCIS `live3.SYSTRN/SYSDTL` are **cross-database synonyms**; `INFORMATION_SCHEMA` and `sys.columns` return nothing | Use `SELECT TOP 0 * FROM x` (`tools/discover.py`); for metadata use `sys.objects type SN` or the base DB | [synonyms-facades](../concepts/synonyms-facades.md) |
| 2 | RTCIS `EUSKIRCHEN.live3` facade is **trimmed** (misses SETTYP, KITID…) | Read base tables from `[EUSKIRCHEN_simp].live3`; `AGV_INVENTORY_VIEW`/`USERS` only in `EUSKIRCHEN.live3` | same |
| 3 | Collation RTCIS `SQL_Latin1_General_CP850_BIN2`, PrIME `SQL_Latin1_General_CP1_CI_AS` | Temp-key joins across engines need `COLLATE DATABASE_DEFAULT` (else error 468) | Euskirchen Q15–Q18 |
| 4 | RTCIS `AGV_INVENTORY_VIEW.ULID20` = PrIME `invlod.LODNUM` (20 chars); raw `ULID` is 19 (no GS1 check digit) | `LEFT(LODNUM,19) = ULID`; length histogram first | [pallet-id](../concepts/pallet-id.md) |
| 5 | Replica `GETDATE()` is UTC; WMS dates are site-local | `CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime)` | [site-local-time](../concepts/site-local-time.md) |
| 6 | RTCIS replica keeps **~40 days** of `systrn/sysdtl` (2026-09-10 → 2026-10-20 at test) | History windows > 40 d cannot be baselined | R11 (33 d), R12 (90 d) |
| 7 | HVR lag at DE08 ~10 s, not blocked (2026-10-14) | Check `EUSKIRCHEN_RTDS.hvr.hvr_is*` `trailer_cap_begin` before blaming SQL | `raw/memories/hvr_latency_prime2022.md` |
| 8 | DE08 server is **DEV-FULL**: inventory/master data migrated from RTCIS (comparable pallet by pallet); work orders (`000920…`, `INTEU…`) and receipts (`TEST…`) are test data | Value comparison only on inventory/master data; orders/receipts graded B | 0/66 DE08 orders in RTCIS systrn |
| 9 | DE08 has almost no outbound work (~35 pick rows, 0 LIST_ID) and 2 line-supply moves ever | Use Athens / Crailsheim as witness; DE08 zero rows ≠ defect | R08–R12 |
| 10 | `prtmst` is **dual-row per part** (`WH_ID_TMPL` = site and `----`) | Always `AND p.WH_ID_TMPL = @wh_id`; blind join doubles rows | [grain-and-fanout](../concepts/grain-and-fanout.md) |
| 11 | PrIME splits one pallet+item+lot across 2 `invdtl` rows on **51 DE08 keys** (RTCIS 0) | Sum details per key first (OBS8) | `results/compare.json` R07 |
| 12 | `STKUOM` is a 1/1000 sub-unit for metric packaging (2M/G/MM/ML on 233 items) | Use receiving level `prtftp_dtl RCV_FLG=1` | [receiving-uom](../concepts/receiving-uom.md) |
| 13 | `rcvtrk.TRKREF` is the **supplier name** (one value → 729 rows at Athens); load ref = `rcvinv.WAYBIL` (= TRKNUM before `~`, 88/88 DE08, 703/703 Athens) | Measure, don't name-match | R05/R06 |
| 14 | `SUP_LOTNUM` = RTCIS VNDCOD (4 chars) + VNDLOT (6,992/6,992 DE08); `SUPNUM` = 10-digit SAP vendor (0/181) | `LEFT(SUP_LOTNUM,4)` / `SUBSTRING(SUP_LOTNUM,5,100)`; empty at Athens | R01/R16 |
| 15 | `pckwrk_view` inside a wide join fails at DE08 (Msg 8622 plan hints) | Use explicit `pckwrk_hdr` + `pckwrk_dtl` join on WRKREF; `inventory_view` is fine | Euskirchen Q01 |
| 16 | GTIN is a **row** in `alt_prtmst` (`ALT_PRT_TYP='GTIN'`: 32,920 DE08 / 41,807 WMD1) | Select by receiving UOM, never pin `'CS'` (pinned: 64.8% populated; fixed: 98.4%) | [prime-anti-patterns](../learnings/prime-anti-patterns.md) |
| 17 | `prtdsc` keyed by `COLNAM='prtnum\|prt_client_id\|wh_id_tmpl'` + LOCALE; pinning `GERMAN` blanked 50.1% at Euskirchen | Caller `@locale` + fallback chain via `OUTER APPLY TOP 1 … ORDER BY CASE` | same |
| 18 | PrIME 2022 `AREMST` has no FWIFLG (moved to `LOC_TYP`); some sites have `'X'` and `'X '` keys | RTRIM area keys | `raw/memories/timbr_api.md` |
| 19 | RTCIS quantities `untdtl.casqty`, `systrn.trnqty`, `item_config.caslay`, `item_uom.u_height` are **numeric(22,0)**; 0 fractional casqty rows of ~100k; metric packaging is truncated (4250.4 → 4250 on 549 pallets, never rounded) | PrIME quantity outputs use `FLOOR(...)` cast `numeric(22,0)` | `results/probe_casqty_height.json` |
| 20 | PrIME `prtftp_dtl` LEN/WID/HGT are **cm**; pallet HGT includes the ~15 cm base; DE08 packaging footprints are all `NONE` with 1×1×1 placeholders | [pallet-dimensions](../concepts/pallet-dimensions.md) | same |
| 21 | 314 of the 315 R01 pallets whose quantity still differs had RTCIS transactions after the DE08 load (310 RTCIS lower = consumed) | Snapshot, not mapping | R01 compare |
| 22 | Receipt door = `trlr.YARD_LOC` (DE08 DOOR16/17, loc type RSDK; set on 17/50 DE08, 12/578 Athens receipts). `trlr.STOLOC` is the trailer's own location (= trailer id, type DSPCH) | R05/R06 LOCATN | results/field_check.json |
| 23 | `rcvinv.PO_NUM` empty on 0/93 DE08 receipts (and Athens) — PrIME receipts carry no PO | R05/R06/R15/R16 PO = NULL | results/probe_empty_fields.json |
| 24 | `invlod.LSTDTE` set on 303/97,793 DE08 pallets (only after a move); `ADDDTE`/`LAST_UPD_DT` ~100%. No PrIME date equals RTCIS ctrl_date on the same pallet (7/4,659) — DE08 dates are load dates | R16 ctrl_date = COALESCE(LSTDTE, ADDDTE) | results/probe_field_gaps.json |
| 25 | `locmst.CNTDTE` set on 72/40,110 DE08 locations, none RSTO; `rplcfg` pick faces on 72 locations; `wkodtl.SUP_LOTNUM` on 5/1,057 work-order lines; `invhld` 0 rows | R17 count/pick-face fields, R03 vendor, R14 hold date empty or differ | results/probe_empty_fields.json |
| 26 | No PrIME zone column reproduces RTCIS `zoncod` (best MOV_ZONE_ID purity 0.77 over 202 zones). RTCIS service blocks/remarks (serflg/serflg_commnt) not migrated; USEFLG 0 → RTCIS Y on 81% | R01 ZONCOD, R17 serflg | results/probe_field_gaps.json |
| 27 | Of 24,667 same pallets, 11,079 same location; 11,142 differ because the RTCIS CIMAT automated-store bin does not exist as a PrIME location; 1,692 real moves | R01/R07 LOCATN | results/probe_field_gaps.json |
| 28 | RTCIS warehouse unit = PrIME receiving level on 100% packaging and 86% FERT items (stock unit 58%); 1,568 FERT items are IT in RTCIS but CS in PrIME. DE08 `dscmst` GERMAN prtfam text = English (87/92 vs 87/93) | R07/R14 unit, R13 grpdsc | results/probe_unit_locale.json |

## Contradictions
- Older KB pages say `prt_class_name` holds item class; it is empty at Athens — use `prtmst.TYPCOD` (expert correction, raw/reference §2).
- `raw/memories/euskirchen_rtcis_prime2022.md` (2026-10-08) said the line filter is `TO_ARECOD IN prdlin_mst.PRCARE`; superseded 2026-10-14 by location type `PROD` ([line-supply](../concepts/line-supply.md)).
