-- R06 Beladeschein (RTCIS). T-SQL transliteration of the SYS_get_RTCIS Oracle text.
-- Param: @Ladungsnummer (rcphdr.BOLNUM).
-- das_rcphst (DAS receipt history, not replicated) -> items with any receipt line in RTCIS rcpdtl/rcpexp history.
WITH sq1 AS (
    SELECT DISTINCT rh.rrnumb, rh.rectyp, rh.bolnum, rh.delvid,
           CASE rh.rcvsit WHEN '0' THEN 'DE07' WHEN '1' THEN 'DE08' WHEN '2' THEN 'DE09' WHEN '3' THEN 'DE20,RH.RCVSIT' END AS dc,
           rh.vndcod, re.itmcod, re.ponumb AS po, tr.aptdat, tr.trlnum, tl.locatn, tn.trknam, tr.asgdat,
           it.itmgrp, ig.grpdsc, it.itmdsc
    FROM [EUSKIRCHEN_simp].live3.rcphdr rh
    JOIN [EUSKIRCHEN_simp].live3.rcpexp re ON rh.rrnumb = re.rrnumb
    JOIN [EUSKIRCHEN_simp].live3.trukio tr ON rh.rrnumb = tr.rrnumb
    JOIN [EUSKIRCHEN_simp].live3.trailer tl ON tr.trlnum = tl.trlnum AND tr.trklin = tl.trklin
    JOIN [EUSKIRCHEN_simp].live3.trklin tn ON tl.trklin = tn.trklin
    JOIN [EUSKIRCHEN_simp].live3.itmmst it ON re.itmcod = it.itmcod
    JOIN [EUSKIRCHEN_simp].live3.itmgrp ig ON it.itmgrp = ig.itmgrp
    WHERE rh.bolnum = @Ladungsnummer
), sq2 AS (
    SELECT re.itmcod FROM [EUSKIRCHEN_simp].live3.rcpexp re
    WHERE re.rrnumb NOT IN (SELECT rrnumb FROM [EUSKIRCHEN_simp].live3.rcphdr WHERE bolnum = @Ladungsnummer)
    GROUP BY re.itmcod
), A AS (
    SELECT sq1.rrnumb, sq1.rectyp, sq1.bolnum AS bn, sq1.delvid AS ib, sq1.dc, sq1.vndcod, sq1.itmcod AS it, sq1.po,
           FORMAT(sq1.aptdat, 'dd.MM.yyyy HH:mm:ss') AS aptdat, sq1.trlnum, sq1.locatn, sq1.trknam,
           FORMAT(sq1.asgdat, 'dd.MM.yyyy HH:mm:ss') AS asgdat, sq1.itmgrp, sq1.itmdsc, sq1.grpdsc,
           CASE WHEN sq2.itmcod IS NULL AND sq1.itmgrp IN ('PCO', 'WCO', 'PEOC', 'PBG', 'PAPPWP') THEN 'A'
                WHEN sq2.itmcod IS NULL THEN 'Y' ELSE 'N' END AS new_material
    FROM sq1 LEFT JOIN sq2 ON sq1.itmcod = sq2.itmcod
), x AS (
    SELECT it.itmcod, it.itmgrp, ig.GRPDSC,
           CASE WHEN ic.laypul = 1 AND ic.UDEPTH BETWEEN 120 AND 140 THEN 'OK' ELSE 'NOK' END AS Check_Pal_Dim,
           CASE WHEN iu.U_LENGTH > 0 AND iu.U_WIDTH > 0 AND iu.u_height > 0 AND iu.dimuom IS NOT NULL AND it.PALFLG = 'Y' THEN 'OK' ELSE 'NOK' END AS Check_Gebinde_Dim,
           CASE WHEN ic.UDEPTH >= 120 AND ic.UWIDTH >= 80 THEN 'OK' ELSE 'NOK' END AS Check_Holzpal_Dim,
           CASE WHEN bl.PUT_ZONLST IN ('CONTP', 'BAGSP', 'FILMP', 'LEIM') THEN 'OK' ELSE 'NOK' END AS CHECK_ZONLST
    FROM [EUSKIRCHEN_simp].live3.itmmst it
    JOIN [EUSKIRCHEN_simp].live3.item_config ic ON it.itmcod = ic.itmcod
    JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON iu.itmcod = ic.itmcod AND it.itmcod = iu.itmcod
    JOIN [EUSKIRCHEN_simp].live3.itmgrp ig ON it.itmgrp = ig.itmgrp
    JOIN [EUSKIRCHEN_simp].live3.blditm bl ON it.itmcod = bl.itmcod AND it.itmcls = bl.itmcls AND ic.ULPALL = bl.ULPALL
    WHERE it.itmcls = 'P' AND iu.WHSFLG = 'Y' AND ic.DEFAULT_CONF = 'Y' AND ic.laypul = 1 AND bl.blding IN ('0004')
), B AS (
    SELECT x.itmcod, x.itmgrp, x.grpdsc,
           CASE WHEN x.Check_Pal_Dim = 'OK' AND Check_Gebinde_Dim = 'OK' AND Check_Holzpal_Dim = 'OK' THEN 'OK' ELSE 'NOK' END AS Stammdaten,
           CASE WHEN x.CHECK_ZONLST = 'OK' THEN 'Ja' ELSE 'Nein' END AS AGV_Lagerbereich
    FROM x
)
SELECT a.rrnumb, a.rectyp, a.bn, a.ib, a.dc, a.vndcod, a.it, a.po, a.aptdat, a.trlnum, a.locatn, a.trknam, a.asgdat,
       a.new_material, b.stammdaten, b.agv_lagerbereich, a.itmdsc, b.itmgrp, b.grpdsc
FROM A a LEFT JOIN B b ON a.it = b.itmcod;
