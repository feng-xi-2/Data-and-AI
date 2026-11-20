-- Level A Occupied Pallet - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '_0%A'
          AND prtnum LIKE '[689]%'
        
        UNION ALL
        
        SELECT
            'LEVEL_A_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '_0%A'
          AND prtnum NOT LIKE '[689]%'
        
        UNION ALL
        
        SELECT
            'PROBLEM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE 'PROB%';
