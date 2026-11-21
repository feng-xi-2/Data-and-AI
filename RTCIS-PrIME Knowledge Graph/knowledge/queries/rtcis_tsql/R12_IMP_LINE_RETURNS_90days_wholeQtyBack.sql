-- R12 IMP line returns, whole quantity back within 16 h (RPM_System, not RTCIS).
-- The original reads RPM_System.dbo.tbl_Line_Delivery_History / tbl_Line_Return_History (filled by R08/R09 and R10/R11)
-- and tbl_RTCIS_ITMMST_Import / tbl_RTCIS_ITMGRP_Import (filled from R13 + itmmst). RPM_System is not reachable from
-- the replicas, so this test version recomputes the same feeds from RTCIS directly over the retained history.
-- Window literal 90 days, as the original (RTCIS replica keeps ~40 days, so the effective window is shorter).
WITH deliv AS (
    SELECT st.SYSDAT AS DELIVERY_DATE,
           CASE sd.LOCATN WHEN 'SILOB' THEN 'ULINA4' WHEN 'SILOA' THEN 'ULINA3' ELSE sd.LOCATN END AS LINE,
           SUBSTRING(st.PRDORD, 4, 9) AS PROCESS_ORDER, sd.ITMCOD, st.TRNQTY AS QTY, iu.UOM AS WHSE_UNIT, LEFT(sd.ULID, 20) AS ULID
    FROM [EUSKIRCHEN_simp].live3.sysdtl sd
    JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
    JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON iu.ITMCLS = sd.ITMCLS AND iu.ITMCOD = sd.ITMCOD AND iu.WHSFLG = 'Y'
    WHERE sd.ITMCLS = 'P' AND sd.SUBSIT = '0' AND sd.LOCATN LIKE 'ULIN%' AND st.TRNTYP IN ('DEPSUL', 'LINUSE')
), ret AS (
    SELECT sd.ULID AS ULID, st.SYSDAT AS RETURN_DATE, st.TRNQTY AS QTY
    FROM [EUSKIRCHEN_simp].live3.sysdtl sd
    JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
    WHERE sd.ITMCLS = 'P' AND sd.SUBSIT = '0' AND sd.LOCATN LIKE 'ULIN%' AND st.TRNTYP = 'MANLID'
), RankedDeliveries AS (
    SELECT a.DELIVERY_DATE, a.LINE, a.PROCESS_ORDER, a.ITMCOD, c.ITMGRP, g.grpdsc, a.QTY, a.WHSE_UNIT, a.ULID,
           ROW_NUMBER() OVER (PARTITION BY a.ULID ORDER BY a.DELIVERY_DATE ASC) AS DeliveryRank
    FROM deliv a
    JOIN [EUSKIRCHEN_simp].live3.itmmst c ON a.ITMCOD = c.ITMCOD AND c.ITMCLS = 'P'
    JOIN [EUSKIRCHEN_simp].live3.itmgrp g ON c.itmgrp = g.itmgrp AND c.itmcls = g.itmcls
    WHERE a.DELIVERY_DATE > CAST(GETDATE() - 90 AS date) AND a.DELIVERY_DATE < CAST(GETDATE() AS date)
      AND a.LINE NOT LIKE 'ULINA%' AND a.LINE NOT LIKE 'ULINC%'
), RankedReturns AS (
    SELECT b.ULID, b.RETURN_DATE, b.QTY, ROW_NUMBER() OVER (PARTITION BY b.ULID ORDER BY b.RETURN_DATE ASC) AS ReturnRank
    FROM ret b
)
SELECT d.DELIVERY_DATE, d.LINE, d.PROCESS_ORDER, d.ITMCOD, d.ITMGRP, d.grpdsc, d.QTY, d.WHSE_UNIT, d.ULID,
       r.RETURN_DATE, r.QTY AS RETURN_QTY, DATEDIFF(MINUTE, d.DELIVERY_DATE, r.RETURN_DATE) AS DATE_DIFF
FROM RankedDeliveries d
JOIN RankedReturns r ON d.ULID = r.ULID AND d.DeliveryRank = r.ReturnRank
WHERE d.DELIVERY_DATE < r.RETURN_DATE AND DATEDIFF(MINUTE, d.DELIVERY_DATE, r.RETURN_DATE) < 960 AND d.QTY = r.QTY
ORDER BY d.ULID, d.DELIVERY_DATE ASC;
