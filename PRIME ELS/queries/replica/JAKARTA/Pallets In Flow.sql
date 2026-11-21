-- Pallets In Flow - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Pallets In Flow (process diagnosis) - every pallet sitting in a process stage (not in storage) now: stage, location, minutes since its last move
-- Stage rules from config/process_stages.csv (Object = Pallet, Rule with site tokens, first match by Rule_Priority); Flow_No 0 stages (X_*) are dropped.
-- ot = trailers on site now (same definition as the Open Trailers feed). Times are site-local; ages are at Snapshot.
WITH ot AS (
    SELECT r.TRLR_ID
    FROM prodwms.trlr AS r
    WHERE r.TRLR_ID IN (SELECT t.TRLR_ID FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS t WHERE t.TRNDTE >= '2026-10-20 00:00:00')
      AND (CASE WHEN r.TRLR_COD LIKE 'RCV%' THEN CASE r.TRLR_STAT WHEN 'OR' THEN 'T_IN_YARD' WHEN 'CI' THEN 'T_IN_YARD' WHEN 'PFL' THEN 'T_IN_YARD' WHEN 'PTL' THEN 'T_IN_YARD' WHEN 'R' THEN 'T_IN_UNLOAD' WHEN 'UNLD' THEN 'T_IN_UNLOAD' WHEN 'SUSP' THEN 'T_IN_UNLOAD' WHEN 'C' THEN 'T_IN_CLOSE' WHEN 'P' THEN 'T_IN_CLOSE' END
             ELSE CASE r.TRLR_STAT WHEN 'O' THEN 'T_OUT_YARD' WHEN 'OLDG' THEN 'T_OUT_YARD' WHEN 'CI' THEN 'T_OUT_YARD' WHEN 'PFL' THEN 'T_OUT_YARD' WHEN 'PTL' THEN 'T_OUT_YARD' WHEN 'LDG' THEN 'T_OUT_LOAD' WHEN 'SUSP' THEN 'T_OUT_LOAD' WHEN 'L' THEN 'T_OUT_CLOSE' WHEN 'C' THEN 'T_OUT_CLOSE' WHEN 'P' THEN 'T_OUT_CLOSE' END END) IS NOT NULL
), p AS (
    SELECT iv.lodnum, iv.stoloc,
           MAX(iv.lstmov)              AS Last_Move,
           MIN(iv.rcvdte)              AS Received,
           MIN(iv.prtnum)              AS Item,
           COUNT(DISTINCT iv.prtnum)   AS Items,
           SUM(iv.untqty)              AS Units
    FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS iv
    WHERE iv.lodnum IS NOT NULL
    GROUP BY iv.lodnum, iv.stoloc
), c AS (
    SELECT p.*, lm.arecod AS Area,
        CASE
            WHEN p.stoloc IN (SELECT TRLR_ID FROM ot) THEN 'P_TRAILER'
            WHEN p.stoloc LIKE 'TRL%' THEN 'X_TRAILER_OFFSITE'
            WHEN p.stoloc LIKE '~NA~' THEN 'P_PROBLEM'
            WHEN p.stoloc LIKE '~NA~' THEN 'P_RETURN'
            WHEN p.stoloc LIKE '~NA~' OR p.stoloc LIKE '~NA~' THEN 'P_HOFF'
            WHEN p.stoloc LIKE '~NA~' THEN 'P_LTA'
            WHEN p.stoloc LIKE '~NA~' OR p.stoloc = '~NA~' THEN 'P_LINE'
            WHEN lm.arecod LIKE 'RDTS%' THEN 'P_RDT'
            WHEN (lm.arecod LIKE 'RS%' OR lm.arecod LIKE 'RCV%') OR lm.arecod LIKE '~NA~' THEN 'P_RCV'
            WHEN (lm.arecod LIKE 'SHST%') OR p.stoloc LIKE 'DOOR%' THEN 'P_SHIPSTG'
        END AS Stage_Key
    FROM p
    LEFT JOIN (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01') AS lm ON lm.stoloc = p.stoloc
    
), n AS (
    SELECT DATEADD(HOUR, 7, GETUTCDATE()) AS Snapshot
)
SELECT c.Stage_Key,
       c.lodnum                                                  AS Pallet,
       c.stoloc                                                  AS Location,
       c.Area,
       c.Item,
       c.Items,
       c.Units,
       COALESCE(c.Last_Move, c.Received)                         AS [Last Move],
       DATEDIFF(MINUTE, COALESCE(c.Last_Move, c.Received), n.Snapshot) AS [Minutes In Location],
       n.Snapshot
FROM c
CROSS JOIN n
WHERE c.Stage_Key IS NOT NULL AND c.Stage_Key NOT LIKE 'X[_]%'
