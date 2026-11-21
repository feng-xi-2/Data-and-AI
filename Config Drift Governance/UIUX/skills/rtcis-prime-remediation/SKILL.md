---
name: rtcis-prime-remediation
description: 'Use when converting or reconciling legacy RTCIS Oracle-origin WMS SQL to PrIME 2022 SQL Server. Trigger phrases: "translate this RTCIS query", "remediate to PrIME 2022", "why does not this RTCIS SQL run on PrIME".'
---

# RTCIS to PrIME SQL Remediation

## Metadata

- Kind: knowledge
- Owner: WHS GenAI / SQL Remediation
- Sources:
   - `FLOW-2-RTCIS-TO-PRIME-REMEDIATION.md`
   - `RTCIS-TO-PRIME-ARCHITECTURE.md`
   - `.github/tools/verified-mappings.json`

## Purpose

Cross-platform translation of legacy RTCIS SQL into production-ready PrIME 2022 SQL.
RTCIS is the decommissioning Oracle-origin WMS (schema `esiliv1`, `live3`, UPPERCASE
identifiers); PrIME 2022 is the SQL Server replacement (`dbo`, lowercase). This is
**NOT** a 1:1 find-and-replace.

## When NOT to use

- Same-platform PrIME 2014 → 2022 upgrades → use **PrIME 2014 → 2022 Remediation**.
- Plain Oracle execution against RTCIS only → use **Oracle RTCIS query**.

## The three layers of every translation

1. **Structure** — tables, joins, FK chains (e.g. `LOCATN`→`locmst`, `SYSTRN`→`cnthst`).
2. **Column names** — RTCIS columns map to PrIME columns, not always same name.
3. **Filter values** — business-meaning, not literal. `ITMCLS='F'` → `typcod='FERT'`;
   `ORACLE_RTCIS..LIVE3.` linked-server prefix → strip entirely, map table to `dbo.`.

## Method

1. Read the **business intent** of the original query first.
2. 3-layer lookup: accumulated knowledge (`translation-learnings.json`) →
   data model / ERD (`prime-datamodel.json`) → live Athens validation.
3. Rebuild the query for the PrIME 2022 model.
4. **Verify row-count parity** against the Athens replica before returning.

## Validation

- Validate only on `ATHENS_REPLICA` (never Crailsheim — still 2014).
- No `esiliv1.` / `live3.` / `ORACLE_RTCIS..` prefixes may remain in the output.

## Outputs

- Pomezia 34-query remediation report (HTML)
- Vendor queries remediated (HTML)
- Remediated `.sql` with a side-by-side before/after and a validation note.
