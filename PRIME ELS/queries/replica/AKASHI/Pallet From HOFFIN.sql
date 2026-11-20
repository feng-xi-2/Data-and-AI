-- Pallet From HOFFIN - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'HOFF_IN_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE 'CSTCO-IN'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_IN_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE 'CSTCO-IN'
          AND prtnum NOT LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE 'CSTCO-OUT'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'JP01') AS inventory_view
        WHERE stoloc LIKE 'CSTCO-OUT'
          AND prtnum NOT LIKE '8%';
