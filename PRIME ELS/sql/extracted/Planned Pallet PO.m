let
    __Enabled = fnFeature("Has_Production"),
    __Body =
        let
            Source = Sql.Database(ReplicaServer, ReplicaDatabase,
                [Query=fnSiteSql("
        SELECT
            w.wkonum        AS work_order,
            w.prdlin        AS product_line,
            d.lngdsc        AS status,
            w.sch_begdte    AS planned_start,
            w.sch_enddte    AS planned_end,
            DATEDIFF(HOUR, w.sch_begdte, w.sch_enddte) AS duration_hours,
            w.prtnum,
            prtdsc.lngdsc   AS description,
            w.wkoqty        AS planned_cases,
            p.untpal        AS cases_per_pallet,
            p.ftpcod,
            CAST(CAST(w.wkoqty AS DECIMAL(18,2)) / NULLIF(p.untpal, 0) AS DECIMAL(18,2)) AS planned_pallets,
            CAST(
                (CAST(w.wkoqty AS DECIMAL(18,2)) / NULLIF(p.untpal, 0))
                / NULLIF(DATEDIFF(HOUR, w.sch_begdte, w.sch_enddte), 0)
            AS DECIMAL(18,2)) AS planned_pallets_per_hour
        FROM (SELECT * FROM {S}.wkohdr WHERE wh_id = '{WH_ID}') w
        JOIN {S}.dscmst d
            ON d.colnam = 'wkosts'
           AND d.locale_id = '{DSC_LOCALE}'
           AND w.wkosts = d.colval
        LEFT JOIN (
            SELECT DISTINCT prtnum, ftpcod, untpal
            FROM {T_FOOTPRINT}
            WHERE prtnum LIKE '{FG_PRTNUM_LIKE}'
        ) p
            ON p.prtnum = w.prtnum
        LEFT JOIN {S}.prtdsc
            ON prtdsc.colval LIKE CONCAT(w.prtnum, '%{WH_ID}%')
           AND prtdsc.locale_id = '{PRTDSC_LOCALE}'
        WHERE w.prtnum LIKE '{FG_PRTNUM_LIKE}'
        AND w.sch_enddte >= DATEADD(DAY, -{WO_WINDOW_DAYS}, DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))
                  AND w.sch_begdte <  DATEADD(DAY, {WO_WINDOW_DAYS}, DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()))
                ORDER BY w.sch_begdte;
                ")]
            ),
        
             TypedSource = Table.TransformColumnTypes(Source, {
                {"planned_start",   type datetime},
                {"planned_end",     type datetime},
                {"planned_pallets", type number}
            }),
        
            DedupSource = Table.Distinct(TypedSource,
                {"work_order", "planned_start", "planned_end", "planned_pallets"}),
        
            // 1) Generate one row per SHIFT DAY the work order covers (shift day = 06:00 to 06:00 next day)
            //    Shift day of date D covers timestamps from D 06:00 to (D+1) 06:00.
            //    Convert planned_start to shift day: if hour < 6, it belongs to previous shift day.
            AddShiftDayList = Table.AddColumn(DedupSource, "ShiftDayList", each
                let
                    // Determine shift day of planned_start and planned_end
                    startShiftDay = if DateTime.Time([planned_start]) < #time(ShiftStartH, 0, 0)
                                    then Date.AddDays(Date.From([planned_start]), -1)
                                    else Date.From([planned_start]),
                    endShiftDay   = if DateTime.Time([planned_end]) < #time(ShiftStartH, 0, 0)
                                    then Date.AddDays(Date.From([planned_end]),   -1)
                                    else Date.From([planned_end]),
                    dayCount      = Duration.Days(endShiftDay - startShiftDay) + 1
                in
                    List.Dates(startShiftDay, dayCount, #duration(1, 0, 0, 0)),
                type list),
        
            ExpandShiftDays = Table.ExpandListColumn(AddShiftDayList, "ShiftDayList"),
            TypeShiftDayCol = Table.TransformColumnTypes(ExpandShiftDays, {{"ShiftDayList", type date}}),
            RenameShiftDay  = Table.RenameColumns(TypeShiftDayCol, {{"ShiftDayList", "shift_date"}}),
        
            // 2) Generate one row per 4-hour bucket within each shift day (6 buckets: B1..B6)
            AddBucketList = Table.AddColumn(RenameShiftDay, "BucketList", each
                {1, 2, 3, 4, 5, 6},
                type list),
        
            ExpandBuckets = Table.ExpandListColumn(AddBucketList, "BucketList"),
            RenameBucket  = Table.RenameColumns(ExpandBuckets, {{"BucketList", "Bucket_Sort"}}),
            TypeBucket    = Table.TransformColumnTypes(RenameBucket, {{"Bucket_Sort", Int64.Type}}),
        
            // 3) Build bucket window anchored at 06:00 of the shift day
            //    B1 = shift_date 06:00 → 10:00
            //    B2 = shift_date 10:00 → 14:00
            //    B3 = shift_date 14:00 → 18:00
            //    B4 = shift_date 18:00 → 22:00
            //    B5 = shift_date 22:00 → next_day 02:00
            //    B6 = next_day 02:00 → next_day 06:00
            AddBucketWindow = Table.AddColumn(TypeBucket, "bucket_window", each
                let
                    // Anchor: shift_date 06:00
                    anchor = #datetime(Date.Year([shift_date]), Date.Month([shift_date]), Date.Day([shift_date]), ShiftStartH, 0, 0),
                    startH = ([Bucket_Sort] - 1) * 4,
                    endH   = [Bucket_Sort] * 4,
                    bStart = anchor + #duration(0, startH, 0, 0),
                    bEnd   = anchor + #duration(0, endH,   0, 0)
                in
                    [ bucket_start = bStart, bucket_end = bEnd ],
                type record),
        
            ExpandBucketWindow = Table.ExpandRecordColumn(AddBucketWindow, "bucket_window",
                {"bucket_start", "bucket_end"},
                {"bucket_start", "bucket_end"}),
        
            TypeBucketWindow = Table.TransformColumnTypes(ExpandBucketWindow, {
                {"bucket_start", type datetime},
                {"bucket_end",   type datetime}
            }),
        
            // 4) Overlap in minutes between planned window and this bucket
            AddOverlapMinutes = Table.AddColumn(TypeBucketWindow, "overlap_minutes", each
                let
                    oStart = List.Max({[planned_start], [bucket_start]}),
                    oEnd   = List.Min({[planned_end],   [bucket_end]}),
                    diff   = Duration.TotalMinutes(oEnd - oStart)
                in
                    if diff > 0 then diff else 0,
                type number),
        
            // 5) Keep only buckets that actually overlap the WO
            FilterOverlap = Table.SelectRows(AddOverlapMinutes, each [overlap_minutes] > 0),
        
            // 6) Total WO duration in minutes
            AddTotalMinutes = Table.AddColumn(FilterOverlap, "total_minutes", each
                Duration.TotalMinutes([planned_end] - [planned_start]), type number),
        
            // 7) Fraction of WO in this bucket
            AddFraction = Table.AddColumn(AddTotalMinutes, "fraction", each
                if [total_minutes] = 0 then 0 else [overlap_minutes] / [total_minutes], type number),
        
            // 8) Prorated planned pallets per bucket
            AddPlannedBucket = Table.AddColumn(AddFraction, "planned_pallets_bucket", each
                (try [planned_pallets] otherwise 0) * [fraction], type number),
        
            // 9) Bucket_4h label — reflects the actual time windows (with 06:00 anchor)
            AddBucket4h = Table.AddColumn(AddPlannedBucket, "Bucket_4h", each
                let
                    // Compute start/end hour-of-day (with wrap for buckets after midnight)
                    startH_raw = ShiftStartH + ([Bucket_Sort] - 1) * 4,
                    endH_raw   = ShiftStartH + [Bucket_Sort] * 4,
                    startH     = Number.Mod(startH_raw, 24),
                    endH       = Number.Mod(endH_raw,   24)
                in
                    "B" & Text.From([Bucket_Sort]) & " (" &
                    Text.PadStart(Text.From(startH), 2, "0") & ":00-" &
                    Text.PadStart(Text.From(endH),   2, "0") & ":00)",
                type text),
        
            // 10) BucketDateKey: yyyyMMdd-<sort> — based on shift_date (NOT calendar date)
            AddBucketDateKey = Table.AddColumn(AddBucket4h, "BucketDateKey", each
                Date.ToText([shift_date], "yyyyMMdd") & "-" & Text.From([Bucket_Sort]),
                type text),
        
            // 11) Debug label
            AddDebugLabel = Table.AddColumn(AddBucketDateKey, "debug_label", each
                [work_order] & " | " &
                DateTime.ToText([planned_start], "yyyy-MM-dd HH:mm") & " -> " &
                DateTime.ToText([planned_end],   "yyyy-MM-dd HH:mm") & " | " &
                "shift " & Date.ToText([shift_date], "yyyy-MM-dd") & " " &
                [Bucket_4h] & " | " &
                Number.ToText([overlap_minutes], "F1") & " min overlap",
                type text),
        
            #"Renamed Columns" = Table.RenameColumns(AddDebugLabel, {{"prtnum", "FG GCAS"}})
        in
            #"Renamed Columns",
    __Result = if __Enabled then __Body else #table(type table [work_order = text, product_line = text, status = text, planned_start = datetime, planned_end = datetime, duration_hours = Int64.Type, #"FG GCAS" = text, description = text, planned_cases = Int64.Type, cases_per_pallet = Int64.Type, planned_pallets = number, overlap_minutes = number, total_minutes = number, fraction = number, debug_label = text, planned_pallets_per_hour = number, ftpcod = text, Bucket_Sort = Int64.Type, bucket_start = datetime, bucket_end = datetime, planned_pallets_bucket = number, Bucket_4h = text, BucketDateKey = text, shift_date = datetime], {})
in
    __Result