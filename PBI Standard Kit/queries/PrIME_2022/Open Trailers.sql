-- Open Trailers - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Open Trailers.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {PRTDSC_LOCALE}, {START_DT}, {TRAILER_STAGE_CASE} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- Open Trailers (process diagnosis) - trailers on site now (checked in, not dispatched): process stage, door / yard, minutes on site and in the current status
-- Stage_Key from config/trailer_status.csv (WMS trlr_stat -> process stage); Status = WMS description (dscmst). Times are site-local; ages are at Snapshot.
WITH a AS (
    SELECT t.TRLR_ID,
           MAX(CONVERT(DATETIME, t.TRNDTE))                                   AS Last_Change,
           MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS Checkin
    FROM dbo.trlract AS t
    WHERE t.TRNDTE >= '{START_DT}'
    GROUP BY t.TRLR_ID
), r0 AS (
    SELECT r.TRLR_ID, r.TRLR_NUM, r.CARCOD, r.TRLR_COD, r.TRLR_STAT, r.YARD_LOC, r.STOLOC, r.ARRDTE,
           {{TRAILER_STAGE_CASE}} AS Stage_Key
    FROM dbo.trlr AS r
    WHERE r.TRLR_ID IN (SELECT TRLR_ID FROM a)
), n AS (
    SELECT DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) AS Snapshot
)
SELECT r0.TRLR_ID                                                          AS TrailerID,
       r0.TRLR_NUM                                                         AS [Trailer Number],
       r0.CARCOD                                                           AS Carrier,
       CASE WHEN r0.TRLR_COD LIKE 'RCV%' THEN 'Inbound' ELSE 'Outbound' END AS Direction,
       r0.TRLR_COD                                                         AS [Trailer Code],
       r0.TRLR_STAT                                                        AS [Status Code],
       COALESCE(ds.lngdsc, r0.TRLR_STAT)                                   AS Status,
       r0.Stage_Key,
       COALESCE(r0.YARD_LOC, r0.STOLOC)                                    AS [Door / Yard],
       COALESCE(a.Checkin, CONVERT(DATETIME, r0.ARRDTE))                   AS [Check-in],
       a.Last_Change                                                       AS [Last Status Change],
       DATEDIFF(MINUTE, COALESCE(a.Checkin, CONVERT(DATETIME, r0.ARRDTE), a.Last_Change), n.Snapshot) AS [Minutes On Site],
       DATEDIFF(MINUTE, a.Last_Change, n.Snapshot)                         AS [Minutes In Status],
       (SELECT COUNT(DISTINCT iv.lodnum) FROM dbo.inventory_view AS iv WHERE iv.stoloc = r0.TRLR_ID) AS [Pallets On Trailer],
       n.Snapshot
FROM r0
JOIN a ON a.TRLR_ID = r0.TRLR_ID
CROSS JOIN n
LEFT JOIN dbo.dscmst AS ds ON ds.colnam = 'trlr_stat' AND ds.colval = r0.TRLR_STAT AND ds.locale_id = '{PRTDSC_LOCALE}'
WHERE r0.Stage_Key IS NOT NULL
