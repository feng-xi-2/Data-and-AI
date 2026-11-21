---
name: timbr-nlq
description: 'Use to resolve natural-language warehouse questions through the timbr Semantic Layer and governed business ontology. Trigger phrases: "NL Query", "semantic layer", "business term to SQL", "governed metric", "timbr".'
---

# timbr Semantic NLQ

## Metadata

- Kind: tool
- Owner: Semantic Layer Steward / WHS Data Product
- Sources:
  - `Data Strategy.docx`
  - `SQL_Translations/_data_strategy_extract.txt`
  - `EU_NPI_Agentic_Flow_Design/EU_NPI_Agentic_Flow_Design.html`
  - `Presentations/Semantic_Layer_JFM26_Script.md`

## Purpose

Resolve business language into governed metrics, dimensions, filters, joins and SQL access paths through timbr.

## Procedure

1. Identify the business terms, metric, site, timeframe and required data freshness.
2. Resolve terms through the semantic model rather than directly guessing table names.
3. Generate the approved SQL intent and query path.
4. Run the Knowledge Graph path in parallel when lineage, mapping or evidence is needed.
5. Return query, result, explanation, source path and fallback status.

## Quality gates

- Use direct replica access only as controlled fallback and log why fallback was required.
- Expose metric definitions and source lineage in the answer trace.
- Promote repeated user corrections to candidate semantic-layer refinements.
