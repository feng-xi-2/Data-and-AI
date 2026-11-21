---
title: Table map RTCIS → PrIME 2022
type: entity
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md, raw/schema/verified-mappings.json, raw/kb/RTCIS_DATABASE_REFERENCE.md]
evidence: [results/map_inventory_fields.json]
updated: 2026-10-20
---
# Tables

| RTCIS | PrIME 2022 | Note |
|---|---|---|
| `unitld` (pallet) | `invlod` | ULID20 = LODNUM ([pallet-id](../concepts/pallet-id.md)) |
| `untdtl` (pallet content) | `invsub` + `invdtl` | `invlod→invsub(LODNUM)→invdtl(SUBNUM)`; sum details per key ([grain-and-fanout](../concepts/grain-and-fanout.md)) |
| `AGV_INVENTORY_VIEW` | invlod+invsub+invdtl+prtmst+locmst+aremst | view = unitld/untdtl/ctlgrp/itmmst/locatn + building |
| `itmmst` | `prtmst` | always `AND WH_ID_TMPL = @wh_id` (dual rows) |
| `itmgrp` | `prtfam` + `dscmst` (`COLNAM='prtfam'`) | `dscmst` = code catalogue × locale, keyed (COLNAM, COLVAL, LOCALE_ID) |
| `item_uom` / `item_config` | `prtftp` / `prtftp_dtl` (footprint levels) | 1:n → `OUTER APPLY TOP 1`; `prtftp_view` = shortcut; `untinp` gone → `untlay` |
| `ctlgrp` (lot) | `invdtl.LOTNUM`, `prtlot` | lot status lives on inventory (`INVSTS`) |
| `locatn` | `locmst` + `aremst` + `loc_typ` | 2022: flags moved aremst → locmst / loc_typ |
| `subsit` | `wh` / building (`aremst.BLDG_ID`) | [building-subsit](../concepts/building-subsit.md) |
| `systrn` + `sysdtl` | `dlytrn` (one row per move) | TRNTYP → ACTCOD, no 1:1 |
| `prdlin` / `lindel` | `prdlin_mst` / `wkodtl` (PRCLOC) | |
| `prdque` / `porecipe` | `wkohdr` / `wkodtl` | WKOSTS P/I/C/W |
| `rcphdr` / `rcpexp` / `trukio` / `trailer` / `trklin` | `rcvtrk` / `rcvinv` + `rcvlin` / `trlr` / `trlr` / `carhdr` | TRUKIO → `trlr` (not trlract) |
| `ordhdr` / `orddtl` | `ord` / `ord_line` | no `__b` suffix; ORDDTL→TRUKIO = 5-hop bridge (raw/reference §5) |
| shipment (`shipid`) | `shipment` → `stop.CAR_MOVE_ID` | carrier move, not SHIP_ID |
| pick / setup | `pckwrk_hdr` (LIST_ID, PALLET_ID, WRKREF) + `pckwrk_dtl` (ORDNUM, SHIP_ID…) | `pckwrk_view` fails in wide joins at DE08; `dbo.pckwrk` does not exist |
| `users` | `les_usr_ath` + `adrmst` (FIRST_NAME, LAST_NAME) | |
| `equip` | `vehtyp` + `dscmst 'vehtyp_id'` | different code set |
| `custmr` | `adrmst` via `ord.ST_ADR_ID` | not `cstmst` |
| STKCNT/STKMIS/STKCOR txns | `cnthst` (+ `dlytrn` INVADJ/ADJAPP) | no STKMIS in PrIME |
| item barcode | `alt_prtmst` (`ALT_PRT_TYP`) | discriminated rows |

Full PrIME 2022 data model: `raw/schema/prime-datamodel.json` (7 MB) and `raw/schema/erd-index.json`; column-level
facts: [mappings](../ground-truth/mappings.md).
