-- LOC_UTIL - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/LOC_UTIL.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- LOCATION UTILISATION (live now): usable storage locations (useflg = 1, stoflg = 1, capacity > 0) that hold inventory
-- (inventory_view, not the curqvl counter) / all usable storage locations.
SELECT CAST(COUNT(i.stoloc) AS FLOAT) / NULLIF(COUNT(*), 0) AS v
FROM dbo.locmst l
LEFT JOIN (SELECT DISTINCT stoloc FROM dbo.inventory_view WHERE wh_id = '{WH_ID}') i ON i.stoloc = l.stoloc
WHERE l.wh_id = '{WH_ID}' AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0
