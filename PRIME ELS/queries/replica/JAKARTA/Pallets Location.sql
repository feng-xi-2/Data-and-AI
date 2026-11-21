-- Pallets Location - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT p.gcas AS material_gcas, x.lngdsc AS material_desc,
       p.stoloc, lm.arecod, lm.arecod AS sto_zone_id,
       CASE
         WHEN p.stoloc LIKE '~NA~'                   THEN 'HOFF_IN'
         WHEN p.stoloc LIKE '~NA~'                  THEN 'HOFF_OUT'
         WHEN p.stoloc LIKE 'C%A'                    THEN 'F0_A'
         WHEN p.stoloc LIKE '~NA~' OR p.stoloc= '~NA~' THEN 'EOL'
         WHEN lm.arecod LIKE 'RDTS%'                        THEN 'IN_TRANSIT'
         WHEN lm.arecod LIKE 'PE%'        THEN 'LINE'
         WHEN lm.arecod LIKE 'RS%' OR lm.arecod LIKE 'RCV%'                         THEN 'RECEIVING'
         WHEN lm.arecod LIKE 'SHST%'         THEN 'SHIPPING'
         WHEN lm.arecod IS NOT NULL
          AND CAST(lm.arecod AS NVARCHAR(40)) NOT IN ('~NA~') THEN 'BIN'
         ELSE 'OTHER'
       END AS loc_type,
       p.lodnum AS pallet_lpn, p.lotnum, p.invsts,
       p.qty_buom, fp.qty_per_pallet,
       CAST(p.qty_buom*1.0/NULLIF(fp.qty_per_pallet,0) AS DECIMAL(18,2)) AS pallet_equiv,
       p.received_dte, p.fifo_dte, p.last_move_dte,
       DATEDIFF(MINUTE, COALESCE(CASE WHEN p.received_dte <= DATEADD(HOUR, 7, GETUTCDATE()) THEN p.received_dte END, CASE WHEN p.fifo_dte <= DATEADD(HOUR, 7, GETUTCDATE()) THEN p.fifo_dte END), DATEADD(HOUR, 7, GETUTCDATE())) AS aging_minutes,
       DATEDIFF(MINUTE, p.last_move_dte,                     DATEADD(HOUR, 7, GETUTCDATE())) AS minutes_in_loc
FROM (SELECT iv.prtnum AS gcas, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts,
             MAX(iv.lotnum) AS lotnum,
             SUM(iv.untqty) AS qty_buom,
             MIN(iv.rcvdte) AS received_dte,
             MIN(CASE WHEN iv.fifdte < DATEADD(YEAR, 1, GETDATE()) THEN iv.fifdte END) AS fifo_dte,
             MAX(iv.lstmov) AS last_move_dte
      FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') iv
WHERE iv.wh_id='ID01' AND iv.prtnum NOT LIKE '8%'
      GROUP BY iv.prtnum, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts) p
LEFT JOIN (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01')  lm ON lm.stoloc=p.stoloc AND lm.wh_id='ID01'

LEFT JOIN (SELECT f.prtnum, f.prt_client_id, MAX(fd.untqty) AS qty_per_pallet
           FROM (SELECT * FROM prodwms.prtftp WHERE wh_id = 'ID01') f
           JOIN (SELECT * FROM prodwms.prtftp_dtl WHERE wh_id = 'ID01') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                 AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
           WHERE f.wh_id='ID01' AND f.defftp_flg=1 AND f.prtnum NOT LIKE '8%'
           GROUP BY f.prtnum, f.prt_client_id) fp
       ON fp.prtnum=p.gcas AND fp.prt_client_id=p.prt_client_id
LEFT JOIN prodwms.prtdsc x ON x.colval=p.gcas+'|'+p.prt_client_id+'|ID01' AND x.locale_id='US_ENGLISH'
