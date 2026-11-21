-- Pallet From HOFFIN - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'HOFF_IN_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum LIKE '[689]%'
        
        UNION ALL
        
        SELECT
            'HOFF_IN_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum NOT LIKE '[689]%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum LIKE '[689]%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum NOT LIKE '[689]%';
