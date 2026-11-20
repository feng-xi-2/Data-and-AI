-- Pallets In Flow (process diagnosis) - every pallet sitting in a process stage (not in storage) now: stage, location, minutes since its last move
-- Stage rules from config/process_stages.csv (Object = Pallet, Rule with site tokens, first match by Rule_Priority); Flow_No 0 stages (X_*) are dropped.
-- ot = trailers on site now (same definition as the Open Trailers feed). Times are site-local; ages are at Snapshot.
WITH ot AS (
    SELECT r.TRLR_ID
    FROM {S}.trlr AS r
    WHERE r.TRLR_ID IN (SELECT t.TRLR_ID FROM {S}.trlract AS t WHERE t.TRNDTE >= '{START_DT}')
      AND ({{TRAILER_STAGE_CASE}}) IS NOT NULL
), p AS (
    SELECT iv.lodnum, iv.stoloc,
           MAX(iv.lstmov)              AS Last_Move,
           MIN(iv.rcvdte)              AS Received,
           MIN(iv.prtnum)              AS Item,
           COUNT(DISTINCT iv.prtnum)   AS Items,
           SUM(iv.untqty)              AS Units
    FROM {S}.inventory_view AS iv
    WHERE iv.lodnum IS NOT NULL
    GROUP BY iv.lodnum, iv.stoloc
), c AS (
    SELECT p.*, lm.arecod AS Area,
        {{PALLET_STAGE_CASE}} AS Stage_Key
    FROM p
    LEFT JOIN {S}.locmst AS lm ON lm.stoloc = p.stoloc
    {LOC_TYP_JOIN}
), n AS (
    SELECT DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) AS Snapshot
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
