---
name: write-query-for-report
description: 'Use when a user asks for a warehouse report query. Trigger phrases: "write a query for a report", "add a column to this report", "Lima trailer dwell", "Cabuyao volume".'
---

# Write a Query for a Report

## Metadata

- Kind: flow
- Owner: WHS GenAI / SQL Remediation
- Sources:
  - `SQL_Translations/Cabuyao_Payya_Volume_Validation.xlsx`
  - `FLOW-1-RTCIS-QUERY-IRA-MM.md`

## Purpose

Turn a business reporting need into a validated, production-ready WMS query —
including the derived columns the report must render.

## Method

1. Capture the **business question** precisely.
2. Find the source tables (footprint `prtftp_dtl`, `shipment_line`, `pckwrk_view`, …).
3. Build the query.
4. **Validate it live** before delivery.

## Two hard-won lessons

- **Report rendering**: adding a column to the `SELECT` is not enough — the groovy
  `[[ … ]]` report block must also emit the line (the Cabuyao volume lesson).
- **Units**: Cabuyao footprint is in **cm** → CBM = cm³ / 1e6. Always check units.

## Examples

- Lima trailer dwell / location history
- Cabuyao Payya volume (CBM)

## Outputs

- Cabuyao Payya volume validation (XLSX)
- Cabuyao final Payya volume query (SQL)
- Lima trailer dwell history (CSV)
