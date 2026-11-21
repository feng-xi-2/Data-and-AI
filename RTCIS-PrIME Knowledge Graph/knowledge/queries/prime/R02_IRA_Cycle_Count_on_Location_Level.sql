-- R02 IRA Cycle Count on Location Level -> PrIME 2022
-- Params: @wh_id, @strStart_Date, @strEnd_Date ('mm/dd/yyyy hh:mi:ss'), @subsit (LIKE on building: '%' or 'B1'/'B2'),
--         @itmcls ('F' -> FERT, 'P' -> ROH)
-- RTCIS STKCNT/STKMIS/STKCOR transactions -> PrIME cnthst (one row per count event).
--   stkcnt = 1 per count event; stkmis = 1 when counted qty <> system qty (PrIME has NO STKMIS txn - verified IRA fleet);
--   stkcor -> 1 when a dlytrn inventory adjustment (INVADJ/ADJAPP) hit the same location+day [INFERRED].
--   locatn.count_itmcls -> item class of the counted part; pre/post_count_ok -> none (PrIME has no such flags, dropped).
--   arecod RA/CP/RO -> location type RSTO (measured: all RA/RO/CP locations are RSTO); dtltyp 'F' -> implicit.
--   techid -> cnthst.CNT_USR_ID; name -> adrmst first/last name via les_usr_ath.ADR_ID.
--   subsit decode -> building of the location (B1 = former DE07, B2 = former DE08).
WITH ev AS (
    SELECT h.CNTDTE AS gendat, a.BLDG_ID AS subsit,
           CASE p.TYPCOD WHEN 'FERT' THEN 'F' WHEN 'ROH' THEN 'P' ELSE p.TYPCOD END AS count_itmcls,
           h.STOLOC AS locatn, h.CNT_USR_ID,
           CONCAT(ad.FIRST_NAME, ' ', ad.LAST_NAME) AS name,
           CASE WHEN h.UNTQTY <> h.CNTQTY THEN 1 ELSE 0 END AS miss
    FROM dbo.cnthst h
    JOIN dbo.locmst m ON m.STOLOC = h.STOLOC AND m.WH_ID = h.WH_ID
    JOIN dbo.aremst a ON a.ARECOD = m.ARECOD AND a.WH_ID = m.WH_ID
    JOIN dbo.loc_typ t ON t.LOC_TYP_ID = m.LOC_TYP_ID
    LEFT JOIN dbo.prtmst p ON p.PRTNUM = h.PRTNUM AND p.PRT_CLIENT_ID = h.PRT_CLIENT_ID AND p.WH_ID_TMPL = h.WH_ID
    LEFT JOIN dbo.les_usr_ath u ON u.USR_ID = h.CNT_USR_ID
    LEFT JOIN dbo.adrmst ad ON ad.ADR_ID = u.ADR_ID
    WHERE h.WH_ID = @wh_id
      AND h.CNTDTE BETWEEN CONVERT(datetime, @strStart_Date, 101) AND CONVERT(datetime, @strEnd_Date, 101)
      AND a.BLDG_ID LIKE @subsit
      AND t.LOC_TYP = 'RSTO'
      AND CASE p.TYPCOD WHEN 'FERT' THEN 'F' WHEN 'ROH' THEN 'P' ELSE p.TYPCOD END = @itmcls
), adj AS (
    SELECT DISTINCT x.FRSTOL AS locatn, CAST(x.TRNDTE AS date) AS day
    FROM dbo.dlytrn x
    WHERE x.WH_ID = @wh_id AND x.ACTCOD IN ('INVADJ', 'ADJAPP')
      AND x.TRNDTE BETWEEN CONVERT(datetime, @strStart_Date, 101) AND CONVERT(datetime, @strEnd_Date, 101)
)
SELECT CONVERT(varchar(10), ev.gendat, 103) AS stkcnt_date,
       CONVERT(varchar(8), ev.gendat, 108)  AS time,
       ev.subsit, ev.count_itmcls, ev.locatn,
       1                                   AS stkcnt,
       MAX(ev.miss)                        AS stkmis,
       MAX(CASE WHEN adj.locatn IS NULL THEN 0 ELSE 1 END) AS stkcor,
       ev.name
FROM ev
LEFT JOIN adj ON adj.locatn = ev.locatn AND adj.day = CAST(ev.gendat AS date)
GROUP BY ev.gendat, ev.subsit, ev.count_itmcls, ev.locatn, ev.name
ORDER BY stkcnt_date, ev.locatn, time;
