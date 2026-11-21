---
name: whs-process-discovery
description: 'Use to map out how a warehouse actually runs before a PrIME migration or M&M assessment. Trigger phrases: "discover the process flow for <site>", "what is the footprint", "build the M&M pre-assessment input".'
---

# WHS Process Discovery (M&M)

## Metadata

- Kind: flow
- Owner: WHS GenAI / Process Discovery
- Sources:
  - `WH_MM_Process_Input.ipynb`
  - `MM Toolbox/`

## Purpose

Discover a site's warehouse process footprint from its data and standards, then feed
the M&M D1–D4 pre-assessment.

## Method

1. Walk the SDC-numbered flow (**Modules 01–11**).
2. Link each stage to its RTCIS tables and FK chains.
3. Classify movements: **FP** (finished product) vs **RPM** (raw / packaging material).
4. Flag **SDC deviations** (where the site differs from standard).
5. Emit the structured input that the M&M D1–D4 auto-fill consumes.

## Latest run

Minhang PrIME M&M.

## Outputs

- WH M&M interactive flow (HTML)
- Minhang PrIME M&M Agenda (XLSX)
- WH M&M process-input notebook (IPYNB)
