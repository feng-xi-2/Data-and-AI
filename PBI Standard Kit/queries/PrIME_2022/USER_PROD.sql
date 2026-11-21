-- USER_PROD - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/USER_PROD.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FROM}, {TO}, {USR_EXCLUDE}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- USER PRODUCTIVITY: pallets moved per active user-hour = SUM over (user, hour) of DISTINCT pallets / number of (user, hour)
-- pairs with activity. A pallet touched twice by the same user in the same hour (e.g. pick + deposit) counts once.
WITH uh AS (
    SELECT d.usr_id, CAST(d.trndte AS DATE) AS dy, DATEPART(HOUR, d.trndte) AS hr, COUNT(DISTINCT d.lodnum) AS plt
    FROM dbo.dlytrn d
    WHERE d.wh_id = '{WH_ID}' AND d.trndte >= '{FROM}' AND d.trndte < '{TO}'
      AND d.usr_id IS NOT NULL AND d.usr_id NOT IN ({USR_EXCLUDE}) AND d.lodnum IS NOT NULL
      AND d.actcod NOT IN ('LOCSTSCHG','ATELOCSETAUTO','ATELOCCLRAUTO','INVSTSCHG','LOTDATECHANGED','LOCOVRRID','WRKSUSP','ENG_EXEMP_CHG')
    GROUP BY d.usr_id, CAST(d.trndte AS DATE), DATEPART(HOUR, d.trndte)
)
SELECT CAST(SUM(plt) AS FLOAT) / NULLIF(COUNT(*), 0) AS v FROM uh
