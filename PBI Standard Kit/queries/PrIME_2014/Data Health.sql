-- Data Health - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Data Health.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- Data Health (KPI #6 daily health check) - replica freshness and retention per source object, for the configured warehouse
SELECT 'dlytrn'  AS Source_Object,
       (SELECT MAX(trndte) FROM prodwms.dlytrn WHERE wh_id = '{WH_ID}')  AS Last_Event_Local,
       (SELECT COUNT_BIG(*) FROM prodwms.dlytrn WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM prodwms.dlytrn WHERE wh_id = '{WH_ID}')))  AS Rows_Last_24h,
       SYSUTCDATETIME() AS Db_Utc_Now,
       (SELECT MIN(trndte) FROM prodwms.dlytrn WHERE wh_id = '{WH_ID}')  AS First_Event_Local
UNION ALL
SELECT 'trlract',
       (SELECT MAX(trndte) FROM prodwms.trlract WHERE wh_id = '{WH_ID}'),
       (SELECT COUNT_BIG(*) FROM prodwms.trlract WHERE wh_id = '{WH_ID}'
          AND trndte >= DATEADD(HOUR, -24, (SELECT MAX(trndte) FROM prodwms.trlract WHERE wh_id = '{WH_ID}'))),
       SYSUTCDATETIME(),
       (SELECT MIN(trndte) FROM prodwms.trlract WHERE wh_id = '{WH_ID}')
