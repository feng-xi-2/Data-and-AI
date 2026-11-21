---
name: ira-query
description: 'Use to calculate Inventory Record Accuracy per warehouse area for a site latest cycle counts across PrIME 2014 and PrIME 2022. Trigger phrases: "what is the IRA for <site>", "inventory accuracy by area", "cycle count accuracy".'
---

# IRA Query (Inventory Record Accuracy)

## Metadata

- Kind: flow
- Owner: WHS GenAI / SQL Remediation
- Sources:
   - `FLOW-1-RTCIS-QUERY-IRA-MM.md`
   - `SQL_Translations/IRA_2Step_Query.sql`

## Purpose

Computes IRA% by warehouse area for the most recent cycle-count cycle. Must work on
both PrIME **2014** (`inventory_view`) and **2022** (base tables `invlod`+`invsub`+`invdtl`).

## Why two paths

The single `inventory_view` fans out across `invlod`/`invsub`/`invdtl` and **times
out on some replicas even at low row counts** (a view-shape problem, not data
volume). Prefer the **all-locations base-table path** with a bounded window.

## Method

1. Detect platform (2014 vs 2022) and pick the path.
2. Resolve the **majority plant code** via `prtmst.vc_itmgrp` where the site is
   multi-client (do not pick an arbitrary tie-break — use the item-group attribute).
3. Window to the latest cycle (bounded, to avoid timeouts).
4. Aggregate per area: `POSTCNT`, `PRECNT`, `IRA_SCORE`.

## Critical correctness rule

A tie in plant code must be resolved by the **right data attribute**
(`vc_itmgrp`), not an arbitrary tiebreaker. Consistency without correctness is wrong.

## Outputs

- IRA 3-way comparison report (Xiqing / Lima / Cairo) (HTML)
- IRA V8 vs V5 comparison (HTML)
- `IRA_2Step_Query.sql` — production query, both platform variants
