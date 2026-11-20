-- TTAT - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
WITH 
-- ============================================
-- 1) INBOUND TRAILERS
-- ============================================
InboundTrailers AS (
    SELECT 
        'Inbound' AS [Direction],
        CAST(NULL AS NVARCHAR(20)) AS [Trailer Type],
        t.TRLR_ID       AS [TrailerID],
        MAX(t.TRLR_NUM) AS [Trailer Number],
        MAX(t.TRKNUM)   AS [Truck Number],
        CAST(NULL AS NVARCHAR(50)) AS [Load],
        CAST(NULL AS NVARCHAR(100)) AS [Route To],
        CAST(NULL AS NVARCHAR(50)) AS [Dock ID],
        
        MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Check-in],
        MIN(CONVERT(DATETIME, d.TRNDTE)) AS [First Scan / Start Loading],
        CAST(NULL AS DATETIME) AS [End Loading],
        MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Close],
        MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Dispatch],
        
        CAST(MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Check-in Date],
        CAST(MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Close Date],
        CAST(MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Dispatch Date],
        
        DATEDIFF(MINUTE,
            MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END),
            MIN(CONVERT(DATETIME, d.TRNDTE))
        ) AS [Scan - Checkin (Minutes)],
        
        DATEDIFF(MINUTE,
            MIN(CONVERT(DATETIME, d.TRNDTE)),
            MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END)
        ) AS [Process Time (Minutes)],
        
        DATEDIFF(MINUTE,
            MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END),
            MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END)
        ) AS [TTAT (Minutes)]
    
    FROM (SELECT a.TRLR_ID, a.TRLR_NUM, a.ACTCOD, a.TRNDTE, a.TRLR_COD, a.TRKNUM, rt.trknum AS RCV_TRKNUM FROM dbo.TRLRACT a LEFT JOIN dbo.rcvtrk rt ON rt.trlr_id = a.TRLR_ID AND rt.wh_id = a.WH_ID WHERE a.WH_ID = 'BR01') t
    LEFT JOIN (SELECT * FROM dbo.DLYTRN WHERE wh_id = 'BR01') d ON d.FRSTOL = t.RCV_TRKNUM
    WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= '2026-10-01 00:00:00'
      AND t.ACTCOD IN ('TCHKIN', 'TCLOSE', 'TDSP')
    GROUP BY t.TRLR_ID
    HAVING 
        MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
        AND MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
        AND MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
),

-- ============================================
-- 2) OUTBOUND TRAILERS
-- ============================================
OutboundTrailers AS (
    SELECT 
        'Outbound' AS [Direction],
        CASE 
            WHEN MAX(t.TRLR_COD) LIKE 'STO' THEN 'Fast Lanes'
            ELSE 'Normal Shipping'
        END AS [Trailer Type],
        t.TRLR_ID       AS [TrailerID],
        MAX(t.TRLR_NUM) AS [Trailer Number],
        CAST(NULL AS NVARCHAR(50)) AS [Truck Number],
        MAX(t.CAR_MOVE_ID) AS [Load],
        MAX(adrmst.ctry_name) AS [Route To],
        MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN t.YARD_LOC END) AS [Dock ID],
        
        MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Check-in],
        MIN(CONVERT(DATETIME, d.TRNDTE)) AS [First Scan / Start Loading],
        MAX(CASE WHEN t.TRLR_STAT LIKE 'L%' AND t.ACTCOD LIKE 'TL%' 
             THEN CONVERT(DATETIME, t.TRNDTE) END) AS [End Loading],
        MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Close],
        MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) AS [Dispatch],
        
        CAST(MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Check-in Date],
        CAST(MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Close Date],
        CAST(MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) AS DATE) AS [Dispatch Date],
        
        DATEDIFF(MINUTE,
            MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END),
            MIN(CONVERT(DATETIME, d.TRNDTE))
        ) AS [Scan - Checkin (Minutes)],
        
        DATEDIFF(MINUTE,
            MIN(CONVERT(DATETIME, d.TRNDTE)),
            MAX(CASE WHEN t.TRLR_STAT LIKE 'L%' AND t.ACTCOD LIKE 'TL%' 
                 THEN CONVERT(DATETIME, t.TRNDTE) END)
        ) AS [Process Time (Minutes)],
        
        DATEDIFF(MINUTE,
            MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END),
            MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END)
        ) AS [TTAT (Minutes)]
    
    FROM (SELECT * FROM dbo.TRLRACT WHERE wh_id = 'BR01') t
    LEFT JOIN (SELECT * FROM dbo.DLYTRN WHERE wh_id = 'BR01') d   ON t.TRLR_ID = d.TOSTOL
    LEFT JOIN (SELECT * FROM dbo.ord WHERE wh_id = 'BR01') AS ord        ON t.CAR_MOVE_ID = ord.vc_car_move_id
    LEFT JOIN dbo.adrmst     ON ord.rt_adr_id = adrmst.adr_id
    WHERE t.TRNDTE >= '2026-10-01 00:00:00' AND (
        (t.TRLR_COD LIKE 'SHIP' AND (t.ACTCOD IN ('TCHKIN','TCLOSE','TDSP') OR t.ACTCOD LIKE 'TL%'))
        OR
        (t.TRLR_COD LIKE 'STO'  AND (t.ACTCOD IN ('TCHKIN','TCLOSE','TDSP') OR t.ACTCOD LIKE 'TL%'))
    )
    GROUP BY t.TRLR_ID
    HAVING 
        MIN(CONVERT(DATETIME, d.TRNDTE)) IS NOT NULL
        AND MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
        AND MAX(CASE WHEN t.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
        AND MAX(CASE WHEN t.TRLR_STAT LIKE 'L%' AND t.ACTCOD LIKE 'TL%' 
                 THEN CONVERT(DATETIME, t.TRNDTE) END) IS NOT NULL
),

