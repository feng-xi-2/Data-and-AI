let
    __Enabled = fnFeature("Has_Production"),
    __Body =
        let
            // Convert Power BI parameter to SQL datetime string
            StartDateValue = DateTime.ToText(
                DateTime.From(StartDateParameter),
                "yyyy-MM-dd HH:mm:ss.fff"
            ),
        
            SqlQuery = "
                DECLARE @StartDate DATETIME = '" & StartDateValue & "';
        
                WITH
                FilteredDlytrn AS (
                    SELECT
                        d.frstol, d.tostol, d.actcod, d.devcod,
                        d.lodnum, d.trndte, d.prtnum, d.trnqty,
                        d.lotnum, d.sup_lotnum, d.usr_id
                    FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') AS d
                    WHERE d.trndte >= CASE WHEN @StartDate > DATEADD(DAY, -{DETAIL_DAYS}, GETDATE()) THEN @StartDate ELSE DATEADD(DAY, -{DETAIL_DAYS}, GETDATE()) END AND d.trndte >= {INC_FROM} AND d.trndte < {INC_TO}
                      AND (
                            d.actcod IN ('PUT_DRCT','RCV')
                         OR d.devcod = 'WCS_ALTA'
                         OR d.tostol LIKE '{LOC_PROD_SUPPLY}'
                         OR d.tostol LIKE '{LOC_PROD_CHECKIN}'
                          )
                ),
        
                -- Item enrichment ------------------------------------------------
                ftp AS (
                    SELECT prtnum, prt_client_id, wh_id, untpal
                    FROM (SELECT * FROM {S}.prtftp_view WHERE wh_id = '{WH_ID}') AS prtftp_view
                    WHERE wh_id = '{WH_ID}' AND defftp_flg = 1
                ),
                desc_lookup AS (
                    SELECT
                        pm.prtnum,
                        pm.prt_client_id,
                        MAX(p.lngdsc) AS description
                    FROM {S}.prtmst pm
                    LEFT JOIN {S}.prtdsc p
                        ON p.colval IN (
                              COALESCE(CAST(pm.prtnum AS VARCHAR(100)), '')
                            + '|' + COALESCE(CAST(pm.prt_client_id AS VARCHAR(100)), '')
                            + '|' + COALESCE(pm.wh_id_tmpl, ''),
                              CAST(pm.prtnum AS VARCHAR(100)),
                              CAST(pm.prtnum AS VARCHAR(100))
                            + '|' + COALESCE(CAST(pm.prt_client_id AS VARCHAR(100)), ''),
                              CAST(pm.prtnum AS VARCHAR(100)) + '||'
                        )
                    GROUP BY pm.prtnum, pm.prt_client_id
                ),
                item_master AS (
                    SELECT
                        pm.prtnum,
                        MAX(pm.typcod)       AS typcod,
                        MAX(dl.description)  AS description,
                        MAX(pm.stkuom)       AS buom,
                        MAX(ftp.untpal)      AS buom_per_pallet
                    FROM {S}.prtmst pm
                    LEFT JOIN desc_lookup dl
                        ON  dl.prtnum        = pm.prtnum
                        AND dl.prt_client_id = pm.prt_client_id
                    LEFT JOIN ftp
                        ON  ftp.prtnum        = pm.prtnum
                        AND ftp.prt_client_id = pm.prt_client_id
                    GROUP BY pm.prtnum
                ),
        
                -- Work-order header ----------------------------------------------
                wo_header AS (
                    SELECT
                        wkonum, wh_id, prdlin, sch_begdte,
                        prtnum AS fg_prtnum,
                        wkoqty AS fg_planned_qty,
                        wkosts
                    FROM (SELECT * FROM {S}.wkohdr WHERE wh_id = '{WH_ID}') AS wkohdr
                    WHERE wh_id = '{WH_ID}'
                ),
        
                -- Component planned qty (non-FERT only) --------------------------
                wo_component AS (
                    SELECT
                        d.wkonum, d.wh_id,
                        d.prtnum        AS cmp_prtnum,
                        SUM(d.linqty)   AS cmp_planned_qty_cases
                    FROM (SELECT * FROM {S}.wkodtl WHERE wh_id = '{WH_ID}') d
                    LEFT JOIN item_master im ON im.prtnum = d.prtnum
                    WHERE d.linsts NOT IN ('C','B')
                      AND ISNULL(im.typcod,'') <> 'FERT'
                    GROUP BY d.wkonum, d.wh_id, d.prtnum
                ),
        
                -- Return / LTA / WCS_ALTA activity -------------------------------
                ReturnAndLTA AS (
                    SELECT DISTINCT
                        w.wkonum                              AS [Work Order],
                        CAST(NULL AS NVARCHAR(50))            AS [Work Order Line],
                        h.prdlin                              AS [Production Line],
                        h.sch_begdte                          AS [Scheduled Begin Date],
                        RIGHT(h.fg_prtnum, 8)                 AS [FG GCAS],
                        fg.description                        AS [FG Description],
                        h.fg_planned_qty                      AS [FG Planned Qty Cases],
                        ROUND(CAST(h.fg_planned_qty AS decimal(18,4))
                              / NULLIF(fg.buom_per_pallet, 0), 0)
                                                              AS [FG Planned Qty Pallets],
                        CASE
                            WHEN d.actcod = 'PUT_DRCT' THEN 'Return'
                            WHEN d.actcod = 'RCV'      THEN 'LTA'
                            WHEN d.devcod = 'WCS_ALTA' THEN 'WCS_ALTA'
                        END                                   AS Activity,
                        d.lodnum                              AS LPN,
                        CAST(NULL AS NVARCHAR(50))            AS Destination,
                        d.trndte                              AS [Time Scanned],
                        CAST(d.trndte AS DATE)                AS [Date],
                        RIGHT(d.prtnum, 8)                    AS Component_GCAS,
                        im.description                        AS Component_Description,
                        im.buom                               AS Component_BUOM,
                        im.buom_per_pallet                    AS Component_BUOM_Per_Pallet,
                        CASE WHEN ISNULL(im.typcod,'') <> 'FERT'
                             THEN wc.cmp_planned_qty_cases END
                                                              AS Component_Planned_Qty_Cases,
                        CASE WHEN ISNULL(im.typcod,'') <> 'FERT'
                             THEN ROUND(CAST(wc.cmp_planned_qty_cases AS decimal(18,4))
                                        / NULLIF(im.buom_per_pallet, 0), 0) END
                                                              AS Component_Planned_Qty_Pallets,
                        pm.rptuom                             AS UOM,
                        pm.typcod                             AS [Prod Type],
                        pm.shelf_life                         AS [Shelf Life],
                        pm.vc_prtcat                          AS [Prod Category],
                        pm.vc_subsec                          AS [Prod Subsector],
                        d.trnqty                              AS [Quantity per Pallet],
                        d.lotnum                              AS [Lot Num],
                        d.sup_lotnum                          AS [Supplier Lot],
                        d.usr_id                              AS UserId
                    FROM (SELECT * FROM {S}.wkodtl WHERE wh_id = '{WH_ID}') AS w
                    JOIN FilteredDlytrn AS d       ON d.frstol = w.wkonum
                    LEFT JOIN wo_header    h  ON h.wkonum = w.wkonum AND h.wh_id = w.wh_id
                    LEFT JOIN item_master  fg ON fg.prtnum = h.fg_prtnum
                    LEFT JOIN item_master  im ON im.prtnum = d.prtnum
                    LEFT JOIN wo_component wc ON wc.wkonum  = w.wkonum
                                             AND wc.wh_id   = w.wh_id
                                             AND wc.cmp_prtnum = d.prtnum
                    LEFT JOIN {S}.prtmst   pm ON pm.prtnum = d.prtnum
                    WHERE d.actcod IN ('PUT_DRCT','RCV')
                       OR d.devcod = 'WCS_ALTA'
                ),
        
                -- Supply-to-Production / Prod Check-in ---------------------------
                SupplyAndCheckin AS (
                    SELECT
                        p.wkonum                              AS [Work Order],
                        CAST(p.wkolin AS NVARCHAR(50))        AS [Work Order Line],
                        h.prdlin                              AS [Production Line],
                        h.sch_begdte                          AS [Scheduled Begin Date],
                        RIGHT(h.fg_prtnum, 8)                 AS [FG GCAS],
                        fg.description                        AS [FG Description],
                        h.fg_planned_qty                      AS [FG Planned Qty Cases],
                        ROUND(CAST(h.fg_planned_qty AS decimal(18,4))
                              / NULLIF(fg.buom_per_pallet, 0), 0)
                                                              AS [FG Planned Qty Pallets],
                        CASE
                            WHEN d.tostol LIKE '{LOC_PROD_SUPPLY}' THEN 'Supply to Production'
                            WHEN d.tostol LIKE '{LOC_PROD_CHECKIN}' THEN 'Prod Check-in'
                        END                                   AS Activity,
                        d.lodnum                              AS LPN,
                        d.tostol                              AS Destination,
                        d.trndte                              AS [Time Scanned],
                        CAST(d.trndte AS DATE)                AS [Date],
                        RIGHT(d.prtnum, 8)                    AS Component_GCAS,
                        im.description                        AS Component_Description,
                        im.buom                               AS Component_BUOM,
                        im.buom_per_pallet                    AS Component_BUOM_Per_Pallet,
                        CASE WHEN ISNULL(im.typcod,'') <> 'FERT'
                             THEN wc.cmp_planned_qty_cases END
                                                              AS Component_Planned_Qty_Cases,
                        CASE WHEN ISNULL(im.typcod,'') <> 'FERT'
                             THEN ROUND(CAST(wc.cmp_planned_qty_cases AS decimal(18,4))
                                        / NULLIF(im.buom_per_pallet, 0), 0) END
                                                              AS Component_Planned_Qty_Pallets,
                        pm.rptuom                             AS UOM,
                        pm.typcod                             AS [Prod Type],
                        pm.shelf_life                         AS [Shelf Life],
                        pm.vc_prtcat                          AS [Prod Category],
                        pm.vc_subsec                          AS [Prod Subsector],
                        d.trnqty                              AS [Quantity per Pallet],
                        d.lotnum                              AS [Lot Num],
                        CAST(NULL AS NVARCHAR(50))            AS [Supplier Lot],
                        d.usr_id                              AS UserId
                    FROM FilteredDlytrn AS d
                    JOIN (SELECT * FROM {S}.pckwrk_view WHERE wh_id = '{WH_ID}') AS p       ON d.lodnum = p.pallet_id
                    LEFT JOIN wo_header    h  ON h.wkonum = p.wkonum
                    LEFT JOIN item_master  fg ON fg.prtnum = h.fg_prtnum
                    LEFT JOIN item_master  im ON im.prtnum = d.prtnum
                    LEFT JOIN wo_component wc ON wc.wkonum    = p.wkonum
                                             AND wc.cmp_prtnum = d.prtnum
                    LEFT JOIN {S}.prtmst   pm ON pm.prtnum = d.prtnum
                    WHERE d.tostol LIKE '{LOC_PROD_SUPPLY}'
                       OR d.tostol LIKE '{LOC_PROD_CHECKIN}'
                )
        
                SELECT * FROM ReturnAndLTA
                UNION ALL
                SELECT * FROM SupplyAndCheckin;
            ",
        
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query = fnSiteSql(SqlQuery)]
            ),
        
            // Ensure correct data types
            Typed = Table.TransformColumnTypes(Source, {
                {"Work Order",                     type text},
                {"Work Order Line",                type text},
                {"Production Line",                type text},
                {"Scheduled Begin Date",           type datetime},
                {"FG GCAS",                        type text},
                {"FG Description",                 type text},
                {"FG Planned Qty Cases",           type number},
                {"FG Planned Qty Pallets",         type number},
                {"Activity",                       type text},
                {"LPN",                            type text},
                {"Destination",                    type text},
                {"Time Scanned",                   type datetime},
                {"Date",                           type date},
                {"Component_GCAS",                 type text},
                {"Component_Description",          type text},
                {"Component_BUOM",                 type text},
                {"Component_BUOM_Per_Pallet",      type number},
                {"Component_Planned_Qty_Cases",    type number},
                {"Component_Planned_Qty_Pallets",  type number},
                {"UOM",                            type text},
                {"Prod Type",                      type text},
                {"Shelf Life",                     type number},
                {"Prod Category",                  type text},
                {"Prod Subsector",                 type text},
                {"Quantity per Pallet",            type number},
                {"Lot Num",                        type text},
                {"Supplier Lot",                   type text},
                {"UserId",                         type text}
            })
        in
            Typed,
    __Result = if __Enabled then __Body else #table(type table [#"Work Order" = text, #"Work Order Line" = text, Activity = text, LPN = text, Destination = text, #"Time Scanned" = datetime, UOM = text, #"Quantity per Pallet" = number, #"Lot Num" = text, #"Supplier Lot" = text, UserId = text, Date = datetime, #"Prod Type" = text, #"Shelf Life" = number, #"Prod Category" = text, #"Prod Subsector" = text, #"Production Line" = text, #"Scheduled Begin Date" = datetime, #"FG GCAS" = text, #"FG Description" = text, #"FG Planned Qty Cases" = number, #"FG Planned Qty Pallets" = number, Component_GCAS = text, Component_Description = text, Component_BUOM = text, Component_BUOM_Per_Pallet = number, Component_Planned_Qty_Cases = number, Component_Planned_Qty_Pallets = number], {})
in
    __Result