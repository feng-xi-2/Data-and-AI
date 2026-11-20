-- LOCATION UTILISATION (live now): usable storage locations (useflg = 1, stoflg = 1, capacity > 0) that hold inventory
-- (inventory_view, not the curqvl counter) / all usable storage locations.
SELECT CAST(COUNT(i.stoloc) AS FLOAT) / NULLIF(COUNT(*), 0) AS v
FROM {S}.locmst l
LEFT JOIN (SELECT DISTINCT stoloc FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') i ON i.stoloc = l.stoloc
WHERE l.wh_id = '{WH_ID}' AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0
