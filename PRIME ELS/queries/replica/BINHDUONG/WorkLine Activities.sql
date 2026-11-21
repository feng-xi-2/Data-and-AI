-- WorkLine Activities - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:20 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
DECLARE @StartDate DATETIME = '2026-07-26 00:00:00';
        
                WITH
                FilteredDlytrn AS (
                    SELECT
                        d.frstol, d.tostol, d.actcod, d.devcod,
                        d.lodnum, d.trndte, d.prtnum, d.trnqty,
                        d.lotnum, d.sup_lotnum, d.usr_id
                    FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') AS d
                    WHERE d.trndte >= CASE WHEN @StartDate > DATEADD(DAY, -14, GETDATE()) THEN @StartDate ELSE DATEADD(DAY, -14, GETDATE()) END AND d.trndte >= '1900-01-01' AND d.trndte < '9999-12-31'
                      AND (
                            d.actcod IN ('PUT_DRCT','RCV')
                         OR d.devcod = 'WCS_ALTA'
                         OR d.tostol LIKE 'PL%'
                         OR d.tostol LIKE 'BD%'
                          )
                ),
        
                -- Item enrichment ------------------------------------------------
                ftp AS (
                    SELECT prtnum, prt_client_id, wh_id, untpal
                    FROM (SELECT * FROM dbo.prtftp_view WHERE wh_id = 'VN07') AS prtftp_view
                    WHERE wh_id = 'VN07' AND defftp_flg = 1
                ),
                desc_lookup AS (
                    SELECT
                        pm.prtnum,
                        pm.prt_client_id,
                        MAX(p.lngdsc) AS description
                    FROM dbo.prtmst pm
                    LEFT JOIN dbo.prtdsc p
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
                    FROM dbo.prtmst pm
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
                    FROM (SELECT * FROM dbo.wkohdr WHERE wh_id = 'VN07') AS wkohdr
                    WHERE wh_id = 'VN07'
                ),
        
                -- Component planned qty (non-FERT only) --------------------------
                wo_component AS (
                    SELECT
                        d.wkonum, d.wh_id,
                        d.prtnum        AS cmp_prtnum,
                        SUM(d.linqty)   AS cmp_planned_qty_cases
                    FROM (SELECT * FROM dbo.wkodtl WHERE wh_id = 'VN07') d
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
                    FROM (SELECT * FROM dbo.wkodtl WHERE wh_id = 'VN07') AS w
                    JOIN FilteredDlytrn AS d       ON d.frstol = w.wkonum
                    LEFT JOIN wo_header    h  ON h.wkonum = w.wkonum AND h.wh_id = w.wh_id
                    LEFT JOIN item_master  fg ON fg.prtnum = h.fg_prtnum
                    LEFT JOIN item_master  im ON im.prtnum = d.prtnum
                    LEFT JOIN wo_component wc ON wc.wkonum  = w.wkonum
                                             AND wc.wh_id   = w.wh_id
                                             AND wc.cmp_prtnum = d.prtnum
                    LEFT JOIN dbo.prtmst   pm ON pm.prtnum = d.prtnum
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
                            WHEN d.tostol LIKE 'PL%' THEN 'Supply to Production'
                            WHEN d.tostol LIKE 'BD%' THEN 'Prod Check-in'
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
                    JOIN (SELECT * FROM dbo.pckwrk_view WHERE wh_id = 'VN07') AS p       ON d.lodnum = p.pallet_id
                    LEFT JOIN wo_header    h  ON h.wkonum = p.wkonum
                    LEFT JOIN item_master  fg ON fg.prtnum = h.fg_prtnum
                    LEFT JOIN item_master  im ON im.prtnum = d.prtnum
                    LEFT JOIN wo_component wc ON wc.wkonum    = p.wkonum
                                             AND wc.cmp_prtnum = d.prtnum
                    LEFT JOIN dbo.prtmst   pm ON pm.prtnum = d.prtnum
                    WHERE d.tostol LIKE 'PL%'
                       OR d.tostol LIKE 'BD%'
                )
        
                SELECT * FROM ReturnAndLTA
                UNION ALL
                SELECT * FROM SupplyAndCheckin;
