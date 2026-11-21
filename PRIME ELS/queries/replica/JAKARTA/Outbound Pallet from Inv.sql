-- Outbound Pallet from Inv - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM prodwms.pckwrk_view WHERE wh_id = 'ID01') p
        WHERE p.last_upd_dt >= '2026-10-20 00:00:00'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc LIKE 'C%A'
          AND p.srcare = 'WHPF-C'
          AND p.pallet_id IS NOT NULL
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        UNION ALL
        
        SELECT
            'LEVEL_OTHER' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM prodwms.pckwrk_view WHERE wh_id = 'ID01') p
        WHERE p.last_upd_dt >= '2026-10-20 00:00:00'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc NOT LIKE 'C%A'
          AND p.srcare = 'WHPF-C'
          AND p.pallet_id IS NOT NULL
          AND p.srcloc NOT IN (
              SELECT DISTINCT stoloc
              FROM (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01') AS locmst
              WHERE CAST(arecod AS NVARCHAR(40)) IN ('~NA~')
          )
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        
        ORDER BY Allocated_FROM, Day, Hour_Of_Day;
