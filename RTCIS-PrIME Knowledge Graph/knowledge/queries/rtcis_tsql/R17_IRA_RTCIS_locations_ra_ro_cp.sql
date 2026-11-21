-- R17 IRA RTCIS locations RA/RO/CP (RTCIS). T-SQL transliteration of the OpenQuery(LIVE, ...) Oracle text.
-- The trailing note "auf Zonecode BA setzen" in the source file is a comment, not SQL. No parameters.
WITH s1 AS (
    SELECT subsit, locatn, count_itmcls, pikzon, CYCDAT, POST_COUNT_OK, PRE_COUNT_OK, SERFLG, SERFLG_COMMNT, ACTDAT, ITMCOD, ARECOD
    FROM [EUSKIRCHEN_simp].live3.locatn
    WHERE arecod IN ('RA', 'RO', 'CP') AND subsit IN ('0', '1') AND locatn NOT LIKE 'AL%' AND locatn NOT LIKE 'SILO%' AND locatn NOT LIKE 'CIMAT'
      AND locatn NOT IN (SELECT locatn FROM [EUSKIRCHEN_simp].live3.locatn WHERE subsit = '0' AND zoncod = 'D9')
), s2 AS (
    SELECT it.itmcod, iu.uom AS wm_unit, ic.caslay
    FROM [EUSKIRCHEN_simp].live3.itmmst it
    JOIN [EUSKIRCHEN_simp].live3.item_config ic ON it.itmcod = ic.itmcod
    LEFT JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.itmcod = iu.itmcod
    WHERE it.itmcls = 'F' AND iu.WHSFLG = 'Y' AND ic.default_conf = 'Y'
)
SELECT CASE s1.subsit WHEN '0' THEN 'DE07' WHEN '1' THEN 'DE08' WHEN '2' THEN 'DE09' END AS subsit,
       CASE WHEN PIKZON = 'P1' THEN '0001' WHEN PIKZON = 'P2' THEN '0002' WHEN PIKZON = 'P4' THEN '0004' WHEN PIKZON = 'P6' THEN '0006'
            WHEN PIKZON IN ('H2', 'K1') THEN '0015' WHEN PIKZON = 'P7' THEN '0007' WHEN PIKZON IN ('P8', 'CP', 'BA', 'BF') THEN '0008'
            WHEN PIKZON = 'P9' THEN 'CIMAT' WHEN PIKZON = '1P' THEN '0011' WHEN PIKZON = '2P' THEN '0012' WHEN PIKZON = '3P' THEN '0013'
            WHEN PIKZON = '4P' THEN '0014' WHEN s1.subsit = '2' AND PIKZON IN ('A0', 'C0') THEN 'CC'
            WHEN PIKZON = 'X1' THEN '0001' WHEN PIKZON = 'X2' THEN '0002' WHEN PIKZON = 'X3' THEN '0003' WHEN PIKZON = 'X4' THEN '0004'
            WHEN PIKZON = 'X5' THEN '0005' WHEN s1.locatn LIKE '6%' THEN '0006' WHEN s1.locatn LIKE '8%' THEN '0008'
            WHEN s1.locatn LIKE '15%' THEN '0015' WHEN s1.locatn LIKE 'HOF%' THEN 'AUSSENBEREICH' WHEN s1.locatn LIKE 'LTANK%' THEN '0001'
            ELSE s1.locatn END AS blding,
       s1.locatn, s1.count_itmcls, s1.CYCDAT, ROUND(DATEDIFF(second, s1.CYCDAT, GETDATE()) / 86400.0, 0) AS last_count_durration_days,
       s1.POST_COUNT_OK, s1.PRE_COUNT_OK, s1.serflg, s1.serflg_commnt, FORMAT(s1.actdat, 'dd.MM.yyyy HH:mm') AS actdat,
       s1.itmcod, s1.arecod, CAST(s2.caslay AS varchar(20)) AS caslay, s2.wm_unit,
       FORMAT(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime), 'dd.MM.yyyy HH:mm') AS last_update
FROM s1 LEFT JOIN s2 ON s1.itmcod = s2.itmcod
ORDER BY subsit, s1.locatn, s1.arecod;
