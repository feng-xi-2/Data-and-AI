-- Pallets Location - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/extracted/Pallets Location.m (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {AREA_RDTS}, {FG_PRTNUM_LIKE}, {LOC_EOL}, {LOC_EOL_EXACT}, {LOC_HOFF_IN}, {LOC_HOFF_OUT}, {LOC_LEVEL_A}, {PRTDSC_LOCALE}, {WH_ID}, {ZONES_EXCL_BIN} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

SELECT p.gcas AS material_gcas, x.lngdsc AS material_desc,
       p.stoloc, lm.arecod, lm.sto_zone_id AS sto_zone_id,
       CASE
         WHEN p.stoloc LIKE '{LOC_HOFF_IN}'                   THEN 'HOFF_IN'
         WHEN p.stoloc LIKE '{LOC_HOFF_OUT}'                  THEN 'HOFF_OUT'
         WHEN p.stoloc LIKE '{LOC_LEVEL_A}'                    THEN 'F0_A'
         WHEN p.stoloc LIKE '{LOC_EOL}' OR p.stoloc= '{LOC_EOL_EXACT}' THEN 'EOL'
         WHEN lm.arecod LIKE '{AREA_RDTS}'                        THEN 'IN_TRANSIT'
         WHEN lt.prod_flg=1 OR lt.prd_stgflg=1        THEN 'LINE'
         WHEN lt.rcv_stgflg=1                         THEN 'RECEIVING'
         WHEN lt.shp_dck_flg=1 OR lt.stgflg=1         THEN 'SHIPPING'
         WHEN lm.sto_zone_id IS NOT NULL
          AND CAST(lm.sto_zone_id AS NVARCHAR(40)) NOT IN ({ZONES_EXCL_BIN}) THEN 'BIN'
         ELSE 'OTHER'
       END AS loc_type,
       p.lodnum AS pallet_lpn, p.lotnum, p.invsts,
       p.qty_buom, fp.qty_per_pallet,
       CAST(p.qty_buom*1.0/NULLIF(fp.qty_per_pallet,0) AS DECIMAL(18,2)) AS pallet_equiv,
       p.received_dte, p.fifo_dte, p.last_move_dte,
       DATEDIFF(MINUTE, COALESCE(CASE WHEN p.received_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.received_dte END, CASE WHEN p.fifo_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.fifo_dte END), DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())) AS aging_minutes,
       DATEDIFF(MINUTE, p.last_move_dte,                     DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())) AS minutes_in_loc
FROM (SELECT iv.prtnum AS gcas, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts,
             MAX(iv.lotnum) AS lotnum,
             SUM(iv.untqty) AS qty_buom,
             MIN(iv.rcvdte) AS received_dte,
             MIN(CASE WHEN iv.fifdte < DATEADD(YEAR, 1, GETDATE()) THEN iv.fifdte END) AS fifo_dte,
             MAX(iv.lstmov) AS last_move_dte
      FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = '{WH_ID}') iv
WHERE iv.wh_id='{WH_ID}' AND iv.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
      GROUP BY iv.prtnum, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts) p
LEFT JOIN (SELECT * FROM dbo.locmst WHERE wh_id = '{WH_ID}')  lm ON lm.stoloc=p.stoloc AND lm.wh_id='{WH_ID}'
LEFT JOIN dbo.loc_typ lt ON lt.loc_typ_id=lm.loc_typ_id AND lt.wh_id='{WH_ID}'
LEFT JOIN (SELECT f.prtnum, f.prt_client_id, MAX(fd.untqty) AS qty_per_pallet
           FROM (SELECT * FROM dbo.prtftp WHERE wh_id = '{WH_ID}') f
           JOIN (SELECT * FROM dbo.prtftp_dtl WHERE wh_id = '{WH_ID}') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                 AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
           WHERE f.wh_id='{WH_ID}' AND f.defftp_flg=1 AND f.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
           GROUP BY f.prtnum, f.prt_client_id) fp
       ON fp.prtnum=p.gcas AND fp.prt_client_id=p.prt_client_id
LEFT JOIN dbo.prtdsc x ON x.colval=p.gcas+'|'+p.prt_client_id+'|{WH_ID}' AND x.locale_id='{PRTDSC_LOCALE}'
