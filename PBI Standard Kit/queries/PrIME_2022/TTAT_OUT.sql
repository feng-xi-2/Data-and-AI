-- TTAT_OUT - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/TTAT_OUT.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FROM}, {SNAP}, {TO}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- OUTBOUND TTAT: average minutes check-in (TCHKIN) -> close (TCLOSE) of outbound trailers (any code but RCV*) closed in the window.
-- Completed trucks only: check-in, close and dispatch recorded - dispatched by the model snapshot {SNAP} (reconcile_kpis.py).
WITH t AS (
    SELECT a.trlr_id,
           MAX(CASE WHEN a.actcod = 'TCHKIN' THEN a.trndte END) AS chk,
           MAX(CASE WHEN a.actcod = 'TCLOSE' THEN a.trndte END) AS cls,
           MAX(CASE WHEN a.actcod = 'TDSP'   THEN a.trndte END) AS dsp
    FROM dbo.trlract a
    WHERE a.wh_id = '{WH_ID}' AND a.trlr_cod NOT LIKE 'RCV%' AND a.trndte >= DATEADD(DAY, -7, '{FROM}')
    GROUP BY a.trlr_id
)
SELECT AVG(CAST(DATEDIFF(MINUTE, chk, cls) AS FLOAT)) AS v
FROM t WHERE chk IS NOT NULL AND dsp IS NOT NULL
  -- loaded trucks only (BD definition): an empty trailer closed days later is not a truck turnaround (20-Nov Jakarta TRL0294709, 0 pallets, 36 h)
  AND EXISTS (SELECT 1 FROM dbo.dlytrn d WHERE d.wh_id = '{WH_ID}' AND d.tostol = t.trlr_id AND d.lodnum IS NOT NULL) AND dsp < '{SNAP}' AND cls >= '{FROM}' AND cls < '{TO}'
