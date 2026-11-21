let
    __Enabled = fnFeature("Has_Production"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
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
            DATEDIFF(MINUTE, s.adddte, DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())) AS AGING_MINUTES,
            s.dstloc                                            AS DESTINATION_LOC,
            COALESCE(st.loc_type, 'N/A')        AS LOC_TYPE,
            COALESCE(st.stoloc,   'N/A')        AS WH_LOCATION,
            st.invsts                                           AS INV_STATUS,
            st.onhand_qty_buom                                  AS ONHAND_QTY_BUOM,
            CAST(st.oldest_fifo_date AS DATE)                   AS FIFO_DATE,
            DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())                      AS LAST_REFRESHED
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
            FROM (SELECT * FROM {S}.rplwrk WHERE wh_id = '{WH_ID}') r
            LEFT JOIN (SELECT * FROM {S}.prtmst_view WHERE wh_id = '{WH_ID}') pv
                ON  pv.prtnum        = r.prtnum
                AND pv.prt_client_id = r.prt_client_id
                AND pv.wh_id         = r.wh_id
            LEFT JOIN (SELECT * FROM {S}.prtftp WHERE wh_id = '{WH_ID}') f
                ON  f.prtnum        = pv.prtnum
                AND f.prt_client_id = pv.prt_client_id
                AND f.wh_id         = pv.wh_id
                AND f.defftp_flg    = 1
            LEFT JOIN (SELECT * FROM {S}.prtftp_dtl WHERE wh_id = '{WH_ID}') fd
                ON  fd.prtnum        = f.prtnum
                AND fd.prt_client_id = f.prt_client_id
                AND fd.wh_id         = f.wh_id
                AND fd.ftpcod        = f.ftpcod
                AND fd.uomcod        = COALESCE(pv.dspuom, pv.stkuom)
            LEFT JOIN {S}.prtdsc d
                ON d.colval = r.prtnum + '|' + r.client_id + '|' + r.wh_id
            WHERE r.wh_id = '{WH_ID}'
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
                FROM (SELECT * FROM {S}.WKOHDR WHERE wh_id = '{WH_ID}') h
                WHERE h.WH_ID = '{WH_ID}'
                  AND EXISTS (SELECT 1 FROM (SELECT * FROM {S}.rplwrk WHERE wh_id = '{WH_ID}') r2
                              WHERE r2.wh_id = '{WH_ID}'
                                AND r2.wkonum = h.WKONUM)
                GROUP BY h.WH_ID, h.WKONUM
            ) wh
            OUTER APPLY (
                SELECT TOP 1 p.lngdsc
                FROM {S}.prtdsc p
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
                CASE WHEN il.stoloc LIKE '{LOC_HOFF_IN}'  THEN 'HOFF_IN'
                     WHEN il.stoloc LIKE '{LOC_HOFF_OUT}' THEN 'HOFF_OUT'
                     ELSE 'BIN' END   AS loc_type,
                id.invsts,
                SUM(id.untqty)        AS onhand_qty_buom,
                MIN(id.fifdte)        AS oldest_fifo_date
            FROM {S}.invdtl id
            JOIN {S}.invsub isub ON isub.subnum = id.subnum
            JOIN (SELECT * FROM {S}.invlod WHERE wh_id = '{WH_ID}') il   ON il.lodnum   = isub.lodnum
            WHERE il.wh_id = '{WH_ID}'
              AND il.stoloc NOT LIKE '{LOC_EOL}'
              AND il.stoloc <> '{LOC_EOL_EXACT}'
              AND id.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
              AND EXISTS (SELECT 1 FROM (SELECT * FROM {S}.rplwrk WHERE wh_id = '{WH_ID}') r3
                          WHERE r3.wh_id  = '{WH_ID}'
                            AND r3.prtnum = id.prtnum)
            GROUP BY il.wh_id, id.prtnum, il.stoloc, id.invsts
        ) st
            ON  st.wh_id   = s.wh_id
            AND st.prtnum  = s.item
            AND st.stoloc <> s.dstloc
        
        /* 4. REQUEST_BY: last dlytrn user before the request */
        OUTER APPLY (
            SELECT TOP 1 dt.usr_id, dt.actcod, dt.trndte
            FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') dt
            WHERE dt.prtnum  = s.item
              AND dt.trndte <= s.adddte
              AND dt.trndte >= DATEADD(DAY, -2, s.adddte)      -- limit scan
              AND (dt.frstol = s.workorder OR dt.tostol = s.dstloc)
            ORDER BY dt.trndte DESC
        ) rq
        
        /* 5. LAST_ACTION_BY: latest dlytrn user after the request */
        OUTER APPLY (
            SELECT TOP 1 dt.usr_id, dt.trndte
            FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') dt
            WHERE dt.prtnum  = s.item
              AND dt.trndte >  s.adddte
              AND (dt.frstol = s.workorder OR dt.tostol = s.dstloc)
            ORDER BY dt.trndte DESC
        ) la
        
        ")])
        in
            Source,
    __Result = if __Enabled then __Body else #table(type table [WRK_ORDER = text, WO_STATUS = text, FG_GCAS = text, FG_DESCRIPTION = text, RPL_REF = text, SHORT_MATERIAL = text, MATERIAL_DESCRIPTION = text, SHORT_QTY = Int64.Type, UOM = text, SHORT_SINCE = datetime, DESTINATION_LOC = text, LOC_TYPE = text, WH_LOCATION = text, INV_STATUS = text, ONHAND_QTY_BUOM = Int64.Type, FIFO_DATE = datetime, REQUEST_BY = text, REQUEST_ACTIVITY = text, REQUEST_ACTION_TIME = datetime, LAST_ACTION_BY = text, LAST_ACTION_TIME = datetime, AGING_MINUTES = Int64.Type, LAST_REFRESHED = datetime], {})
in
    __Result