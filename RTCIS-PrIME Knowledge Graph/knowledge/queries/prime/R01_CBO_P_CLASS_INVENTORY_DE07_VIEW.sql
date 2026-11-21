-- R01 CBO_P_CLASS_INVENTORY_DE07_VIEW -> PrIME 2022
-- Caller binds @wh_id ('DE08'). RTCIS packaging (ITMCLS 'P') in subsit '0' (DE07) = PrIME ROH stock in building B1.
-- Mapping (same-pallet evidence, tools/map_inventory_fields.py, Euskirchen 2026-10-20):
--   ULID20 = invlod.LODNUM (exact, 20 chars)      ITMCLS 'P' -> prtmst.TYPCOD 'ROH'
--   subsit '0' (DE07) -> aremst.BLDG_ID 'B1' (99.2%) ITMGRP -> prtmst.PRTFAM (99.9%)
--   CTLGRP -> invdtl.LOTNUM (98.4%)               FIFODT -> invdtl.FIFDTE (99.5%)
--   CASQTY -> UNTQTY / receiving-UOM factor (94%)  ULPALL -> invdtl.FTPCOD (90%)
--   OBS6 DEVIATION (declared): RUIZ.RS converts with UNTQTY/UNTCAS; the receiving-level factor reproduces RTCIS CASQTY on
--   94% of same pallets vs 85% for UNTCAS (results/map_inventory_fields.json). Zero fallback + decimal kept as OBS6.
--   CASQTY is numeric(22,0) in RTCIS and truncated: metric packaging is stocked in 1/1000 units (2M/MM/G), so PrIME gives
--   4250.400 M2 where RTCIS shows 4250 (RTCIS = FLOOR on 549 pallets, = ROUND-only on 0) -> FLOOR, numeric(22,0)
--   (results/probe_casqty_height.json). The exact PrIME stock is the unfloored value.
--   OBS8: PrIME splits 51 DE08 pallet+item+lot keys over 2 invdtl rows (RTCIS: 0) -> details summed per key first.
--   QASTAT RL/HD -> INVSTS U/B (value set differs: returned as PrIME code)
--   ZONCOD -> locmst.ARECOD (PrIME area; different code set)
--   PIKZON X1..X5/XC (Halle) -> LEFT(ARECOD,2) '01'..'05' (pick zone X3->03, X4->04 ... measured)  [INFERRED: 'Modul' unmapped]
--   VNDCOD/VNDLOT -> LEFT(SUP_LOTNUM,4) / rest   (Euskirchen convention, 100% same-pallet)
--   item_uom WHSFLG UOM -> prtftp_dtl RCV_FLG=1 UOMCOD (100% same-pallet).
--   u_height (cm, + 15 cm pallet base when PALFLG) -> pallet-level prtftp_dtl.HGT (PAL_FLG=1), cm, base included
--   (FERT DE08: PL HGT = LY HGT x layers + 15 on 15,145/20,141) [INFERRED]. DE08 packaging footprints are all 'NONE'
--   with placeholder 1 x 1 x 1 dims -> HGT <= 1 returned NULL, not a fake height; live Athens ROH has real heights.
--   SAP marm (f6p) has a PAL unit for 3 of 1,624 items -> no alternative source (results/probe_sap_pallet_height.json).
--   itmmst PICFLG='Y' / PALFLG -> no PrIME flag: PICFLG dropped (99.8% of P items are 'Y'); PALFLG -> prtftp PAL level exists [INFERRED]
--   item_config default ULPALL join -> footprint of the pallet (FTPCOD) itself
--   CBO_CTLGRP (lots in stock or receipt) -> lot of the stock itself (inner join was a pure existence filter)
SELECT DISTINCT
       l.STOLOC                                             AS LOCATN,
       d.PRTNUM                                             AS ITMCOD,
       p.PRTFAM                                             AS ITMGRP,
       l.LODNUM                                             AS ULID20,
       CAST(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN d.UNTQTY ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END) AS numeric(22,0)) AS CASQTY,
       d.INVSTS                                             AS QASTAT,
       d.FIFDTE                                             AS FIFODT,
       d.LOTNUM                                             AS CTLGRP,
       d.FTPCOD                                             AS ULPALL,
       m.ARECOD                                             AS ZONCOD,
       CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime) AS last_update,
       CASE LEFT(m.ARECOD, 2) WHEN '01' THEN 'Halle 1' WHEN '02' THEN 'Halle 2' WHEN '03' THEN 'Halle 3'
                              WHEN '04' THEN 'Halle 4' WHEN '05' THEN 'Halle 5' ELSE 'not defined' END AS BLDING,
       CASE WHEN LEFT(p.PRTFAM, 1) = 'W' OR p.PRTFAM = 'PAPPWP' THEN 'Wipes'
            WHEN LEFT(p.PRTFAM, 1) = 'R' THEN 'Rawmaterial'
            WHEN LEFT(p.PRTFAM, 1) = 'P' THEN 'Packmaterial' ELSE 'not defined' END AS MATTYP,
       CONVERT(int, CASE WHEN ph.HGT > 1 THEN ph.HGT END)  AS calculated_pal_height,
       r.UOMCOD                                             AS UOM,
       NULLIF(LEFT(d.SUP_LOTNUM, 4), '')                    AS VNDCOD,
       NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '')          AS VNDLOT,
       CONCAT(d.FTPCOD, d.PRTNUM)                           AS ULPAL_ITEM
FROM dbo.invlod l
JOIN (SELECT s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM, MAX(i.FTPCOD) AS FTPCOD, MAX(i.INVSTS) AS INVSTS,
             MIN(i.FIFDTE) AS FIFDTE, MAX(i.SUP_LOTNUM) AS SUP_LOTNUM, SUM(i.UNTQTY) AS UNTQTY
      FROM dbo.invsub s JOIN dbo.invdtl i ON i.SUBNUM = s.SUBNUM
      GROUP BY s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM) d ON d.LODNUM = l.LODNUM
JOIN dbo.prtmst p  ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = l.WH_ID
JOIN dbo.locmst m  ON m.STOLOC = l.STOLOC AND m.WH_ID = l.WH_ID
JOIN dbo.aremst a  ON a.ARECOD = m.ARECOD AND a.WH_ID = m.WH_ID
OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f
             WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND f.WH_ID = l.WH_ID
               AND f.FTPCOD = d.FTPCOD AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) r
OUTER APPLY (SELECT TOP 1 f.HGT FROM dbo.prtftp_dtl f
             WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND f.WH_ID = l.WH_ID
               AND f.FTPCOD = d.FTPCOD AND f.PAL_FLG = 1 ORDER BY f.UOMLVL DESC) ph
WHERE l.WH_ID = @wh_id
  AND p.TYPCOD = 'ROH'
  AND a.BLDG_ID = 'B1'
  AND r.UOMCOD IS NOT NULL;
