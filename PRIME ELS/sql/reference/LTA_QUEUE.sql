-- LTA QUEUE (live now): distinct pallets currently in an LTA lane.
SELECT COUNT(DISTINCT i.lodnum) AS v
FROM {S}.inventory_view i
WHERE i.wh_id = '{WH_ID}' AND i.stoloc LIKE '{LOC_LTA}'
