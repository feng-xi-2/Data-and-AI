-- Location Utilisation - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Location Utilisation (KPI #4 warehouse space) - generic for every PrIME 2014 / 2022 site
SELECT
    l.arecod                                                                AS Area,
    CASE WHEN l.stoloc LIKE 'F0%A' THEN 'Level A' ELSE 'Other' END AS Level_Class,
    CASE WHEN l.lochgt > 150 THEN 'TALL' ELSE 'SHORT' END      AS Height_Class,
    COUNT(*)                                                                AS Locations,
    SUM(CASE WHEN l.curqvl > 0 OR l.pndqvl > 0 THEN 1 ELSE 0 END)           AS Occupied_Locations,
    SUM(CAST(l.maxqvl AS DECIMAL(18,2)))                                    AS Capacity_Qvl,
    SUM(CAST(l.curqvl + l.pndqvl AS DECIMAL(18,2)))                         AS Used_Qvl,
    SUM(CASE WHEN l.maxqvl - (l.curqvl + l.pndqvl) > 0
             THEN CAST(l.maxqvl - (l.curqvl + l.pndqvl) AS DECIMAL(18,2)) ELSE 0 END) AS Free_Qvl
FROM (SELECT * FROM dbo.locmst WHERE wh_id = 'VN07') AS l
WHERE l.wh_id = 'VN07'
  AND l.useflg = 1
  AND l.stoflg = 1
  AND l.maxqvl > 0
GROUP BY l.arecod,
         CASE WHEN l.stoloc LIKE 'F0%A' THEN 'Level A' ELSE 'Other' END,
         CASE WHEN l.lochgt > 150 THEN 'TALL' ELSE 'SHORT' END
