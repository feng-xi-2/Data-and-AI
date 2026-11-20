-- Data Health - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:24 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Data Health (KPI #6 daily health check) - replica freshness and retention per source object, for the configured warehouse
SELECT 'dlytrn'  AS Source_Object,
       (SELECT MAX(trndte) FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') AS dlytrn WHERE wh_id = 'JP01')  AS Last_Event_Local,
       (SELECT COUNT_BIG(*) FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') AS dlytrn WHERE wh_id = 'JP01'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') AS dlytrn WHERE wh_id = 'JP01')))  AS Rows_Last_24h,
       SYSUTCDATETIME() AS Db_Utc_Now,
       (SELECT MIN(trndte) FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') AS dlytrn WHERE wh_id = 'JP01')  AS First_Event_Local
UNION ALL
SELECT 'trlract',
       (SELECT MAX(trndte) FROM (SELECT * FROM dbo.trlract WHERE wh_id = 'JP01') AS trlract WHERE wh_id = 'JP01'),
       (SELECT COUNT_BIG(*) FROM (SELECT * FROM dbo.trlract WHERE wh_id = 'JP01') AS trlract WHERE wh_id = 'JP01'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM (SELECT * FROM dbo.trlract WHERE wh_id = 'JP01') AS trlract WHERE wh_id = 'JP01'))),
       SYSUTCDATETIME(),
       (SELECT MIN(trndte) FROM (SELECT * FROM dbo.trlract WHERE wh_id = 'JP01') AS trlract WHERE wh_id = 'JP01')
