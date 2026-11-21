-- LTA_QUEUE - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/LTA_QUEUE.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_LTA}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- LTA QUEUE (live now): distinct pallets currently in an LTA lane.
SELECT COUNT(DISTINCT i.lodnum) AS v
FROM dbo.inventory_view i
WHERE i.wh_id = '{WH_ID}' AND i.stoloc LIKE '{LOC_LTA}'
