---
name: oracle-rtcis-query
description: 'Use to run read-only SQL directly against a live RTCIS Oracle-origin WMS instance. Trigger phrases: "query RTCIS directly", "run this against esiliv1", "pull the live RTCIS rows".'
---

# Oracle RTCIS Query

## Metadata

- Kind: tool
- Owner: WHS GenAI / SQL Remediation
- Sources:
  - `FLOW-1-RTCIS-QUERY-IRA-MM.md`
  - `FLOW-2-RTCIS-TO-PRIME-REMEDIATION.md`
  - `.github/tools/prime-datamodel.json`

## Purpose

Tool skill that connects to a live RTCIS instance and runs governed, **read-only**
SQL. RTCIS is the legacy Oracle-origin WMS being decommissioned — schema `esiliv1`
/ `live3`, **UPPERCASE** identifiers, linked-server prefix `ORACLE_RTCIS..LIVE3.`.

## When to use

- You need the **source-of-truth** RTCIS rows (e.g. to validate a remediation, or
  to baseline a count before/after a PrIME 2022 translation).
- Feeding the **RTCIS → PrIME Remediation** skill with a live reference result.

## Contract

- **Read-only.** Never write/DDL against RTCIS.
- UPPERCASE table/column identifiers; quote where the dialect requires.
- Strip / do not introduce `ORACLE_RTCIS..LIVE3.` linked-server prefixes in returned
  SQL meant for PrIME — that belongs to the remediation step.
- Handles connection, parameter binding, paging, typed result return.

## Typical inputs

- Site / replica selector (e.g. London, Minhang)
- RTCIS table(s): `LOCATN`, `SYSTRN`, `UNTDTL_VIEW`, `ITEM_CONFIG`, …

## Outputs

- Typed result set (rows) for downstream remediation / validation
- The exact RTCIS query executed (for the audit trail)
