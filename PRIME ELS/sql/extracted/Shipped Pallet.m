let
    // Convert the Power BI parameter to SQL-compatible string
    StartDateValue = DateTime.ToText(
        DateTime.From(StartDateParameter),
        "yyyy-MM-dd HH:mm:ss.fff"
    ),

    // Build the SQL dynamically
    SqlQuery = "
DECLARE @StartDate DATETIME = '" & StartDateValue & "';

WITH cte AS (
    SELECT
        PRTNUM, LOTNUM, TRNQTY, LODNUM,
        TRY_CONVERT(datetime, TRNDTE) AS TranDate,
        TOSTOL,
        CASE
            WHEN OPRCOD LIKE 'SUP%' AND (TOSTOL LIKE '{LOC_PROD_SUPPLY}' OR TOSTOL LIKE '{LOC_PROD_CHECKIN}') AND LODNUM IS NOT NULL THEN 'LSL'
            WHEN ACTCOD LIKE 'RCV' AND PRTNUM LIKE '{FG_PRTNUM_LIKE}' AND TOSTOL LIKE '{LOC_LTA}' THEN 'LTA'
            WHEN FRSTOL LIKE '{LOC_RETURN}' THEN 'LRTN'
            WHEN (((ACTCOD LIKE 'TRLR%' OR ACTCOD LIKE 'FL_XFR') AND TOSTOL LIKE '{LOC_TRAILER}')
                OR (OPRCOD LIKE 'UTR' AND PRTNUM LIKE '{FG_PRTNUM_LIKE}' AND (TOSTOL LIKE '{LOC_DOOR_PATTERN}' AND TRY_CAST(SUBSTRING(TOSTOL, 2, 3) AS INT) BETWEEN 1 AND 199))) THEN 'LOAD'
            WHEN ACTCOD LIKE 'RCV' AND TO_ARECOD LIKE '{AREA_RCV_STAGE}' THEN 'RCV'
            ELSE NULL
        END AS ReportType
    FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') AS dlytrn
    WHERE TRNDTE >= DATEADD(DAY, -1, '{START_DT}') AND ((OPRCOD LIKE 'SUP%' AND (TOSTOL LIKE '{LOC_PROD_SUPPLY}' OR TOSTOL LIKE '{LOC_PROD_CHECKIN}') AND LODNUM IS NOT NULL)
        OR (ACTCOD LIKE 'RCV' AND PRTNUM LIKE '{FG_PRTNUM_LIKE}' AND TOSTOL LIKE '{LOC_LTA}')
        OR (FRSTOL LIKE '{LOC_RETURN}')
        OR (((ACTCOD LIKE 'TRLR%' OR ACTCOD LIKE 'FL_XFR') AND TOSTOL LIKE '{LOC_TRAILER}')
            OR (OPRCOD LIKE 'UTR' AND PRTNUM LIKE '{FG_PRTNUM_LIKE}' AND (TOSTOL LIKE '{LOC_DOOR_PATTERN}' AND TRY_CAST(SUBSTRING(TOSTOL, 2, 3) AS INT) BETWEEN 1 AND 199)))
        OR (ACTCOD LIKE 'RCV' AND TO_ARECOD LIKE '{AREA_RCV_STAGE}'))
),
cte_ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY LODNUM, ReportType ORDER BY TranDate ASC) AS rn
    FROM cte
    WHERE TranDate >= @StartDate
        AND ReportType IS NOT NULL
        AND LODNUM IS NOT NULL
)
SELECT
    CAST(TranDate AS date)                                AS [Date],
    DATEPART(hour, TranDate)                              AS [Hour],
    COUNT(CASE WHEN ReportType = 'LTA'  THEN LODNUM END)  AS LTA_Count,
    COUNT(CASE WHEN ReportType = 'LSL'  THEN LODNUM END)  AS LSL_Count,
    COUNT(CASE WHEN ReportType = 'RCV'  THEN LODNUM END)  AS RCV_Count,
    COUNT(CASE WHEN ReportType = 'LOAD' THEN LODNUM END)  AS LOAD_Count,
    COUNT(LODNUM)                                         AS Total_Pallet_Events_InHour
FROM cte_ranked
WHERE rn = 1
GROUP BY CAST(TranDate AS date), DATEPART(hour, TranDate)
ORDER BY [Date], [Hour];
    ",

    // Execute query
    Source = Sql.Database(ReplicaServer, ReplicaDatabase,
        [Query = fnSiteSql(SqlQuery)]
    ),

    #"Renamed Columns" = Table.RenameColumns(
        Source,
        {
            {"LOAD_Count", "Total Shipped Pallet"},
            {"LTA_Count",  "LTA Pallet"},
            {"LSL_Count",  "LSL Pallet"},
            {"RCV_Count",  "Received Pallet"}
        }
    ),

    #"Changed Type" = Table.TransformColumnTypes(
        #"Renamed Columns",
        {{"Date", type date}}
    ),

    // ✅ Shift_date: if Hour < 6, belongs to previous calendar day's shift day
    #"Added Shift_Date" = Table.AddColumn(
        #"Changed Type",
        "shift_date",
        each if [Hour] < ShiftStartH then Date.AddDays([Date], -1) else [Date],
        type date
    ),

    // ✅ Bucket_Sort: 06:00-anchored. Hour 6-9→1, 10-13→2, 14-17→3, 18-21→4, 22,23,0,1→5, 2-5→6
    #"Added Bucket_Sort" = Table.AddColumn(
        #"Added Shift_Date",
        "Bucket_Sort",
        each Number.IntegerDivide(Number.Mod([Hour] - ShiftStartH + 24, 24), 4) + 1,
        Int64.Type
    ),

    // ✅ Bucket_4h label: "B1 (06:00-10:00)", "B5 (22:00-02:00)", "B6 (02:00-06:00)", etc.
    #"Added Bucket_4h" = Table.AddColumn(
        #"Added Bucket_Sort",
        "Bucket_4h",
        each
            let
                startH_raw = ShiftStartH + ([Bucket_Sort] - 1) * 4,
                endH_raw   = ShiftStartH + [Bucket_Sort] * 4,
                startH     = Number.Mod(startH_raw, 24),
                endH       = Number.Mod(endH_raw,   24)
            in
                "B" & Text.From([Bucket_Sort]) & " (" &
                Text.PadStart(Text.From(startH), 2, "0") & ":00-" &
                Text.PadStart(Text.From(endH),   2, "0") & ":00)",
        type text
    ),

    #"Added BucketDateKey" = Table.AddColumn(
        #"Added Bucket_4h",
        "BucketDateKey",
        each Date.ToText([shift_date], "yyyyMMdd") & "-" & Text.From([Bucket_Sort]),
        type text
    )
in
    #"Added BucketDateKey"