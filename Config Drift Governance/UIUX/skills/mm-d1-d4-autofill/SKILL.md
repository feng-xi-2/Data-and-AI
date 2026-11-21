---
name: mm-d1-d4-autofill
description: 'Use to derive Process Discovery / Match & Mapping D1-D4 workbook inputs from warehouse exports and validated knowledge. Trigger phrases: "auto-fill M&M", "derive D1-D4", "pre-fill the assessment", "site footprint and flows".'
---

# M&M D1-D4 Auto-fill

## Metadata

- Kind: flow
- Owner: WHS GenAI / Process Discovery
- Sources:
  - `WH_MM_Process_Input.ipynb`
  - `WH_MM_Flow.html`
  - `SQL_Translations/_mm_audit/_MM_TRANSFER_PACK/`
  - `MM Toolbox/`

## Purpose

Populate M&M D1-D4 pre-assessment values from site data, standards, graph relationships and deterministic derivation rules.

## Procedure

1. Load the site export, site registry and available WMS platform details.
2. Derive D1 footprint, D2 flows, D3 volume/statistics and D4 configuration.
3. Cross-check standards through the M&M transfer pack and Knowledge Graph.
4. Preserve provenance for every value: source table, query, rule, workbook cell and confidence.
5. Export workbook-ready results and a review list for gaps, deviations and interview-only fields.

## Quality gates

- Never fill a value without evidence or a marked derivation rule.
- Separate standard process, configured process and actual transactional behavior.
- Prefer deterministic SQL/graph evidence over free-text assumptions.
