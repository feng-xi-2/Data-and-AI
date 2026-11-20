-- Level A Available Pallet Spot - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
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
        FROM (SELECT * FROM dbo.locmst WHERE wh_id = 'JP01') AS l
        INNER JOIN dbo.sto_zone AS k ON k.sto_zone_id = l.sto_zone_id
        WHERE l.useflg = 1
          AND l.stoflg = 1
          AND l.curqvl <= 1
          AND l.maxqvl <= 2
          AND l.pndqvl <= 1
          AND l.stoloc LIKE '~NA~'
        ORDER BY Date DESC, l.stoloc;
