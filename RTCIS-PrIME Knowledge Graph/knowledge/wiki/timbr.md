---
title: Timbr semantic layer
type: source
status: documented
sources: [raw/timbr/README.md, raw/timbr/skill/SKILL.md, raw/timbr/_mapping_conventions.json, raw/timbr/_gcfc_ontology.json, raw/timbr/npi_disposal_extension.sql, raw/timbr/amiens_bb_extension.sql, raw/timbr/npi_disposal_kpi_views.sql, raw/timbr/langgraph/README.md, raw/memories/timbr_api.md, raw/memories/timbr_agent_connection.md]
evidence: []
updated: 2026-10-20
---
# Timbr

Timbr (`timbrdev.pg.com`) is the semantic layer (ontology of concepts → mappings onto site replicas). Converted PrIME
SQL is the natural **mapping SELECT** for a Timbr concept, so this wiki's ground truth feeds Timbr work.

## Files in raw/timbr
| File | Role |
|---|---|
| `README.md` | Offline ontology extension: process (scope → design offline → validate → compare → owner-approved deploy), test evidence, open gates |
| `skill/` | Copilot skill *timbr-ontology-authoring-testing* (SKILL.md, business-to-ontology guide, check runner) |
| `npi_disposal_extension.sql`, `amiens_bb_extension.sql` | Proposed concepts + Amiens BB mappings (**not deployed**) |
| `npi_disposal_generated.sql`, `npi_disposal_new_sites.sql` | Generated all-PrIME site mappings (do not hand-edit) |
| `npi_disposal_kpi_views.sql` | Proposed measures / KPI views |
| `_mapping_conventions.json`, `_gcfc_ontology.json` | House mapping conventions; GCFC ontology dump |
| `langgraph/` | REST + MCP client (`timbr_api_and_mcp.py`) and LangGraph agent README |

## Facts `[LEARNED]` (raw/memories/timbr_api.md)
- REST: `POST https://timbrdev.pg.com/timbr/api/query/`, header `x-api-key: <token>`, body
  `{"ontology_name": "...", "query": "..."}` — ontology **must** be in the body. Token from env `TIMBR_TOKEN` / `.env`; never commit.
- **Silent 3,000-row cap** on every result — aggregate in SQL or page.
- `location`, `case` are reserved words → ``dtimbr.`location` ``. Metadata: `SHOW CREATE CONCEPT/MAPPING`, `SHOW MAPPINGS`, `SHOW PROPERTIES`.
- Mapping = `<concept>_<datasource>`, one per site DB; PrIME mappings are templates: `dc = WH_ID`;
  `sap_plant = PRT_CLIENT_ID` else POLDAT `VC-PRIME-SAP/PLANT_CD`.
- **Double-count trap:** `*_amiens_kh` mappings `USING "amiens_bb"` → BB rows counted twice. Amiens BB (FR57) and
  KH (FR88) are different sites, same SAP plant 4106, split by SAP SLoc.
- **No-touch rule:** never change other owners' live mappings — audit only (`audit_existing_mappings.py`).
- Native `langchain-timbr` SDK blocked on Python 3.14 (tiktoken pin); MCP path works with a token.

## How this wiki connects
A converted, graded PrIME query (grade A/B) can become a Timbr mapping SELECT. Before that: validate with the skill's
checks (structural validator + negative controls), compare keyed results against the direct replica, and get owner
approval for any DDL. Proposal results are simulations or passthrough, **not** deployed-concept results.
