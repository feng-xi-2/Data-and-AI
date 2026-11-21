-- TTAT_IN - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/TTAT_IN.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FROM}, {TO}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- INBOUND TTAT: average minutes check-in (TCHKIN) -> dispatch (TDSP) of inbound trailers (RCV*) dispatched in the window.
-- Processed trucks only: check-in, close (goods receipt finished) and dispatch recorded.
WITH t AS (
    SELECT a.trlr_id,
           MAX(CASE WHEN a.actcod = 'TCHKIN' THEN a.trndte END) AS chk,
           MAX(CASE WHEN a.actcod = 'TDSP'   THEN a.trndte END) AS dsp,
           MAX(CASE WHEN a.actcod = 'TCLOSE' THEN a.trndte END) AS cls
    FROM dbo.trlract a
    WHERE a.wh_id = '{WH_ID}' AND a.trlr_cod LIKE 'RCV%' AND a.trndte >= DATEADD(DAY, -7, '{FROM}')
    GROUP BY a.trlr_id
)
SELECT AVG(CAST(DATEDIFF(MINUTE, chk, dsp) AS FLOAT)) AS v
FROM t WHERE chk IS NOT NULL AND cls IS NOT NULL AND dsp >= '{FROM}' AND dsp < '{TO}'
