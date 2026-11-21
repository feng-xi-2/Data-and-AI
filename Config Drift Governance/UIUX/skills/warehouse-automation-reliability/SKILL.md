---
name: warehouse-automation-reliability
description: 'Grounding knowledge that defines warehouse automation reliability KPIs (availability, throughput, MTBF/MTTR, fault and downtime) with sample WCS-replica queries, used to write and validate MEGA Automation KPI questions. Trigger phrases: "automation reliability", "MEGA KPI", "MTBF", "MTTR", "availability KPI", "WCS query".'
---

# Warehouse Automation Reliability — Definition and Sample Queries

## Metadata

- Kind: knowledge
- Owner: Automation KPI Product Owner / WHS Data Product
- Status: Coming soon (grounding for MEGA Automation KPI Assistant)
- Sources:
  - `UIUX/docs/WHS_GenAI_Platform_Technical_Design.md`
  - `Data Strategy.docx`
  - WCS replica (via Databricks)

## Purpose

Provide the canonical definitions of warehouse automation reliability KPIs and a set of
sample WCS-replica queries, so a natural-language MEGA KPI question can be written, run
against the real database, and iterated until the result is validated. Used as the grounding
knowledge for the MEGA Automation KPI Assistant.

## KPI definitions

- **Availability** — proportion of scheduled time an automation asset (sorter, conveyor,
  AS/RS, shuttle) is able to run. `Availability = uptime / (uptime + downtime)`.
- **Throughput** — units, cartons or totes processed per unit time (e.g. cartons/hour) for
  an asset, line or zone.
- **MTBF (Mean Time Between Failures)** — average operating time between consecutive faults.
  `MTBF = total operating time / number of failures`.
- **MTTR (Mean Time To Repair)** — average time to restore an asset after a fault.
  `MTTR = total downtime / number of failures`.
- **Fault / downtime** — count and duration of fault events by asset, fault code and shift.

## Sample WCS queries (illustrative)

```sql
-- Availability per asset per day
SELECT asset_id,
       SUM(uptime_sec)  AS uptime_sec,
       SUM(downtime_sec) AS downtime_sec,
       SUM(uptime_sec) * 1.0 / NULLIF(SUM(uptime_sec) + SUM(downtime_sec), 0) AS availability
FROM   wcs_asset_state
WHERE  state_date = :date
GROUP  BY asset_id;

-- MTBF / MTTR per asset over a window
SELECT asset_id,
       SUM(operating_sec) * 1.0 / NULLIF(COUNT(fault_id), 0) AS mtbf_sec,
       SUM(downtime_sec)  * 1.0 / NULLIF(COUNT(fault_id), 0) AS mttr_sec
FROM   wcs_fault_event
WHERE  fault_ts BETWEEN :from_ts AND :to_ts
GROUP  BY asset_id;

-- Throughput per zone per hour
SELECT zone_id,
       DATE_TRUNC('hour', processed_ts) AS hr,
       COUNT(*)                          AS units
FROM   wcs_unit_processed
WHERE  processed_ts BETWEEN :from_ts AND :to_ts
GROUP  BY zone_id, DATE_TRUNC('hour', processed_ts);
```

## Procedure

1. Map the natural-language KPI question to a KPI definition above (availability, throughput,
   MTBF/MTTR, fault/downtime) and the required asset/zone/shift dimensions.
2. Pick the matching sample query as a template and bind the site, asset and time window.
3. Write the MEGA KPI query against the WCS replica via Databricks (timbr Semantic Layer first,
   Neo4j Knowledge Graph as fall-back).
4. Validate against the real database result and iterate the query until the result is correct.
5. Return the query, the result and a plain-language explanation.

## Quality gates

- Keep status as Coming soon until WCS KPI source contracts and golden KPI checks exist.
- Use the canonical KPI formulas above; do not redefine availability/MTBF/MTTR per query.
- Log KPI source freshness and the validation iteration that produced the final result.
