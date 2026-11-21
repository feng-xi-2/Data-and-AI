let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
            SELECT
            l.stoloc,
            l.lstdte AS Date,
            (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END) AS pallet_spots,
            CASE WHEN l.lochgt > {TALL_HEIGHT_CM}
                 THEN (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END)
                 ELSE 0
            END AS pallet_spots_height_over_150,
            CASE WHEN l.lochgt <= {TALL_HEIGHT_CM}
                 THEN (CASE WHEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) > 0 THEN l.maxqvl - (l.curqvl + ROUND(l.pndqvl, 0)) ELSE 0 END)
                 ELSE 0
            END AS pallet_spots_height_150_or_less,
            l.lochgt AS location_height,
            CASE WHEN l.lochgt > {TALL_HEIGHT_CM} THEN 'OVER_150' ELSE '150_OR_LESS' END AS height_category
        FROM (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') AS l
        {STO_ZONE_JOIN}
        WHERE l.useflg = 1
          AND l.stoflg = 1
          AND l.curqvl <= 1
          AND l.maxqvl <= 2
          AND l.pndqvl <= 1
          AND l.stoloc LIKE '{LOC_LEVEL_A}'
        ORDER BY Date DESC, l.stoloc;
        
        ")]
            )
        in
            #"Source",
    __Result = if __Enabled then __Body else #table(type table [stoloc = text, Date = datetime, pallet_spots = number, pallet_spots_height_over_150 = number, pallet_spots_height_150_or_less = number, location_height = number, height_category = text], {})
in
    __Result