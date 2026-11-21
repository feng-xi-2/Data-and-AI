let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
                SELECT
            'LEVEL_A' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM {S}.pckwrk_view WHERE wh_id = '{WH_ID}') p
        WHERE p.last_upd_dt >= '{START_DT}'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc LIKE '{LOC_LEVEL_A}'
          AND p.srcare = '{AREA_LEVEL_A_PICK}'
          AND p.pallet_id IS NOT NULL
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        UNION ALL
        
        SELECT
            'LEVEL_OTHER' AS Allocated_FROM,
            CAST(p.last_upd_dt AS DATE) AS Day,
            DATEPART(HOUR, p.last_upd_dt) AS Hour_Of_Day,
            COUNT(DISTINCT p.pallet_id) AS Allocated_Pallet_Count
        FROM (SELECT * FROM {S}.pckwrk_view WHERE wh_id = '{WH_ID}') p
        WHERE p.last_upd_dt >= '{START_DT}'
          AND p.last_upd_dt <= GETDATE()
          AND p.srcloc NOT LIKE '{LOC_LEVEL_A}'
          AND p.srcare = '{AREA_LEVEL_A_PICK}'
          AND p.pallet_id IS NOT NULL
          AND p.srcloc NOT IN (
              SELECT DISTINCT stoloc
              FROM (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') AS locmst
              WHERE CAST({ZONE_COL} AS NVARCHAR(40)) IN ({ZONES_EXCL_PICK})
          )
        GROUP BY CAST(p.last_upd_dt AS DATE), DATEPART(HOUR, p.last_upd_dt)
        
        ORDER BY Allocated_FROM, Day, Hour_Of_Day;
        
        ")]
            ),
            #"Changed Type" = Table.TransformColumnTypes(Source,{{"Day", type date}})
        in
            #"Changed Type",
    __Result = if __Enabled then __Body else #table(type table [Allocated_FROM = text, Day = datetime, Hour_Of_Day = Int64.Type, Allocated_Pallet_Count = Int64.Type], {})
in
    __Result