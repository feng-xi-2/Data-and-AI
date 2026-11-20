-- Level A Occupied Pallet - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            'LEVEL_A_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE 'C%A'
          AND prtnum LIKE '8%'
        
        UNION ALL
        
        SELECT
            'LEVEL_A_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE 'C%A'
          AND prtnum NOT LIKE '8%'
        
        UNION ALL
        
        SELECT
            'PROBLEM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS inventory_view
        WHERE stoloc LIKE '~NA~';
