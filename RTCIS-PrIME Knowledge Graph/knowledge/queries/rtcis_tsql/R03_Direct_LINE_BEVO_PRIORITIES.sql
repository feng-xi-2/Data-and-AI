-- R03 Direct LINE BEVO priorities (RTCIS). T-SQL transliteration of the OpenQuery(RTCIS, ...) Oracle text.
-- The original also builds sub-query C (lots by ctlgrp) but never selects it: kept out (dead in the original).
-- No parameters.
WITH rl AS (
    SELECT ul.ULID, ul.locatn, ud.itmcod, ct.ctlgrp, ct.vndlot, ct.vndcod
    FROM [EUSKIRCHEN_simp].live3.unitld ul
    JOIN [EUSKIRCHEN_simp].live3.untdtl ud ON ul.ULID = ud.ulid
    JOIN [EUSKIRCHEN_simp].live3.ctlgrp ct ON ud.ITMCOD = ct.ITMCOD AND ud.CTLGRP = ct.CTLGRP
    WHERE ud.itmcls = 'P' AND ul.locatn NOT LIKE '%RWZ%' AND ct.qastat = 'RL'
), B AS (SELECT COUNT(ULID) ULIDs, locatn, itmcod, vndlot, vndcod FROM rl GROUP BY locatn, itmcod, vndlot, vndcod),
   D AS (SELECT COUNT(ULID) ULIDs, vndcod, vndlot FROM rl GROUP BY vndcod, vndlot),
   E AS (
    SELECT R.PRDORD, Q.ACTDAT, Q.ENDDAT, R.SPCCD1, SUM(R.EXPQTY - R.ACTQTY) AS Offener_Bedarf_IN_WM_Unit, L.PLNUMB AS LINIE, Q.ITMCOD
    FROM [EUSKIRCHEN_simp].live3.PORECIPE R
    JOIN [EUSKIRCHEN_simp].live3.PRDQUE Q ON R.PRDORD = Q.PRDORD
    LEFT JOIN [EUSKIRCHEN_simp].live3.PRDLIN L ON R.DELIV_PRDLIN = L.PRDLIN
    WHERE R.SPCCD1_ITMCLS = 'P' AND Q.COMPLETE_FLAG = 'A' AND L.SUBSIT = '0' AND R.EXPQTY - R.ACTQTY > 0
    GROUP BY R.SPCCD1, R.PRDORD, Q.ACTDAT, Q.ENDDAT, L.PLNUMB, Q.ITMCOD, L.PRDORD)
SELECT A.PLNUMB, A.PRDORD, E.ACTDAT, E.ENDDAT, A.ITMCOD, A.SPCCOD, A.LINSEQ, A.LOCATN,
       A.CTLGRP, A.VNDCOD, A.VNDLOT, B.ULIDs AS ULIDs_anhand_Ort, D.ULIDs AS ULIDs_anhand_Vendor_Lot,
       FORMAT(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime), 'dd.MM.yyyy HH:mm') AS Last_Update
FROM [EUSKIRCHEN_simp].live3.lindel A
LEFT JOIN B ON A.spccod = B.itmcod AND A.locatn = B.locatn AND A.vndlot = B.vndlot AND A.vndcod = B.vndcod
LEFT JOIN D ON A.VNDCOD = D.VNDCOD AND A.VNDLOT = D.VNDLOT
LEFT JOIN E ON A.ITMCOD = E.ITMCOD AND A.SPCCOD = E.SPCCD1 AND A.PRDORD = E.PRDORD
UNION
SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       FORMAT(MAX(ul.sysdat), 'dd.MM.yyyy HH:mm')
FROM [EUSKIRCHEN_simp].live3.systrn ul;
