let
    __Enabled = fnFeature("Has_Production"),
    __Body =
        let
            // Convert the Power BI parameter to SQL-compatible string
            StartDateValue = DateTime.ToText(
                DateTime.From(StartDateParameter),
                "yyyy-MM-dd HH:mm:ss.fff"
            ),
        
            SqlQuery = "
                DECLARE @StartDate DATETIME = '" & StartDateValue & "';
        
                   WITH lta_map (lta_source, prod_line, category) AS (
                SELECT * FROM (VALUES {LTA_MAP_VALUES}) AS m(lta_source, prod_line, category)
            ),
            cte AS (
                SELECT
                    d.LODNUM,
                    TRY_CONVERT(datetime, d.INS_DT) AS InsDate,
                    d.TOSTOL,
                    d.FRSTOL,
                    d.PRTNUM                        AS FG_GCAS,        
                    d.TRNQTY,                                
                    {PROD_SRC_EXPR} AS LTA_SOURCE
                FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') d
                WHERE
                    ({PROD_TXN_FILTER})
                    AND d.PRTNUM LIKE '{FG_PRTNUM_LIKE}'
                    AND ({PROD_SCOPE})
            ),
            -- Item enrichment (description + BUOM)
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
            ftp AS (
                SELECT prtnum, untpal
                FROM (SELECT * FROM {S}.prtftp_view WHERE wh_id = '{WH_ID}') AS prtftp_view
                WHERE wh_id = '{WH_ID}' AND defftp_flg = 1
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
        
                COUNT(DISTINCT CASE WHEN {PROD_ARRIVED_COND} THEN c.LODNUM END) AS PalletsArrivedAtLine,
                COUNT(DISTINCT CASE WHEN {PROD_LEFT_COND} THEN c.LODNUM END) AS PalletsLeftFromLine
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
            ",
        
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query = fnSiteSql(SqlQuery)]
            ),
        
            // Ensure correct data types
            Typed = Table.TransformColumnTypes(Source, {
                {"WORKSTATION_LTA",       type text},
                {"PRODUCT_LINE",          type text},
                {"DEPARTMENT",            type text},
                {"ReportDate",            type date},
                {"FG_GCAS",               type text},
                {"ReportHour",            type text},
                {"PalletsArrivedAtLine",  Int64.Type},
                {"PalletsLeftFromLine",   Int64.Type}
            }),
        
            #"Added ReportHour_Sort" = Table.AddColumn(
                Typed,
                "ReportHour_Sort",
                each
                    let h = Number.From([ReportHour])
                    in Number.Mod(h - ShiftStartH + 24, 24),
                Int64.Type
            ),
        
            #"Added Shift_Date" = Table.AddColumn(
                #"Added ReportHour_Sort",
                "shift_date",
                each if Number.From([ReportHour]) < ShiftStartH
                     then Date.AddDays([ReportDate], -1)
                     else [ReportDate],
                type date
            ),
        
            #"Added Bucket_Sort" = Table.AddColumn(
                #"Added Shift_Date",
                "Bucket_Sort",
                each Number.IntegerDivide(Number.Mod(Number.From([ReportHour]) - ShiftStartH + 24, 24), 4) + 1,
                Int64.Type
            ),
        
            #"Added Bucket_4h" = Table.AddColumn(
                #"Added Bucket_Sort",
                "Bucket_4h",
                each
                    let
                        startH_raw = ShiftStartH + ([Bucket_Sort] - 1) * 4,
                        endH_raw   = ShiftStartH + [Bucket_Sort] * 4,
                        startH     = Number.Mod(startH_raw, 24),
                        endH       = Number.Mod(endH_raw,   24)
                    in
                        "B" & Text.From([Bucket_Sort]) & " (" &
                        Text.PadStart(Text.From(startH), 2, "0") & ":00-" &
                        Text.PadStart(Text.From(endH),   2, "0") & ":00)",
                type text
            ),
        
            #"Added BucketDateKey" = Table.AddColumn(
                #"Added Bucket_4h",
                "BucketDateKey",
                each Date.ToText([shift_date], "yyyyMMdd") & "-" & Text.From([Bucket_Sort]),
                type text
            )
        in
            #"Added BucketDateKey",
    __Result = if __Enabled then __Body else #table(type table [WORKSTATION_LTA = text, PRODUCT_LINE = text, DEPARTMENT = text, ReportDate = datetime, ReportHour = text, PalletsArrivedAtLine = Int64.Type, PalletsLeftFromLine = Int64.Type, Bucket_Sort = Int64.Type, Bucket_4h = text, BucketDateKey = text, shift_date = datetime, ReportHour_Sort = Int64.Type, FG_GCAS = text, FG_Description = text, FG_Cases_Per_Pallet = Int64.Type], {})
in
    __Result