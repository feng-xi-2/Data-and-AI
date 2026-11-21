-- INBOUND TTAT: average minutes check-in (TCHKIN) -> dispatch (TDSP) of inbound trailers (RCV*) dispatched in the window.
-- Processed trucks only: check-in, close (goods receipt finished) and dispatch recorded.
WITH t AS (
    SELECT a.trlr_id,
           MAX(CASE WHEN a.actcod = 'TCHKIN' THEN a.trndte END) AS chk,
           MAX(CASE WHEN a.actcod = 'TDSP'   THEN a.trndte END) AS dsp,
           MAX(CASE WHEN a.actcod = 'TCLOSE' THEN a.trndte END) AS cls
    FROM {S}.trlract a
    WHERE a.wh_id = '{WH_ID}' AND a.trlr_cod LIKE 'RCV%' AND a.trndte >= DATEADD(DAY, -7, '{FROM}')
    GROUP BY a.trlr_id
)
SELECT AVG(CAST(DATEDIFF(MINUTE, chk, dsp) AS FLOAT)) AS v
FROM t WHERE chk IS NOT NULL AND cls IS NOT NULL AND dsp >= '{FROM}' AND dsp < '{TO}'
