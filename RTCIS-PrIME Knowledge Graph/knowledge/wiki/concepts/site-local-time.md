---
title: Site-local time
type: concept
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/hvr_latency_prime2022.md]
evidence: []
updated: 2026-10-20
---
# Site-local time

Replica `GETDATE()` is **UTC**; WMS business dates are **site-local**. For "now" in Euskirchen/Athens-relative windows:

```sql
DECLARE @now datetime = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime);
-- RTCIS sysdate - 120/24/60  ->  DATEADD(minute, -120, @now)
```
Use the site's Windows time-zone name (Athens: `GTB Standard Time`). Selecting a DATETIMEOFFSET to the client hits
ODBC type -155 — cast to `datetime` in SQL or register a converter ([connect](../connect.md)).
HVR replica freshness (lag) is a separate question: check the `hvr` schema before blaming SQL
([data-facts](../ground-truth/data-facts.md) #7).
