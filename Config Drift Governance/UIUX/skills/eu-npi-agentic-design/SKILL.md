---
name: eu-npi-agentic-design
description: 'Use to design or review the EU NPI Disposal Assistant. Trigger phrases: "EU NPI design", "NPI disposal assistant", "NPI agentic flow", "NPI site variants", "NPI in design".'
---

# EU NPI Agentic Design

## Metadata

- Kind: design
- Owner: EU NPI Product Owner / WHS GenAI Platform
- Status: In design
- Sources:
  - `EU_NPI_Agentic_Flow_Design/EU_NPI_Agentic_Flow_Design.html`
  - `UIUX/docs/WHS_GenAI_Platform_Technical_Design.md`
  - `Presentations/WHS_GenAI_Portfolio_Script.md`

## Purpose

Provide a governed design workflow for the EU NPI Disposal Assistant across 19 EU sites and three WMS patterns.

## Procedure

1. Start from the five-phase NPI process: input gathering, decision, DO creation, communication, execution and booking.
2. Identify site variant, WMS system, cadence, DO type, sloc strategy, source files, automation and approval rules.
3. Ground structured data in PSDH/NPI portal, ScrApp, PrIME replica, RTCIS replica, SAP-approved checks and SharePoint/DC files.
4. Resolve business concepts through NPI semantic ontology and Knowledge Graph lineage.
5. Return build backlog, pilot assumptions, source gaps, human approval points and test cases.

## Quality gates

- Keep status as In design until pilot source access, approval workflow, golden tests and output reports are validated.
- Do not imply direct SAP or WMS writeback unless a governed deterministic workflow exists.
- Preserve site-specific variants instead of forcing one global process.
