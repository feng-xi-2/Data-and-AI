-- R14 HD Sperrungen FP ohne Sperrgrund -> PrIME 2022. Params: @wh_id, @locale.
-- RTCIS lot status ctlgrp.QASTAT 'HD' on finished goods -> PrIME inventory status INVSTS 'B' (Blocked) on FERT stock
--   (same-pallet: HD -> B 87%, remainder Q/U where the lot status changed). Grouped per item + lot as the original.
-- Herkunft from SUBSTRING(lot,5,..) unchanged: LOTNUM = CTLGRP on 98.4% of same pallets.
-- MENGE: SUM(casqty) -> SUM(FLOOR(UNTQTY / receiving factor)) - RTCIS casqty is numeric(22,0) per detail; WM_UNIT -> receiving UOM.
-- OBS6 DEVIATION (declared): receiving factor instead of RUIZ.RS UNTCAS. OBS8 safe: SUM per item+lot.
-- BESTAND_SU (stock in SU = statistical units via item_uom 'SU' factor): PrIME has no 'SU' footprint level (0 rows)
--   -> NULL [ELIMINATED; needs the SU conversion source, e.g. SAP].
-- SPERR_DATUM (ctlgrp.CTRL_DATE = last change of the lot record) -> prtlot.LAST_UPD_DT [INFERRED].
-- "ohne Sperrgrund": the original lists every HD lot (no reason filter) - kept. PrIME invhld (hold + reason) is empty at DE08.
WITH s1 AS (
    SELECT d.PRTNUM AS itmcod, d.LOTNUM AS ctlgrp, d.INVSTS AS qastat,
           CAST(SUM(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN CAST(d.UNTQTY AS decimal(19,3)) ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END)) AS numeric(22,0)) AS qty,
           MAX(r.UOMCOD) AS uom, MAX(pl.LAST_UPD_DT) AS ctrl_date, MAX(p.PRTFAM) AS itmgrp, MAX(d.PRT_CLIENT_ID) AS prt_client_id
    FROM dbo.invlod l JOIN dbo.invsub s ON s.LODNUM = l.LODNUM JOIN dbo.invdtl d ON d.SUBNUM = s.SUBNUM
    JOIN dbo.prtmst p ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = l.WH_ID
    LEFT JOIN dbo.prtlot pl ON pl.PRTNUM = d.PRTNUM AND pl.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND pl.LOTNUM = d.LOTNUM AND pl.WH_ID = l.WH_ID
    OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID
                 AND f.WH_ID = l.WH_ID AND f.FTPCOD = d.FTPCOD AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) r
    WHERE l.WH_ID = @wh_id AND p.TYPCOD = 'FERT' AND d.INVSTS = 'B'
    GROUP BY d.PRTNUM, d.LOTNUM, d.INVSTS
)
SELECT DISTINCT s1.itmgrp AS ITMGRP,
       CASE WHEN SUBSTRING(s1.ctlgrp, 5, 2) = '01' THEN 'Euskirchen'
            WHEN SUBSTRING(s1.ctlgrp, 5, 2) = '02' THEN 'Crailsheim'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4847' THEN 'Blois'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4499' THEN 'Euskirchen'
            WHEN SUBSTRING(s1.ctlgrp, 5, 4) = '4544' THEN 'EUS DACH CC'
            ELSE 'Sonstige' END AS Herkunft,
       s1.itmcod AS ARTIKEL, ds.LNGDSC AS BESCHREIBUNG, s1.ctlgrp AS LOTNUMMER, s1.qastat AS QA_STATUS, s1.qty AS MENGE,
       s1.uom AS WM_UNIT, CAST(NULL AS varchar(40)) AS BESTAND_SU, FORMAT(s1.ctrl_date, 'dd.MM.yyyy') AS SPERR_DATUM
FROM s1
OUTER APPLY (SELECT TOP 1 x.LNGDSC FROM dbo.prtdsc x WHERE x.COLNAM = 'prtnum|prt_client_id|wh_id_tmpl'
             AND x.COLVAL IN (s1.itmcod + '|' + s1.prt_client_id + '|' + @wh_id, s1.itmcod + '|' + s1.prt_client_id + '|----')
             AND x.LOCALE_ID IN (@locale, 'US_ENGLISH') AND x.LNGDSC IS NOT NULL
             ORDER BY CASE WHEN x.COLVAL LIKE '%|----' THEN 2 ELSE 1 END, CASE WHEN x.LOCALE_ID = @locale THEN 1 ELSE 2 END) ds
ORDER BY Herkunft, ITMGRP;
