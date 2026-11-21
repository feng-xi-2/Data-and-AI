---
name: warehouse-query-writing
description: Write a new read-only SQL query from a plain-language warehouse question (stock, pallets, locations, areas, picks, receipts, shipments, movements) on RTCIS, PrIME 2014 or PrIME 2022. Use when the user asks a question instead of pasting SQL.
license: Internal use
metadata:
  source: RTCIS-PrIME knowledge graph (catalog-validated tables, join paths from expert-validated queries)
---
# Writing a query from a question

## Steps
1. **Find the tables**: `search_knowledge` with the business words of the question (pallet, load, area, part, pick …),
   then `describe_tables` for the real columns. Business words → tables:
   - pallet / load / LPN → RTCIS `unitld` (+`untdtl` for items); PrIME `invlod` → `invsub` → `invdtl`
   - part / item / SKU → RTCIS `itmmst`; PrIME `prtmst` (+ `prtdsc` descriptions)
   - location / area / zone → RTCIS `locatn` (`zoncod`, `arecod`); PrIME `locmst` (`arecod`) + `aremst`
   - pick work / wave → PrIME `pckwrk_hdr` / `pckwrk_dtl` / `pckbat`; RTCIS `caspik`, `wavhdr`
   - movements / transactions → PrIME `dlytrn`; RTCIS `systrn` + `sysdtl` (about 40 days kept)
2. **Start from a validated example** (`find_examples`) when one matches; adapt instead of rewriting.
3. **Join only on validated join paths** (`join_paths`). Examples: `invdtl.subnum = invsub.subnum`,
   `invsub.lodnum = invlod.lodnum`, `invlod.stoloc = locmst.stoloc AND invlod.wh_id = locmst.wh_id`,
   `aremst.arecod = locmst.arecod`.
4. **Filters**: PrIME warehouse tables `wh_id = @wh_id`; `prtmst` also `WH_ID_TMPL = @wh_id`; RTCIS sub-site via `subsit`.
5. **Grain**: the output has exactly the grouping the question names, nothing finer. Join and filter keys (RTCIS
   `subsit`, PrIME `wh_id`) are not grouping columns unless the question asks "per sub-site" / "per warehouse".
   Count distinct keys (`COUNT(DISTINCT lodnum)`) when a join can repeat a row; quantities can overflow `int` —
   `SUM(CAST(x AS bigint))`.
6. Run with `run_sql`. 0 rows → re-check the join columns and the `@wh_id` value before answering; say so if the data
   really has none.

## Three different zeros
- EMPTY: valid input, no rows → probably a wrong join or filter; fix it.
- BLOCKED: the site lacks the data (e.g. no line supply at DE08) → say it is unproven.
- SKIP: no row of the required shape to test with.
