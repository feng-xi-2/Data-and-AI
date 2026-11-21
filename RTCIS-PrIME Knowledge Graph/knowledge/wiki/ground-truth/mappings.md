---
title: RTCIS → PrIME 2022 mappings with measured agreement
type: ground-truth
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md, raw/schema/verified-mappings.json, raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md]
evidence: [results/map_inventory_fields.json, results/compare.json, results/compare.csv]
updated: 2026-10-20
---
# Mappings `[DB]` (Euskirchen, measured 2026-10-20)

Agreement = same physical pallet / item / lot / location in RTCIS `EUSKIRCHEN` and PrIME `DE08`
(`tools/map_inventory_fields.py` → `results/map_inventory_fields.json`, 25,388 matched pallet-items;
`tools/compare.py` → `results/compare.json`). Table-level map: [tables](../entities/tables.md). Broader
documented maps (52 tables / 64 columns, Pomezia/Athens): `raw/schema/verified-mappings.json` and
[complete-reference](../sources/complete-reference.md). **When this page and a documented map disagree, this page wins
for Euskirchen** — but re-measure at a new site (sites populate discriminators differently).

| RTCIS | PrIME | Agreement | Tag |
|---|---|---|---|
| ITMCLS `F` / `P` | `prtmst.TYPCOD` `FERT` / `ROH` | 99.9% (10 UNBW, 8 HALB) | MAPPED |
| ITMCOD | `PRTNUM` | 100% | MAPPED |
| ITMGRP | `prtmst.PRTFAM` | 99.9% (`VC_ITMGRP` empty) | MAPPED |
| GRPDSC | `dscmst` prtfam LNGDSC (US_ENGLISH) | 87/93 groups | MAPPED |
| ITMDSC | `prtdsc` (COLNAM `prtnum\|prt_client_id\|wh_id_tmpl`, site row then `----`, locale chain) | 98.8% | MAPPED |
| ITMNUM ("Categorie") | none (15 prtmst columns tested, 0%) | — | `[ELIMINATED]` |
| CTLGRP | `invdtl.LOTNUM` | 98.4% | MAPPED |
| FIFODT | `invdtl.FIFDTE` | 99.5% | MAPPED |
| QASTAT `RL`/`HD`/`QU` | `invdtl.INVSTS` `U`/`B`/`Q` | RL→U 97%, HD→B 88% | MAPPED (code set differs) — [inventory-status](../concepts/inventory-status.md) |
| VNDCOD / VNDLOT | `LEFT(SUP_LOTNUM,4)` / `SUBSTRING(SUP_LOTNUM,5,100)` | 100% | MAPPED (Euskirchen convention) |
| `SUPNUM` | 10-digit SAP vendor, **not** VNDCOD | 0/181 | — |
| PONUMB (lot PO) | none populated at DE08 | — | `[ELIMINATED]` (DEV data) |
| CASQTY | `FLOOR(UNTQTY / receiving-level UNTQTY)` (`prtftp_dtl RCV_FLG=1`), zero fallback, `numeric(22,0)` | 94% (85% with `UNTCAS`); R01 92%, R16 100% after FLOOR | MAPPED + DEVIATION from OBS6 — [receiving-uom](../concepts/receiving-uom.md) |
| UOM (WHSFLG) | receiving `UOMCOD` (`RCV_FLG=1`) | P items 100% (711/711); FP `IT`→`CS` 50% | MAPPED |
| ULPALL | `invdtl.FTPCOD` | 90% | MAPPED |
| u_height (cm; +15 if PALFLG) | pallet-level `prtftp_dtl.HGT` (`PAL_FLG=1`), cm, base included; `<= 1` = placeholder → NULL | FERT: PL = LY × layers + 15 on 75%; DE08 ROH all placeholders | `[INFERRED]` — [pallet-dimensions](../concepts/pallet-dimensions.md) |
| item_config udepth / uwidth (cm) | pallet-level `WID` / `LEN` (cm, orientation swapped) | 17,119/20,257 | MAPPED |
| locatn count_itmcls | area infix `FP`→F, `PM`/`RP`→P, else CL rule (stock class of location, else dominant class of area) | 98.8% where RTCIS set | MAPPED |
| SUBSIT `0` (DE07) / `1` (DE08) | `aremst.BLDG_ID` `B1` / `B2` | 99.2% / 98.9% | MAPPED — [building-subsit](../concepts/building-subsit.md) |
| BLDING `0001`…`0015` | `'00' + LEFT(ARECOD,2)` | 43% (100% on packaging R16) | `[INFERRED]` |
| PIKZON X1–X5 / P6 / P7 / 2P–4P / H2 | `LEFT(ARECOD,2)` 01–05 / 06 / 07 / 12–14 / 15 | 95–100% per zone | MAPPED |
| ZONCOD | `locmst.ARECOD` (different code set) | — | MAPPED (vocabulary) |
| LOCATN | `STOLOC` (same names; CIMAT → CIMATSTO) | names 100% | MAPPED |
| locatn ARECOD RA/RO/CP | loc type `RSTO`; area type SUBP=CP, PAPA/LEDO=RA, HOFF/MIXE=RO, PSTO/LOAP/FUPA = RA+RO | — | `[PARTIAL]` |
| locatn COUNT_ITMCLS | see count_itmcls row above | | |
| CYCDAT | `locmst.CNTDTE` | DEV counts differ | `[INFERRED]` |
| PRE/POST_COUNT_OK | none | — | `[ELIMINATED]` |
| ULIN% line location | destination `loc_typ.LOC_TYP_CAT='PROD'` (PLIN/PSTD/PSTA) | 43/43 ULIN map (ULIN82→EU82, ULINCV→SLCV) | MAPPED — [line-supply](../concepts/line-supply.md) |
| DEPSUL / LINUSE / CASXFR | `dlytrn` into a PROD location | | MAPPED (event) |
| MANLID (return from line) | `dlytrn` out of PROD into non-PROD | not observable at DE08 | `[INFERRED]` |
| PRDORD | latest `pckwrk_dtl.WKONUM` on the pallet; `SUBSTRING(4,9)` only for `000%` 12-char | separate number ranges on DEV | `[INFERRED]` |
| rcphdr BOLNUM (Ladungsnummer) | `rcvinv.WAYBIL` | 88/88 DE08, 703/703 Athens | MAPPED |
| DELVID | `rcvinv.INVNUM` (SAP inbound delivery) | DEV data | `[INFERRED]` |
| APTDAT / ASGDAT | `rcvtrk.EXPDTE` / `trlr.ARRDTE` (outbound: `appt.start_dte` via `trlr.appt_id`) | | `[INFERRED]` |
| TRKNAM | `carhdr.CARNAM` | | MAPPED |
| `BUOMDEN/BUOMNUM` 'SU' factor | no `SU` level in PrIME | — | `[ELIMINATED]` |
| fifo_window (group) | `prtmst.FIFWIN` per part, 30 everywhere at DE08 | 45/93 | `[ELIMINATED]` |
| shipid | `stop.CAR_MOVE_ID` via `shipment.STOP_ID` | expert OBS2 | MAPPED `[EXPERT]` |
| setup (settyp / setup_id) | list pick `pckwrk_hdr.LIST_ID`; `DENSE_RANK() OVER (PARTITION BY ORDNUM ORDER BY LIST_ID)`, zero-padded | 422/422 EUS orders | MAPPED `[EXPERT]` |
| GTIN | `alt_prtmst.ALT_PRTNUM` where `ALT_PRT_TYP='GTIN'`, UOM = receiving UOM | expert OBS1 | MAPPED `[EXPERT]` |
| TRUKIO | `trlr` (not `trlract`) | expert correction | MAPPED `[EXPERT]` |
| customer name (`custmr.CSTNAM`) | `adrmst.ADRNAM` via `ord.ST_ADR_ID` (not `cstmst`) | KB learning 64 | MAPPED `[DOC]` |
| STKCNT/STKMIS/STKCOR | `cnthst` (+ `dlytrn` INVADJ/ADJAPP); PrIME has no STKMIS (miss = UNTQTY ≠ CNTQTY) | DEV counts | `[INFERRED]` |
| TRNTYP (CASPIK, CASXFR …) | `dlytrn.ACTCOD` — **no 1:1**; keep RTCIS intent, verify per site | | `[INFERRED]` `[DOC]` |

## Contradictions
- 2026-10-20 (earlier the same day) u_height was declared `[ELIMINATED]` after testing `HGT*100`; PrIME dims are cm —
  superseded by the pallet-level HGT mapping above ([pallet-dimensions](../concepts/pallet-dimensions.md)).
- OBS6 (expert) says `UNTQTY/UNTCAS`; DB shows the receiving-level factor reproduces CASQTY on 94% vs 85% → declared
  DEVIATION; revert by replacing receiving `UNTQTY` with `d.UNTCAS`.
- Line filter `TO_ARECOD IN prdlin_mst.PRCARE` (2026-10-08) superseded by `LOC_TYP_CAT='PROD'` (2026-10-14).
