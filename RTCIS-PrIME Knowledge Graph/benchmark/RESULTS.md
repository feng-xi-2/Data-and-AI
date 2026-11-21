# Benchmark results

Run 2026-11-21 09:43. Gold = the database engines (plan + result-set lineage); see tools/benchmark.py.

## T1 Entity recognition (SQL text -> tables / columns)

| side | entity | P | R | F1 | tp / pred / gold |
|---|---|---|---|---|---|
| rtcis | tables | 0.94 | 0.79 | 0.859 | 79 / 84 / 100 |
| rtcis | columns | 0.875 | 0.786 | 0.828 | 335 / 383 / 426 |
| prime | tables | 1.0 | 1.0 | 1.0 | 123 / 123 / 123 |
| prime | columns | 0.991 | 0.963 | 0.977 | 543 / 548 / 564 |

## T2 Graph build (Text2KGBench metrics)

| stage | relation | P | R | F1 | OC | SH | RH | OH |
|---|---|---|---|---|---|---|---|---|
| extractor | READS | 0.976 | 0.906 | 0.94 | 1.0 | 0.0 | 0.0 | 0.0 |
| extractor | READS_COLUMN | 0.943 | 0.887 | 0.914 | 1.0 | 0.0 | 0.0 | 0.005 |
| extractor | DERIVED_FROM | 0.849 | 0.555 | 0.671 | 1.0 | 0.0 | 0.0 | 0.0 |
| extractor | ALL | 0.94 | 0.847 | 0.891 | 1.0 | 0.0 | 0.0 | 0.004 |
| graph | READS | 0.976 | 0.906 | 0.94 | 1.0 | 0.0 | 0.0 | 0.0 |
| graph | READS_COLUMN | 0.948 | 0.887 | 0.916 | 1.0 | 0.0 | 0.0 | 0.0 |
| graph | DERIVED_FROM | 0.849 | 0.555 | 0.671 | 1.0 | 0.0 | 0.0 | 0.0 |
| graph | ALL | 0.943 | 0.847 | 0.892 | 1.0 | 0.0 | 0.0 | 0.0 |

`extractor` = before the catalog gate, `graph` = what was loaded. OC/SH/RH/OH as defined in Text2KGBench.

## T3 Conversion lookup on Cosmos (RTCIS column -> PrIME 2022 column)

| verdict | fields | share |
|---|---|---|
| direct MAPS_TO hit | 31 | 53% |
| no knowledge | 20 | 34% |
| learned from other converted queries | 6 | 10% |
| knowledge points elsewhere | 2 | 3% |

