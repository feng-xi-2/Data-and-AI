-- User Activity - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/User Activity.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {ACT_DAYS}, {MOVE_CLASS_CASE}, {MOVE_EXCLUDE_LIST}, {USR_EXCLUDE} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

-- User Activity (KPI #5 user productivity) - pallets moved per RF user per hour, last {ACT_DAYS} days
-- Pallets_Moved     = distinct pallets per user / hour / operation / activity (a pallet picked + deposited counts in both rows)
-- Pallets_User_Hour = each pallet once per user-hour (credited to the first operation / activity code) -> SUM = pallets moved
-- Shift_Date        = the shift day of the hour (shift day starts at Cfg_Site.Shift1_Start, site-local) = the report day
-- Move_Class        = process step of the transaction (config/movement_classes.csv); status / system events (Counts_As_Move = 0) are excluded
WITH d0 AS (
    SELECT d.trndte, d.usr_id, d.oprcod, d.actcod, d.lodnum,
           {{MOVE_CLASS_CASE}} AS Move_Class
    FROM dbo.dlytrn AS d
    WHERE d.trndte >= DATEADD(DAY, -{ACT_DAYS}, GETDATE())
      AND d.usr_id IS NOT NULL
      AND d.usr_id NOT IN ({USR_EXCLUDE})
      AND d.lodnum IS NOT NULL
      AND d.actcod NOT IN ({{MOVE_EXCLUDE_LIST}})
), x AS (
    SELECT
        CAST(d.trndte AS DATE)          AS Activity_Date,
        DATEPART(HOUR, d.trndte)        AS Activity_Hour,
        d.usr_id                        AS User_Id,
        COALESCE(d.oprcod, '(none)')    AS Operation,
        d.actcod                        AS Activity_Code,
        d.Move_Class,
        d.lodnum,
        COUNT(*)                        AS n
    FROM d0 AS d
    GROUP BY CAST(d.trndte AS DATE), DATEPART(HOUR, d.trndte), d.usr_id, COALESCE(d.oprcod, '(none)'), d.actcod, d.Move_Class, d.lodnum
), y AS (
    SELECT x.*, ROW_NUMBER() OVER (PARTITION BY Activity_Date, Activity_Hour, User_Id, lodnum ORDER BY Operation, Activity_Code, Move_Class) AS rn
    FROM x
)
SELECT
    Activity_Date,
    Activity_Hour,
    CAST(DATEADD(HOUR, Activity_Hour - {Shift1_Start}, CAST(Activity_Date AS DATETIME)) AS DATE) AS Shift_Date,
    User_Id,
    Operation,
    Activity_Code,
    Move_Class,
    SUM(n)                                  AS Transactions,
    COUNT(*)                                AS Pallets_Moved,
    SUM(CASE WHEN rn = 1 THEN 1 ELSE 0 END) AS Pallets_User_Hour
FROM y
GROUP BY Activity_Date, Activity_Hour, User_Id, Operation, Activity_Code, Move_Class
