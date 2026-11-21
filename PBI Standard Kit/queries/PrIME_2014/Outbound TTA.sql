-- Outbound TTA - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Outbound TTA.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {START_DT}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- Outbound TTA (KPI #3 outbound) - trailer loading time per load, from Excel Query13 (TCHG/LDG -> TL/L)
-- One row per trailer (carrier move / code can be set after check-in). Loaded = explicit TL / L status; sites that never set it
-- (BD STO fast lanes) -> the last loading scan (TLDG), the same end-of-loading the TTAT table uses.
WITH ev AS (
    SELECT t.TRLR_ID, MAX(t.CAR_MOVE_ID) AS CAR_MOVE_ID, MAX(t.TRLR_COD) AS TRLR_COD,
           MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN t.YARD_LOC END)                                        AS Dock_ID,
           MAX(CASE WHEN t.ACTCOD = 'TCHKIN' THEN CONVERT(DATETIME, t.TRNDTE) END)                       AS Checkin_Dt,
           MIN(CASE WHEN t.TRLR_STAT = 'LDG' AND t.ACTCOD IN ('TCHG','TLDG') THEN CONVERT(DATETIME, t.TRNDTE) END) AS Start_Loading,
           COALESCE(MAX(CASE WHEN t.TRLR_STAT = 'L' AND t.ACTCOD = 'TL' THEN CONVERT(DATETIME, t.TRNDTE) END),
                    MAX(CASE WHEN t.ACTCOD = 'TLDG' THEN CONVERT(DATETIME, t.TRNDTE) END))               AS End_Loading,
           MAX(CASE WHEN t.ACTCOD = 'TCLOSE' THEN CONVERT(DATETIME, t.TRNDTE) END)                       AS Close_Dt,
           MAX(CASE WHEN t.ACTCOD = 'TDSP' THEN CONVERT(DATETIME, t.TRNDTE) END)                         AS Dispatch_Dt
    FROM prodwms.trlract AS t
    WHERE t.TRLR_COD IN ('SHIP','STO')
      AND t.WH_ID = '{WH_ID}'
      AND t.TRNDTE >= '{START_DT}'
    GROUP BY t.TRLR_ID
),
route AS (
    SELECT o.vc_car_move_id, MAX(a.ctry_name) AS ctry_name
    FROM prodwms.ord AS o
    JOIN prodwms.adrmst AS a ON a.adr_id = o.rt_adr_id
    WHERE o.wh_id = '{WH_ID}' AND o.vc_car_move_id IS NOT NULL
    GROUP BY o.vc_car_move_id
),
pal AS (
    SELECT d.tostol, COUNT(DISTINCT d.lodnum) AS pallets
    FROM prodwms.dlytrn AS d
    WHERE d.trndte >= '{START_DT}' AND d.lodnum IS NOT NULL
      AND d.tostol IN (SELECT TRLR_ID FROM ev)
    GROUP BY d.tostol
)
SELECT ev.TRLR_ID                                                            AS TrailerID,
       ev.CAR_MOVE_ID                                                        AS [Load],
       CASE WHEN ev.TRLR_COD = 'STO' THEN 'Fast Lanes' ELSE 'Normal Shipping' END AS [Trailer Type],
       ev.Dock_ID                                                            AS [Dock ID],
       ev.Checkin_Dt                                                         AS [Check-in],
       ev.Start_Loading                                                      AS [Start Loading],
       ev.End_Loading                                                        AS [End Loading],
       ev.Close_Dt                                                           AS [Transport Equipment Close],
       ev.Dispatch_Dt                                                        AS [Dispatch],
       r.ctry_name                                                           AS [Route To],
       COALESCE(p.pallets, 0)                                                AS Pallets,
       DATEDIFF(MINUTE, ev.Start_Loading, ev.End_Loading)                    AS [Load Time (Minutes)],
       DATEDIFF(MINUTE, ev.Checkin_Dt, ev.Close_Dt)                          AS [TTAT (Minutes)]
FROM ev
LEFT JOIN route AS r ON r.vc_car_move_id = ev.CAR_MOVE_ID
LEFT JOIN pal   AS p ON p.tostol = ev.TRLR_ID
WHERE ev.Close_Dt IS NOT NULL
