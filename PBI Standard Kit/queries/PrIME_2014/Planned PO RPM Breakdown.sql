-- Planned PO RPM Breakdown - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/extracted/Planned PO RPM Breakdown.m (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FG_PRTNUM_LIKE}, {PRTDSC_LOCALE}, {WH_ID}, {WO_WINDOW_DAYS} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

        WITH wo AS (
            SELECT w.wh_id, w.client_id, w.wkonum, w.wkorev, w.prdlin,
                   s.lngdsc AS wo_status, w.sch_begdte, w.sch_enddte,
                   w.prtnum AS fg_gcas, w.wkoqty
            FROM (SELECT * FROM prodwms.wkohdr WHERE wh_id = '{WH_ID}') w
            JOIN prodwms.dscmst s ON s.colnam='wkosts' AND s.locale_id='US_ENGLISH' AND s.colval=w.wkosts
            WHERE w.wh_id='{WH_ID}' AND w.prtnum LIKE '{FG_PRTNUM_LIKE}'
              AND w.sch_begdte >= DATEADD(DAY, -{WO_WINDOW_DAYS},DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))
              AND w.sch_begdte <  DATEADD(DAY, {WO_WINDOW_DAYS},DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))
        ),
        line AS (
            SELECT o.wkonum, d.prtnum AS material_gcas, d.prt_client_id,
                   SUM(d.linqty)     AS required_qty,
                   SUM(d.tot_dlvqty) AS delivered_qty,
                   SUM(d.tot_cnsqty) AS consumed_qty
            FROM wo o
            JOIN (SELECT * FROM prodwms.wkodtl WHERE wh_id = '{WH_ID}') d ON d.wh_id=o.wh_id AND d.client_id=o.client_id
                             AND d.wkonum=o.wkonum AND d.wkorev=o.wkorev
            WHERE d.prtnum <> o.fg_gcas AND d.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
            GROUP BY o.wkonum, d.prtnum, d.prt_client_id
        ),
        mat AS (
            SELECT l.material_gcas,
                   MAX(fd.untqty) AS mat_qty_per_pallet,
                   MAX(x.lngdsc)  AS material_desc
            FROM (SELECT DISTINCT material_gcas, prt_client_id FROM line) l
            LEFT JOIN (SELECT * FROM prodwms.prtftp WHERE wh_id = '{WH_ID}') f      ON f.prtnum=l.material_gcas AND f.prt_client_id=l.prt_client_id
                                       AND f.wh_id='{WH_ID}' AND f.defftp_flg=1
            LEFT JOIN (SELECT * FROM prodwms.prtftp_dtl WHERE wh_id = '{WH_ID}') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                       AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
            LEFT JOIN prodwms.prtdsc x      ON x.colval=l.material_gcas+'|'+l.prt_client_id+'|{WH_ID}'
                                       AND x.locale_id='{PRTDSC_LOCALE}'
            GROUP BY l.material_gcas
        ),
        fg AS (
            SELECT prtnum, MAX(untpal) AS fg_cases_per_pallet
            FROM (SELECT prtnum, ftpcod, untpal FROM prodwms.prtftp_view WHERE wh_id = '{WH_ID}' AND defftp_flg = 1) AS footprint_md
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
        
