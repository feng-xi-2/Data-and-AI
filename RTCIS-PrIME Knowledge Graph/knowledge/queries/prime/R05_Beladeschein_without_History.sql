-- R05 Beladeschein without history -> PrIME 2022. Params: @wh_id, @Ladungsnummer.
-- RTCIS receipt header/truck/trailer -> PrIME inbound receipt:
--   rcphdr.RRNUMB -> rcvtrk.TRKNUM; RECTYP -> rcvinv.INVTYP; BOLNUM (Ladungsnummer) -> rcvinv.WAYBIL (= TRKNUM before '~',
--   88/88 DE08, 703/703 Athens; rcvtrk.TRKREF is the SUPPLIER NAME, not a load reference); DELVID (SAP inbound delivery) -> rcvinv.INVNUM;
--   RCVSIT decode -> rcvtrk.WH_ID; VNDCOD -> rcvinv.SUPNUM; rcpexp ITMCOD/PONUMB -> rcvlin.PRTNUM / rcvinv.PO_NUM
--   (PO_NUM empty at DE08); trukio APTDAT -> rcvtrk.EXPDTE; ASGDAT -> trlr.ARRDTE; trailer TRLNUM -> trlr.TRLR_NUM;
--   LOCATN (RTCIS trailer door, e.g. 'DOOR 09') -> trlr.YARD_LOC (door/yard spot: DE08 DOOR16/17 type RSDK; trlr.STOLOC is the trailer's own location = trailer id, type DSPCH - wrong source, fixed 2026-10-21); trklin TRKNAM (haulier) -> carhdr.CARNAM.
-- Branch 1 (receipt without expected lines) and branch 2 (with lines) kept as in the original.
WITH h AS (
    SELECT t.TRKNUM AS RRNUMB, i.INVTYP AS RECTYP, i.WAYBIL AS BOLNUM, i.INVNUM AS DELVID, t.WH_ID AS DC, i.SUPNUM AS VNDCOD,
           t.EXPDTE AS APTDAT, tr.TRLR_NUM AS TRLNUM, tr.YARD_LOC AS LOCATN, c.CARNAM AS TRKNAM, tr.ARRDTE AS ASGDAT, i.PO_NUM
    FROM dbo.rcvtrk t
    JOIN dbo.rcvinv i ON i.TRKNUM = t.TRKNUM AND i.WH_ID = t.WH_ID
    JOIN dbo.trlr tr ON tr.TRLR_ID = t.TRLR_ID
    LEFT JOIN dbo.carhdr c ON c.CARCOD = tr.CARCOD
    WHERE t.WH_ID = @wh_id AND i.WAYBIL = @Ladungsnummer
), sq1 AS (
    SELECT DISTINCT h.RRNUMB, h.RECTYP, h.BOLNUM, h.DELVID, h.DC, h.VNDCOD, '0' AS IT, '0' AS PO, h.APTDAT, h.TRLNUM, h.LOCATN, h.TRKNAM, h.ASGDAT
    FROM h WHERE NOT EXISTS (SELECT 1 FROM dbo.rcvlin r WHERE r.TRKNUM = h.RRNUMB AND r.WH_ID = @wh_id)
    UNION
    SELECT DISTINCT h.RRNUMB, h.RECTYP, h.BOLNUM, h.DELVID, h.DC, h.VNDCOD, r.PRTNUM, ISNULL(h.PO_NUM, ''), h.APTDAT, h.TRLNUM, h.LOCATN, h.TRKNAM, h.ASGDAT
    FROM h JOIN dbo.rcvlin r ON r.TRKNUM = h.RRNUMB AND r.INVNUM = h.DELVID AND r.WH_ID = @wh_id
)
SELECT sq1.RRNUMB, sq1.RECTYP, sq1.BOLNUM AS BN, sq1.DELVID AS IB, sq1.DC, sq1.VNDCOD, sq1.IT, sq1.PO,
       FORMAT(sq1.APTDAT, 'dd.MM.yyyy HH:mm:ss') AS APTDAT, sq1.TRLNUM, sq1.LOCATN, sq1.TRKNAM,
       FORMAT(sq1.ASGDAT, 'dd.MM.yyyy HH:mm:ss') AS ASGDAT
FROM sq1;
