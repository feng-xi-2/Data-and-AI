---
name: replica-troubleshooting-rca
description: 'Use when a query times out or runs slow on a warehouse read replica. Trigger phrases: "this query times out on <site>", "why is the replica slow", "root cause of the IRA timeout".'
---

# Replica Troubleshooting and RCA

## Metadata

- Kind: knowledge
- Owner: WHS GenAI / SQL Remediation
- Sources:
  - `SQL_Translations/WH_MM_IRA_RootCause_Analysis.html`
  - `SQL_Translations/WH_MM_Query_Timeout_Playbook.html`

## Purpose

Diagnose read-replica query timeouts and latency, find the **root cause**, and
prescribe a fix. Evidence beats assumption.

## Method

1. **Confirm the symptom** — which site / replica, reproducible?
2. **Measure latency** — instrument the actual query (`_check_xq_latency.py`).
3. **Identify the cause**, e.g.:
   - a simple `inventory_view` that fans out across `invlod`/`invsub`/`invdtl`
     can time out even at **low** row counts (view shape, not volume);
   - replica lag;
   - missing index.
4. **Prescribe the fix** — the bounded all-locations rewrite, or an index.

## Worked evidence

Cairo times out with **fewer** rows than Xiqing — proving the cause is the view
shape, not data volume. The fix is the bounded base-table rewrite, not "add more
timeout".

## Diagnosis-vs-prescription rule

Correctly identifying the root cause is necessary but **not sufficient**. The fix
must respect the business intent of the query, not just make the symptom go away.

## Outputs

- IRA root-cause analysis (HTML)
- IRA timeout report (HTML)
- Query timeout playbook (HTML)
- Latency-measurement tool (`_check_xq_latency.py`)
