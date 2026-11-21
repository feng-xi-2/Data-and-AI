let
    __Enabled = fnFeature("Has_HOFF"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("SELECT
            'HOFF_IN_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_HOFF_IN}'
          AND prtnum LIKE '{FG_PRTNUM_LIKE}'
        
        UNION ALL
        
        SELECT
            'HOFF_IN_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_HOFF_IN}'
          AND prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_FG' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_HOFF_OUT}'
          AND prtnum LIKE '{FG_PRTNUM_LIKE}'
        
        UNION ALL
        
        SELECT
            'HOFF_OUT_PM' AS metric_type,
            stoloc,
            prtnum,
            lodnum
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') AS inventory_view
        WHERE stoloc LIKE '{LOC_HOFF_OUT}'
          AND prtnum NOT LIKE '{FG_PRTNUM_LIKE}';
        
        ")]
            )
        in
            #"Source",
    __Result = if __Enabled then __Body else #table(type table [prtnum = text, lodnum = text, stoloc = text, metric_type = text], {})
in
    __Result