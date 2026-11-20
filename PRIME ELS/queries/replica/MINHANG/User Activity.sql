-- User Activity - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- User Activity (KPI #5 user productivity) - pallets moved per RF user per hour, last 14 days
-- Pallets_Moved     = distinct pallets per user / hour / operation / activity (a pallet picked + deposited counts in both rows)
-- Pallets_User_Hour = each pallet once per user-hour (credited to the first operation / activity code) -> SUM = pallets moved
-- Shift_Date        = the shift day of the hour (shift day starts at Cfg_Site.Shift1_Start, site-local) = the report day
-- Move_Class        = process step of the transaction (config/movement_classes.csv); status / system events (Counts_As_Move = 0) are excluded
WITH d0 AS (
    SELECT d.trndte, d.usr_id, d.oprcod, d.actcod, d.lodnum,
           CASE WHEN d.actcod IN ('TRLR_LOAD', 'TLDG') OR (d.tostol LIKE 'TRL%') THEN '6 Load to trailer'
             WHEN d.actcod IN ('RCV', 'RCVSTG', 'IDNTFY', 'IDNTFY_UNXP', 'ASN_TRUST', 'ASN_NONTRUST', 'TRLR_UNLD', 'RVRCP') OR d.oprcod IN ('UID', 'URC') THEN '1 Receive'
             WHEN d.actcod IN ('IDNTFY_WO') OR (d.frstol LIKE '~NA~' OR d.frstol LIKE '~NA~' OR d.frstol LIKE '~NA~') THEN '2 Production take-away'
             WHEN d.actcod IN ('FL_XFR_PTWY', 'PUT_DRCT', 'PUT_UNDR') OR d.oprcod IN ('STO') THEN '3 Put-away'
             WHEN d.actcod IN ('PALRPL') OR d.oprcod IN ('PIARPL', 'PRP', 'RPL') THEN '4 Replenish'
             WHEN d.actcod IN ('LSTPCK', 'PALPCK', 'PALPCKMOV', 'CASPCKMOV', 'PCKSTEAL', 'ORDMIXPAL') OR d.oprcod IN ('PCK', 'LPCK') THEN '5 Pick'
             WHEN d.actcod IN ('FL_XFR', 'PL_XFR', 'GENMOV') OR d.oprcod IN ('TRN', 'TRR', 'UTR') THEN '7 Transfer'
             ELSE '8 Other move' END AS Move_Class
    FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'BR01') AS d
    WHERE d.trndte >= DATEADD(DAY, -14, GETDATE()) AND d.trndte >= '1900-01-01' AND d.trndte < '9999-12-31'
      AND d.usr_id IS NOT NULL
      AND d.usr_id NOT IN ('SUPER','NOUSER')
      AND d.lodnum IS NOT NULL
      AND d.actcod NOT IN ('LOCSTSCHG', 'ATELOCSETAUTO', 'ATELOCCLRAUTO', 'INVSTSCHG', 'LOTDATECHANGED', 'LOCOVRRID', 'WRKSUSP', 'ENG_EXEMP_CHG')
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
    CAST(DATEADD(HOUR, Activity_Hour - 6, CAST(Activity_Date AS DATETIME)) AS DATE) AS Shift_Date,
    User_Id,
    Operation,
    Activity_Code,
    Move_Class,
    SUM(n)                                  AS Transactions,
    COUNT(*)                                AS Pallets_Moved,
    SUM(CASE WHEN rn = 1 THEN 1 ELSE 0 END) AS Pallets_User_Hour
FROM y
GROUP BY Activity_Date, Activity_Hour, User_Id, Operation, Activity_Code, Move_Class
