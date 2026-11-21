---
name: rtcis-prime-conversion
description: Convert a SQL query between RTCIS, PrIME 2014 and PrIME 2022 (usually RTCIS -> PrIME 2022). Use when the user pastes SQL and asks to convert, translate, remediate or migrate it, or gives a source and a different target database.
license: Internal use
metadata:
  source: RTCIS-PrIME LLM wiki (method, criteria, expert rules OBS1-8, anti-patterns), validated against replicas
---
# Converting a query between engines

Not a find-and-replace: tables, columns, join paths **and filter values** change between engines.

## Steps
1. **Read the source contract** given in the request (output columns, in order). It was run on the source database.
2. **Classify the wrapper**:
   - plain T-SQL on `live3.*` → already SQL Server; only the objects change.
   - `EXEC …SYS_get_RTCIS null, '<oracle>', p1..p5` or `OpenQuery(RTCIS|LIVE, '…')` → Oracle text, `''` = one quote;
     transliterate: `decode`→`CASE`, `nvl`→`ISNULL`, `substr`→`SUBSTRING`, `(+)`→`LEFT JOIN`, `||`→`CONCAT`,
     `sysdate`→site-local now, `to_date(x,'mm/dd/yyyy hh24:mi:ss')`→`CONVERT(datetime,x,101)`.
3. **Map every source object** with `graph_context` (validated MAPS_TO with value verdicts) and `describe_tables` on the
   target. Typical PrIME 2022 targets: `unitld`→`invlod`, `untdtl`→`invdtl` (+`invsub`), `itmmst`→`prtmst`/`prtdsc`,
   `locatn`→`locmst`, `zoncod`→`aremst` + zone tables, `systrn`+`sysdtl`→`dlytrn`, `ordhdr`→`ord`, `caspik`→`pckwrk_hdr`/`pckwrk_dtl`.
   Measured keys: `LODNUM = ULID20` (or `LEFT(LODNUM,19) = ULID`), `PRTNUM = ITMCOD`, `LOTNUM = CTLGRP`, `STOLOC = LOCATN`.
   A mapping marked `CODE SET DIFFERS` needs a value translation, not a column swap.
4. **Join with `join_paths`** of the target engine; add `wh_id = @wh_id` on every warehouse table.
5. **Keep the grain** (expert rule OBS8): PrIME can hold several `invdtl` rows for one RTCIS row — aggregate per
   LODNUM + PRTNUM + PRT_CLIENT_ID + LOTNUM when the source had one row per pallet; keep DISTINCT / GROUP BY as in the source.
6. **Keep the contract** (OBS5): every source column, same name and order; no source → `CAST(NULL AS …)` + reason.
7. **Never invent inputs** (OBS4): literal time windows of the source stay literal.
8. Run on the target with `run_sql`, fix, run again. Report columns that come back empty in every row.

## Expert rules (site expert reviews, Euskirchen)
- OBS1 GTIN = `alt_prtmst` row chosen by the receiving UOM (`prtftp_dtl RCV_FLG = 1`), not a CS>IT>SW ranking.
- OBS2 RTCIS `shipid` = PrIME `stop.CAR_MOVE_ID` (via `shipment.STOP_ID`), not `shipment.SHIP_ID`.
- OBS3 RTCIS setup = PrIME list pick `pckwrk_hdr.LIST_ID`.
- OBS6 case quantity = `UNTQTY / UNTCAS` with zero fallback, **cast to decimal** (int/int truncates).
- OBS7 keep the source's picked-inventory filter and HAVING clause.

## Anti-patterns (each measured)
- Never pin a discriminated dimension: `prtdsc` by `LOCALE_ID` (blanked 50 % of descriptions), `alt_prtmst` by `UOMCOD`
  (blanked 35 % of GTINs). Use the configuration (`RCV_FLG = 1`) or a preference chain with `OUTER APPLY TOP 1 … ORDER BY CASE`.
- `prtmst` without `WH_ID_TMPL` doubles rows (template + warehouse row).
- `pckwrk_view` cannot be planned at DE08 → join `pckwrk_hdr` + `pckwrk_dtl`.
- `rcvtrk.TRKREF` is the supplier name, not the load reference (`rcvinv.WAYBIL`). Measure, don't name-match.
