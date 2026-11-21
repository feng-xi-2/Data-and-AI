-- LTA_QUEUE - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/LTA_QUEUE.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_LTA}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- LTA QUEUE (live now): distinct pallets currently in an LTA lane.
SELECT COUNT(DISTINCT i.lodnum) AS v
FROM prodwms.inventory_view i
WHERE i.wh_id = '{WH_ID}' AND i.stoloc LIKE '{LOC_LTA}'
