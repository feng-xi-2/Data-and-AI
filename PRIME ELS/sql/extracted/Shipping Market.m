let
    __Enabled = fnFeature("Has_SAP_Plan"),
    __Body =
        let
            GCASRaw = #"FG GCAS",
        
            GCASList =
                List.Transform(
                    Text.Split(GCASRaw, ","),
                    each Text.Trim(Text.Trim(_), "'")
                ),
        
            ValuesClause =
                Text.Combine(
                    List.Transform(GCASList, each "('" & _ & "')"),
                    ","
                ),
        
            SQL = "
        WITH gcas_list(gcas) AS (
            VALUES " & ValuesClause & "
        ),
        ortec_filtered AS (
            SELECT
                o.matnr,
                LTRIM(o.matnr, '0') AS matnr_key,   -- normalize ONCE
                o.sapto,
                o.psttr
            FROM cdl_oss_prod.silver_sap_a6p.zr3ortec o
            JOIN gcas_list g
              ON RIGHT(o.matnr, 8) = g.gcas
            WHERE o.sap_chng_type_code <> 'D'
              AND o.sapfrom = '{SAP_Plant}'                -- no cast, string compare
              AND o.psttr  >= '{START_YYYYMMDD}'            -- no cast (assumes string/date storage)
        ),
        mara_fert AS (
            SELECT DISTINCT LTRIM(matnr, '0') AS matnr_key
            FROM cdl_oss_prod.silver_sap_a6p.mara
            WHERE sap_chng_type_code <> 'D'
              AND mtart = 'FERT'
        ),
        plants AS (
            SELECT TRIM(plant) AS plant_key, city, country_region_key
            FROM cdl_oss_prod.silver_sap_a6p.t001w_plants_branches
            WHERE sap_chng_type_code <> 'D'
        )
        SELECT
            RIGHT(o.matnr, 8)          AS MatNr,
            p.city                     AS DestinationCity,
            p.country_region_key       AS MarketCode,
            MIN(o.psttr)               AS EarliestShipDate,
            MAX(o.psttr)               AS LatestShipDate
        FROM ortec_filtered o
        LEFT SEMI JOIN mara_fert m
            ON o.matnr_key = m.matnr_key
        LEFT JOIN plants p
            ON TRIM(o.sapto) = p.plant_key
        GROUP BY
            RIGHT(o.matnr, 8),
            p.city,
            p.country_region_key
        ",
        
            Source =
                Value.NativeQuery(
                    Databricks.Catalogs(DatabricksHost, DatabricksHttpPath,
                        [Catalog="cdl_oss_prod", Implementation="2.0"]
                    ){[Name="cdl_oss_prod",Kind="Database"]}[Data],
                    fnSiteSql(SQL),
                    null,
                    [EnableFolding=false]        // we're passing native SQL, skip folding overhead
                ),
            #"Renamed Columns" = Table.RenameColumns(Source,{{"MatNr", "FG GCAS"}})
        in
            #"Renamed Columns",
    __Result = if __Enabled then __Body else #table(type table [#"FG GCAS" = text, DestinationCity = text, MarketCode = text, EarliestShipDate = text, LatestShipDate = text], {})
in
    __Result