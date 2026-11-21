-- Shipments - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Shipments (process diagnosis) - outbound shipments created in the last 14 days: WMS status, process stage, open / done, age in the current status
-- Stage_Key / Is_Open / status start from config/shipment_status.csv; Status = WMS description (dscmst). Times are site-local; ages are at Snapshot.
WITH sl AS (
    SELECT l.ship_id, COUNT(*) AS Lines
    FROM (SELECT * FROM dbo.shipment_line WHERE wh_id = 'BR01') AS l
    GROUP BY l.ship_id
), s0 AS (
    SELECT s.ship_id, s.shpsts, s.carcod, s.dstloc, s.adddte, s.alcdte, s.stgdte, s.loddte, s.late_shpdte,
           CASE s.shpsts WHEN 'R' THEN 'O_READY' WHEN 'I' THEN 'O_INPROC' WHEN 'S' THEN 'O_STAGED' WHEN 'L' THEN 'O_LOADING' WHEN 'D' THEN 'O_LOADING' WHEN 'C' THEN 'O_DONE' WHEN 'B' THEN 'O_CANCEL' WHEN 'X' THEN 'O_TRANSFER' ELSE 'O_OTHER' END AS Stage_Key,
           CASE s.shpsts WHEN 'R' THEN 1 WHEN 'I' THEN 1 WHEN 'S' THEN 1 WHEN 'L' THEN 1 WHEN 'D' THEN 1 WHEN 'C' THEN 0 WHEN 'B' THEN 0 WHEN 'X' THEN 0 ELSE 1 END AS Is_Open,
           CASE s.shpsts WHEN 'R' THEN s.adddte WHEN 'I' THEN COALESCE(s.alcdte, s.adddte) WHEN 'S' THEN COALESCE(s.stgdte, s.alcdte, s.adddte) WHEN 'L' THEN COALESCE(s.stgdte, s.alcdte, s.adddte) WHEN 'D' THEN COALESCE(s.loddte, s.stgdte, s.alcdte, s.adddte) WHEN 'C' THEN COALESCE(s.loddte, s.stgdte, s.alcdte, s.adddte) WHEN 'B' THEN s.adddte WHEN 'X' THEN s.adddte ELSE s.adddte END AS Status_Since
    FROM (SELECT * FROM dbo.shipment WHERE wh_id = 'BR01') AS s
    WHERE s.adddte >= DATEADD(DAY, -14, GETDATE()) AND s.adddte >= '2026-10-01 00:00:00'
), n AS (
    SELECT DATEADD(HOUR, 8, GETUTCDATE()) AS Snapshot
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
LEFT JOIN dbo.dscmst AS ds ON ds.colnam = 'shpsts' AND ds.colval = s0.shpsts AND ds.locale_id = 'US_ENGLISH'
