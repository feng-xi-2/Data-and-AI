-- Shipped Pallet - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:24 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
DECLARE @StartDate DATETIME = '2026-10-01 00:00:00';

WITH cte AS (
    SELECT
        PRTNUM, LOTNUM, TRNQTY, LODNUM,
        TRY_CONVERT(datetime, TRNDTE) AS TranDate,
        TOSTOL,
        CASE
            WHEN OPRCOD LIKE 'SUP%' AND (TOSTOL LIKE 'PL%' OR TOSTOL LIKE '~NA~') AND LODNUM IS NOT NULL THEN 'LSL'
            WHEN ACTCOD LIKE 'RCV' AND PRTNUM LIKE '8%' AND TOSTOL LIKE 'LT%' THEN 'LTA'
            WHEN FRSTOL LIKE 'RTN%' THEN 'LRTN'
            WHEN (((ACTCOD LIKE 'TRLR%' OR ACTCOD LIKE 'FL_XFR') AND TOSTOL LIKE 'TRL%')
                OR (OPRCOD LIKE 'UTR' AND PRTNUM LIKE '8%' AND (TOSTOL LIKE 'C[0-9][0-9][0-9]' AND TRY_CAST(SUBSTRING(TOSTOL, 2, 3) AS INT) BETWEEN 1 AND 199))) THEN 'LOAD'
            WHEN ACTCOD LIKE 'RCV' AND TO_ARECOD LIKE 'RCST%' THEN 'RCV'
            ELSE NULL
        END AS ReportType
    FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') AS dlytrn
    WHERE TRNDTE >= DATEADD(DAY, -1, '2026-10-01 00:00:00') AND ((OPRCOD LIKE 'SUP%' AND (TOSTOL LIKE 'PL%' OR TOSTOL LIKE '~NA~') AND LODNUM IS NOT NULL)
        OR (ACTCOD LIKE 'RCV' AND PRTNUM LIKE '8%' AND TOSTOL LIKE 'LT%')
        OR (FRSTOL LIKE 'RTN%')
        OR (((ACTCOD LIKE 'TRLR%' OR ACTCOD LIKE 'FL_XFR') AND TOSTOL LIKE 'TRL%')
            OR (OPRCOD LIKE 'UTR' AND PRTNUM LIKE '8%' AND (TOSTOL LIKE 'C[0-9][0-9][0-9]' AND TRY_CAST(SUBSTRING(TOSTOL, 2, 3) AS INT) BETWEEN 1 AND 199)))
        OR (ACTCOD LIKE 'RCV' AND TO_ARECOD LIKE 'RCST%'))
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
