-- Planned PO RPM Breakdown - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:19 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
WITH wo AS (
            SELECT w.wh_id, w.client_id, w.wkonum, w.wkorev, w.prdlin,
                   s.lngdsc AS wo_status, w.sch_begdte, w.sch_enddte,
                   w.prtnum AS fg_gcas, w.wkoqty
            FROM (SELECT * FROM dbo.wkohdr WHERE wh_id = 'VN07') w
            JOIN dbo.dscmst s ON s.colnam='wkosts' AND s.locale_id='US_ENGLISH' AND s.colval=w.wkosts
            WHERE w.wh_id='VN07' AND w.prtnum LIKE '8%'
              AND w.sch_begdte >= DATEADD(DAY, -30,DATEADD(HOUR, 7, GETUTCDATE()))
              AND w.sch_begdte <  DATEADD(DAY, 30,DATEADD(HOUR, 7, GETUTCDATE()))
        ),
        line AS (
            SELECT o.wkonum, d.prtnum AS material_gcas, d.prt_client_id,
                   SUM(d.linqty)     AS required_qty,
                   SUM(d.tot_dlvqty) AS delivered_qty,
                   SUM(d.tot_cnsqty) AS consumed_qty
            FROM wo o
            JOIN (SELECT * FROM dbo.wkodtl WHERE wh_id = 'VN07') d ON d.wh_id=o.wh_id AND d.client_id=o.client_id
                             AND d.wkonum=o.wkonum AND d.wkorev=o.wkorev
            WHERE d.prtnum <> o.fg_gcas AND d.prtnum NOT LIKE '8%'
            GROUP BY o.wkonum, d.prtnum, d.prt_client_id
        ),
        mat AS (
            SELECT l.material_gcas,
                   MAX(fd.untqty) AS mat_qty_per_pallet,
                   MAX(x.lngdsc)  AS material_desc
            FROM (SELECT DISTINCT material_gcas, prt_client_id FROM line) l
            LEFT JOIN (SELECT * FROM dbo.prtftp WHERE wh_id = 'VN07') f      ON f.prtnum=l.material_gcas AND f.prt_client_id=l.prt_client_id
                                       AND f.wh_id='VN07' AND f.defftp_flg=1
            LEFT JOIN (SELECT * FROM dbo.prtftp_dtl WHERE wh_id = 'VN07') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                       AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
            LEFT JOIN dbo.prtdsc x      ON x.colval=l.material_gcas+'|'+l.prt_client_id+'|VN07'
                                       AND x.locale_id='ES-ES'
            GROUP BY l.material_gcas
        ),
        fg AS (
            SELECT prtnum, MAX(untpal) AS fg_cases_per_pallet
            FROM binhduong_replica.footprint_md
            WHERE prtnum IN (SELECT fg_gcas FROM wo)
            GROUP BY prtnum
        )
        SELECT o.wkonum, o.prdlin, o.wo_status, o.sch_begdte, o.sch_enddte,
               o.fg_gcas, o.wkoqty AS fg_planned_cases, f.fg_cases_per_pallet,
               CAST(o.wkoqty*1.0/NULLIF(f.fg_cases_per_pallet,0) AS DECIMAL(18,2)) AS fg_planned_pallets,
               l.material_gcas, m.material_desc, m.mat_qty_per_pallet,
               l.required_qty, l.delivered_qty, l.consumed_qty,
               CAST(l.required_qty *1.0/NULLIF(m.mat_qty_per_pallet,0) AS DECIMAL(18,2)) AS required_pallets,
               CAST(l.delivered_qty*1.0/NULLIF(m.mat_qty_per_pallet,0) AS DECIMAL(18,2)) AS delivered_pallets,
               CAST(CASE WHEN l.required_qty>l.delivered_qty THEN l.required_qty-l.delivered_qty ELSE 0 END
                    *1.0/NULLIF(m.mat_qty_per_pallet,0) AS DECIMAL(18,2))             AS remaining_pallets,
               CEILING(l.required_qty*1.0/NULLIF(m.mat_qty_per_pallet,0))              AS required_pallets_full
        FROM wo o
        JOIN line l      ON l.wkonum=o.wkonum
        LEFT JOIN mat m  ON m.material_gcas=l.material_gcas
        LEFT JOIN fg f   ON f.prtnum=o.fg_gcas
        OPTION (HASH JOIN)
