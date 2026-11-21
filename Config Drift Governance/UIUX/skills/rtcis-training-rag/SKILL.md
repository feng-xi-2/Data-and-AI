---
name: rtcis-training-rag
description: 'Use to answer operator-facing how-to questions from RTCIS training modules and Work Instructions. Trigger phrases: "training module", "work instruction", "operator steps", "how do I perform this RTCIS task".'
---

# RTCIS Training RAG

## Metadata

- Kind: knowledge
- Owner: WHS Capability / Training Lead
- Sources:
  - `RTCIS Training Modules/`
  - `SQL_Translations/_neo4j_graph_summary.md`
  - `ALL_LEARNINGS.md`

## Purpose

Retrieve training and Work Instruction content for practical operator or support answers.

## Procedure

1. Identify the task, role, system and site context.
2. Search training modules and Work Instructions first.
3. Use the Knowledge Graph to map modules to SDC process, table, or configuration context when needed.
4. Return step-level guidance with document citation and any known site deviations.
5. Mark outdated or missing training sources for knowledge lifecycle review.

## Quality gates

- Do not invent operator steps when no training evidence exists.
- Distinguish standard procedure from site-specific variation.
- Require steward approval before publishing new shared training guidance.
