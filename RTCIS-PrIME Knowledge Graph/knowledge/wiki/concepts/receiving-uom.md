---
title: Receiving-UOM quantity factor
type: concept
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/rtcis_prime_conversion_kit.md]
evidence: [results/map_inventory_fields.json, results/compare.json, results/probe_casqty_height.json]
updated: 2026-10-20
---
# Receiving-UOM quantity factor

RTCIS reports quantities in the warehouse UOM (cases for FP, base unit for packaging). PrIME stores `invdtl.UNTQTY` in
the stock UOM. The footprint level flagged `prtftp_dtl.RCV_FLG = 1` reproduces the RTCIS UOM and quantity. `[DB]`

```sql
OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f
             WHERE f.PRTNUM = d.PRTNUM AND f.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND f.WH_ID = l.WH_ID
               AND f.FTPCOD = d.FTPCOD AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) r
...
CAST(FLOOR(CASE WHEN ISNULL(r.UNTQTY, 0) = 0 THEN d.UNTQTY
          ELSE CAST(d.UNTQTY AS decimal(19,3)) / r.UNTQTY END) AS numeric(22,0)) AS [Quantity]
```
(Tested form: `queries/prime/R07_FP_Inventory_on_SSCC18_Level.sql`.)

| Measure | Result |
|---|---|
| Receiving `UOMCOD` = RTCIS base UOM | 711/711 packaging items (DE08) |
| `TRNQTY / RCV-level UNTQTY` = RTCIS qty | 18/18 line moves |
| CASQTY agreement, receiving factor | **94%** of matched pallets |
| CASQTY agreement, `UNTCAS` (expert OBS6 form) | 85% |
| `STKUOM` is a 1/1000 sub-unit (2M/G/MM/ML) | 233 metric packaging items — never use for RTCIS UOM |

FP unit `IT` → `CS` agrees only 50% — a vocabulary difference, documented. Pallet UoM = footprint code holds at f6p/n6p
sites (Amiens, Dallas) but not at Cabuyao/Louveira.

## Why CASQTY was not an integer (fixed 2026-10-20)
RTCIS `untdtl.casqty` is `numeric(22,0)`: whole units only (0 fractional of ~100k rows). PrIME stocks metric packaging
in a 1/1000 sub-unit (`STKUOM` 2M / MM / G) and the receiving level is M2 / M / KG with `UNTQTY = 1000`, so
`4250400 / 1000 = 4250.400 M2`. RTCIS shows 4250 — truncated (RTCIS = FLOOR on 549 pallets, = ROUND-only on 0;
4781.7 → 4781). FERT stocked in IT with a CS receiving level gives partial cases the same way (32 pallets). All quantity
outputs now use `CAST(FLOOR(...) AS numeric(22,0))` (R01, R07, R08–R12, R14, R15, R16): R01 78% → 92%, R16 7% → 100%.
The unfloored value is the exact PrIME stock — keep it if the business prefers precision ([open-decisions](../open-decisions.md)).

This is a **declared deviation** from [OBS6](../experts/ruiz-rs-obs.md). Footprint basics: `prtmst.UNTPAL/UNTCAS/UNTINP`
do not exist in PrIME — join `prtftp_dtl` per UOM (raw/reference §7 Footprint pattern).
