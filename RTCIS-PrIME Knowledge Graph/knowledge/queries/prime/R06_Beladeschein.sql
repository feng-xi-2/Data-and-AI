-- R06 Beladeschein -> PrIME 2022. Params: @wh_id, @locale, @Ladungsnummer. Receipt mapping as R05 (BOLNUM -> rcvinv.WAYBIL; trailer door -> trlr.YARD_LOC).
-- new_material: item never received before this load (das_rcphst history -> rcvlin of other loads).
-- Master-data checks (Stammdaten, AGV_Lagerbereich) re-expressed on PrIME footprint data:
--   item_config udepth / uwidth (cm) -> pallet-level WID / LEN (cm; FERT DE08 same item+footprint 17,119/20,257: RTCIS 80x120
--   = PrIME LEN 120 WID 80). Check_Pal_Dim udepth 120-140 -> WID 120-140; Check_Holzpal udepth>=120, uwidth>=80 -> WID, LEN.
--   item_uom dims + dimuom + PALFLG -> receiving-level LEN/WID/HGT > 1 (1 x 1 x 1 is the DE08 'NONE' footprint placeholder) [INFERRED]
--   blditm PUT_ZONLST ('CONTP','BAGSP','FILMP','LEIM') in building 0004 -> no PrIME equivalent of a put-away zone list
--   per building; AGV_Lagerbereich returned NULL [ELIMINATED - needs site put-away configuration owner].
-- itmgrp/grpdsc -> PRTFAM / dscmst 'prtfam' (87/93 shared groups have identical text).
WITH sq1 AS (
    SELECT DISTINCT t.TRKNUM AS rrnumb, i.INVTYP AS rectyp, i.WAYBIL AS bolnum, i.INVNUM AS delvid, t.WH_ID AS dc, i.SUPNUM AS vndcod,
           r.PRTNUM AS itmcod, ISNULL(i.PO_NUM, '') AS po, t.EXPDTE AS aptdat, tr.TRLR_NUM AS trlnum, tr.YARD_LOC AS locatn,
           c.CARNAM AS trknam, tr.ARRDTE AS asgdat, p.PRTFAM AS itmgrp, g.LNGDSC AS grpdsc, ds.LNGDSC AS itmdsc
    FROM dbo.rcvtrk t
    JOIN dbo.rcvinv i ON i.TRKNUM = t.TRKNUM AND i.WH_ID = t.WH_ID
    JOIN dbo.rcvlin r ON r.TRKNUM = i.TRKNUM AND r.INVNUM = i.INVNUM AND r.WH_ID = i.WH_ID
    JOIN dbo.trlr tr ON tr.TRLR_ID = t.TRLR_ID
    LEFT JOIN dbo.carhdr c ON c.CARCOD = tr.CARCOD
    JOIN dbo.prtmst p ON p.PRTNUM = r.PRTNUM AND p.PRT_CLIENT_ID = r.PRT_CLIENT_ID AND p.WH_ID_TMPL = t.WH_ID
    LEFT JOIN dbo.dscmst g ON g.COLNAM = 'prtfam' AND g.COLVAL = p.PRTFAM AND g.LOCALE_ID = 'US_ENGLISH'
    OUTER APPLY (SELECT TOP 1 x.LNGDSC FROM dbo.prtdsc x WHERE x.COLNAM = 'prtnum|prt_client_id|wh_id_tmpl'
                 AND x.COLVAL IN (r.PRTNUM + '|' + r.PRT_CLIENT_ID + '|' + t.WH_ID, r.PRTNUM + '|' + r.PRT_CLIENT_ID + '|----')
                 AND x.LOCALE_ID IN (@locale, 'US_ENGLISH') AND x.LNGDSC IS NOT NULL
                 ORDER BY CASE WHEN x.COLVAL LIKE '%|----' THEN 2 ELSE 1 END, CASE WHEN x.LOCALE_ID = @locale THEN 1 ELSE 2 END) ds
    WHERE t.WH_ID = @wh_id AND i.WAYBIL = @Ladungsnummer
), sq2 AS (
    SELECT r.PRTNUM AS itmcod FROM dbo.rcvlin r JOIN dbo.rcvinv i ON i.TRKNUM = r.TRKNUM AND i.INVNUM = r.INVNUM AND i.WH_ID = r.WH_ID
    WHERE r.WH_ID = @wh_id AND ISNULL(i.WAYBIL, '') <> @Ladungsnummer GROUP BY r.PRTNUM
), A AS (
    SELECT sq1.*, CASE WHEN sq2.itmcod IS NULL AND sq1.itmgrp IN ('PCO', 'WCO', 'PEOC', 'PBG', 'PAPPWP') THEN 'A'
                       WHEN sq2.itmcod IS NULL THEN 'Y' ELSE 'N' END AS new_material
    FROM sq1 LEFT JOIN sq2 ON sq1.itmcod = sq2.itmcod
), B AS (
    SELECT p.PRTNUM AS itmcod, p.PRTFAM AS itmgrp, g.LNGDSC AS grpdsc,
           CASE WHEN pl.WID BETWEEN 120 AND 140 AND pl.LEN >= 80 AND rc.LEN > 1 AND rc.WID > 1 AND rc.HGT > 1
                THEN 'OK' ELSE 'NOK' END AS stammdaten,
           CAST(NULL AS varchar(4)) AS agv_lagerbereich
    FROM dbo.prtmst p
    LEFT JOIN dbo.dscmst g ON g.COLNAM = 'prtfam' AND g.COLVAL = p.PRTFAM AND g.LOCALE_ID = 'US_ENGLISH'
    OUTER APPLY (SELECT TOP 1 f.LEN, f.WID FROM dbo.prtftp_dtl f WHERE f.PRTNUM = p.PRTNUM AND f.PRT_CLIENT_ID = p.PRT_CLIENT_ID
                 AND f.WH_ID = p.WH_ID_TMPL AND f.PAL_FLG = 1 ORDER BY f.UOMLVL DESC) pl
    OUTER APPLY (SELECT TOP 1 f.LEN, f.WID, f.HGT FROM dbo.prtftp_dtl f WHERE f.PRTNUM = p.PRTNUM AND f.PRT_CLIENT_ID = p.PRT_CLIENT_ID
                 AND f.WH_ID = p.WH_ID_TMPL AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) rc
    WHERE p.WH_ID_TMPL = @wh_id AND p.TYPCOD = 'ROH'
)
SELECT a.rrnumb, a.rectyp, a.bolnum AS bn, a.delvid AS ib, a.dc, a.vndcod, a.itmcod AS it, a.po,
       FORMAT(a.aptdat, 'dd.MM.yyyy HH:mm:ss') AS aptdat, a.trlnum, a.locatn, a.trknam,
       FORMAT(a.asgdat, 'dd.MM.yyyy HH:mm:ss') AS asgdat, a.new_material, b.stammdaten, b.agv_lagerbereich, a.itmdsc, b.itmgrp, b.grpdsc
FROM A a LEFT JOIN B b ON a.itmcod = b.itmcod;
