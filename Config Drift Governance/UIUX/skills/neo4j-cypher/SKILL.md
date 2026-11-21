---
name: neo4j-cypher
description: 'Use to query the WHS Knowledge Graph for lineage, mappings, standards, process relationships and validation evidence. Trigger phrases: "use the Knowledge Graph", "show lineage", "map this table or value", "what relationship connects these".'
---

# Neo4j Cypher

## Metadata

- Kind: tool
- Owner: WHS Knowledge Graph Steward
- Sources:
  - `SQL_Translations/_neo4j_graph_summary.md`
  - `SQL_Translations/_neo4j_export_merged.json`
  - `SQL_Translations/_neo4j_export_merged.cypher`
  - `SQL_Translations/neo4j_kb_api.py`

## Purpose

Run graph retrieval as the Knowledge Graph path in NL Query, SQL remediation, Process Discovery and design review tasks.

## Procedure

1. Convert the question into graph intent: lineage, mapping, evidence, standards, impact or validation.
2. Query the graph for node and relationship evidence.
3. Return graph path, relationship types, source documents and validation status.
4. Run in parallel with the timbr Semantic Layer when a business term also needs SQL metric resolution.
5. If graph evidence and SQL result disagree, flag the discrepancy and ask for steward review.

## Quality gates

- Report graph validation limits instead of overstating coverage.
- Preserve relationship names and source provenance.
- Prefer deterministic graph relationships over inferred text-only claims.
