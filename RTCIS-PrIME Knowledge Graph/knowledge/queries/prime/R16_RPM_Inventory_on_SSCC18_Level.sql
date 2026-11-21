-- R16 RPM inventory on SSCC18 level -> PrIME 2022.
-- Params: @wh_id, @locale, @subsit ('0'->B1, '1'->B2, '%'), @itmcod (LIKE), @grpdsc, @ulid (LIKE)
-- Mappings as R07 (packaging: TYPCOD 'ROH'); 'WIR007' + HOF -> 'BW-SUBSTRATE-EX' kept on PRTFAM.
-- OBS6 DEVIATION (declared): receiving factor instead of RUIZ.RS UNTCAS; OBS8: invdtl summed per pallet+item+lot.
-- PONUMB -> NULL (rcvinv.PO_NUM filled on 0/93 DE08 receipts). iv.ctrl_date (unitld last change) -> last move
--   invlod.LSTDTE, else pallet creation ADDDTE [INFERRED]. LSTDTE alone is set on 303/97,793 DE08 pallets (empty column);
--   no PrIME date equals RTCIS ctrl_date on the same pallet (7/4,659) because DE08 dates are migration dates
--   (results/probe_field_gaps.json).
SELECT CASE a.BLDG_ID WHEN 'B1' THEN 'DE07' WHEN 'B2' THEN 'DE08' ELSE a.BLDG_ID END AS [Subsit],
       '00' + LEFT(m.ARECOD, 2) AS [Building], l.STOLOC AS [Location], l.LODNUM AS [Pallet Number], d.FTPCOD AS [Pallet Type],
       d.PRTNUM AS [Item Code], ds.LNGDSC AS [Item Description],
       CASE WHEN p.PRTFAM = 'WIR007' AND LEFT(l.STOLOC, 3) = 'HOF' THEN 'BW-SUBSTRATE-EX' ELSE g.LNGDSC END AS [Item Group Description],
       d.LOTNUM AS [Control Group], NULLIF(LEFT(d.SUP_LOTNUM, 4), '') AS [Vendor Cod], NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '') AS [Vendor Lot],
       d.INVSTS AS [QA Status],
       CAST(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN d.UNTQTY ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END) AS numeric(22,0)) AS [Quantity],
       d.FIFDTE AS [First Receipt Date], CAST(NULL AS nvarchar(20)) AS [PO Number], COALESCE(l.LSTDTE, l.ADDDTE) AS ctrl_date,
       CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime) AS sysdate
FROM dbo.invlod l
JOIN (SELECT s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM, MAX(i.FTPCOD) AS FTPCOD, MAX(i.INVSTS) AS INVSTS,
             MIN(i.FIFDTE) AS FIFDTE, MAX(i.SUP_LOTNUM) AS SUP_LOTNUM, SUM(i.UNTQTY) AS UNTQTY
      FROM dbo.invsub s JOIN dbo.invdtl i ON i.SUBNUM = s.SUBNUM
      GROUP BY s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM) d ON d.LODNUM = l.LODNUM
JOIN dbo.prtmst p ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = l.WH_ID
JOIN dbo.locmst m ON m.STOLOC = l.STOLOC AND m.WH_ID = l.WH_ID
JOIN dbo.aremst a ON a.ARECOD = m.ARECOD AND a.WH_ID = m.WH_ID
LEFT JOIN dbo.dscmst g ON g.COLNAM = 'prtfam' AND g.COLVAL = p.PRTFAM AND g.LOCALE_ID = 'US_ENGLISH'
OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID
             AND f.WH_ID = l.WH_ID AND f.FTPCOD = d.FTPCOD AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) r
OUTER APPLY (SELECT TOP 1 x.LNGDSC FROM dbo.prtdsc x WHERE x.COLNAM = 'prtnum|prt_client_id|wh_id_tmpl'
             AND x.COLVAL IN (d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|' + l.WH_ID, d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|----')
             AND x.LOCALE_ID IN (@locale, 'US_ENGLISH') AND x.LNGDSC IS NOT NULL
             ORDER BY CASE WHEN x.COLVAL LIKE '%|----' THEN 2 ELSE 1 END, CASE WHEN x.LOCALE_ID = @locale THEN 1 ELSE 2 END) ds
WHERE l.WH_ID = @wh_id AND p.TYPCOD = 'ROH'
  AND a.BLDG_ID LIKE CASE @subsit WHEN '0' THEN 'B1' WHEN '1' THEN 'B2' ELSE @subsit END
  AND d.PRTNUM LIKE @itmcod AND g.LNGDSC IN (@grpdsc) AND l.LODNUM LIKE @ulid;
