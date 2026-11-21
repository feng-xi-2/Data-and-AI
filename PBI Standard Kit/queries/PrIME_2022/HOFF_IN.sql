-- HOFF_IN - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/HOFF_IN.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {LOC_HOFF_IN}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- HOFF IN (live now): distinct pallets currently staged in a HOFF IN location.
SELECT COUNT(DISTINCT i.lodnum) AS v
FROM dbo.inventory_view i
WHERE i.wh_id = '{WH_ID}' AND i.stoloc LIKE '{LOC_HOFF_IN}'