| query | field | RTCIS (engine) | PrIME 2022 (engine) | graph direct | learned (other queries) | verdict |
|---|---|---|---|---|---|---|
| R01 | CTLGRP | `untdtl.ctlgrp` | `invdtl.lotnum` | invdtl.lotnum | - | direct MAPS_TO hit |
| R01 | ITMCOD | `untdtl.itmcod` | `invdtl.prtnum` | invdtl.prtnum | - | direct MAPS_TO hit |
| R01 | ITMGRP | `itmmst.itmgrp` | `prtmst.prtfam` | prtmst.prtfam | - | direct MAPS_TO hit |
| R01 | LOCATN | `unitld.locatn` | `invlod.stoloc` | - | - | no knowledge |
| R01 | UOM | `item_uom.uom` | `prtftp_dtl.uomcod` | prtftp_dtl.rcv_flg, prtftp_dtl.uomcod | prtmst.stkuom | direct MAPS_TO hit |
| R01 | ZONCOD | `locatn.zoncod` | `locmst.arecod` | locmst.arecod, locmst.sto_zone_id | - | direct MAPS_TO hit |
| R02 | locatn | `sysdtl.locatn` | `cnthst.stoloc` | dlytrn.frstol, dlytrn.tostol | dlytrn.frstol, dlytrn.tostol | knowledge points elsewhere |
| R04 | equip | `equip.equip` | `vehtyp.vehtyp_id` | - | - | no knowledge |
| R06 | bn | `rcphdr.bolnum` | `rcvinv.waybil` | rcvinv.waybil | - | direct MAPS_TO hit |
| R06 | grpdsc | `itmgrp.grpdsc` | `dscmst.lngdsc` | - | dscmst.lngdsc, invlod.stoloc, prtmst.prtfam | learned from other converted queries |
| R06 | ib | `rcphdr.delvid` | `rcvinv.invnum` | rcvinv.invnum | - | direct MAPS_TO hit |
| R06 | it | `rcpexp.itmcod` | `rcvlin.prtnum` | rcvlin.prtnum | - | direct MAPS_TO hit |
| R06 | itmdsc | `itmmst.itmdsc` | `prtdsc.lngdsc` | - | - | no knowledge |
| R06 | itmgrp | `itmmst.itmgrp` | `prtmst.prtfam` | prtmst.prtfam | - | direct MAPS_TO hit |
| R06 | locatn | `trailer.locatn` | `trlr.yard_loc` | - | - | no knowledge |
| R06 | rectyp | `rcphdr.rectyp` | `rcvinv.invtyp` | - | - | no knowledge |
| R06 | rrnumb | `rcphdr.rrnumb` | `rcvtrk.trknum` | - | - | no knowledge |
| R06 | trknam | `trklin.trknam` | `carhdr.carnam` | - | - | no knowledge |
| R06 | trlnum | `trukio.trlnum` | `trlr.trlr_num` | - | - | no knowledge |
| R06 | vndcod | `rcphdr.vndcod` | `rcvinv.supnum` | - | - | no knowledge |
| R07 | Control Group | `untdtl.ctlgrp` | `invdtl.lotnum` | invdtl.lotnum | - | direct MAPS_TO hit |
| R07 | Item Code | `untdtl.itmcod` | `invdtl.prtnum` | invdtl.prtnum | - | direct MAPS_TO hit |
| R07 | Item Description | `itmmst.itmdsc` | `prtdsc.lngdsc` | - | - | no knowledge |
| R07 | Item Group Description | `itmgrp.grpdsc` | `dscmst.lngdsc` | - | dscmst.lngdsc, invlod.stoloc, prtmst.prtfam | learned from other converted queries |
| R07 | Location | `unitld.locatn` | `invlod.stoloc` | - | - | no knowledge |
| R07 | WHSE Unit | `item_uom.uom` | `prtftp_dtl.uomcod` | prtftp_dtl.rcv_flg, prtftp_dtl.uomcod | prtmst.stkuom | direct MAPS_TO hit |
| R10 | CTLGRP | `sysdtl.ctlgrp` | `dlytrn.lotnum` | dlytrn.lotnum | dlytrn.lotnum | direct MAPS_TO hit |
| R10 | ITMCOD | `sysdtl.itmcod` | `dlytrn.prtnum` | dlytrn.prtnum | dlytrn.prtnum | direct MAPS_TO hit |
| R10 | ULID | `sysdtl.ulid` | `dlytrn.lodnum` | dlytrn.lodnum | dlytrn.lodnum | direct MAPS_TO hit |
| R11 | CTLGRP | `sysdtl.ctlgrp` | `dlytrn.lotnum` | dlytrn.lotnum | dlytrn.lotnum | direct MAPS_TO hit |
| R11 | ITMCOD | `sysdtl.itmcod` | `dlytrn.prtnum` | dlytrn.prtnum | dlytrn.prtnum | direct MAPS_TO hit |
| R11 | ULID | `sysdtl.ulid` | `dlytrn.lodnum` | dlytrn.lodnum | dlytrn.lodnum | direct MAPS_TO hit |
| R12 | DELIVERY_DATE | `systrn.sysdat` | `dlytrn.trndte` | - | - | no knowledge |
| R12 | ITMCOD | `sysdtl.itmcod` | `dlytrn.prtnum` | dlytrn.prtnum | dlytrn.prtnum | direct MAPS_TO hit |
| R12 | ITMGRP | `itmmst.itmgrp` | `prtmst.prtfam` | prtmst.prtfam | - | direct MAPS_TO hit |
| R12 | RETURN_DATE | `systrn.sysdat` | `dlytrn.trndte` | - | - | no knowledge |
| R12 | WHSE_UNIT | `item_uom.uom` | `prtftp_dtl.uomcod` | prtftp_dtl.rcv_flg, prtftp_dtl.uomcod | prtmst.stkuom | direct MAPS_TO hit |
| R12 | grpdsc | `itmgrp.grpdsc` | `dscmst.lngdsc` | - | dscmst.lngdsc, invlod.stoloc, prtmst.prtfam | learned from other converted queries |
| R13 | itmgrp | `itmgrp.itmgrp` | `prtfam.prtfam` | - | dscmst.lngdsc, invlod.stoloc, prtmst.prtfam | knowledge points elsewhere |
| R14 | ARTIKEL | `ctlgrp.itmcod` | `invdtl.prtnum` | invdtl.prtnum, prtlot.prtnum | - | direct MAPS_TO hit |
| R14 | BESCHREIBUNG | `itmmst.itmdsc` | `prtdsc.lngdsc` | - | - | no knowledge |
| R14 | LOTNUMMER | `ctlgrp.ctlgrp` | `invdtl.lotnum` | invdtl.lotnum | - | direct MAPS_TO hit |
| R14 | QA_STATUS | `ctlgrp.qastat` | `invdtl.invsts` | - | invdtl.invsts | learned from other converted queries |
| R15 | Control Group | `untdtl.ctlgrp` | `invdtl.lotnum` | invdtl.lotnum | - | direct MAPS_TO hit |
| R15 | First Receipt Date | `ctlgrp.fifodt` | `invdtl.fifdte` | invdtl.fifdte | invdtl.fifdte | direct MAPS_TO hit |
| R15 | Item Code | `untdtl.itmcod` | `invdtl.prtnum` | invdtl.prtnum | - | direct MAPS_TO hit |
| R15 | Item Description | `itmmst.itmdsc` | `prtdsc.lngdsc` | - | - | no knowledge |
| R15 | Item Group Description | `itmgrp.grpdsc` | `dscmst.lngdsc` | - | dscmst.lngdsc, invlod.stoloc, prtmst.prtfam | learned from other converted queries |
| R15 | Location | `unitld.locatn` | `invlod.stoloc` | - | - | no knowledge |
| R15 | QA Status | `ctlgrp.qastat` | `invdtl.invsts` | - | invdtl.invsts | learned from other converted queries |
| R16 | Control Group | `untdtl.ctlgrp` | `invdtl.lotnum` | invdtl.lotnum | - | direct MAPS_TO hit |
| R16 | Item Code | `untdtl.itmcod` | `invdtl.prtnum` | invdtl.prtnum | - | direct MAPS_TO hit |
| R16 | Item Description | `itmmst.itmdsc` | `prtdsc.lngdsc` | - | - | no knowledge |
| R16 | Location | `unitld.locatn` | `invlod.stoloc` | - | - | no knowledge |
| R17 | CYCDAT | `locatn.cycdat` | `locmst.cntdte` | locmst.cntdte | - | direct MAPS_TO hit |
| R17 | itmcod | `locatn.itmcod` | `rplcfg.prtnum` | - | - | no knowledge |
| R17 | locatn | `locatn.locatn` | `locmst.stoloc` | locmst.stoloc | - | direct MAPS_TO hit |
| R17 | serflg_commnt | `locatn.serflg_commnt` | `locmst.lokcod` | - | - | no knowledge |
| R17 | wm_unit | `item_uom.uom` | `prtftp_dtl.uomcod` | prtftp_dtl.rcv_flg, prtftp_dtl.uomcod | prtmst.stkuom | direct MAPS_TO hit |

