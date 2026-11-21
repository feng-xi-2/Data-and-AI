---
name: prime-2014-2022-remediation
description: 'Use when upgrading PrIME 2014 prodwms SQL to PrIME 2022 dbo SQL. Trigger phrases: "upgrade this 2014 query", "Areas to Zones", "cntflg is gone", "why does this 2014 query fail on 2022".'
---

# PrIME 2014 to 2022 Remediation

## Metadata

- Kind: knowledge
- Owner: WHS GenAI / SQL Remediation
- Sources:
  - `FLOW-3-PRIME-2014-TO-2022-REMEDIATION.md`
  - `PRIME-2014-TO-2022-REMEDIATION-GUIDE.md`
  - `SQL_Translations/_alias_resolution_2014_2022.json`

## Purpose

Same-platform version upgrade of PrIME 2014 SQL to PrIME 2022. Both are SQL Server,
so the syntax mostly carries over — the work is in the **data-model change**.

## Key structural changes (2014 → 2022)

| 2014 (prodwms) | 2022 (dbo) | Note |
|---|---|---|
| flat **Area**-centric model | multi-layer **Zone** architecture | `aremst` → `zonmst` + `locmst` |
| `cntflg` on area | **removed** | countability now derived per-location |
| `untinp` | `untlay` | unit layout table renamed |
| flags on `aremst` | flags migrate to `locmst` | per-location, not per-area |
| direct tables | **synonym-based** schema | resolve synonyms first |

## Method

1. Identify the business intent (what the 2014 query measures).
2. Map each 2014 table/column through `_alias_resolution_2014_2022.json`.
3. Rebuild joins for the Zone model (location → zone → area).
4. Validate on **ATHENS_REPLICA** only. **Crailsheim is still 2014** — never validate there.

## Worked example — IRA / CL translation

The Inventory Record Accuracy (IRA) and Countable-Location (CL) queries are the
canonical 2014→2022 example: the 2014 `inventory_view` path is rebuilt onto the
2022 base tables (`invlod` + `invsub` + `invdtl`) with the Zone joins.

## Outputs

- IRA / CL conversion report (HTML) — 2014 vs 2022 side-by-side
- `IRA_2Step_Query.sql` — the validated 2-step query (2014 + 2022 variants)
- 2014↔2022 alias resolution map (JSON)
