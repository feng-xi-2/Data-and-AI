-- Shipments - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Shipments.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {ACT_DAYS}, {PRTDSC_LOCALE}, {SHIPMENT_OPEN_CASE}, {SHIPMENT_SINCE_CASE}, {SHIPMENT_STAGE_CASE}, {START_DT} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- Shipments (process diagnosis) - outbound shipments created in the last {ACT_DAYS} days: WMS status, process stage, open / done, age in the current status
-- Stage_Key / Is_Open / status start from config/shipment_status.csv; Status = WMS description (dscmst). Times are site-local; ages are at Snapshot.
WITH sl AS (
    SELECT l.ship_id, COUNT(*) AS Lines
    FROM prodwms.shipment_line AS l
    GROUP BY l.ship_id
), s0 AS (
    SELECT s.ship_id, s.shpsts, s.carcod, s.dstloc, s.adddte, s.alcdte, s.stgdte, s.loddte, s.late_shpdte,
           {{SHIPMENT_STAGE_CASE}} AS Stage_Key,
           {{SHIPMENT_OPEN_CASE}} AS Is_Open,
           {{SHIPMENT_SINCE_CASE}} AS Status_Since
    FROM prodwms.shipment AS s
    WHERE s.adddte >= DATEADD(DAY, -{ACT_DAYS}, GETDATE()) AND s.adddte >= '{START_DT}'
), n AS (
    SELECT DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) AS Snapshot
)
SELECT s0.ship_id                                        AS Shipment,
       s0.shpsts                                         AS [Status Code],
       COALESCE(ds.lngdsc, s0.shpsts)                    AS Status,
       s0.Stage_Key,
       s0.Is_Open,
       s0.carcod                                         AS Carrier,
       s0.dstloc                                         AS [Dest Location],
       s0.adddte                                         AS Created,
       CAST(s0.adddte AS DATE)                           AS [Created Date],
       s0.alcdte                                         AS Allocated,
       s0.stgdte                                         AS Staged,
       s0.loddte                                         AS Loaded,
       s0.late_shpdte                                    AS [Late Ship],
       COALESCE(sl.Lines, 0)                             AS Lines,
       s0.Status_Since                                   AS [Status Since],
       DATEDIFF(MINUTE, s0.Status_Since, n.Snapshot)     AS [Minutes In Status],
       DATEDIFF(MINUTE, s0.adddte, n.Snapshot)           AS [Minutes Since Created],
       CASE WHEN s0.Is_Open = 1 AND s0.late_shpdte < n.Snapshot THEN 1 ELSE 0 END AS Is_Late,
       n.Snapshot
FROM s0
CROSS JOIN n
LEFT JOIN sl ON sl.ship_id = s0.ship_id
LEFT JOIN prodwms.dscmst AS ds ON ds.colnam = 'shpsts' AND ds.colval = s0.shpsts AND ds.locale_id = '{PRTDSC_LOCALE}'
