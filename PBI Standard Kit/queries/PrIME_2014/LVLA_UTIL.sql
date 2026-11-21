-- LVLA_UTIL - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/LVLA_UTIL.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_LEVEL_A}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- LEVEL A UTILISATION (live now): same as LOC_UTIL for the Level A locations (stoloc LIKE LOC_LEVEL_A).
SELECT CAST(COUNT(i.stoloc) AS FLOAT) / NULLIF(COUNT(*), 0) AS v
FROM prodwms.locmst l
LEFT JOIN (SELECT DISTINCT stoloc FROM prodwms.inventory_view WHERE wh_id = '{WH_ID}') i ON i.stoloc = l.stoloc
WHERE l.wh_id = '{WH_ID}' AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0 AND l.stoloc LIKE '{LOC_LEVEL_A}'
