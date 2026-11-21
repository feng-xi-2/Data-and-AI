-- Data Health - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Data Health (KPI #6 daily health check) - replica freshness and retention per source object, for the configured warehouse
SELECT 'dlytrn'  AS Source_Object,
       (SELECT MAX(trndte) FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') AS dlytrn WHERE wh_id = 'ID01')  AS Last_Event_Local,
       (SELECT COUNT_BIG(*) FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') AS dlytrn WHERE wh_id = 'ID01'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') AS dlytrn WHERE wh_id = 'ID01')))  AS Rows_Last_24h,
       SYSUTCDATETIME() AS Db_Utc_Now,
       (SELECT MIN(trndte) FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') AS dlytrn WHERE wh_id = 'ID01')  AS First_Event_Local
UNION ALL
SELECT 'trlract',
       (SELECT MAX(trndte) FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS trlract WHERE wh_id = 'ID01'),
       (SELECT COUNT_BIG(*) FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS trlract WHERE wh_id = 'ID01'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS trlract WHERE wh_id = 'ID01'))),
       SYSUTCDATETIME(),
       (SELECT MIN(trndte) FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS trlract WHERE wh_id = 'ID01')
