-- Process Edges - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Process Edges (process mining, last 7 days) - directly-follows graph measured from the event logs of three case types:
--   Pallet : case = LPN (dlytrn.lodnum), activity = process step (config/movement_classes.csv), time = dlytrn.trndte; the first move
--            after the pallet arrives (Flow_Role IN) counts as its put-away even when booked as a transfer (FL_XFR at Minhang)
--   Order  : case = shipment: created -> pick released (allocated) -> picked & staged -> loaded -> truck dispatched (shipment -> stop -> car_move -> trlr)
--   Truck  : case = trailer: check-in -> (un)loading -> closed -> dispatched (trlract)
-- One row per edge: hand-offs, distinct cases, median / p95 minutes between the two steps OVER CASES (each case's average gap counts
-- once - a dummy LPN bouncing between two steps does not drown the real pallets). Consecutive repeats of a step are one step
-- (a put-away pick-up + deposit). Open orders / trucks end in an 'Open: waiting after <step>' node with their age at Snapshot = where
-- the flow is stuck now. Pallets have no open node (a stored pallet is stock, not stuck - see Pallets In Flow).
WITH n AS (
    SELECT DATEADD(HOUR, 7, GETUTCDATE()) AS Snapshot
), pev0 AS (
    SELECT d.lodnum AS case_id, d.trndte AS ts, CASE WHEN d.actcod IN ('TRLR_LOAD', 'TLDG') OR (d.tostol LIKE 'TRL%') THEN '6 Load to trailer'
             WHEN d.actcod IN ('RCV', 'RCVSTG', 'IDNTFY', 'IDNTFY_UNXP', 'ASN_TRUST', 'ASN_NONTRUST', 'TRLR_UNLD', 'RVRCP') OR d.oprcod IN ('UID', 'URC') THEN '1 Receive'
             WHEN d.actcod IN ('IDNTFY_WO') OR (d.frstol LIKE '~NA~' OR d.frstol LIKE '~NA~' OR d.frstol LIKE '~NA~') THEN '2 Production take-away'
             WHEN d.actcod IN ('FL_XFR_PTWY', 'PUT_DRCT', 'PUT_UNDR') OR d.oprcod IN ('STO') THEN '3 Put-away'
             WHEN d.actcod IN ('PALRPL') OR d.oprcod IN ('PIARPL', 'PRP', 'RPL') THEN '4 Replenish'
             WHEN d.actcod IN ('LSTPCK', 'PALPCK', 'PALPCKMOV', 'CASPCKMOV', 'PCKSTEAL', 'ORDMIXPAL') OR d.oprcod IN ('PCK', 'LPCK') THEN '5 Pick'
             WHEN d.actcod IN ('FL_XFR', 'PL_XFR', 'GENMOV') OR d.oprcod IN ('TRN', 'TRR', 'UTR') THEN '7 Transfer'
             ELSE '8 Other move' END AS step
    FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') AS d
    WHERE d.trndte >= DATEADD(DAY, -7, GETDATE())
      AND d.lodnum IS NOT NULL
      AND d.actcod NOT IN ('LOCSTSCHG', 'ATELOCSETAUTO', 'ATELOCCLRAUTO', 'INVSTSCHG', 'LOTDATECHANGED', 'LOCOVRRID', 'WRKSUSP', 'ENG_EXEMP_CHG')
), pev AS (
    -- the first move after the pallet arrives (Flow_Role IN) is its put-away, even when the site books it as a transfer / other move
    SELECT p0.case_id, p0.ts,
           CASE WHEN '3 Put-away' <> '~NA~' AND p0.step IN ('7 Transfer', '8 Other move', '9 Status / system event')
                     AND LAG(p0.step) OVER (PARTITION BY p0.case_id ORDER BY p0.ts, p0.step) IN ('1 Receive', '2 Production take-away')
                THEN '3 Put-away' ELSE p0.step END AS step
    FROM pev0 AS p0
), s AS (
    SELECT s.ship_id, s.shpsts, s.adddte, s.alcdte, s.stgdte, s.loddte, cm.trlr_id,
           CASE s.shpsts WHEN 'R' THEN 1 WHEN 'I' THEN 1 WHEN 'S' THEN 1 WHEN 'L' THEN 1 WHEN 'D' THEN 1 WHEN 'C' THEN 0 WHEN 'B' THEN 0 WHEN 'X' THEN 0 ELSE 1 END AS Is_Open
    FROM (SELECT * FROM prodwms.shipment WHERE wh_id = 'ID01') AS s
    LEFT JOIN prodwms.stop AS st ON st.stop_id = s.stop_id
    LEFT JOIN prodwms.car_move AS cm ON cm.car_move_id = st.car_move_id
    WHERE s.adddte >= DATEADD(DAY, -7, GETDATE())
      AND s.shpsts NOT IN ('B', 'X')
), dsp AS (
    SELECT t.TRLR_ID, MAX(CASE WHEN t.ACTCOD = 'TDSP' THEN CONVERT(DATETIME, t.TRNDTE) END) AS Dispatch_Dt
    FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS t
    WHERE t.TRNDTE >= DATEADD(DAY, -7 - 3, GETDATE())
    GROUP BY t.TRLR_ID
), oev AS (
    SELECT s.ship_id AS case_id, s.adddte AS ts, '1 Order created' AS step, s.Is_Open FROM s
    UNION ALL SELECT s.ship_id, s.alcdte, '2 Pick released', s.Is_Open FROM s WHERE s.alcdte IS NOT NULL
    UNION ALL SELECT s.ship_id, s.stgdte, '3 Picked & staged', s.Is_Open FROM s WHERE s.stgdte IS NOT NULL
    UNION ALL SELECT s.ship_id, s.loddte, '4 Loaded', s.Is_Open FROM s WHERE s.loddte IS NOT NULL
    UNION ALL SELECT s.ship_id, dsp.Dispatch_Dt, '5 Truck dispatched', 0 FROM s JOIN dsp ON dsp.TRLR_ID = s.trlr_id WHERE dsp.Dispatch_Dt IS NOT NULL
), ta AS (
    SELECT a.TRLR_ID, r.TRLR_COD, CONVERT(DATETIME, a.TRNDTE) AS ts, a.ACTCOD, a.TRLR_STAT
    FROM (SELECT * FROM prodwms.trlract WHERE wh_id = 'ID01') AS a
    JOIN prodwms.trlr AS r ON r.TRLR_ID = a.TRLR_ID
    WHERE a.TRNDTE >= DATEADD(DAY, -7, GETDATE())
), tev0 AS (
    SELECT ta.TRLR_ID AS case_id, ta.ts,
           CASE WHEN ta.TRLR_COD LIKE 'RCV%' THEN 'IN ' ELSE 'OUT ' END
           + CASE WHEN ta.ACTCOD = 'TCHKIN' THEN '1 check-in'
                  WHEN ta.ACTCOD = 'TDSP' THEN '4 dispatched'
                  WHEN ta.ACTCOD = 'TCLOSE' THEN '3 closed'
                  WHEN ta.TRLR_STAT IN ('R', 'UNLD', 'LDG', 'L') THEN CASE WHEN ta.TRLR_COD LIKE 'RCV%' THEN '2 unloading' ELSE '2 loading' END
             END AS step
    FROM ta
), tev AS (
    SELECT tev0.case_id, MIN(tev0.ts) AS ts, tev0.step,
           CASE WHEN MAX(CASE WHEN tev0.step LIKE '%4 dispatched' THEN 1 ELSE 0 END) OVER (PARTITION BY tev0.case_id) = 1 THEN 0 ELSE 1 END AS Is_Open
    FROM tev0
    WHERE tev0.step IS NOT NULL
    GROUP BY tev0.case_id, tev0.step
), ev AS (
    SELECT 'Pallet' AS Flow, pev.case_id, pev.ts, pev.step, 0 AS Is_Open FROM pev
    UNION ALL SELECT 'Order', oev.case_id, oev.ts, oev.step, oev.Is_Open FROM oev WHERE oev.ts IS NOT NULL
    UNION ALL SELECT 'Truck', tev.case_id, tev.ts, tev.step, tev.Is_Open FROM tev
), c1 AS (
    SELECT ev.*, LAG(ev.step) OVER (PARTITION BY ev.Flow, ev.case_id ORDER BY ev.ts, ev.step) AS prev_step
    FROM ev
), c2 AS (
    SELECT c1.Flow, c1.case_id, c1.ts, c1.step, c1.Is_Open,
           LEAD(c1.step) OVER (PARTITION BY c1.Flow, c1.case_id ORDER BY c1.ts, c1.step) AS next_step,
           LEAD(c1.ts)   OVER (PARTITION BY c1.Flow, c1.case_id ORDER BY c1.ts, c1.step) AS next_ts
    FROM c1
    WHERE c1.prev_step IS NULL OR c1.prev_step <> c1.step
), e AS (
    SELECT c2.Flow, c2.step AS From_Step, c2.next_step AS To_Step, c2.case_id, 0 AS Is_Open_Edge,
           DATEDIFF(SECOND, c2.ts, c2.next_ts) / 60.0 AS Gap_Min
    FROM c2
    WHERE c2.next_step IS NOT NULL
    UNION ALL
    SELECT c2.Flow, c2.step, 'Open: waiting after ' + c2.step, c2.case_id, 1,
           DATEDIFF(SECOND, c2.ts, n.Snapshot) / 60.0
    FROM c2 CROSS JOIN n
    WHERE c2.next_step IS NULL AND c2.Is_Open = 1 AND c2.Flow <> 'Pallet'
), ec AS (
    -- ONE row per case and hand-off (its average gap): a dummy LPN that bounces 1,000x between two steps counts once, like any pallet
    SELECT e.Flow, e.From_Step, e.To_Step, e.case_id, MAX(e.Is_Open_Edge) AS Is_Open_Edge, COUNT(*) AS n, AVG(e.Gap_Min) AS Gap_Min
    FROM e
    GROUP BY e.Flow, e.From_Step, e.To_Step, e.case_id
), m AS (
    SELECT ec.*,
           PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY ec.Gap_Min) OVER (PARTITION BY ec.Flow, ec.From_Step, ec.To_Step) AS Median_Min,
           PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ec.Gap_Min) OVER (PARTITION BY ec.Flow, ec.From_Step, ec.To_Step) AS P95_Min
    FROM ec
), g AS (
    SELECT m.Flow,
           m.From_Step,
           m.To_Step,
           TRY_CAST(CASE WHEN m.From_Step LIKE 'IN %' THEN SUBSTRING(m.From_Step, 4, 1)
                         WHEN m.From_Step LIKE 'OUT %' THEN SUBSTRING(m.From_Step, 5, 1) ELSE LEFT(m.From_Step, 1) END AS INT)        AS From_No,
           CASE WHEN MAX(m.Is_Open_Edge) = 1 THEN 99
                ELSE TRY_CAST(CASE WHEN m.To_Step LIKE 'IN %' THEN SUBSTRING(m.To_Step, 4, 1)
                                   WHEN m.To_Step LIKE 'OUT %' THEN SUBSTRING(m.To_Step, 5, 1) ELSE LEFT(m.To_Step, 1) END AS INT) END AS To_No,
           MAX(m.Is_Open_Edge)                                                                                              AS Is_Open_Edge,
           SUM(m.n)                                                                                                         AS Transitions,
           COUNT(DISTINCT m.case_id)                                                                                        AS Cases,
           CAST(MAX(m.Median_Min) AS DECIMAL(12, 1))                                                                        AS Median_Min,
           CAST(MAX(m.P95_Min) AS DECIMAL(12, 1))                                                                           AS P95_Min
    FROM m
    GROUP BY m.Flow, m.From_Step, m.To_Step
)
-- Edge_Kind: Open = not yet at the next step now; Side = extra handling with a SIDE move class (config/movement_classes.csv Flow_Role);
-- Storage = from the put-away to the next step = time in storage (stock waiting for demand, not a process wait);
-- Back = to an earlier step of the sequence (rework / return); Forward = the main flow (the bottleneck is the largest Forward hand-off;
-- the Sankeys show Forward + Storage + Open)
SELECT g.Flow, g.From_Step, g.To_Step, g.From_No, g.To_No, g.Is_Open_Edge,
       CASE WHEN g.Is_Open_Edge = 1 THEN 'Open'
            WHEN g.Flow = 'Pallet' AND (g.From_Step IN ('7 Transfer', '8 Other move', '9 Status / system event') OR g.To_Step IN ('7 Transfer', '8 Other move', '9 Status / system event')) THEN 'Side'
            WHEN g.To_No < g.From_No THEN 'Back'
            WHEN g.Flow = 'Pallet' AND g.From_Step = '3 Put-away' THEN 'Storage'
            ELSE 'Forward' END                                                                                          AS Edge_Kind,
       g.Transitions, g.Cases, g.Median_Min, g.P95_Min, n.Snapshot
FROM g CROSS JOIN n
