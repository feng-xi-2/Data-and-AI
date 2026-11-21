-- Outbound Pallet from Inv - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM dbo.pckwrk_view WHERE wh_id = 'BR01') p
        WHERE p.last_upd_dt >= '2026-10-01 00:00:00'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc LIKE '_0%A'
          AND p.srcare = 'BR01-FW'
          AND p.pallet_id IS NOT NULL
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        UNION ALL
        
        SELECT
            'LEVEL_OTHER' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM dbo.pckwrk_view WHERE wh_id = 'BR01') p
        WHERE p.last_upd_dt >= '2026-10-01 00:00:00'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc NOT LIKE '_0%A'
          AND p.srcare = 'BR01-FW'
          AND p.pallet_id IS NOT NULL
          AND p.srcloc NOT IN (
              SELECT DISTINCT stoloc
              FROM (SELECT * FROM dbo.locmst WHERE wh_id = 'BR01') AS locmst
              WHERE CAST(sto_zone_id AS NVARCHAR(40)) IN ('10030')
          )
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        
        ORDER BY Allocated_FROM, Day, Hour_Of_Day;
