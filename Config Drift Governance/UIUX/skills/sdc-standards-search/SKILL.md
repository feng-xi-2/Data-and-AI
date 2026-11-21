---
name: sdc-standards-search
description: 'Use to answer warehouse standards questions from SDC, SOP, OpStd, PMC, WI, SEM and REF sources. Trigger phrases: "what is the standard", "how should this process work", "show the PMC or WI", "is this site deviating from SDC".'
---

# SDC Standards Search

## Metadata

- Kind: knowledge
- Owner: WHS Capability / Knowledge Steward
- Sources:
  - `RTCIS Training Modules/`
  - `Sample Data RTCIS PRIME/SDC/`
  - `SQL_Translations/_neo4j_graph_summary.md`
  - `SQL_Translations/_mm_audit/_MM_TRANSFER_PACK/03_knowledge_bases/`

## Purpose

Retrieve and cite the applicable SDC module, PMC process, Work Instruction or related standard for warehouse process questions.

## Procedure

1. Identify the process area, site, system and business term.
2. Search Warehouse Knowledge first: SDC, PMC, WI, training modules and M&M KB.
3. Use the Knowledge Graph when the question requires process lineage or table/process mapping.
4. If the standard conflicts with live configuration or site evidence, report both and flag the conflict.
5. Return a concise answer with source document, section and evidence type.

## Quality gates

- Do not treat a generic standard as actual site behavior unless live evidence or site documentation confirms it.
- Mark gaps as interview-only or source-missing instead of inventing an answer.
- Escalate changes to shared standards through the Skill Platform review workflow.
