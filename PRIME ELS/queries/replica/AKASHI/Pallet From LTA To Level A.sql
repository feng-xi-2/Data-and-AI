-- Pallet From LTA To Level A - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A' AS LEVEL_TYPE,
            CAST(a.trndte AS DATE) AS Day,
            DATEPART(HOUR, a.trndte) AS [Hour Of Day],
            COUNT(DISTINCT a.lodnum) AS PALLETS
        FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') a
        INNER JOIN (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') b
            ON b.lodnum = a.lodnum
        INNER JOIN (SELECT * FROM dbo.wkohdr WHERE wh_id = 'JP01') w
            ON w.wkonum = b.frstol
           AND w.prtnum = b.prtnum
        WHERE a.trndte >= '2026-10-01 00:00:00' AND a.trndte >= '1900-01-01' AND a.trndte < '9999-12-31'
          AND a.trndte <= GETDATE()
          AND a.to_arecod NOT LIKE 'RDTS'
          AND a.fr_arecod LIKE 'RDTS'
          AND a.tostol LIKE '~NA~'
          AND a.to_arecod IS NOT NULL
          AND b.oprcod = 'UID'
          AND b.actcod = 'RCV'
          AND b.trndte <= a.trndte
        GROUP BY CAST(a.trndte AS DATE), DATEPART(HOUR, a.trndte)
        
        UNION ALL
        
        SELECT
            'LEVEL_OTHER' AS LEVEL_TYPE,
            CAST(a.trndte AS DATE) AS Day,
            DATEPART(HOUR, a.trndte) AS [Hour Of Day],
            COUNT(DISTINCT a.lodnum) AS PALLETS
        FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') a
        INNER JOIN (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') b
            ON b.lodnum = a.lodnum
        INNER JOIN (SELECT * FROM dbo.wkohdr WHERE wh_id = 'JP01') w
            ON w.wkonum = b.frstol
           AND w.prtnum = b.prtnum
        WHERE a.trndte >= '2026-10-01 00:00:00' AND a.trndte >= '1900-01-01' AND a.trndte < '9999-12-31'
          AND a.trndte <= GETDATE()
          AND a.to_arecod NOT LIKE 'RDTS'
          AND a.fr_arecod LIKE 'RDTS'
          AND a.tostol NOT LIKE '~NA~'
          AND a.to_arecod = '~NA~'
          AND a.tostol NOT IN (
              SELECT DISTINCT stoloc
              FROM (SELECT * FROM dbo.locmst WHERE wh_id = 'JP01') AS locmst
              WHERE CAST(sto_zone_id AS NVARCHAR(40)) IN ('10029')
          )
          AND a.to_arecod IS NOT NULL
          AND b.oprcod = 'UID'
          AND b.actcod = 'RCV'
          AND b.trndte <= a.trndte
        GROUP BY CAST(a.trndte AS DATE), DATEPART(HOUR, a.trndte)
        
        ORDER BY LEVEL_TYPE, Day, [Hour Of Day];
