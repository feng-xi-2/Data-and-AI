-- Level A Available Pallet Spot - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            l.stoloc,
            l.lstdte AS Date,
            (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END) AS pallet_spots,
            CASE WHEN l.lochgt > 150
                 THEN (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END)
                 ELSE 0
            END AS pallet_spots_height_over_150,
            CASE WHEN l.lochgt <= 150
                 THEN (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END)
                 ELSE 0
            END AS pallet_spots_height_150_or_less,
            l.lochgt AS location_height,
            CASE WHEN l.lochgt > 150 THEN 'OVER_150' ELSE '150_OR_LESS' END AS height_category
        FROM (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01') AS l
        
        WHERE l.useflg = 1
          AND l.stoflg = 1
          AND l.curqvl <= 1
          AND l.maxqvl <= 2
          AND l.pndqvl <= 1
          AND l.stoloc LIKE 'C%A'
        ORDER BY Date DESC, l.stoloc;
