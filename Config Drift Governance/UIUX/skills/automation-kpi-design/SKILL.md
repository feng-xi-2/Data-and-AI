---
name: automation-kpi-design
description: 'Use to design the Automation KPI Assistant for WCS/WMS monitoring, KPI store, scheduler, Grafana-style signals and RCA. Trigger phrases: "Automation KPI", "WCS monitoring", "WMS KPI", "Grafana", "KPI scheduler", "automation RCA".'
---

# Automation KPI Design

## Metadata

- Kind: design
- Owner: Automation KPI Product Owner / WHS Data Product
- Status: In design
- Sources:
  - `UIUX/docs/WHS_GenAI_Platform_Technical_Design.md`
  - `Data Strategy.docx`
  - `kb/WH_Data_Replica_Servers.md`

## Purpose

Define the Automation KPI Assistant as a governed monitoring, explanation and RCA workflow over WCS/WMS and warehouse KPI signals.

## Procedure

1. Define KPI, source system, site, refresh need and criticality.
2. Resolve semantic definitions for KPI, dimension and threshold.
3. Connect WCS/WMS replica data, scheduler snapshots, KPI store and Grafana-style signal views when approved.
4. Use RCA playbooks and Warehouse Knowledge to explain deviations.
5. Return impact, likely root cause, evidence, action owner, follow-up due date and feedback capture.

## Quality gates

- Keep status as In design until KPI source contracts and golden KPI checks exist.
- Separate monitoring/explanation from operational writeback.
- Log source freshness, threshold definition and RCA confidence.
