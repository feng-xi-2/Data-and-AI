-- OUTBOUND TTAT: average minutes check-in (TCHKIN) -> close (TCLOSE) of outbound trailers (any code but RCV*) closed in the window.
-- Completed trucks only: check-in, close and dispatch recorded - dispatched by the model snapshot {SNAP} (reconcile_kpis.py).
WITH t AS (
    SELECT a.trlr_id,
           MAX(CASE WHEN a.actcod = 'TCHKIN' THEN a.trndte END) AS chk,
           MAX(CASE WHEN a.actcod = 'TCLOSE' THEN a.trndte END) AS cls,
           MAX(CASE WHEN a.actcod = 'TDSP'   THEN a.trndte END) AS dsp
    FROM {S}.trlract a
    WHERE a.wh_id = '{WH_ID}' AND a.trlr_cod NOT LIKE 'RCV%' AND a.trndte >= DATEADD(DAY, -7, '{FROM}')
    GROUP BY a.trlr_id
)
SELECT AVG(CAST(DATEDIFF(MINUTE, chk, cls) AS FLOAT)) AS v
FROM t WHERE chk IS NOT NULL AND dsp IS NOT NULL AND dsp < '{SNAP}' AND cls >= '{FROM}' AND cls < '{TO}'
