-- HOFF IN (live now): distinct pallets currently staged in a HOFF IN location.
SELECT COUNT(DISTINCT i.lodnum) AS v
FROM {S}.inventory_view i
WHERE i.wh_id = '{WH_ID}' AND i.stoloc LIKE '{LOC_HOFF_IN}'
