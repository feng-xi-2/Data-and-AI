-- R14 HD Sperrungen FP ohne Sperrgrund (RTCIS). T-SQL transliteration of the SYS_get_RTCIS Oracle text.
-- The source file ends with stray text (", nullm Code], x.[FIFO Date], x.Subsit, x.Location") after the EXEC: a paste
-- remnant, not part of the query. "COST" in the original is a UOM factor (SU per WHS unit), not itmmst.cost;
-- BESTAND_SU = stock expressed in SU (statistical units). No parameters.
WITH s1 AS (
    SELECT c.itmcod, c.ctlgrp, c.qastat, SUM(u.casqty) AS qty, c.CTRL_DATE
    FROM [EUSKIRCHEN_simp].live3.ctlgrp c
    JOIN [EUSKIRCHEN_simp].live3.untdtl u ON c.itmcod = u.itmcod AND u.ctlgrp = c.ctlgrp
    WHERE u.itmcls = 'F' AND c.qastat = 'HD'
    GROUP BY c.itmcod, c.ctlgrp, c.qastat, c.CTRL_DATE
), su AS (
    SELECT it.itmcod, it.itmgrp, it.ITMDSC, CAST(iu.BUOMDEN AS float) / iu.BUOMNUM AS result1
    FROM [EUSKIRCHEN_simp].live3.itmmst it JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.itmcod = iu.itmcod
    WHERE it.itmcls = 'F' AND iu.uom = 'SU'
), wh AS (
    SELECT it.itmcod, iu.UOM, CAST(iu.BUOMDEN AS float) / iu.BUOMNUM AS result2
    FROM [EUSKIRCHEN_simp].live3.itmmst it JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.itmcod = iu.itmcod
    WHERE it.itmcls = 'F' AND iu.WHSFLG = 'Y'
), s2 AS (
    SELECT su.itmcod, su.itmgrp, su.result1 / wh.result2 AS COST, su.itmdsc, wh.UOM
    FROM su JOIN wh ON su.itmcod = wh.itmcod
)
SELECT DISTINCT s2.ITMGRP,
       CASE WHEN SUBSTRING(s1.ctlgrp, 5, 2) = '01' THEN 'Euskirchen'
            WHEN SUBSTRING(s1.ctlgrp, 5, 2) = '02' THEN 'Crailsheim'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4847' THEN 'Blois'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4499' THEN 'Euskirchen'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4544' THEN 'EUS DACH CC'
            ELSE 'Sonstige' END AS Herkunft,
       s1.itmcod AS ARTIKEL, s2.ITMDSC AS BESCHREIBUNG, s1.ctlgrp AS LOTNUMMER, s1.qastat AS QA_STATUS, s1.qty AS MENGE,
       s2.uom AS WM_UNIT, CAST(s2.COST * s1.qty AS varchar(40)) AS BESTAND_SU, FORMAT(s1.ctrl_date, 'dd.MM.yyyy') AS SPERR_DATUM
FROM s1 JOIN s2 ON s1.itmcod = s2.itmcod
ORDER BY Herkunft, s2.ITMGRP;
