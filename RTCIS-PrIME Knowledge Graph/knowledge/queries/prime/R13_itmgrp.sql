-- R13 itmgrp -> PrIME 2022. Params: @wh_id, @locale (caller-bound; US_ENGLISH matches RTCIS text best, falls back to it).
-- itmgrp -> prtfam; grpdsc -> dscmst 'prtfam' LNGDSC (87/93 shared groups identical at Euskirchen);
-- itmcls (F/P) -> dominant prtmst.TYPCOD of the family's parts mapped back to F/P (FERT->F, ROH->P, else TYPCOD);
-- fifo_window -> NULL: PrIME FIFWIN is per part and 30 on every DE08 part (RTCIS group values e.g. 90) [ELIMINATED].
SELECT f.PRTFAM AS itmgrp,
       ISNULL(d.LNGDSC, de.LNGDSC) AS grpdsc,
       CASE t.TYPCOD WHEN 'FERT' THEN 'F' WHEN 'ROH' THEN 'P' ELSE t.TYPCOD END AS itmcls,
       CAST(NULL AS int) AS fifo_window
FROM dbo.prtfam f
LEFT JOIN dbo.dscmst d ON d.COLNAM = 'prtfam' AND d.COLVAL = f.PRTFAM AND d.LOCALE_ID = @locale
LEFT JOIN dbo.dscmst de ON de.COLNAM = 'prtfam' AND de.COLVAL = f.PRTFAM AND de.LOCALE_ID = 'US_ENGLISH'
OUTER APPLY (SELECT TOP 1 p.TYPCOD FROM dbo.prtmst p WHERE p.PRTFAM = f.PRTFAM AND p.WH_ID_TMPL = @wh_id
             GROUP BY p.TYPCOD ORDER BY COUNT(*) DESC) t;