-- ============================================
-- 3) GCAS BREAKDOWN — INBOUND
-- ============================================
GcasInbound AS (
    SELECT 
        'Inbound'                   AS [Direction],
        t.TRLR_ID                   AS TrailerID,
        d.prtnum                    AS GCAS,
        COUNT(DISTINCT d.lodnum)    AS PalletsForGcas
    FROM (SELECT a.TRLR_ID, a.TRLR_NUM, a.ACTCOD, a.TRNDTE, a.TRLR_COD, a.TRKNUM, rt.trknum AS RCV_TRKNUM FROM dbo.TRLRACT a LEFT JOIN dbo.rcvtrk rt ON rt.trlr_id = a.TRLR_ID AND rt.wh_id = a.WH_ID WHERE a.WH_ID = 'BR01') t
    JOIN (SELECT * FROM dbo.dlytrn WHERE wh_id = 'BR01') d ON d.FRSTOL = t.RCV_TRKNUM
    WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= '2026-10-01 00:00:00'
      AND d.lodnum IS NOT NULL
      AND d.prtnum IS NOT NULL
    GROUP BY t.TRLR_ID, d.prtnum
),

-- ============================================
-- 4) GCAS BREAKDOWN — OUTBOUND
-- ============================================
GcasOutbound AS (
    SELECT 
        'Outbound'                  AS [Direction],
        tr.trlr_id                  AS TrailerID,
        d.prtnum                    AS GCAS,
        COUNT(DISTINCT d.lodnum)    AS PalletsForGcas
    FROM dbo.trlr AS tr
    JOIN (SELECT * FROM dbo.dlytrn WHERE wh_id = 'BR01') AS d ON tr.trlr_id = d.tostol
    WHERE d.lodnum IS NOT NULL AND d.trndte >= '2026-10-01 00:00:00'
      AND d.prtnum IS NOT NULL
    GROUP BY tr.trlr_id, d.prtnum
),

-- ============================================
-- 5) COMBINED GCAS
-- ============================================
GcasCombined AS (
    SELECT * FROM GcasInbound
    UNION ALL
    SELECT * FROM GcasOutbound
),

-- ============================================
-- 6) COMBINED TRAILERS
-- ============================================
AllTrailers AS (
    SELECT * FROM InboundTrailers
    UNION ALL
    SELECT * FROM OutboundTrailers
)

SELECT 
    t.*,
    g.GCAS,
    g.PalletsForGcas AS [Pallets For GCAS]
FROM AllTrailers t
LEFT JOIN GcasCombined g
    ON t.[TrailerID] = g.[TrailerID]
   AND t.[Direction] = g.[Direction]
ORDER BY 
    t.[Direction],
    t.[Check-in] ASC,
    t.[TrailerID],
    g.GCAS;
