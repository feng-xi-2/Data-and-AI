-- PRODUCED PALLETS (Prod Pallets Day -> PPH): distinct pallets produced in the window.
-- LTA take-away sites: the pallet LEAVES an LTA lane (PROD_LEFT_COND on the transaction itself); work-order sites
-- (PROD_LEFT_COND = LTA_SOURCE): the pallet is RECEIVED from a work order (PROD_SCOPE). Each pallet counted once.
SELECT COUNT(DISTINCT d.lodnum) AS v
FROM {S}.dlytrn d
WHERE d.wh_id = '{WH_ID}' AND d.trndte >= '{FROM}' AND d.trndte < '{TO}'
  AND d.lodnum IS NOT NULL
  AND ({PROD_TXN_FILTER})
  AND ({PROD_LEFT_REF})
