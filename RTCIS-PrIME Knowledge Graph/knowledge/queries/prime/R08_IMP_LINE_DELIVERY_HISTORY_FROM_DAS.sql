-- R08 IMP line delivery history (DAS variant, last 3 days) -> PrIME 2022. Params: @wh_id, @locale (caller-bound).
-- RTCIS: packaging (P) to ULIN% via DEPSUL/LINUSE, plus CASXFR case transfers to a ULIN% line (needs PRDORD).
-- PrIME: one dlytrn row per move; a delivery to a line = ROH pallet moved INTO a location whose location-type category is
--   'PROD' (line PLIN, line staging PSTD, shared staging PSTA). Measured at Euskirchen: all 43 RTCIS ULIN* map 1:1 to PROD
--   locations (ULIN82->EU82, ULINCV->SLCV). Case transfers (CASXFR) are the same dlytrn shape (CASPCK/LSTPCK), so both
--   UNION branches collapse into one filter. DAS archive vs live RTCIS: PrIME has one dlytrn; window kept literal
--   (3 days) - RUIZ.RS OBS4: no runtime input the original did not have.
-- PRDORD: optional in branch 1 (original commented the filter out) -> OUTER APPLY latest pick work WKONUM on the pallet;
--   SUBSTRING(4,9) only for 12-char SAP orders '000%' (internal INTEU... orders returned whole).
-- QTY/WM_UNIT: TRNQTY / receiving-UOM factor and receiving UOM (RTCIS WHSFLG UOM == base UOM for every P item).
-- VENDOR/VENDOR_LOT: SUP_LOTNUM = VNDCOD(4) + VNDLOT at Euskirchen. ULID: LODNUM is 20 chars like RTCIS SUBSTR(ULID,1,20).
-- SILOA/SILOB decode -> dropped (dead: SILO% never passes the line filter in the original).
WITH m AS (
    SELECT d.TOSTOL AS LOCATN, d.TRNDTE AS SYSDAT, d.PRTNUM AS ITMCOD, LEFT(ds.LNGDSC, 15) AS ITMDSC, d.LOTNUM AS CTLGRP,
           NULLIF(LEFT(d.SUP_LOTNUM, 4), '') AS VNDCOD, NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '') AS VNDLOT,
           CAST(FLOOR(CASE WHEN ISNULL(u.UNTQTY, 0) = 0 THEN d.TRNQTY ELSE CAST(d.TRNQTY AS decimal(19,3)) / u.UNTQTY END) AS numeric(22,0)) AS TRNQTY,
           ISNULL(u.UOMCOD, p.STKUOM) AS UOM,
           CASE WHEN w.WKONUM LIKE '000%' AND LEN(w.WKONUM) = 12 THEN SUBSTRING(w.WKONUM, 4, 9) ELSE w.WKONUM END AS PRDORD,
           LEFT(d.LODNUM, 20) AS ULID
    FROM dbo.dlytrn d
    JOIN dbo.prtmst p ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = d.WH_ID
    OUTER APPLY (SELECT TOP 1 pd.WKONUM FROM dbo.pckwrk_hdr ph JOIN dbo.pckwrk_dtl pd ON pd.WRKREF = ph.WRKREF
                 WHERE ph.PALLET_ID = d.LODNUM AND ph.WH_ID = d.WH_ID AND pd.WKONUM IS NOT NULL ORDER BY pd.LAST_UPD_DT DESC) w
    OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID
                 AND f.WH_ID = d.WH_ID AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) u
    OUTER APPLY (SELECT TOP 1 x.LNGDSC FROM dbo.prtdsc x WHERE x.COLNAM = 'prtnum|prt_client_id|wh_id_tmpl'
                 AND x.COLVAL IN (d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|' + d.WH_ID, d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|----')
                 AND x.LOCALE_ID IN (@locale, 'US_ENGLISH') AND x.LNGDSC IS NOT NULL
                 ORDER BY CASE WHEN x.COLVAL LIKE '%|----' THEN 2 ELSE 1 END, CASE WHEN x.LOCALE_ID = @locale THEN 1 ELSE 2 END) ds
    WHERE d.WH_ID = @wh_id AND d.LODNUM IS NOT NULL AND p.TYPCOD = 'ROH'
      AND EXISTS (SELECT 1 FROM dbo.locmst lm JOIN dbo.loc_typ t ON t.LOC_TYP_ID = lm.LOC_TYP_ID
                  WHERE lm.STOLOC = d.TOSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD')
      AND d.TRNDTE > DATEADD(day, -3, GETDATE())
)
SELECT DISTINCT LOCATN AS LINE, FORMAT(SYSDAT, 'yyyy-MM-dd HH:mm:ss') AS DELIVERY_DATE, ITMCOD, ITMDSC AS DESCRIPTION, CTLGRP,
       VNDCOD AS VENDOR, VNDLOT AS VENDOR_LOT, TRNQTY AS QTY, UOM AS WM_UNIT, PRDORD AS PROCESS_ORDER, ULID,
       CONCAT(ULID, FORMAT(SYSDAT, 'yyyy.MM.dd HH:mm:ss')) AS ID_NR
FROM m;
