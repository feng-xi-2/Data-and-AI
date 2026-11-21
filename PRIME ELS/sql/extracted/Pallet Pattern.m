let
    SqlQuery = "
        SELECT DISTINCT prtnum, ftpcod, untpal
        FROM {T_FOOTPRINT}
        WHERE prtnum LIKE '{FG_PRTNUM_LIKE}'
    ",
    Source = Sql.Database(ReplicaServer, ReplicaDatabase,
        [Query = fnSiteSql(SqlQuery)]
    )
in
    Source