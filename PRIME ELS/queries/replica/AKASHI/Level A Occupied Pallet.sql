-- Level A Occupied Pallet - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'LEVEL_A_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum NOT LIKE '8%'
        
        UNION ALL
        
        SELECT
            'PROBLEM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE 'PROB%';
