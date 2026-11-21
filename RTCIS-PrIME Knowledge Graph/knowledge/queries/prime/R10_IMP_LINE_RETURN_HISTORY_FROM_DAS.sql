-- R10 IMP line return history (DAS variant, last 3 days) -> PrIME 2022. Params: @wh_id, @locale (caller-bound).
-- Window literal (OBS4); no DISTINCT - the original has none (OBS8: keep the original grain).
-- RTCIS MANLID at ULIN% = a pallet/ULID created at the line for packaging coming back from production.
-- PrIME: ROH pallet moved OUT OF a PROD-category location (line / line staging) into a non-PROD location [INFERRED: PrIME has
--   no MANLID; the return is the reverse move. Re-labelling at the line, if any, is not a separate event in dlytrn].
--   LINE = FRSTOL (the line the material left). Other column mappings as R08.
WITH m AS (
    SELECT d.FRSTOL AS LOCATN, d.TRNDTE AS SYSDAT, d.PRTNUM AS ITMCOD, LEFT(ds.LNGDSC, 15) AS ITMDSC, d.LOTNUM AS CTLGRP,
           NULLIF(LEFT(d.SUP_LOTNUM, 4), '') AS VNDCOD, NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '') AS VNDLOT,
           CAST(FLOOR(CASE WHEN ISNULL(u.UNTQTY, 0) = 0 THEN d.TRNQTY ELSE CAST(d.TRNQTY AS decimal(19,3)) / u.UNTQTY END) AS numeric(22,0)) AS TRNQTY,
           ISNULL(u.UOMCOD, p.STKUOM) AS UOM,
           CASE WHEN w.WKONUM LIKE '000%' AND LEN(w.WKONUM) = 12 THEN SUBSTRING(w.WKONUM, 4, 9) ELSE w.WKONUM END AS PRDORD,
           d.LODNUM AS ULID
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
                  WHERE lm.STOLOC = d.FRSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD')
      AND NOT EXISTS (SELECT 1 FROM dbo.locmst lm JOIN dbo.loc_typ t ON t.LOC_TYP_ID = lm.LOC_TYP_ID
                      WHERE lm.STOLOC = d.TOSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD')
      AND d.TRNDTE > DATEADD(day, -3, GETDATE())
)
SELECT LOCATN AS LINE, FORMAT(SYSDAT, 'yyyy-MM-dd HH:mm:ss') AS RETURN_DATE, ITMCOD, ITMDSC AS DESCRIPTION, CTLGRP,
       VNDCOD AS VENDOR, VNDLOT AS VENDOR_LOT, TRNQTY AS QTY, UOM AS WM_UNIT, PRDORD AS PROCESS_ORDER, ULID,
       CONCAT(ULID, FORMAT(SYSDAT, 'yyyy.MM.dd HH:mm:ss')) AS ID_NR
FROM m;
