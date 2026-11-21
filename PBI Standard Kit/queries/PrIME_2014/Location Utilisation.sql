-- Location Utilisation - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Location Utilisation.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_LEVEL_A}, {TALL_HEIGHT_CM}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

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
FROM prodwms.locmst AS l
WHERE l.wh_id = '{WH_ID}'
  AND l.useflg = 1
  AND l.stoflg = 1
  AND l.maxqvl > 0
GROUP BY l.arecod,
         CASE WHEN l.stoloc LIKE '{LOC_LEVEL_A}' THEN 'Level A' ELSE 'Other' END,
         CASE WHEN l.lochgt > {TALL_HEIGHT_CM} THEN 'TALL' ELSE 'SHORT' END
