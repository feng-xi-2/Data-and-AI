-- R12 IMP line returns, whole quantity back within 16 h -> PrIME 2022. Param: @wh_id. Window literal 90 days (OBS4).
-- In production this query reads RPM_System tables that R08-R11/R13 fill; once those feeds are switched to the PrIME
-- versions, the ORIGINAL R12 text runs unchanged. This file recomputes the same feeds from PrIME dlytrn for testing.
-- LINE NOT LIKE 'ULINA%' / 'ULINC%' -> shared staging SLA* / SLC* at Euskirchen (1:1 location mapping ULINA1->SLA1,
--   ULINC6->SLC6, ULINCV->SLCV) [INFERRED, site-specific names].
-- ITMGRP / grpdsc -> PRTFAM / dscmst 'prtfam'.
WITH moves AS (
    SELECT d.TRNDTE, d.PRTNUM, d.PRT_CLIENT_ID, d.LODNUM, d.FRSTOL, d.TOSTOL,
           CAST(FLOOR(CASE WHEN ISNULL(u.UNTQTY, 0) = 0 THEN d.TRNQTY ELSE CAST(d.TRNQTY AS decimal(19,3)) / u.UNTQTY END) AS numeric(22,0)) AS QTY,
           u.UOMCOD,
           CASE WHEN EXISTS (SELECT 1 FROM dbo.locmst lm JOIN dbo.loc_typ t ON t.LOC_TYP_ID = lm.LOC_TYP_ID
                             WHERE lm.STOLOC = d.TOSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD') THEN 1 ELSE 0 END AS to_line,
           CASE WHEN EXISTS (SELECT 1 FROM dbo.locmst lm JOIN dbo.loc_typ t ON t.LOC_TYP_ID = lm.LOC_TYP_ID
                             WHERE lm.STOLOC = d.FRSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD') THEN 1 ELSE 0 END AS from_line
    FROM dbo.dlytrn d
    JOIN dbo.prtmst p ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = d.WH_ID
    OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID
                 AND f.WH_ID = d.WH_ID AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) u
    WHERE d.WH_ID = @wh_id AND d.LODNUM IS NOT NULL AND p.TYPCOD = 'ROH'
), RankedDeliveries AS (
    SELECT m.TRNDTE AS DELIVERY_DATE, m.TOSTOL AS LINE,
           CASE WHEN w.WKONUM LIKE '000%' AND LEN(w.WKONUM) = 12 THEN SUBSTRING(w.WKONUM, 4, 9) ELSE w.WKONUM END AS PROCESS_ORDER,
           m.PRTNUM AS ITMCOD, p.PRTFAM AS ITMGRP, g.LNGDSC AS grpdsc, m.QTY, m.UOMCOD AS WHSE_UNIT, m.LODNUM AS ULID,
           ROW_NUMBER() OVER (PARTITION BY m.LODNUM ORDER BY m.TRNDTE ASC) AS DeliveryRank
    FROM moves m
    JOIN dbo.prtmst p ON p.PRTNUM = m.PRTNUM AND p.PRT_CLIENT_ID = m.PRT_CLIENT_ID AND p.WH_ID_TMPL = @wh_id
    LEFT JOIN dbo.dscmst g ON g.COLNAM = 'prtfam' AND g.COLVAL = p.PRTFAM AND g.LOCALE_ID = 'US_ENGLISH'
    OUTER APPLY (SELECT TOP 1 pd.WKONUM FROM dbo.pckwrk_hdr ph JOIN dbo.pckwrk_dtl pd ON pd.WRKREF = ph.WRKREF
                 WHERE ph.PALLET_ID = m.LODNUM AND ph.WH_ID = @wh_id AND pd.WKONUM IS NOT NULL ORDER BY pd.LAST_UPD_DT DESC) w
    WHERE m.to_line = 1
      AND m.TRNDTE > CAST(GETDATE() - 90 AS date) AND m.TRNDTE < CAST(GETDATE() AS date)
      AND m.TOSTOL NOT LIKE 'SLA%' AND m.TOSTOL NOT LIKE 'SLC%'
), RankedReturns AS (
    SELECT m.LODNUM AS ULID, m.TRNDTE AS RETURN_DATE, m.QTY,
           ROW_NUMBER() OVER (PARTITION BY m.LODNUM ORDER BY m.TRNDTE ASC) AS ReturnRank
    FROM moves m WHERE m.from_line = 1 AND m.to_line = 0
)
SELECT d.DELIVERY_DATE, d.LINE, d.PROCESS_ORDER, d.ITMCOD, d.ITMGRP, d.grpdsc, d.QTY, d.WHSE_UNIT, d.ULID,
       r.RETURN_DATE, r.QTY AS RETURN_QTY, DATEDIFF(MINUTE, d.DELIVERY_DATE, r.RETURN_DATE) AS DATE_DIFF
FROM RankedDeliveries d
JOIN RankedReturns r ON d.ULID = r.ULID AND d.DeliveryRank = r.ReturnRank
WHERE d.DELIVERY_DATE < r.RETURN_DATE AND DATEDIFF(MINUTE, d.DELIVERY_DATE, r.RETURN_DATE) < 960 AND d.QTY = r.QTY
ORDER BY d.ULID, d.DELIVERY_DATE ASC;
