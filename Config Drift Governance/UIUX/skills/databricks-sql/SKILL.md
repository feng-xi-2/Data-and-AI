---
name: databricks-sql
description: 'Use to execute governed read-only SQL against warehouse data replicas, Databricks SQL paths or approved data products. Trigger phrases: "run this query", "validate on replica", "check row count", "return database result".'
---

# Databricks SQL

## Metadata

- Kind: tool
- Owner: WHS Data Engineering / Platform
- Sources:
  - `Databricks_Connect.ipynb`
  - `kb/WH_Data_Replica_Servers.md`
  - `SQL_Translations/`

## Purpose

Provide the Data Agent with a governed structured-query execution path for approved warehouse data sources.

## Procedure

1. Confirm the target source, site, schema and access boundary.
2. Resolve the semantic object or physical table path.
3. Execute read-only SQL with parameters and bounded result size.
4. Return typed rows, schema, row count, execution time, source, freshness and generated SQL.
5. Attach validation evidence when the result feeds a shared answer or report.

## Quality gates

- Read-only only unless a separate governed operational workflow approves writeback.
- Use bounded windows and all-locations base-table paths when views time out.
- Log direct-source use as fallback if the semantic path is bypassed.
