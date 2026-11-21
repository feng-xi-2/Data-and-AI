---
name: taco-optimizer-design
description: 'Use to design or review iDecide TACO POC for trailer scheduling optimization. Trigger phrases: "TACO", "iDecide TACO", "trailer scheduling", "TACO optimizer", "TACO POC".'
---

# iDecide TACO Optimizer Design

## Metadata

- Kind: design
- Owner: iDecide / TACO Product Owner and WHS GenAI Platform
- Status: POC
- Sources:
  - `Presentations/WHS_GenAI_Portfolio.html`
  - `Presentations/WHS_GenAI_Portfolio_Script.md`
  - `UIUX/docs/WHS_GenAI_Platform_Technical_Design.md`

## Purpose

Guide the TACO POC design for explainable trailer scheduling parameter tuning.

## Procedure

1. Capture the current operational context: performance, time window, recent issues, approved external context and existing TACO parameter state.
2. Retrieve scheduling standards, prior tuning decisions and constraint knowledge.
3. Narrow candidate parameter combinations before the existing optimizer evaluates scenarios.
4. Compare candidates against baseline and produce recommendation, expected impact, risk and rollback plan.
5. Save the accepted strategy as a personal skill first; publish shared strategy only after steward review.

## Quality gates

- The AI recommends and narrows; the deterministic optimizer and safety gate evaluate.
- Any operational setting change needs human checkpoint and rollback plan.
- If the result is not better than baseline, roll back and log the learning.
