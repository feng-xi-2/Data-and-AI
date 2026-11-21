let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("SELECT DISTINCT a.prtnum,a.lodnum,
                a.frstol as A_LOCATION,
                b.tostol as FINAL_LOCATION,
                b.trndte as MOVE_DATE
           from (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') a,
                (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') b
          where a.lodnum = b.lodnum
            and a.frstol like '{LOC_LEVEL_A}'
            and a.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and a.trndte >= '{START_DT}'
            and b.fr_arecod LIKE '{AREA_RDTS}'
            and b.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and b.trndte >= a.trndte AND b.trndte >= {INC_FROM} AND b.trndte < {INC_TO}
            and b.tostol not like '{LOC_LEVEL_A}'
            and b.tostol in (select stoloc
                               from (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') AS locmst
                              where {ZONE_COL} is not null
                                and CAST({ZONE_COL} AS NVARCHAR(40)) not in ({ZONES_EXCL_BIN}))
        order by move_date desc;
        
        ")]
            ),
            #"Renamed Columns" = Table.RenameColumns(Source,{{"prtnum", "GCAS"}})
        in
            #"Renamed Columns",
    __Result = if __Enabled then __Body else #table(type table [GCAS = text, lodnum = text, A_LOCATION = text, FINAL_LOCATION = text, MOVE_DATE = datetime], {})
in
    __Result