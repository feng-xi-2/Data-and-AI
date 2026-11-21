let
    __Enabled = fnFeature("Has_SAP_Plan"),
    __Body =
        let
            Source = Value.NativeQuery(
                Databricks.Catalogs(DatabricksHost, DatabricksHttpPath,
                    [Catalog="cdl_oss_prod.silver_sap_a6p", Database=null, QueryTags=null, EnableAutomaticProxyDiscovery=null, Implementation="2.0", Protocol=null]
                ){[Name="cdl_oss_prod.silver_sap_a6p",Kind="Database"]}[Data],
                fnSiteSql("WITH planned AS (#(lf)    SELECT#(lf)        CAST(CAST(b.matnr AS Int) AS String) AS MatNr,#(lf)        b.plnum AS OrderNo,#(lf)        b.plwrk AS Plant,#(lf)        b.verid AS VerID,#(lf)        b.gsmng AS Qty_BUoM,#(lf)        CAST(CONCAT(LEFT(b.psttr,4),'-',SUBSTR(b.psttr,5,2),'-',RIGHT(b.psttr,2),' ',LEFT(LPAD(COALESCE(NULLIF(b.pstti,''),'000000'),6,'0'),2),':',SUBSTR(LPAD(COALESCE(NULLIF(b.pstti,''),'000000'),6,'0'),3,2),':',RIGHT(LPAD(COALESCE(NULLIF(b.pstti,''),'000000'),6,'0'),2)) AS timestamp) AS Start_DateTime,#(lf)        CAST(CONCAT(LEFT(b.pedtr,4),'-',SUBSTR(b.pedtr,5,2),'-',RIGHT(b.pedtr,2),' ',LEFT(LPAD(COALESCE(NULLIF(b.pedti,''),'000000'),6,'0'),2),':',SUBSTR(LPAD(COALESCE(NULLIF(b.pedti,''),'000000'),6,'0'),3,2),':',RIGHT(LPAD(COALESCE(NULLIF(b.pedti,''),'000000'),6,'0'),2)) AS timestamp) AS Finish_DateTime#(lf)    FROM cdl_oss_prod.silver_sap_a6p.plaf AS b#(lf)    JOIN cdl_oss_prod.silver_sap_a6p.mara AS d ON CAST(b.matnr AS Int) = CAST(d.matnr AS Int)#(lf)    WHERE b.plwrk = '{SAP_Plant}' AND d.mtart = 'FERT' AND b.paart = 'LA' AND b.beskz = 'E' AND b.sap_chng_type_code <> 'D'#(lf)      AND CAST(CONCAT(LEFT(b.psttr,4),'-',SUBSTR(b.psttr,5,2),'-',RIGHT(b.psttr,2)) AS date) >= DATE_ADD(CURRENT_DATE(), -3)#(lf) ),#(lf) process AS (#(lf)    SELECT#(lf)        CAST(CAST(p.matnr AS Int) AS String) AS MatNr,#(lf)        k.aufnr AS OrderNo,#(lf)        p.dwerk AS Plant,#(lf)        p.verid AS VerID,#(lf)        p.psmng AS Qty_BUoM,#(lf)        COALESCE(MIN(CAST(CONCAT(LEFT(r.isdd,4),'-',SUBSTR(r.isdd,5,2),'-',RIGHT(r.isdd,2),' ',LEFT(LPAD(r.isdz,6,'0'),2),':',SUBSTR(LPAD(r.isdz,6,'0'),3,2),':',RIGHT(LPAD(r.isdz,6,'0'),2)) AS timestamp)),CAST(CONCAT(LEFT(MAX(k.gstrs),4),'-',SUBSTR(MAX(k.gstrs),5,2),'-',RIGHT(MAX(k.gstrs),2),' ',LEFT(LPAD(COALESCE(NULLIF(MAX(k.gsuzs),''),'000000'),6,'0'),2),':',SUBSTR(LPAD(COALESCE(NULLIF(MAX(k.gsuzs),''),'000000'),6,'0'),3,2),':',RIGHT(LPAD(COALESCE(NULLIF(MAX(k.gsuzs),''),'000000'),6,'0'),2)) AS timestamp),CAST(CONCAT(LEFT(MAX(k.gstrp),4),'-',SUBSTR(MAX(k.gstrp),5,2),'-',RIGHT(MAX(k.gstrp),2),' 00:00:00') AS timestamp)) AS Start_DateTime,#(lf)        COALESCE(MAX(CAST(CONCAT(LEFT(r.iedd,4),'-',SUBSTR(r.iedd,5,2),'-',RIGHT(r.iedd,2),' ',LEFT(LPAD(r.iedz,6,'0'),2),':',SUBSTR(LPAD(r.iedz,6,'0'),3,2),':',RIGHT(LPAD(r.iedz,6,'0'),2)) AS timestamp)),CAST(CONCAT(LEFT(MAX(k.gltrs),4),'-',SUBSTR(MAX(k.gltrs),5,2),'-',RIGHT(MAX(k.gltrs),2),' ',LEFT(LPAD(COALESCE(NULLIF(MAX(k.gluzs),''),'000000'),6,'0'),2),':',SUBSTR(LPAD(COALESCE(NULLIF(MAX(k.gluzs),''),'000000'),6,'0'),3,2),':',RIGHT(LPAD(COALESCE(NULLIF(MAX(k.gluzs),''),'000000'),6,'0'),2)) AS timestamp),CAST(CONCAT(LEFT(MAX(k.gltrp),4),'-',SUBSTR(MAX(k.gltrp),5,2),'-',RIGHT(MAX(k.gltrp),2),' 00:00:00') AS timestamp)) AS Finish_DateTime#(lf)    FROM cdl_oss_prod.silver_sap_a6p.afko AS k#(lf)    JOIN cdl_oss_prod.silver_sap_a6p.afpo AS p ON k.aufnr = p.aufnr#(lf)    JOIN cdl_oss_prod.silver_sap_a6p.mara AS d ON CAST(p.matnr AS Int) = CAST(d.matnr AS Int)#(lf)    LEFT JOIN cdl_oss_prod.silver_sap_a6p.afru AS r ON k.aufnr = r.aufnr AND r.sap_chng_type_code <> 'D' AND r.isdd IS NOT NULL AND r.isdd <> '00000000'#(lf)    WHERE p.dwerk = '{SAP_Plant}' AND d.mtart = 'FERT'#(lf)      AND CAST(CONCAT(LEFT(k.gstrp,4),'-',SUBSTR(k.gstrp,5,2),'-',RIGHT(k.gstrp,2)) AS date) >= DATE_ADD(CURRENT_DATE(), -3)#(lf)    GROUP BY p.matnr, k.aufnr, p.dwerk, p.verid, p.psmng#(lf) ),#(lf) combined AS (SELECT * FROM planned UNION ALL SELECT * FROM process),#(lf) su_conv AS (#(lf)    SELECT CAST(matnr AS INT) AS MatNrKey,#(lf)           ROUND(MAX(CAST(umrez AS DOUBLE)) / NULLIF(MAX(CAST(umren AS DOUBLE)), 0), 6) AS SU_Factor#(lf)    FROM cdl_oss_prod.silver_sap_a6p.marm#(lf)    WHERE sap_chng_type_code <> 'D' AND meinh = 'SU'#(lf)      AND TRY_CAST(umrez AS DOUBLE) <> 0 AND TRY_CAST(umren AS DOUBLE) <> 0#(lf)      AND CAST(matnr AS INT) IN (SELECT DISTINCT CAST(MatNr AS INT) FROM combined)#(lf)    GROUP BY CAST(matnr AS INT)#(lf) )#(lf) SELECT#(lf)    u.MatNr,#(lf)    m.maktx AS MatDesc,#(lf)    u.OrderNo,#(lf)    COALESCE(c.mdv01, u.VerID) AS ProdLine,#(lf)    u.Qty_BUoM,#(lf)    sc.SU_Factor,#(lf)    ROUND(CAST(u.Qty_BUoM AS DOUBLE) / NULLIF(sc.SU_Factor, 0), 3) AS Qty_SU,#(lf)    u.Start_DateTime,#(lf)    u.Finish_DateTime#(lf) FROM combined AS u#(lf) LEFT JOIN cdl_oss_prod.silver_sap_a6p.mkal AS c ON c.verid = u.VerID AND c.werks = u.Plant AND CAST(c.matnr AS Int) = CAST(u.MatNr AS Int)#(lf) LEFT JOIN cdl_oss_prod.silver_sap_a6p.makt AS m ON CAST(m.matnr AS Int) = CAST(u.MatNr AS Int) AND m.spras = 'E'#(lf) LEFT JOIN su_conv AS sc ON sc.MatNrKey = CAST(u.MatNr AS Int)#(lf) WHERE Start_DateTime <= DATE_ADD(CURRENT_DATE(), 5)#(lf) ORDER BY u.Start_DateTime, ProdLine, u.MatNr"),
                null,
                [EnableFolding=true]
            ),
        
            #"Typed" = Table.TransformColumnTypes(
                Source,
                {
                    {"MatNr",            type text},
                    {"MatDesc",          type text},
                    {"OrderNo",          type text},
                    {"ProdLine",         type text},
                    {"Qty_BUoM",         type number},
                    {"SU_Factor",        type number},
                    {"Qty_SU",           type number},
                    {"Start_DateTime",   type datetime},
                    {"Finish_DateTime",  type datetime}
                }
            ),
        
            // Pallet Pattern merge (still needed for footprint data)
            #"Merged Pattern" = Table.NestedJoin(
                #"Typed", {"MatNr"},
                #"Pallet Pattern", {"prtnum"},
                "PatternTable", JoinKind.LeftOuter
            ),
            #"Expanded Pattern" = Table.ExpandTableColumn(
                #"Merged Pattern", "PatternTable",
                {"ftpcod", "untpal"},
                {"Footprint", "Cases_Per_Pallet"}
            ),
        
            // Calculated columns
            #"Added Total Pallets" = Table.AddColumn(
                #"Expanded Pattern", "Total Pallets",
                each if [Qty_BUoM] = null or [Cases_Per_Pallet] = null or [Cases_Per_Pallet] = 0
                     then null else Number.RoundUp([Qty_BUoM] / [Cases_Per_Pallet]),
                type number
            ),
            #"Added Duration Hours" = Table.AddColumn(
                #"Added Total Pallets", "Planned Duration (Hours)",
                each if [Start_DateTime] = null or [Finish_DateTime] = null then null
                     else Duration.TotalHours([Finish_DateTime] - [Start_DateTime]),
                type number
            ),
            #"Added Pallets Per Hour" = Table.AddColumn(
                #"Added Duration Hours", "Pallets Per Hour",
                each if [Total Pallets] = null or [#"Planned Duration (Hours)"] = null or [#"Planned Duration (Hours)"] = 0
                     then null else [Total Pallets] / [#"Planned Duration (Hours)"],
                type number
            ),
            #"Added SU Per Hour" = Table.AddColumn(
                #"Added Pallets Per Hour", "SU Per Hour",
                each if [Qty_SU] = null or [#"Planned Duration (Hours)"] = null or [#"Planned Duration (Hours)"] = 0
                     then null else [Qty_SU] / [#"Planned Duration (Hours)"],
                type number
            ),
            #"Added Index" = Table.AddIndexColumn(#"Added SU Per Hour", "RowID", 1, 1, Int64.Type),
            #"Renamed Columns" = Table.RenameColumns(#"Added Index", {{"MatNr", "FG GCAS"}}),
        
            // Slot expansion
            #"Added Slot List" = Table.AddColumn(
                #"Renamed Columns", "SlotList",
                each if [Start_DateTime] = null or [Finish_DateTime] = null then null
                     else let baseDT = #datetime(Date.Year([Start_DateTime]), Date.Month([Start_DateTime]),
                                                 Date.Day([Start_DateTime]), Time.Hour([Start_DateTime]), 0, 0),
                              hoursCount = Number.RoundUp(Duration.TotalHours([Finish_DateTime] - baseDT))
                          in List.Transform({0 .. hoursCount - 1}, each baseDT + #duration(0, _, 0, 0)),
                type list
            ),
            #"Expanded Slots" = Table.ExpandListColumn(#"Added Slot List", "SlotList"),
            #"Renamed Slot" = Table.RenameColumns(#"Expanded Slots", {{"SlotList", "Slot_DateTime"}}),
            #"Added Slot Date" = Table.AddColumn(#"Renamed Slot", "Slot Date",
                each if [Slot_DateTime] = null then null else DateTime.Date([Slot_DateTime]), type date),
            #"Added Slot Hour" = Table.AddColumn(#"Added Slot Date", "Slot Hour",
                each if [Slot_DateTime] = null then null else Time.Hour([Slot_DateTime]), Int64.Type),
            #"Added Slot Shift Date" = Table.AddColumn(#"Added Slot Hour", "Slot Shift Date",
                each if [Slot_DateTime] = null then null
                     else if Time.Hour([Slot_DateTime]) >= 6 then DateTime.Date([Slot_DateTime])
                     else Date.AddDays(DateTime.Date([Slot_DateTime]), -1), type date)
        in
            #"Added Slot Shift Date",
    __Result = if __Enabled then __Body else #table(type table [#"FG GCAS" = text, MatDesc = text, ProdLine = text, Qty_BUoM = number, Footprint = text, Cases_Per_Pallet = Int64.Type, #"Total Pallets" = number, #"Planned Duration (Hours)" = number, #"Pallets Per Hour" = number, RowID = Int64.Type, OrderNo = text, Start_DateTime = datetime, Finish_DateTime = datetime, Slot_DateTime = text, #"Slot Date" = datetime, #"Slot Hour" = Int64.Type, #"Slot Shift Date" = datetime, SU_Factor = number, Qty_SU = number, #"SU Per Hour" = number], {})
in
    __Result