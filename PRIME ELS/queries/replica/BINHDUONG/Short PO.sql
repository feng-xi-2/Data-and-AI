-- Short PO - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:20 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            s.workorder                                         AS WRK_ORDER,
            w.WO_STATUS,
            w.FG_GCAS,
            w.FG_DESCRIPTION,
            s.rplref                                            AS RPL_REF,
            COALESCE(rq.usr_id, 'UNKNOWN')                      AS REQUEST_BY,
            rq.actcod                                           AS REQUEST_ACTIVITY,
            rq.trndte                                           AS REQUEST_ACTION_TIME,
            la.usr_id                                           AS LAST_ACTION_BY,
            la.trndte                                           AS LAST_ACTION_TIME,
            s.item                                              AS SHORT_MATERIAL,
            s.item_desc                                         AS MATERIAL_DESCRIPTION,
            s.dsp_untqty                                        AS SHORT_QTY,
            s.untqty_uom                                        AS UOM,
            s.adddte                                            AS SHORT_SINCE,
            DATEDIFF(MINUTE, s.adddte, DATEADD(HOUR, 7, GETUTCDATE())) AS AGING_MINUTES,
            s.dstloc                                            AS DESTINATION_LOC,
            COALESCE(st.loc_type, 'N/A')        AS LOC_TYPE,
            COALESCE(st.stoloc,   'N/A')        AS WH_LOCATION,
            st.invsts                                           AS INV_STATUS,
            st.onhand_qty_buom                                  AS ONHAND_QTY_BUOM,
            CAST(st.oldest_fifo_date AS DATE)                   AS FIFO_DATE,
            DATEADD(HOUR, 7, GETUTCDATE())                      AS LAST_REFRESHED
        FROM (
            /* 1. SHORT PO */
            SELECT DISTINCT
                r.wh_id,
                r.rplref,
                r.wkonum      AS workorder,
                r.dstloc,
                r.prtnum      AS item,
                d.lngdsc      AS item_desc,
                CASE WHEN pv.dspuom IS NULL THEN r.pckqty
                     ELSE r.pckqty / NULLIF(fd.untqty, 0) END AS dsp_untqty,
                COALESCE(pv.dspuom, pv.stkuom)                 AS untqty_uom,
                r.adddte
            FROM (SELECT * FROM dbo.rplwrk WHERE wh_id = 'VN07') r
            LEFT JOIN (SELECT * FROM dbo.prtmst_view WHERE wh_id = 'VN07') pv
                ON  pv.prtnum        = r.prtnum
                AND pv.prt_client_id = r.prt_client_id
                AND pv.wh_id         = r.wh_id
            LEFT JOIN (SELECT * FROM dbo.prtftp WHERE wh_id = 'VN07') f
                ON  f.prtnum        = pv.prtnum
                AND f.prt_client_id = pv.prt_client_id
                AND f.wh_id         = pv.wh_id
                AND f.defftp_flg    = 1
            LEFT JOIN (SELECT * FROM dbo.prtftp_dtl WHERE wh_id = 'VN07') fd
                ON  fd.prtnum        = f.prtnum
                AND fd.prt_client_id = f.prt_client_id
                AND fd.wh_id         = f.wh_id
                AND fd.ftpcod        = f.ftpcod
                AND fd.uomcod        = COALESCE(pv.dspuom, pv.stkuom)
            LEFT JOIN dbo.prtdsc d
                ON d.colval = r.prtnum + '|' + r.client_id + '|' + r.wh_id
            WHERE r.wh_id = 'VN07'
        ) s
        LEFT JOIN (
            /* 2. WO status + FG + FG description */
            SELECT
                wh.WH_ID,
                wh.WKONUM,
                wh.WO_STATUS,
                wh.FG_GCAS,
                fgd.lngdsc AS FG_DESCRIPTION
            FROM (
                SELECT h.WH_ID, h.WKONUM,
                       MAX(h.WKOSTS) AS WO_STATUS,
                       MAX(h.PRTNUM) AS FG_GCAS
                FROM (SELECT * FROM dbo.WKOHDR WHERE wh_id = 'VN07') h
                WHERE h.WH_ID = 'VN07'
                  AND EXISTS (SELECT 1 FROM (SELECT * FROM dbo.rplwrk WHERE wh_id = 'VN07') r2
                              WHERE r2.wh_id = 'VN07'
                                AND r2.wkonum = h.WKONUM)
                GROUP BY h.WH_ID, h.WKONUM
            ) wh
            OUTER APPLY (
                SELECT TOP 1 p.lngdsc
                FROM dbo.prtdsc p
                WHERE p.colval LIKE wh.FG_GCAS + '|%|' + wh.WH_ID
                ORDER BY p.colval
            ) fgd
        ) w
            ON  w.WH_ID  = s.wh_id
            AND w.WKONUM = s.workorder
        LEFT JOIN (
            /* 3. WH stock - only for materials that are currently short */
            SELECT
                il.wh_id,
                id.prtnum,
                il.stoloc,
                CASE WHEN il.stoloc LIKE 'HO%IN'  THEN 'HOFF_IN'
                     WHEN il.stoloc LIKE 'HO%OUT' THEN 'HOFF_OUT'
                     ELSE 'BIN' END   AS loc_type,
                id.invsts,
                SUM(id.untqty)        AS onhand_qty_buom,
                MIN(id.fifdte)        AS oldest_fifo_date
            FROM dbo.invdtl id
            JOIN dbo.invsub isub ON isub.subnum = id.subnum
            JOIN (SELECT * FROM dbo.invlod WHERE wh_id = 'VN07') il   ON il.lodnum   = isub.lodnum
            WHERE il.wh_id = 'VN07'
              AND il.stoloc NOT LIKE 'BDD%'
              AND il.stoloc <> 'PLDN'
              AND id.prtnum NOT LIKE '8%'
              AND EXISTS (SELECT 1 FROM (SELECT * FROM dbo.rplwrk WHERE wh_id = 'VN07') r3
                          WHERE r3.wh_id  = 'VN07'
                            AND r3.prtnum = id.prtnum)
            GROUP BY il.wh_id, id.prtnum, il.stoloc, id.invsts
        ) st
            ON  st.wh_id   = s.wh_id
            AND st.prtnum  = s.item
            AND st.stoloc <> s.dstloc
        
        /* 4. REQUEST_BY: last dlytrn user before the request */
        OUTER APPLY (
            SELECT TOP 1 dt.usr_id, dt.actcod, dt.trndte
            FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') dt
            WHERE dt.prtnum  = s.item
              AND dt.trndte <= s.adddte
              AND dt.trndte >= DATEADD(DAY, -2, s.adddte)      -- limit scan
              AND (dt.frstol = s.workorder OR dt.tostol = s.dstloc)
            ORDER BY dt.trndte DESC
        ) rq
        
        /* 5. LAST_ACTION_BY: latest dlytrn user after the request */
        OUTER APPLY (
            SELECT TOP 1 dt.usr_id, dt.trndte
            FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') dt
            WHERE dt.prtnum  = s.item
              AND dt.trndte >  s.adddte
              AND (dt.frstol = s.workorder OR dt.tostol = s.dstloc)
            ORDER BY dt.trndte DESC
        ) la
