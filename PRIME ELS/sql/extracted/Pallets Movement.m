let
    SqlQuery = "
SELECT d.dlytrn_id,
       d.trndte                       AS txn_time,
       d.actcod,
       d.oprcod,
       d.frstol                       AS from_loc,
       d.fr_arecod                    AS from_area,
       CAST(lf.{ZONE_COL} AS NVARCHAR(20)) AS from_zone,
       d.tostol                       AS to_loc,
       d.to_arecod                    AS to_area,
       CAST(lt.{ZONE_COL} AS NVARCHAR(20)) AS to_zone,
       d.frinvs, d.toinvs,
       d.trnqty, d.uomcod,
       d.lodnum, d.to_lodnum, d.subnum, d.dtlnum,
       d.usr_id, d.devcod, d.reacod, d.movref, d.cmnt,
       DATEDIFF(MINUTE,
                LAG(d.trndte) OVER (ORDER BY d.trndte, d.dlytrn_id),
                d.trndte)             AS min_since_prev_txn
FROM (SELECT * FROM {S}.dlytrn WHERE wh_id = '{WH_ID}') d
LEFT JOIN (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') lf ON lf.stoloc = d.frstol AND lf.wh_id = d.wh_id
LEFT JOIN (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}') lt ON lt.stoloc = d.tostol AND lt.wh_id = d.wh_id
WHERE d.wh_id  = '{WH_ID}' AND d.trndte >= DATEADD(DAY, -{MOVEMENT_DAYS}, GETDATE()) AND d.trndte >= {INC_FROM} AND d.trndte < {INC_TO}
 -- AND d.lodnum = '<LPN to trace>'
ORDER BY d.trndte, d.dlytrn_id;
",

    Source = Sql.Database(ReplicaServer, ReplicaDatabase,
        [Query = fnSiteSql(SqlQuery), CommandTimeout = #duration(0, 0, 10, 0)]
    )
in
    Source