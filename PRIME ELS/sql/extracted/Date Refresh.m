let
    Source = DateTimeZone.SwitchZone(DateTimeZone.UtcNow(), Number.From(SiteTokens[UTC_Offset_h])),
    ToTable = #table(
        type table [Last Refresh DateTime = datetimezone],
        {{Source}}
    )
in
    ToTable