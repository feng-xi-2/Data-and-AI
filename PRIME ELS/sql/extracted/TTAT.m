let
    SqlQuery = "
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
    
    FROM {TTAT_IN_SRC} t
    LEFT JOIN (SELECT * FROM {S}.DLYTRN WHERE wh_id = '{WH_ID}') d ON {TTAT_IN_RCPT_COND}
    WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= '{START_DT}'
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
    
    FROM (SELECT * FROM {S}.TRLRACT WHERE wh_id = '{WH_ID}') t
    LEFT JOIN (SELECT * FROM {S}.DLYTRN WHERE wh_id = '{WH_ID}') d   ON t.TRLR_ID = d.TOSTOL
    LEFT JOIN (SELECT * FROM {S}.ord WHERE wh_id = '{WH_ID}') AS ord        ON t.CAR_MOVE_ID = ord.vc_car_move_id
    LEFT JOIN {S}.adrmst     ON ord.rt_adr_id = adrmst.adr_id
    WHERE t.TRNDTE >= '{START_DT}' AND (
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
    FROM {TTAT_IN_SRC} t
    JOIN (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') d ON {TTAT_IN_RCPT_COND}
    WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= '{START_DT}'
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
    FROM {S}.trlr AS tr
    JOIN (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') AS d ON tr.trlr_id = d.tostol
    WHERE d.lodnum IS NOT NULL AND d.trndte >= '{START_DT}'
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
    ",

    Source = Sql.Database(ReplicaServer, ReplicaDatabase,
        [Query = fnSiteSql(SqlQuery)]
    ),

    // ============================================
    // Convert datetime/date columns to proper types
    // ============================================
    #"Typed Checkin" = Table.TransformColumnTypes(
        Source,
        {
            {"Check-in",                    type datetime},
            {"First Scan / Start Loading",  type datetime},
            {"End Loading",                 type datetime},
            {"Close",                       type datetime},
            {"Dispatch",                    type datetime},
            {"Check-in Date",               type date},
            {"Close Date",                  type date},
            {"Dispatch Date",               type date}
        }
    ),

    // ============================================
    // Duration in Hours
    // ============================================
    #"Added Scan-Checkin Hours" = Table.AddColumn(
        #"Typed Checkin",
        "Scan - Checkin (Hours)",
        each
            if [#"Check-in"] = null or [#"First Scan / Start Loading"] = null then null
            else Duration.TotalHours([#"First Scan / Start Loading"] - [#"Check-in"]),
        type number
    ),

    // Process Time (Hours) — direction-aware
    #"Added Process Time Hours" = Table.AddColumn(
        #"Added Scan-Checkin Hours",
        "Process Time (Hours)",
        each
            if [#"First Scan / Start Loading"] = null then null
            else if [Direction] = "Outbound" and [#"End Loading"] <> null then
                Duration.TotalHours([#"End Loading"] - [#"First Scan / Start Loading"])
            else if [Direction] = "Inbound" and [#"Close"] <> null then
                Duration.TotalHours([#"Close"] - [#"First Scan / Start Loading"])
            else null,
        type number
    ),

    // TTAT (Hours) — direction-aware
    #"Added TTAT Hours" = Table.AddColumn(
        #"Added Process Time Hours",
        "TTAT (Hours)",
        each
            if [#"Check-in"] = null then null
            else if [Direction] = "Outbound" and [#"Close"] <> null then
                Duration.TotalHours([#"Close"] - [#"Check-in"])
            else if [Direction] = "Inbound" and [#"Dispatch"] <> null then
                Duration.TotalHours([#"Dispatch"] - [#"Check-in"])
            else null,
        type number
    ),

    // ============================================
    // Row ID for reference
    // ============================================
    #"Added Index" = Table.AddIndexColumn(#"Added TTAT Hours", "RowID", 1, 1, Int64.Type),
    #"Renamed Columns" = Table.RenameColumns(#"Added Index",{{"Process Time (Minutes)", "Loading/GR Time (Minutes)"}})

in
    #"Renamed Columns"