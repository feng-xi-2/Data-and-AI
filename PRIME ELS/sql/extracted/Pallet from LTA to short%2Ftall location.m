let
    __Enabled = fnFeature("Has_Production"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("SELECT 
            i.stoloc,
            i.lodnum,
            i.prtnum,
            i.ftpcod,
            p.hgt AS pallet_height,
            CASE WHEN p.hgt > {TALL_HEIGHT_CM} THEN 'OVER_150'
                 ELSE '150_OR_LESS'
            END AS height_category
        FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') i,
             (SELECT * FROM {S}.prtftp_dtl WHERE wh_id = '{WH_ID}') p
        WHERE p.prtnum = i.prtnum
          AND i.stoloc LIKE '{LOC_LTA}'
          AND i.ftpcod = p.ftpcod
          AND p.wh_id = '{WH_ID}'
          AND p.uomcod = 'PL'
          AND i.lstdte >= '{START_DT}';
        ")]
            )
        in
            #"Source",
    __Result = if __Enabled then __Body else #table(type table [stoloc = text, lodnum = text, prtnum = text, ftpcod = text, pallet_height = number, height_category = text], {})
in
    __Result