## Worked conversion plans (live Gremlin)

### R04
- RTCIS tables read: equip
- PrIME 2022 tables proposed by MAPS_TO: dscmst, vehtyp
- PrIME 2022 tables the delivered conversion reads (engine plan): dscmst, vehtyp
- table P/R/F1: 1.0 / 1.0 / 1.0
- expert rules passed: OBS4, OBS5, OBS7, VIEW

### R13
- RTCIS tables read: itmgrp
- PrIME 2022 tables proposed by MAPS_TO: dscmst, prtfam
- PrIME 2022 tables the delivered conversion reads (engine plan): dscmst, prtfam, prtmst
- table P/R/F1: 1.0 / 0.667 / 0.8
- expert rules passed: OBS4, OBS5, OBS7, VIEW, WHT
- finding: NO_SOURCE: NO_SOURCE: PrIME FIFWIN is per part and 30 on every DE08 part; RTCIS keeps a window per item group (e.g. 90).
- finding: NO_SOURCE: NO_SOURCE: as empty note.
- finding: INFERRED: INFERRED: PrIME has no class per item group; derived from the dominant part type of the family. Families without parts come back empty (CHOOKS, COUTSC); EOTEST 

### R16
- RTCIS tables read: agv_inventory_view, ctlgrp, itmgrp, itmmst, subsit
- PrIME 2022 tables proposed by MAPS_TO: aremst, dscmst, invdtl, inventory_view, invlod, invsub, locmst, prtdsc, prtfam, prtlot, prtmst, wh
- PrIME 2022 tables the delivered conversion reads (engine plan): aremst, dscmst, invdtl, invlod, invsub, locmst, prtdsc, prtftp_dtl, prtmst
- table P/R/F1: 0.667 / 0.889 / 0.762
- expert rules passed: FAN, LOC, OBS4, OBS5, OBS6, OBS7, OBS8, VIEW, WHT
- learning: RTCIS `AGV_INVENTORY_VIEW.ULID20` = PrIME `invlod.LODNUM` (20 chars); raw `ULID` is 19 (no GS1 check digit)
- learning: RTCIS `EUSKIRCHEN.live3` facade is **trimmed** (misses SETTYP, KITID…)
- learning: **`subsit='1'` is a site number, not a constant** — parameterise as warehouse.
- finding: NO_SOURCE: NO_SOURCE: as R05 PO.
- finding: NO_SOURCE: NO_SOURCE: as R05 PO.
- finding: SITE_CONVENTION: SITE_CONVENTION: as R01 VNDLOT.

