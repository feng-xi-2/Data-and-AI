-- Produced Pallet - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
DECLARE @StartDate DATETIME = '2026-10-01 00:00:00';
        
                   WITH lta_map (lta_source, prod_line, category) AS (
                SELECT * FROM (VALUES ('MD60B026','MD60B026','MD'),('MD60O014','MD60O014','MD'),('MD60O029','MD60O029','MD'),('MD60O056','MD60O056','MD'),('MD60O080','MD60O080','MD'),('MD60S003','MD60S003','MD'),('MD60S004','MD60S004','MD'),('MD60S041','MD60S041','MD'),('MD61R078','MD61R078','MD'),('PC41APN2','PC41APN2','PC'),('PC41BRN2','PC41BRN2','PC'),('PC41BRN3','PC41BRN3','PC'),('PK50OCPC','PK50OCPC','PK'),('PK58FLOT','PK58FLOT','PK'),('PK63MANU','PK63MANU','PK'),('PK65ECO','PK65ECO','PK'),('PK66LSD','PK66LSD','PK'),('PN81C25','PN81C25','PN'),('TB18BLST','TB18BLST','TB'),('TB18PACK','TB18PACK','TB'),('TB26ASRE','TB26ASRE','TB'),('TC17E362','TC17E362','TC'),('TC19NGCA','TC19NGCA','TC'),('TC20D12A','TC20D12A','TC'),('TC31FLOT','TC31FLOT','TC')) AS m(lta_source, prod_line, category)
            ),
            cte AS (
                SELECT
                    d.LODNUM,
                    TRY_CONVERT(datetime, d.INS_DT) AS InsDate,
                    d.TOSTOL,
                    d.FRSTOL,
                    d.PRTNUM                        AS FG_GCAS,        
                    d.TRNQTY,                                
                    (SELECT TOP 1 w.prdlin FROM dbo.wkohdr w WHERE w.wkonum = d.FRSTOL AND w.wh_id = d.WH_ID) AS LTA_SOURCE
                FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'BR01') d
                WHERE
                    (d.ACTCOD = 'RCV' AND d.OPRCOD = 'UID')
                    AND d.PRTNUM LIKE '[689]%'
                    AND (EXISTS (SELECT 1 FROM dbo.wkohdr w WHERE w.wkonum = d.FRSTOL AND w.wh_id = d.WH_ID))
            ),
            -- Item enrichment (description + BUOM)
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
            ftp AS (
                SELECT prtnum, untpal
                FROM (SELECT * FROM dbo.prtftp_view WHERE wh_id = 'BR01') AS prtftp_view
                WHERE wh_id = 'BR01' AND defftp_flg = 1
            )
            SELECT
                c.LTA_SOURCE                                                 AS WORKSTATION_LTA,
                ISNULL(m.prod_line, 'UNMAPPED')                              AS PRODUCT_LINE,
                ISNULL(m.category,  'UNMAPPED')                              AS DEPARTMENT,
                CONVERT(DATE, c.InsDate)                                     AS ReportDate,
                RIGHT('0' + CAST(DATEPART(hour, c.InsDate) AS VARCHAR(2)), 2) AS ReportHour,
        
                c.FG_GCAS                                                    AS FG_GCAS,
                MAX(dl.description)                                          AS FG_Description,
                MAX(ftp.untpal)                                              AS FG_Cases_Per_Pallet,
        
                COUNT(DISTINCT CASE WHEN c.LTA_SOURCE IS NOT NULL THEN c.LODNUM END) AS PalletsArrivedAtLine,
                COUNT(DISTINCT CASE WHEN c.LTA_SOURCE IS NOT NULL THEN c.LODNUM END) AS PalletsLeftFromLine
            FROM cte c
            LEFT JOIN lta_map m ON m.lta_source = c.LTA_SOURCE
            LEFT JOIN desc_lookup dl ON dl.prtnum = c.FG_GCAS
            LEFT JOIN ftp             ON ftp.prtnum = c.FG_GCAS
            WHERE c.InsDate >= @StartDate
            GROUP BY
                c.LTA_SOURCE,
                m.prod_line,
                m.category,
                CONVERT(DATE, c.InsDate),
                DATEPART(hour, c.InsDate),
                c.FG_GCAS
            ORDER BY
                DEPARTMENT,
                PRODUCT_LINE,
                WORKSTATION_LTA,
                ReportDate,
                ReportHour,
                FG_GCAS;
