-- PROD_PALLETS - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/PROD_PALLETS.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FG_PRTNUM_LIKE}, {FROM}, {PROD_LEFT_REF}, {PROD_TXN_FILTER}, {TO}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- PRODUCED PALLETS (Prod Pallets Day -> PPH): distinct pallets produced in the window.
-- LTA take-away sites: the pallet LEAVES an LTA lane (PROD_LEFT_COND on the transaction itself); work-order sites
-- (PROD_LEFT_COND = LTA_SOURCE): the pallet is RECEIVED from a work order (PROD_SCOPE). Each pallet counted once.
SELECT COUNT(DISTINCT d.lodnum) AS v
FROM dbo.dlytrn d
WHERE d.wh_id = '{WH_ID}' AND d.trndte >= '{FROM}' AND d.trndte < '{TO}'
  AND d.lodnum IS NOT NULL
  AND d.prtnum LIKE '{FG_PRTNUM_LIKE}'                -- finished goods only, as the model (20-Nov Jakarta: 46 material pallets from work orders are not FG)
  AND ({PROD_TXN_FILTER})
  AND ({PROD_LEFT_REF})
