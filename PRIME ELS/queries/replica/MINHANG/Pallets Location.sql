-- Pallets Location - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT p.gcas AS material_gcas, x.lngdsc AS material_desc,
       p.stoloc, lm.arecod, lm.sto_zone_id AS sto_zone_id,
       CASE
         WHEN p.stoloc LIKE '~NA~'                   THEN 'HOFF_IN'
         WHEN p.stoloc LIKE '~NA~'                  THEN 'HOFF_OUT'
         WHEN p.stoloc LIKE '_0%A'                    THEN 'F0_A'
         WHEN p.stoloc LIKE '~NA~' OR p.stoloc= '~NA~' THEN 'EOL'
         WHEN lm.arecod LIKE 'RDTS'                        THEN 'IN_TRANSIT'
         WHEN lt.prod_flg=1 OR lt.prd_stgflg=1        THEN 'LINE'
         WHEN lt.rcv_stgflg=1                         THEN 'RECEIVING'
         WHEN lt.shp_dck_flg=1 OR lt.stgflg=1         THEN 'SHIPPING'
         WHEN lm.sto_zone_id IS NOT NULL
          AND CAST(lm.sto_zone_id AS NVARCHAR(40)) NOT IN ('10041') THEN 'BIN'
         ELSE 'OTHER'
       END AS loc_type,
       p.lodnum AS pallet_lpn, p.lotnum, p.invsts,
       p.qty_buom, fp.qty_per_pallet,
       CAST(p.qty_buom*1.0/NULLIF(fp.qty_per_pallet,0) AS DECIMAL(18,2)) AS pallet_equiv,
       p.received_dte, p.fifo_dte, p.last_move_dte,
       DATEDIFF(MINUTE, COALESCE(CASE WHEN p.received_dte <= DATEADD(HOUR, 8, GETUTCDATE()) THEN p.received_dte END, CASE WHEN p.fifo_dte <= DATEADD(HOUR, 8, GETUTCDATE()) THEN p.fifo_dte END), DATEADD(HOUR, 8, GETUTCDATE())) AS aging_minutes,
       DATEDIFF(MINUTE, p.last_move_dte,                     DATEADD(HOUR, 8, GETUTCDATE())) AS minutes_in_loc
FROM (SELECT iv.prtnum AS gcas, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts,
             MAX(iv.lotnum) AS lotnum,
             SUM(iv.untqty) AS qty_buom,
             MIN(iv.rcvdte) AS received_dte,
             MIN(CASE WHEN iv.fifdte < DATEADD(YEAR, 1, GETDATE()) THEN iv.fifdte END) AS fifo_dte,
             MAX(iv.lstmov) AS last_move_dte
      FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'BR01') iv
WHERE iv.wh_id='BR01' AND iv.prtnum NOT LIKE '[689]%'
      GROUP BY iv.prtnum, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts) p
LEFT JOIN (SELECT * FROM dbo.locmst WHERE wh_id = 'BR01')  lm ON lm.stoloc=p.stoloc AND lm.wh_id='BR01'
LEFT JOIN dbo.loc_typ lt ON lt.loc_typ_id=lm.loc_typ_id AND lt.wh_id='BR01'
LEFT JOIN (SELECT f.prtnum, f.prt_client_id, MAX(fd.untqty) AS qty_per_pallet
           FROM (SELECT * FROM dbo.prtftp WHERE wh_id = 'BR01') f
           JOIN (SELECT * FROM dbo.prtftp_dtl WHERE wh_id = 'BR01') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                 AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
           WHERE f.wh_id='BR01' AND f.defftp_flg=1 AND f.prtnum NOT LIKE '[689]%'
           GROUP BY f.prtnum, f.prt_client_id) fp
       ON fp.prtnum=p.gcas AND fp.prt_client_id=p.prt_client_id
LEFT JOIN dbo.prtdsc x ON x.colval=p.gcas+'|'+p.prt_client_id+'|BR01' AND x.locale_id='US_ENGLISH'
