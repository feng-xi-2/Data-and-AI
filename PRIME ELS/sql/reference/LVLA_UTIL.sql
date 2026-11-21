-- LEVEL A UTILISATION (live now): same as LOC_UTIL for the Level A locations (stoloc LIKE LOC_LEVEL_A).
SELECT CAST(COUNT(i.stoloc) AS FLOAT) / NULLIF(COUNT(*), 0) AS v
FROM {S}.locmst l
LEFT JOIN (SELECT DISTINCT stoloc FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') i ON i.stoloc = l.stoloc
WHERE l.wh_id = '{WH_ID}' AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0 AND l.stoloc LIKE '{LOC_LEVEL_A}'
