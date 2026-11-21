-- R02 IRA Cycle Count on Location Level (RTCIS). T-SQL transliteration of the Oracle text passed to SYS_get_DAS.
-- DAS = RTCIS history archive; the replica keeps ~40 days of systrn/sysdtl, which this reads instead.
-- Params: @strStart_Date, @strEnd_Date ('mm/dd/yyyy hh:mi:ss'), @subsit (LIKE, '0'/'1'/'%'), @itmcls ('F'/'P')
WITH ev AS (
    SELECT DISTINCT t.trntyp, t.gendat, d.subsit, l.count_itmcls, d.locatn, t.techid,
           CONCAT(u.first_name, ' ', u.last_name) AS name
    FROM [EUSKIRCHEN_simp].live3.systrn t
    JOIN [EUSKIRCHEN_simp].live3.sysdtl d ON d.trnseq = t.trnseq
    JOIN [EUSKIRCHEN_simp].live3.locatn l ON l.locatn = d.locatn AND l.subsit = d.subsit
    JOIN EUSKIRCHEN.live3.USERS u ON u.user_id = t.techid
    WHERE t.sysdat BETWEEN CONVERT(datetime, @strStart_Date, 101) AND CONVERT(datetime, @strEnd_Date, 101)
      AND d.subsit LIKE @subsit
      AND t.trntyp IN ('STKCNT', 'STKMIS', 'STKCOR')
      AND l.count_itmcls = @itmcls
      AND l.pre_count_ok IS NOT NULL AND l.post_count_ok IS NOT NULL
      AND l.arecod IN ('RA', 'CP', 'RO')
      AND d.dtltyp = 'F'
), a AS (
    SELECT DISTINCT CONVERT(varchar(8), gendat, 108) AS time, CONVERT(varchar(10), gendat, 103) AS stkcnt_date,
           subsit, count_itmcls, 1 AS stkcnt, locatn, name
    FROM ev WHERE trntyp = 'STKCNT'
), b AS (
    SELECT DISTINCT CONVERT(varchar(8), gendat, 108) AS time, CONVERT(varchar(10), gendat, 103) AS stkmis_date,
           subsit, 1 AS stkmis, locatn, name
    FROM ev WHERE trntyp = 'STKMIS'
), c AS (
    SELECT DISTINCT CONVERT(varchar(8), gendat, 108) AS time, CONVERT(varchar(10), gendat, 103) AS stkcor_date,
           subsit, 1 AS stkcor, locatn, techid, name
    FROM ev WHERE trntyp = 'STKCOR'
)
SELECT a.stkcnt_date, a.time,
       CASE a.subsit WHEN '0' THEN 'DE07' WHEN '1' THEN 'DE08' WHEN '2' THEN 'DE09' ELSE a.subsit END AS subsit,
       a.count_itmcls, a.locatn, a.stkcnt,
       ISNULL(b.stkmis, 0) AS stkmis,
       ISNULL(c.stkcor, 0) AS stkcor,
       a.name
FROM a
LEFT JOIN b ON a.subsit = b.subsit AND a.stkcnt_date = b.stkmis_date AND a.locatn = b.locatn AND a.name = b.name AND a.time = b.time
LEFT JOIN c ON a.subsit = c.subsit AND a.stkcnt_date = c.stkcor_date AND a.locatn = c.locatn AND a.name = c.name AND a.time = c.time
ORDER BY a.stkcnt_date, a.locatn, a.time;
