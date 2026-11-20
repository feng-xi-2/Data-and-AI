let
    SqlQuery = "
SELECT p.gcas AS material_gcas, x.lngdsc AS material_desc,
       p.stoloc, lm.arecod, lm.{ZONE_COL} AS sto_zone_id,
       CASE
         WHEN p.stoloc LIKE '{LOC_HOFF_IN}'                   THEN 'HOFF_IN'
         WHEN p.stoloc LIKE '{LOC_HOFF_OUT}'                  THEN 'HOFF_OUT'
         WHEN p.stoloc LIKE '{LOC_LEVEL_A}'                    THEN 'F0_A'
         WHEN p.stoloc LIKE '{LOC_EOL}' OR p.stoloc= '{LOC_EOL_EXACT}' THEN 'EOL'
         WHEN lm.arecod LIKE '{AREA_RDTS}'                        THEN 'IN_TRANSIT'
         WHEN {LT_LINE_COND}        THEN 'LINE'
         WHEN {LT_RCV_COND}                         THEN 'RECEIVING'
         WHEN {LT_SHIP_COND}         THEN 'SHIPPING'
         WHEN lm.{ZONE_COL} IS NOT NULL
          AND CAST(lm.{ZONE_COL} AS NVARCHAR(40)) NOT IN ({ZONES_EXCL_BIN}) THEN 'BIN'
         ELSE 'OTHER'
       END AS loc_type,
       p.lodnum AS pallet_lpn, p.lotnum, p.invsts,
       p.qty_buom, fp.qty_per_pallet,
       CAST(p.qty_buom*1.0/NULLIF(fp.qty_per_pallet,0) AS DECIMAL(18,2)) AS pallet_equiv,
       p.received_dte, p.fifo_dte, p.last_move_dte,
       DATEDIFF(MINUTE, COALESCE(CASE WHEN p.received_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.received_dte END, CASE WHEN p.fifo_dte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN p.fifo_dte END), DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())) AS aging_minutes,
       DATEDIFF(MINUTE, p.last_move_dte,                     DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE())) AS minutes_in_loc
FROM (SELECT iv.prtnum AS gcas, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts,
             MAX(iv.lotnum) AS lotnum,
             SUM(iv.untqty) AS qty_buom,
             MIN(iv.rcvdte) AS received_dte,
             MIN(CASE WHEN iv.fifdte < DATEADD(YEAR, 1, GETDATE()) THEN iv.fifdte END) AS fifo_dte,
             MAX(iv.lstmov) AS last_move_dte
      FROM (SELECT * FROM {S}.inventory_view WHERE wh_id = '{WH_ID}') iv
WHERE iv.wh_id='{WH_ID}' AND iv.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
      GROUP BY iv.prtnum, iv.prt_client_id, iv.lodnum, iv.stoloc, iv.invsts) p
LEFT JOIN (SELECT * FROM {S}.locmst WHERE wh_id = '{WH_ID}')  lm ON lm.stoloc=p.stoloc AND lm.wh_id='{WH_ID}'
{LOC_TYP_JOIN}
LEFT JOIN (SELECT f.prtnum, f.prt_client_id, MAX(fd.untqty) AS qty_per_pallet
           FROM (SELECT * FROM {S}.prtftp WHERE wh_id = '{WH_ID}') f
           JOIN (SELECT * FROM {S}.prtftp_dtl WHERE wh_id = '{WH_ID}') fd ON fd.prtnum=f.prtnum AND fd.prt_client_id=f.prt_client_id
                                 AND fd.wh_id=f.wh_id AND fd.ftpcod=f.ftpcod AND fd.pal_flg=1
           WHERE f.wh_id='{WH_ID}' AND f.defftp_flg=1 AND f.prtnum NOT LIKE '{FG_PRTNUM_LIKE}'
           GROUP BY f.prtnum, f.prt_client_id) fp
       ON fp.prtnum=p.gcas AND fp.prt_client_id=p.prt_client_id
LEFT JOIN {S}.prtdsc x ON x.colval=p.gcas+'|'+p.prt_client_id+'|{WH_ID}' AND x.locale_id='{PRTDSC_LOCALE}'
",
    Source = Sql.Database(ReplicaServer, ReplicaDatabase,
        [Query = fnSiteSql(SqlQuery), CommandTimeout = #duration(0, 0, 10, 0)]
    ),
    Typed = Table.TransformColumnTypes(Source, {
        {"material_gcas", type text}, {"material_desc", type text},
        {"stoloc", type text}, {"arecod", type text}, {"sto_zone_id", type text},
        {"loc_type", type text}, {"pallet_lpn", type text}, {"lotnum", type text},
        {"invsts", type text}, {"qty_buom", type number}, {"qty_per_pallet", type number},
        {"pallet_equiv", type number},
        {"received_dte", type datetime}, {"fifo_dte", type datetime}, {"last_move_dte", type datetime},
        {"aging_minutes", Int64.Type}, {"minutes_in_loc", Int64.Type}
    }),
    #"Added Loc Order" = Table.AddColumn(Typed, "Loc Order", each
        if      [loc_type] = "RECEIVING"  then 1
        else if [loc_type] = "BIN"        then 2
        else if [loc_type] = "HOFF_IN"    then 3
        else if [loc_type] = "HOFF_OUT"   then 4
        else if [loc_type] = "F0_A"       then 5
        else if [loc_type] = "IN_TRANSIT" then 6
        else if [loc_type] = "LINE"       then 7
        else if [loc_type] = "EOL"        then 8
        else if [loc_type] = "SHIPPING"   then 9
        else 10, Int64.Type),
    #"Added In WH" = Table.AddColumn(#"Added Loc Order", "In WH Storage", each
        List.Contains({"RECEIVING","BIN","HOFF_IN","HOFF_OUT"}, [loc_type]), type logical),
    #"Added Aging Bucket" = Table.AddColumn(#"Added In WH", "Aging Bucket", each
        if      [aging_minutes] = null  then "Unknown"
        else if [aging_minutes] < 240   then "0-4h"
        else if [aging_minutes] < 1440  then "4-24h"
        else if [aging_minutes] < 4320  then "1-3d"
        else if [aging_minutes] < 10080 then "3-7d"
        else ">7d", type text),
    #"Renamed" = Table.RenameColumns(#"Added Aging Bucket",{{"material_gcas", "GCAS"}, {"material_desc", "Description"}, {"stoloc", "Location"}, {"arecod", "Area"}, {"sto_zone_id", "Zone"}, {"loc_type", "Location Type"}, {"pallet_lpn", "Pallet LPN"}, {"lotnum", "Lot"}, {"invsts", "Inv Status"}, {"qty_buom", "Qty (BUOM)"}, {"aging_minutes", "Aging (Min)"}, {"minutes_in_loc", "Min in Location"}})
in
    #"Renamed"