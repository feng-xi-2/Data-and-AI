---
title: The recurring PrIME anti-pattern — discriminated dimensions
type: learning
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md]
evidence: []
updated: 2026-10-20
---
# PrIME anti-pattern: discriminated dimension rows

A dimension row is **discriminated by a value**; pinning it or blind-joining it either blanks or duplicates data. `[DB]`

| # | Table + discriminator | What went wrong | Measured |
|---|---|---|---|
| 1 | `prtdsc` + `LOCALE_ID` | pinning `'GERMAN'` blanked descriptions | 82,086 / 163,748 (50.1%) at Euskirchen |
| 2 | `alt_prtmst` + `UOMCOD` | pinning `'CS'` blanked the GTIN on ~35% of rows | populated 64.8% → 98.4% after fix |
| 3 | `prtmst` + `WH_ID_TMPL` | blind join doubles; inner guard drops site NULLs | dual rows per part |
| 4 | `prtmst`/`prtdsc` two-row grain | `TOP 1` without `ORDER BY` is arbitrary | — |
| 5 | **RTCIS source too**: `ap3.itmcod <> 'B2'` (Q09) | B2 pallet type exists at EUS, absent at London → London never reports a pallet complete | — |

**Rule:** never pin, never blind-join a discriminated dimension. Use a preference chain
(`IN (…)` + `OUTER APPLY TOP 1 … ORDER BY CASE …`) — or, when the platform has a configuration for it (receiving
UOM `RCV_FLG=1`), use the configuration ([OBS1](../experts/ruiz-rs-obs.md)). Defects here are often invisible at
Athens and only fire at Euskirchen (or vice versa) — measure both sites.

`dscmst` is a **code catalogue × locale** keyed (COLNAM, COLVAL, LOCALE_ID) — it can never route per customer or
warehouse; label routing does not live in WMS tables at all.

Related: [grain-and-fanout](../concepts/grain-and-fanout.md), [verification-discipline](verification-discipline.md).
