-- Pallet From HOFFIN - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'HOFF_IN_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_IN_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum NOT LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE '~NA~'
          AND prtnum NOT LIKE '8%';
