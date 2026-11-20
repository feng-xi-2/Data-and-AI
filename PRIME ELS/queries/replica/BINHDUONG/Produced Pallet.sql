-- Produced Pallet - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:19 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
DECLARE @StartDate DATETIME = '2026-07-26 00:00:00';
        
                   WITH lta_map (lta_source, prod_line, category) AS (
                SELECT * FROM (VALUES ('LTAAA','BDAABOTT','HDL'),('LTAAU','BDAUTOYO','LFE'),('LTAFC','BDFCLTO2','FR'),('LTAAK','BDAKSAC1','HDL'),('LTADM','BDDMLSU9','LFE'),('LTAFD','BDFDLKW2','FR'),('LTAAE','BDAEPOU2','HDL'),('LTADX','BDDXLTO5','LFE'),('LTAFR','BDFRLEG1','FR'),('LTAAM','BDAMPOU3','HDL'),('LTADC','BDDCLKWT','LFE'),('LTAFX','BDFXZEUS','FR'),('LTADN','BDDNLTEC','LFE'),('LTAJA','BDJADIP1','HDL'),('LTADD','BDDDLSU1','LFE'),('LTADZ','BDDZLPRE','LFE'),('LTADF','BDDFLSU3','LFE'),('LTADQ','BDDQLMES','LFE'),('LTADV','BDDVLME2','LFE'),('LTADW','BDDWLME3','LFE'),('LTAAT','BDATLME4','LFE'),('LTADJ','BDDJLEG4','LFE'),('LTADK','BDDKLEG2','LFE'),('LTACA','BDCACTM1','LFE')) AS m(lta_source, prod_line, category)
            ),
            cte AS (
                SELECT
                    d.LODNUM,
                    TRY_CONVERT(datetime, d.INS_DT) AS InsDate,
                    d.TOSTOL,
                    d.FRSTOL,
                    d.PRTNUM                        AS FG_GCAS,        
                    d.TRNQTY,                                
                    CASE WHEN d.FRSTOL LIKE 'LT%' THEN LEFT(d.FRSTOL, 5) WHEN d.TOSTOL LIKE 'LT%' THEN LEFT(d.TOSTOL, 5) END AS LTA_SOURCE
                FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') d
                WHERE
                    (d.OPRCOD LIKE 'UTR' OR d.OPRCOD LIKE 'RPMSTO' OR d.OPRCOD LIKE 'LTA%')
                    AND d.PRTNUM LIKE '8%'
                    AND (d.FRSTOL LIKE 'LT%' OR d.TOSTOL LIKE 'LT%')
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
                FROM (SELECT * FROM dbo.prtftp_view WHERE wh_id = 'VN07') AS prtftp_view
                WHERE wh_id = 'VN07' AND defftp_flg = 1
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
        
                COUNT(DISTINCT CASE WHEN c.TOSTOL LIKE 'LT%' THEN c.LODNUM END) AS PalletsArrivedAtLine,
                COUNT(DISTINCT CASE WHEN c.FRSTOL LIKE 'LT%' THEN c.LODNUM END) AS PalletsLeftFromLine
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
