-- Data Health - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Data Health.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- Data Health (KPI #6 daily health check) - replica freshness and retention per source object, for the configured warehouse
SELECT 'dlytrn'  AS Source_Object,
       (SELECT MAX(trndte) FROM dbo.dlytrn WHERE wh_id = '{WH_ID}')  AS Last_Event_Local,
       (SELECT COUNT_BIG(*) FROM dbo.dlytrn WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM dbo.dlytrn WHERE wh_id = '{WH_ID}')))  AS Rows_Last_24h,
       SYSUTCDATETIME() AS Db_Utc_Now,
       (SELECT MIN(trndte) FROM dbo.dlytrn WHERE wh_id = '{WH_ID}')  AS First_Event_Local
UNION ALL
SELECT 'trlract',
       (SELECT MAX(trndte) FROM dbo.trlract WHERE wh_id = '{WH_ID}'),
       (SELECT COUNT_BIG(*) FROM dbo.trlract WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM dbo.trlract WHERE wh_id = '{WH_ID}'))),
       SYSUTCDATETIME(),
       (SELECT MIN(trndte) FROM dbo.trlract WHERE wh_id = '{WH_ID}')
