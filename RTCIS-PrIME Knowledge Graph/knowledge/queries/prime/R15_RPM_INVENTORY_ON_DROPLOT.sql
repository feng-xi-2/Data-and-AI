-- R15 RPM inventory on drop lot -> PrIME 2022. Params: @wh_id, @locale, @itmcod (LIKE), @grpdsc.
-- HOF* (Hof = yard drop lot) locations exist in PrIME too (area 02DROP-RPM at DE08). subsit '0' (DE07) -> building B1.
-- ulid20 -> LODNUM; casqty -> FLOOR(UNTQTY / receiving factor) (RTCIS numeric(22,0), truncated); VNDCOD/VNDLOT -> SUP_LOTNUM split; QASTAT -> INVSTS; FIFODT -> FIFDTE.
-- OBS6 DEVIATION (declared): receiving factor instead of RUIZ.RS UNTCAS. OBS8 safe: COUNT(DISTINCT LODNUM) + SUM per group.
-- PONUMB (lot's purchase order) -> no PrIME source populated at DE08 (rcvinv.PO_NUM empty, rcvlin by item+lot 0 matches) -> NULL.
SELECT CASE a.BLDG_ID WHEN 'B1' THEN 'DE07' WHEN 'B2' THEN 'DE08' ELSE a.BLDG_ID END AS [Subsit],
       l.STOLOC AS [Location], COUNT(DISTINCT l.LODNUM) AS [Count_Pallets], d.PRTNUM AS [Item Code], ds.LNGDSC AS [Item Description],
       g.LNGDSC AS [Item Group Description], d.LOTNUM AS [Control Group],
       NULLIF(LEFT(d.SUP_LOTNUM, 4), '') AS [Vendor Cod], NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '') AS [Vendor Lot],
       d.INVSTS AS [QA Status],
       CAST(SUM(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN CAST(d.UNTQTY AS decimal(19,3)) ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END)) AS numeric(22,0)) AS [Sum_Quantity],
       d.FIFDTE AS [First Receipt Date], CAST(NULL AS nvarchar(20)) AS [PO Number],
       CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime) AS sysdate
FROM dbo.invlod l
JOIN dbo.invsub s ON s.LODNUM = l.LODNUM
JOIN dbo.invdtl d ON d.SUBNUM = s.SUBNUM
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
WHERE l.WH_ID = @wh_id AND p.TYPCOD = 'ROH' AND LEFT(l.STOLOC, 3) = 'HOF' AND a.BLDG_ID = 'B1'
  AND d.PRTNUM LIKE @itmcod AND g.LNGDSC IN (@grpdsc)
GROUP BY a.BLDG_ID, l.STOLOC, d.PRTNUM, ds.LNGDSC, g.LNGDSC, d.LOTNUM, d.SUP_LOTNUM, d.INVSTS, d.FIFDTE;
