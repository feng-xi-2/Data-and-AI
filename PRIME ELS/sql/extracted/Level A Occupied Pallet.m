let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
        SELECT
            'LEVEL_A_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_LEVEL_A}'
          AND prtnum LIKE '{FG_PRTNUM_LIKE}'
        
        UNION ALL
        
        SELECT
            'LEVEL_A_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_LEVEL_A}'
          AND prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
        
        UNION ALL
        
        SELECT
            'PROBLEM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_PROBLEM}';
        ")]
            )
        in
            #"Source",
    __Result = if __Enabled then __Body else #table(type table [metric_type = text, stoloc = text, prtnum = text, lodnum = text], {})
in
    __Result