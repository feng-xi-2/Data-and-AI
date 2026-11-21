-- Data Health (KPI #6 daily health check) - replica freshness and retention per source object, for the configured warehouse
SELECT 'dlytrn'  AS Source_Object,
       (SELECT MAX(trndte) FROM {S}.dlytrn WHERE wh_id = '{WH_ID}')  AS Last_Event_Local,
       (SELECT COUNT_BIG(*) FROM {S}.dlytrn WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM {S}.dlytrn WHERE wh_id = '{WH_ID}')))  AS Rows_Last_24h,
       SYSUTCDATETIME() AS Db_Utc_Now,
       (SELECT MIN(trndte) FROM {S}.dlytrn WHERE wh_id = '{WH_ID}')  AS First_Event_Local
UNION ALL
SELECT 'trlract',
       (SELECT MAX(trndte) FROM {S}.trlract WHERE wh_id = '{WH_ID}'),
       (SELECT COUNT_BIG(*) FROM {S}.trlract WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM {S}.trlract WHERE wh_id = '{WH_ID}'))),
       SYSUTCDATETIME(),
       (SELECT MIN(trndte) FROM {S}.trlract WHERE wh_id = '{WH_ID}')
