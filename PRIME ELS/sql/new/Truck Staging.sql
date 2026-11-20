-- Truck Staging (Trucks & TTAT page) - per truck of the last DETAIL_DAYS days: its dock (door at close, else at a status change, else the
-- check-in location) and the
-- lanes its pallets were staged in, with pallets per lane.
--   OUTBOUND: for every pallet moved onto the trailer, its last location before the load that is not an RF device / forklift area
--             (AREA_RDTS) = the staging lane it was loaded from (storage location when it was loaded directly from the rack).
--   INBOUND : for every pallet received from the truck (TTAT_IN_SRC / TTAT_IN_RCPT_COND, the same link as the TTAT feed), its first
--             location after the receipt that is not an RF device area = the receiving lane / first put-away location.
-- One row per truck x lane; '(RF device only)' = pallet still on / only moved by a forklift; a truck without pallet moves has one row.
WITH trl AS (
    SELECT a.TRLR_ID,
           MAX(CASE WHEN a.TRLR_COD LIKE 'RCV%' THEN 'Inbound' ELSE 'Outbound' END)               AS Direction,
           COALESCE(MAX(CASE WHEN a.ACTCOD = 'TCLOSE' THEN a.YARD_LOC END),                         -- door at close (loaded / unloaded there)
                    MAX(CASE WHEN a.ACTCOD = 'TCHG' THEN a.YARD_LOC END),                           -- door of a status change
                    MAX(CASE WHEN a.ACTCOD = 'TCHKIN' THEN a.YARD_LOC END))                         AS Dock,
           MAX(CASE WHEN a.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, a.TRNDTE) END)                 AS Checkin_Dt,
           MAX(CASE WHEN a.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, a.TRNDTE) END)                 AS Close_Dt,
           MAX(CASE WHEN a.ACTCOD = 'TDSP'   THEN CONVERT(DATETIME, a.TRNDTE) END)                 AS Dispatch_Dt
    FROM {S}.trlract AS a
    WHERE a.WH_ID = '{WH_ID}' AND a.TRNDTE >= DATEADD(DAY, -{DETAIL_DAYS}, GETDATE())
      AND (a.TRLR_COD LIKE 'RCV%' OR a.TRLR_COD IN ('SHIP', 'STO'))
    GROUP BY a.TRLR_ID
),
mv AS (
    SELECT d.lodnum, d.tostol, d.to_arecod, CONVERT(DATETIME, d.trndte) AS ts
    FROM {S}.dlytrn AS d
    WHERE d.wh_id = '{WH_ID}' AND d.trndte >= DATEADD(DAY, -{DETAIL_DAYS} - 2, GETDATE()) AND d.lodnum IS NOT NULL
),
ld AS (
    SELECT m.lodnum, m.tostol AS TRLR_ID, MIN(m.ts) AS Ts
    FROM mv AS m
    JOIN trl ON trl.TRLR_ID = m.tostol AND trl.Direction = 'Outbound'
    GROUP BY m.lodnum, m.tostol
),
ob AS (
    SELECT ld.TRLR_ID, ld.lodnum, ld.Ts, x.tostol AS Lane, x.to_arecod AS Lane_Area,
           ROW_NUMBER() OVER (PARTITION BY ld.TRLR_ID, ld.lodnum ORDER BY x.ts DESC) AS rn
    FROM ld
    LEFT JOIN mv AS x ON x.lodnum = ld.lodnum AND x.ts <= ld.Ts AND x.tostol <> ld.TRLR_ID
                     AND x.to_arecod NOT LIKE '{AREA_RDTS}' AND x.tostol NOT LIKE '{LOC_TRAILER}'
),
rc AS (
    SELECT d.lodnum, t.TRLR_ID, MIN(CONVERT(DATETIME, d.TRNDTE)) AS Ts
    FROM {TTAT_IN_SRC} t
    JOIN (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}' AND trndte >= DATEADD(DAY, -{DETAIL_DAYS} - 2, GETDATE())) d ON {TTAT_IN_RCPT_COND}
    WHERE t.TRLR_COD LIKE 'RCV%' AND t.TRNDTE >= DATEADD(DAY, -{DETAIL_DAYS}, GETDATE()) AND d.lodnum IS NOT NULL
    GROUP BY d.lodnum, t.TRLR_ID
),
ib AS (
    SELECT rc.TRLR_ID, rc.lodnum, rc.Ts, x.tostol AS Lane, x.to_arecod AS Lane_Area,
           ROW_NUMBER() OVER (PARTITION BY rc.TRLR_ID, rc.lodnum ORDER BY x.ts ASC) AS rn
    FROM rc
    LEFT JOIN mv AS x ON x.lodnum = rc.lodnum AND x.ts >= rc.Ts AND x.to_arecod NOT LIKE '{AREA_RDTS}'
),
lanes AS (
    SELECT TRLR_ID, COALESCE(Lane, '(RF device only)') AS Lane, MAX(Lane_Area) AS Lane_Area, COUNT(DISTINCT lodnum) AS Pallets,
           MIN(Ts) AS First_Ts, MAX(Ts) AS Last_Ts
    FROM ob WHERE rn = 1 GROUP BY TRLR_ID, COALESCE(Lane, '(RF device only)')
    UNION ALL
    SELECT TRLR_ID, COALESCE(Lane, '(RF device only)'), MAX(Lane_Area), COUNT(DISTINCT lodnum), MIN(Ts), MAX(Ts)
    FROM ib WHERE rn = 1 GROUP BY TRLR_ID, COALESCE(Lane, '(RF device only)')
)
SELECT trl.Direction                                        AS Direction,
       trl.TRLR_ID                                          AS TrailerID,
       COALESCE(trl.Dock, '(no check-in door)')             AS Dock,
       COALESCE(l.Lane, '(no pallet moves)')                AS [Staging Lane],
       l.Lane_Area                                          AS [Lane Area],
       COALESCE(l.Pallets, 0)                               AS Pallets,
       l.First_Ts                                           AS [First Pallet],
       l.Last_Ts                                            AS [Last Pallet],
       trl.Checkin_Dt                                       AS [Check-in],
       trl.Close_Dt                                         AS [Close],
       trl.Dispatch_Dt                                      AS [Dispatch]
FROM trl
LEFT JOIN lanes AS l ON l.TRLR_ID = trl.TRLR_ID
