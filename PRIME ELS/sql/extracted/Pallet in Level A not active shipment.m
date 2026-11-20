let
    __Enabled = fnFeature("Has_LevelA"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
        SELECT DISTINCT i.newdte,
            i.prtnum,
            i.stoloc,
            SUM(i.untqty - i.comqty) AS Available_qty
        FROM (SELECT * FROM {S}.invsum WHERE wh_id = '{WH_ID}') i
        WHERE i.stoloc LIKE '{LOC_LEVEL_A}'
          AND i.comqty < i.untqty
                  AND EXISTS (SELECT 1 FROM (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') AS l WHERE l.wh_id = i.wh_id AND l.stoloc = i.stoloc AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0)
          AND NOT EXISTS (
              SELECT 1
              FROM (SELECT * FROM {S}.shipment_line WHERE wh_id = '{WH_ID}') sl,
                   (SELECT * FROM {S}.ord_line WHERE wh_id = '{WH_ID}') ol,
                   (SELECT * FROM {S}.shipment WHERE wh_id = '{WH_ID}') s
              WHERE ol.prtnum = i.prtnum
                AND sl.ordnum = ol.ordnum
                AND sl.ordlin = ol.ordlin
                AND sl.ordsln = ol.ordsln
                AND sl.wh_id  = ol.wh_id
                AND sl.linsts = 'P'
                AND sl.linsts NOT IN ('B', 'C')
                AND sl.ship_id = s.ship_id
                AND s.shpsts NOT IN ('B', 'C', 'D')
          )
        AND i.newdte > '{START_DT}'
        GROUP BY i.prtnum, i.stoloc, i.newdte
        ORDER BY newdte DESC;
        ")]
            ),
            #"Renamed Columns" = Table.RenameColumns(Source,{{"prtnum", "GCAS"}, {"stoloc", "Location"}})
        in
            #"Renamed Columns",
    __Result = if __Enabled then __Body else #table(type table [newdte = datetime, GCAS = text, Location = text, Available_qty = Int64.Type], {})
in
    __Result