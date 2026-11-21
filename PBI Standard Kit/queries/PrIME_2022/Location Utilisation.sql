-- Location Utilisation - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Location Utilisation.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_LEVEL_A}, {TALL_HEIGHT_CM}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- Location Utilisation (KPI #4 warehouse space) - generic for every PrIME 2014 / 2022 site
SELECT
    l.arecod                                                                AS Area,
    CASE WHEN l.stoloc LIKE '{LOC_LEVEL_A}' THEN 'Level A' ELSE 'Other' END AS Level_Class,
    CASE WHEN l.lochgt > {TALL_HEIGHT_CM} THEN 'TALL' ELSE 'SHORT' END      AS Height_Class,
    COUNT(*)                                                                AS Locations,
    SUM(CASE WHEN l.curqvl > 0 OR l.pndqvl > 0 THEN 1 ELSE 0 END)           AS Occupied_Locations,
    SUM(CAST(l.maxqvl AS DECIMAL(18,2)))                                    AS Capacity_Qvl,
    SUM(CAST(l.curqvl + l.pndqvl AS DECIMAL(18,2)))                         AS Used_Qvl,
    SUM(CASE WHEN l.maxqvl - (l.curqvl + l.pndqvl) > 0
             THEN CAST(l.maxqvl - (l.curqvl + l.pndqvl) AS DECIMAL(18,2)) ELSE 0 END) AS Free_Qvl
FROM dbo.locmst AS l
WHERE l.wh_id = '{WH_ID}'
  AND l.useflg = 1
  AND l.stoflg = 1
  AND l.maxqvl > 0
GROUP BY l.arecod,
         CASE WHEN l.stoloc LIKE '{LOC_LEVEL_A}' THEN 'Level A' ELSE 'Other' END,
         CASE WHEN l.lochgt > {TALL_HEIGHT_CM} THEN 'TALL' ELSE 'SHORT' END
