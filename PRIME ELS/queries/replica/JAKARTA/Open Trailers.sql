-- Open Trailers - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Open Trailers (process diagnosis) - trailers on site now (checked in, not dispatched): process stage, door / yard, minutes on site and in the current status
-- Stage_Key from config/trailer_status.csv (WMS trlr_stat -> process stage); Status = WMS description (dscmst). Times are site-local; ages are at Snapshot.
WITH a AS (
    SELECT t.TRLR_ID,
           MAX(CONVERT(DATETIME, t.TRNDTE))                                   AS Last_Change,
           MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS Checkin
    FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS t
    WHERE t.TRNDTE >= '2026-10-20 00:00:00'
    GROUP BY t.TRLR_ID
), r0 AS (
    SELECT r.TRLR_ID, r.TRLR_NUM, r.CARCOD, r.TRLR_COD, r.TRLR_STAT, r.YARD_LOC, r.STOLOC, r.ARRDTE,
           CASE WHEN r.TRLR_COD LIKE 'RCV%' THEN CASE r.TRLR_STAT WHEN 'OR' THEN 'T_IN_YARD' WHEN 'CI' THEN 'T_IN_YARD' WHEN 'PFL' THEN 'T_IN_YARD' WHEN 'PTL' THEN 'T_IN_YARD' WHEN 'R' THEN 'T_IN_UNLOAD' WHEN 'UNLD' THEN 'T_IN_UNLOAD' WHEN 'SUSP' THEN 'T_IN_UNLOAD' WHEN 'C' THEN 'T_IN_CLOSE' WHEN 'P' THEN 'T_IN_CLOSE' END
             ELSE CASE r.TRLR_STAT WHEN 'O' THEN 'T_OUT_YARD' WHEN 'OLDG' THEN 'T_OUT_YARD' WHEN 'CI' THEN 'T_OUT_YARD' WHEN 'PFL' THEN 'T_OUT_YARD' WHEN 'PTL' THEN 'T_OUT_YARD' WHEN 'LDG' THEN 'T_OUT_LOAD' WHEN 'SUSP' THEN 'T_OUT_LOAD' WHEN 'L' THEN 'T_OUT_CLOSE' WHEN 'C' THEN 'T_OUT_CLOSE' WHEN 'P' THEN 'T_OUT_CLOSE' END END AS Stage_Key
    FROM prodwms.trlr AS r
    WHERE r.TRLR_ID IN (SELECT TRLR_ID FROM a)
), n AS (
    SELECT DATEADD(HOUR, 7, GETUTCDATE()) AS Snapshot
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
       (SELECT COUNT(DISTINCT iv.lodnum) FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS iv WHERE iv.stoloc = r0.TRLR_ID) AS [Pallets On Trailer],
       n.Snapshot
FROM r0
JOIN a ON a.TRLR_ID = r0.TRLR_ID
CROSS JOIN n
LEFT JOIN prodwms.dscmst AS ds ON ds.colnam = 'trlr_stat' AND ds.colval = r0.TRLR_STAT AND ds.locale_id = 'US_ENGLISH'
WHERE r0.Stage_Key IS NOT NULL