### R01
- RTCIS tables read: agv_inventory_view, cbo_ctlgrp, item_config, item_uom, itmmst, locatn
- PrIME 2022 tables proposed by MAPS_TO: aremst, invdtl, inventory_view, invlod, invsub, loc_typ, locmst, prtdsc, prtftp, prtftp_dtl, prtftp_view, prtmst
- PrIME 2022 tables the delivered conversion reads (engine plan): aremst, invdtl, invlod, invsub, locmst, prtftp_dtl, prtmst
- table P/R/F1: 0.583 / 1.0 / 0.737
- expert rules passed: FAN, OBS4, OBS5, OBS6, OBS7, OBS8, VIEW, WHT
- learning: Of 24,667 same pallets, 11,079 same location; 11,142 differ because the RTCIS CIMAT automated-store bin does not exist as a PrIME location; 1,692 real moves
- learning: Receipt door = `trlr.YARD_LOC` (DE08 DOOR16/17, loc type RSDK; set on 17/50 DE08, 12/578 Athens receipts). `trlr.STOLOC` is the trailer's own location (= trailer id, type DSPCH)
- learning: RTCIS `AGV_INVENTORY_VIEW.ULID20` = PrIME `invlod.LODNUM` (20 chars); raw `ULID` is 19 (no GS1 check digit)
- finding: NOT_CONFIGURED: NOT_CONFIGURED: same cause as the empty note.
- finding: NOT_CONFIGURED: NOT_CONFIGURED: DE08 packaging footprints are 'NONE' with 1x1x1 placeholder dims, so NULL instead of a fake height; Athens (live) fills it on 91% of rows (resul
- finding: SITE_CONVENTION: SITE_CONVENTION: as VNDCOD.

## Natural-language lookups (live Gremlin)

**Which PrIME 2022 table holds the pallet (load) number?**

`g.V().has('pk', 'Column:PrIME2022').has('name', 'lodnum').in('HAS_COLUMN').has('theme', 'Transactional').values('name')`

-> ["pckwrk_view", "wrkque", "lmstrn", "pckwrk_hdr", "cnfrm_bck_serv", "wrkhst", "wcs_disc_snap", "pcklst_slot_load", "invlod", "inv_intransit"] (17 results, 386 ms)

**Where does RTCIS untdtl.casqty go in PrIME 2022, and with which evidence?**

`g.V('Column:rtcis:untdtl.casqty').has('pk', 'Column:RTCIS').outE('MAPS_TO').project('to', 'evidence', 'verdict').by(inV().values('id')).by(coalesce(values('sources'), values('agreement'), constant(''))).by(coalesce(values('value_verdict'), values('tag'), constant('')))`

-> [{"to": "Column:prime:invdtl.untqty", "evidence": "94% (85% with `UNTCAS`); R01 92%, R16 100% after FLOOR", "verdict": "MAPPED + DEVIATION from OBS6 — [receiving-uom](../concepts/r"}] (1 results, 399 ms)

**Which PrIME 2014 columns were renamed in PrIME 2022 (data-model transition map, validated)?**

`g.V().has('pk', 'Column:PrIME2014').outE('MAPS_TO').has('sources', TextP.containing('H5')).limit(8).project('from', 'to').by(outV().values('id')).by(inV().values('id'))`

-> [{"from": "Column:prime14:alloc_search_hdr.alloc_search_id", "to": "Column:prime:alloc_search_path.alloc_search_path_id"}, {"from": "Column:prime14:alloc_search_hdr.wh_id", "to": "Column:prime:alloc_search_path.wh_id"}, {"from": "Column:prime14:sto_area_hdr.ins_user_id", "to": "Column:prime:sto_config_rule.ins_user_id"}, {"from": "Column:prime14:sto_area_hdr.dstare", "to": "Column:prime:sto_config_rule.sto_zone_id"}, {"from": "Column:prime14:sto_area_hdr.bldg_id", "to": "Column:prime:sto_config_rule.bldg_id"}, {"from": "Column:prime14:sto_area_hdr.last_upd_user_id", "to": "Column:prime:sto_con (8 results, 1792 ms)

**Which tables exist in PrIME 2014 but not in PrIME 2022 (no validated mapping)?**

`g.V().has('pk', 'Table:PrIME2014').not(outE('MAPS_TO')).limit(10).values('name')`

-> ["statistics_performance_dh", "uc_tech_audit", "usr_mock_putaway_lod", "vc_ctnaud", "all_constraints", "uc_table_policy_maintenance", "all_ind_columns", "usr_mock_putaway_hdr", "all_indexes", "all_tab_columns"] (10 results, 428 ms)

**Which converted queries are templates for 'inventory' questions, with grade and parameters?**

`g.V().has('pk', 'Query').has('side', 'PrIME2022').has('intent', TextP.containing('nventory')).project('q', 'grade', 'params').by('qid').by('grade').by('params')`

-> [{"q": "R02", "grade": "B", "params": "itmcls,strEnd_Date,strStart_Date,subsit,wh_id"}] (1 results, 367 ms)

**What do the experts say about descriptions (prtdsc)?**

`g.V('Table:prime:prtdsc').has('pk', 'Table:PrIME2022').in('MENTIONS').hasLabel('Learning', 'ExpertRule', 'DataFact').limit(5).values('text')`

-> ["`prtmst`/`prtdsc` two-row grain | `TOP 1` without `ORDER BY` is arbitrary | —", "`prtdsc` + `LOCALE_ID` | pinning `'GERMAN'` blanked descriptions | 82,086 / 163,748 (50.1%) at Euskirchen"] (2 results, 384 ms)

**Which PrIME 2022 tables are in the 'inventory' ERD domain and replicated at Euskirchen DE08?**

`g.V('Domain:inventory').has('pk', 'Domain').in('IN_DOMAIN').where(out('EXISTS_AT').has('id', 'Site:PRIME22_DE08')).values('name')`

-> ["wh", "hist", "ord_line", "locmst", "les_ath_role", "invlod_hist", "rcvinv", "invlod", "invdtl_hist", "ord"] (19 results, 402 ms)

**Which mappings are flagged as conflicting (a person must decide)?**

`g.V().has('pk', 'Column:RTCIS').outE('MAPS_TO').has('conflict').project('from', 'to', 'alt').by(outV().values('id')).by(inV().values('id')).by('conflict')`

-> [{"from": "Column:rtcis:sysdtl.locatn", "to": "Column:prime:dlytrn.tostol", "alt": "dlytrn.frstol,dlytrn.tostol"}, {"from": "Column:rtcis:sysdtl.locatn", "to": "Column:prime:dlytrn.frstol", "alt": "dlytrn.frstol,dlytrn.tostol"}] (2 results, 727 ms)
