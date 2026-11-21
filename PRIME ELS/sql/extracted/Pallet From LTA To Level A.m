let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("SELECT
            'LEVEL_A' AS LEVEL_TYPE,
            CAST(a.trndte AS DATE) AS Day,
            DATEPART(HOUR, a.trndte) AS [Hour Of Day],
            COUNT(DISTINCT a.lodnum) AS PALLETS
        FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') a
        INNER JOIN (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') b
            ON b.lodnum = a.lodnum
        INNER JOIN (SELECT * FROM {S}.wkohdr WHERE wh_id = '{WH_ID}') w
            ON w.wkonum = b.frstol
           AND w.prtnum = b.prtnum
        WHERE a.trndte >= '{START_DT}' AND a.trndte >= {INC_FROM} AND a.trndte < {INC_TO}
          AND a.trndte <= GETDATE()
          AND a.to_arecod NOT LIKE '{AREA_RDTS}'
          AND a.fr_arecod LIKE '{AREA_RDTS}'
          AND a.tostol LIKE '{LOC_LEVEL_A}'
          AND a.to_arecod IS NOT NULL
          AND b.oprcod = 'UID'
          AND b.actcod = 'RCV'
          AND b.trndte <= a.trndte
        GROUP BY CAST(a.trndte AS DATE), DATEPART(HOUR, a.trndte)
        
        UNION ALL
        
        SELECT
            'LEVEL_OTHER' AS LEVEL_TYPE,
            CAST(a.trndte AS DATE) AS Day,
            DATEPART(HOUR, a.trndte) AS [Hour Of Day],
            COUNT(DISTINCT a.lodnum) AS PALLETS
        FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') a
        INNER JOIN (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') b
            ON b.lodnum = a.lodnum
        INNER JOIN (SELECT * FROM {S}.wkohdr WHERE wh_id = '{WH_ID}') w
            ON w.wkonum = b.frstol
           AND w.prtnum = b.prtnum
        WHERE a.trndte >= '{START_DT}' AND a.trndte >= {INC_FROM} AND a.trndte < {INC_TO}
          AND a.trndte <= GETDATE()
          AND a.to_arecod NOT LIKE '{AREA_RDTS}'
          AND a.fr_arecod LIKE '{AREA_RDTS}'
          AND a.tostol NOT LIKE '{LOC_LEVEL_A}'
          AND a.to_arecod = '{AREA_LEVEL_A_PICK}'
          AND a.tostol NOT IN (
              SELECT DISTINCT stoloc
              FROM (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') AS locmst
              WHERE CAST({ZONE_COL} AS NVARCHAR(40)) IN ({ZONES_EXCL_PICK})
          )
          AND a.to_arecod IS NOT NULL
          AND b.oprcod = 'UID'
          AND b.actcod = 'RCV'
          AND b.trndte <= a.trndte
        GROUP BY CAST(a.trndte AS DATE), DATEPART(HOUR, a.trndte)
        
        ORDER BY LEVEL_TYPE, Day, [Hour Of Day];
        
        ")]
            ),
            #"Changed Type" = Table.TransformColumnTypes(Source,{{"Day", type date}})
        in
            #"Changed Type",
    __Result = if __Enabled then __Body else #table(type table [LEVEL_TYPE = text, Day = datetime, PALLETS = Int64.Type, #"Hour Of Day" = Int64.Type], {})
in
    __Result