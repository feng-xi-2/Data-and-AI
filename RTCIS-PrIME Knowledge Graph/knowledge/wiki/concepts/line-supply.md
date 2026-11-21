---
title: Line supply and line return
type: concept
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md, raw/euskirchen/16_LineSupply_prime.sql]
evidence: [results/RTCIS_EUS__rtcis_tsql__R08.json, results/PRIME_WMD1__prime__R08.json]
updated: 2026-10-20
---
# Line supply / line return

**RTCIS:** transactions DEPSUL / LINUSE / CASXFR into `ULIN%` locations; return = MANLID.

**PrIME 2022:** line = **location type**, not area. `[DB]`
```sql
EXISTS (SELECT 1 FROM dbo.locmst lm JOIN dbo.loc_typ t ON t.LOC_TYP_ID = lm.LOC_TYP_ID
        WHERE lm.STOLOC = d.TOSTOL AND lm.WH_ID = d.WH_ID AND t.LOC_TYP_CAT = 'PROD')   -- d = dbo.dlytrn
```
(Tested form: `queries/prime/R09_IMP_LINE_DELIVERY_HISTORY_FROM_RTCIS.sql`.) Line delivery = `dlytrn` **into** a PROD location (PLIN/PSTD/PSTA);
line return = **out of** PROD into non-PROD `[INFERRED]` (not observable at DE08).

| Evidence | Value |
|---|---|
| RTCIS ULIN* → PrIME line-named staging locations | 43/43 map 1:1 (ULIN82→EU82, ULINCV→SLCV) |
| DE08 rows with the fix | 2 (EU82, INTEU822026281); Athens unchanged 121 / 30 d |
| Old filter `TO_ARECOD IN prdlin_mst.PRCARE` | wrong: DE08 `PELINQMR*` areas hold one placeholder location each |
| PRDORD | latest `pckwrk_dtl.WKONUM` on the pallet `[INFERRED]`; `SUBSTRING(4,9)` only for 12-char `000%` SAP orders |
| DE08 vs RTCIS orders | separate number ranges (0/66 overlap) — DEV data, not a mapping error |

DE08 has no real line supply yet → R08–R12 are grade B/C ([rpm-status](../queries/rpm-status.md)). The SILOA/SILOB CASE
in the original is dead under its own `ULIN%` filter.
