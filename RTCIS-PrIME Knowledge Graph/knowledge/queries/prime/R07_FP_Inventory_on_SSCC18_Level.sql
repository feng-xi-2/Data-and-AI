-- R07 FP Inventory on SSCC18 level -> PrIME 2022.
-- Params: @wh_id, @locale, @subsit ('0'->B1, '1'->B2, '%' all), @itmcod (LIKE), @grpdsc, @ulid (LIKE), @locatn (LIKE)
-- su.sitnam (DE07/DE08 subsite) -> building: B1 = former DE07, B2 = former DE08 (99%+ same-pallet); returned as 'DE07'/'DE08'.
-- blding (RTCIS building code '0007') -> '00' + LEFT(ARECOD,2) [INFERRED: 43% exact, area prefix = hall]
-- itmnum ("Categorie": BABYCARE, FABRICCARE ...) -> no PrIME column found (searched 15 prtmst columns) -> NULL [ELIMINATED]
-- qastat RL/HD -> invsts U/B; casqty -> UNTQTY / receiving UOM factor; uom -> receiving UOMCOD; FIFODT -> FIFDTE.
-- OBS6 DEVIATION (declared): receiving factor instead of RUIZ.RS UNTCAS (94% vs 85% same pallets); zero fallback kept.
-- OBS8: PrIME can split one pallet+item+lot over 2 invdtl rows (51 keys at DE08, RTCIS 0) -> summed per key first.
-- casqty is numeric(22,0) in RTCIS (truncated; partial cases of IT-stocked items) -> FLOOR, numeric(22,0).
SELECT CASE a.BLDG_ID WHEN 'B1' THEN 'DE07' WHEN 'B2' THEN 'DE08' ELSE a.BLDG_ID END AS [Subsit],
       '00' + LEFT(m.ARECOD, 2)                         AS [Building],
       l.STOLOC                                         AS [Location],
       l.LODNUM                                         AS [Pallet Number],
       d.FTPCOD                                         AS [Pallet Type],
       d.PRTNUM                                         AS [Item Code],
       ds.LNGDSC                                        AS [Item Description],
       g.LNGDSC                                         AS [Item Group Description],
       d.LOTNUM                                         AS [Control Group],
       CAST(NULL AS nvarchar(30))                       AS [Categorie],
       NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '')      AS [Vendor Lot],
       d.INVSTS                                         AS [QA Status],
       CAST(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN d.UNTQTY ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END) AS numeric(22,0)) AS [Quantity],
       r.UOMCOD                                         AS [WHSE Unit],
       d.FIFDTE                                         AS [First Receipt Date],
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
OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f
             WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND f.WH_ID = l.WH_ID
               AND f.FTPCOD = d.FTPCOD AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) r
OUTER APPLY (SELECT TOP 1 x.LNGDSC FROM dbo.prtdsc x WHERE x.COLNAM = 'prtnum|prt_client_id|wh_id_tmpl'
             AND x.COLVAL IN (d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|' + l.WH_ID, d.PRTNUM + '|' + d.PRT_CLIENT_ID + '|----')
             AND x.LOCALE_ID IN (@locale, 'US_ENGLISH') AND x.LNGDSC IS NOT NULL
             ORDER BY CASE WHEN x.COLVAL LIKE '%|----' THEN 2 ELSE 1 END, CASE WHEN x.LOCALE_ID = @locale THEN 1 ELSE 2 END) ds
WHERE l.WH_ID = @wh_id
  AND p.TYPCOD = 'FERT'
  AND a.BLDG_ID LIKE CASE @subsit WHEN '0' THEN 'B1' WHEN '1' THEN 'B2' ELSE @subsit END
  AND d.PRTNUM LIKE @itmcod
  AND g.LNGDSC IN (@grpdsc)
  AND l.LODNUM LIKE @ulid
  AND l.STOLOC LIKE @locatn;
