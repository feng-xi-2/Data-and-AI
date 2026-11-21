let
    __Enabled = fnFeature("Has_RPM_Master"),
    __Body =
        let
            // ====== SETTINGS ======
            FolderPath     = Text.From(Record.FieldOrDefault(SiteTokens, "RPM_Folder", "")),
            MasterFile     = Text.From(Record.FieldOrDefault(SiteTokens, "RPM_Master_File", "")),
            MapFile        = Text.From(Record.FieldOrDefault(SiteTokens, "RPM_Map_File", "")),
            VendorListFile = Text.From(Record.FieldOrDefault(SiteTokens, "RPM_VendorList_File", "")),
            VendorListSheet = Text.From(Record.FieldOrDefault(SiteTokens, "RPM_VendorList_Sheet", "")),
        
            MapGCASCol   = "GCAS",
            MapVendorCol = "Vendor Code",
        
            JITText    = "JIT",
            NonJITText = "Non-JIT",
        
            FullPath = (fileName as text) as text => Text.TrimEnd(FolderPath, "\") & "\" & fileName,
        
            // ====== HELPERS ======
            LoadSheet = (fileName as text, sheetName as nullable text) as table =>
                let
                    Src   = Excel.Workbook(File.Contents(FullPath(fileName)), true, true),
                    Sheet = if sheetName = null
                            then Table.SelectRows(Src, each [Kind] = "Sheet"){0}[Data]
                            else Src{[Item = sheetName, Kind = "Sheet"]}[Data]
                in
                    Sheet,
        
            CleanKey = (x) => if x = null then null else Text.Upper(Text.Trim(Text.From(x))),
        
            // ====== 1. JIT VENDOR CODES (vendor list: col 1 = Vendor Code, col 4 = JIT flag) ======
            VL      = LoadSheet(VendorListFile, VendorListSheet),
            VLCols  = Table.ColumnNames(VL),
            VLSel   = Table.SelectColumns(VL, {VLCols{0}, VLCols{3}}),
            VLRen   = Table.RenameColumns(VLSel, {{VLCols{0}, "Vendor Code"}, {VLCols{3}, "JITFlag"}}),
            VLKey   = Table.TransformColumns(VLRen, {{"Vendor Code", CleanKey, type text}, {"JITFlag", CleanKey, type text}}),
            JITVendors = Table.Distinct(
                        Table.SelectColumns(
                            Table.SelectRows(VLKey, each [#"Vendor Code"] <> null and [JITFlag] = "JIT"),
                            {"Vendor Code"})),
        
            // ====== 2. MATERIAL -> VENDOR CODE MAP, keep only JIT vendors ======
            MapRaw = LoadSheet(MapFile, null),
            MapSel = Table.SelectColumns(MapRaw, {MapGCASCol, MapVendorCol}),
            MapRen = Table.RenameColumns(MapSel, {{MapGCASCol, "GCAS"}, {MapVendorCol, "Vendor Code"}}),
            MapKey = Table.TransformColumns(MapRen, {{"GCAS", CleanKey, type text}, {"Vendor Code", CleanKey, type text}}),
            MapJIT = Table.NestedJoin(MapKey, {"Vendor Code"}, JITVendors, {"Vendor Code"}, "J", JoinKind.Inner),
            JITGcas = Table.Distinct(Table.SelectColumns(MapJIT, {"GCAS"})),
            JITTag  = Table.AddColumn(JITGcas, "JIT", each JITText, type text),
        
            // ====== 3. MATERIAL MASTER (CSV), non-FG only (GCAS not starting with 8) ======
            MasterCsv = Csv.Document(
                            File.Contents(FullPath(MasterFile)),
                            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
                        ),
            Master      = Table.PromoteHeaders(MasterCsv, [PromoteAllScalars = true]),
            MasterKey   = Table.TransformColumns(Master, {{"Material No.", CleanKey, type text}}),
            MasterNonFG = Table.SelectRows(MasterKey, each [#"Material No."] <> null and not Text.StartsWith([#"Material No."], "8")),
        
            // ====== 4. MAP MATERIAL -> JIT / NON-JIT ======
            Joined   = Table.NestedJoin(MasterNonFG, {"Material No."}, JITTag, {"GCAS"}, "J", JoinKind.LeftOuter),
            Expanded = Table.ExpandTableColumn(Joined, "J", {"JIT"}, {"JIT"}),
            Final    = Table.ReplaceValue(Expanded, null, NonJITText, Replacer.ReplaceValue, {"JIT"})
        in
            Final,
    __Result = if __Enabled then __Body else #table(type table [#"Material No." = text, Description = text, UOM = text, ProdCategory01 = text, ProdCategory02 = text, ProdType01 = text, ProdType02 = text, UOMperPlt_BDWH = text, UOMperPallet_EXWH = text, #"SU per CS" = text, #"IT per CS" = text, #"CS Length" = text, #"CS Width" = text, #"CS Height" = text, #"CS Unit of Dimension" = text, #"CS Volume" = text, #"CS Volume unit" = text, #"CS Gross Weight" = text, #"CS Weight unit" = text, #"EAN UPC" = text, #"CS EAN" = text, #"IT Length" = text, #"IT Width" = text, #"IT Height" = text, #"IT Unit of Dimension" = text, #"IT Volume" = text, #"IT Volume unit" = text, #"IT Gross Weight" = text, #"IT Weight unit" = text, #"BUOM per Pal A2" = text, #"BUOM per Pal C19" = text, #"BUOM per Pal C41" = text, #"BUOM per Pal A1" = text, #"BUOM per Pal H1" = text, #"BUOM per Pal H3" = text, #"Profit Center" = text, PCDescription = text, History_StoreLocation = text, History_StoreSubsite = text, Max_PltPatternBDWH = text, Median_PltPatternBDWH = text, Mean_PltPatternBDWH = text, MostOccured_PltPatternBDWH = text, MostOccured_Frequency = text, #"2ndMostOccured_PltPatternBDWH" = text, #"2ndMostOccured_Frequency" = text, #"3rdMostOccured_PltPatternBDWH" = text, #"3rdMostOccured_Frequency" = text, RestOccured_Frequency = text, TotalFrequency = text, Max_PltPatternEXWH = text, Mean_PltPatternEXWH = text, Median_PltPatternEXWH = text, MostOccured_PltPatternEXWH = text, #"2ndMostOccured_PltPatternEXWH" = text, #"3rdMostOccured_PltPatternEXWH" = text, Active = text, #"Pal H3 Length" = text, #"Pal H3 Width" = text, #"Pal H3 Height" = text, #"Pal H3 Unit of Dimension" = text, #"Pal H3 Volume" = text, #"Pal H3 Volume unit" = text, #"Pal H3 Gross Weight" = text, #"Pal H3 Weight unit" = text, #"Pal H1 Length" = text, #"Pal H1 Width" = text, #"Pal H1 Height" = text, #"Pal H1 Unit of Dimension" = text, #"Pal H1 Volume" = text, #"Pal H1 Volume unit" = text, #"Pal H1 Gross Weight" = text, #"Pal H1 Weight unit" = text, #"Pal A1 Length" = text, #"Pal A1 Width" = text, #"Pal A1 Height" = text, #"Pal A1 Unit of Dimension" = text, #"Pal A1 Volume" = text, #"Pal A1 Volume unit" = text, #"Pal A1 Gross Weight" = text, #"Pal A1 Weight unit" = text, #"Pal C41 Length" = text, #"Pal C41 Width" = text, #"Pal C41 Height" = text, #"Pal C41 Unit of Dimension" = text, #"Pal C41 Volume" = text, #"Pal C41 Volume unit" = text, #"Pal C41 Gross Weight" = text, #"Pal C41 Weight unit" = text, #"Pal C19 Length" = text, #"Pal C19 Width" = text, #"Pal C19 Height" = text, #"Pal C19 Unit of Dimension" = text, #"Pal C19 Volume" = text, #"Pal C19 Volume unit" = text, #"Pal C19 Gross Weight" = text, #"Pal C19 Weight unit" = text, #"Pal A2 Length" = text, #"Pal A2 Width" = text, #"Pal A2 Height" = text, #"Pal A2 Unit of Dimension" = text, #"Pal A2 Volume" = text, #"Pal A2 Volume unit" = text, #"Pal A2 Gross Weight" = text, #"Pal A2 Weight unit" = text, #"MRPCtrllr=buyer" = text, #"DF plant level" = text, #"MRP profile" = text, #"MRP Type" = text, #"MRP Controller" = text, #"Pl. Deliv. Time" = text, #"GR Proc. Time" = text, #"Lot size" = text, #"Reorder Point" = text, #"Safety Stock" = text, #"Min. Lot Size" = text, #"Max. Lot Size" = text, #"Fixed lot size" = text, #"Rounding value" = text, #"Max.stock level" = text, #"Safety time ind" = text, #"Safety time" = text, StdPrice = text, #"Origin group" = text, Language = text, #"Material Type" = text, #"Created On" = text, #"Last Change" = text, #"DG indicator profile" = text, #"IT per BUOM" = text, #"BUOM per CS" = text, #"SU per BUOM" = text, FG_PushPull = text, FG_Size = text, FG_PltPattern = text, FG_WtKG = text, FG_VolDM3 = text, FG_HeightCM = text, FG_LengthCM = text, FG_WidthCM = text, JIT = text], {})
in
    __Result