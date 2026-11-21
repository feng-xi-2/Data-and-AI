# RTCIS ↔ PrIME 2014 ↔ PrIME 2022 Knowledge Graph

A validated knowledge graph of **every table and column** of the three warehouse engines, **how they map onto each other**,
and **how queries were converted** — built from the RTCIS → PrIME LLM wiki, checked against real replica databases, loaded
into **Azure Cosmos DB for Apache Gremlin**, and benchmarked with the Text2KGBench method.

> Rule: **nothing enters the graph unless a real database confirmed it.** Documents propose; the catalog and the data decide.
> Rejected mappings are published too ([benchmark/parts/mappings_*.json](benchmark/), `checks.V1 != PASS`).

| Folder | What |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | design, hosting study (Cosmos Gremlin vs NoSQL vs Fabric vs Neo4j vs Timbr), one-graph-per-theme decision, user interfaces, NL query-writing flow, references |
| [knowledge/](knowledge/) | the knowledge: wiki pages (method, criteria, ground truth, expert rules, learnings, concepts, query pages), the complete RTCIS→PrIME reference, the PrIME 2014→2022 remediation guide, verified mappings, the converted SQL (RTCIS baseline + PrIME 2022) |
| [relationships/](relationships/) | the graph: [ontology.json](relationships/ontology.json) (labels, properties, edge domain/range) + `parts/nodes_*.json`, `parts/edges_*.json` |
| [templates/](templates/) | PrIME SQL header (mapping tags), field-notes (empty / mismatch reasons), query wiki page, tabbed HTML report, [Gremlin traversals](templates/gremlin_queries.md) |
| [tools/](tools/) | catalog → mapping validation → graph build → Cosmos load → benchmark → UI snapshot → public export |
| [benchmark/](benchmark/) | database-grounded gold, predictions, validation results, [RESULTS.md](benchmark/RESULTS.md) |
| [ui/](ui/) | page for the WHS GenAI UI (Knowledge section): mappings, rejected mappings, templates, tables, benchmark, live graph answers |

## Graph at a glance (2026-11-21)
* **Schema** (live catalogs): 1,680 tables / 28,585 columns — RTCIS (Euskirchen + London), PrIME 2014 (Xiqing), PrIME 2022 (Euskirchen DE08 base tables + replica views); PrIME descriptions, keys, theme and ERD domain attached only where the object really exists.
* **Mappings**: 9,254 validated `MAPS_TO` (RTCIS→PrIME 2022, RTCIS→PrIME 2014, PrIME 2014→2022); 54 documented mappings rejected by the catalogs; 182 curated column mappings checked with live values (confirmed / code set differs / not comparable).
* **Conversion knowledge**: 17 converted queries (both engines) as templates, 212 output fields with fill and agreement, findings, 12 expert rules, learnings, data facts, wiki concept pages.

## Run it
```powershell
pip install pyodbc msal gremlinpython
copy tools\sites.example.json tools\sites.local.json      # your replica hosts (git-ignored)
$env:WIKI_ROOT = "<RTCIS-PrIME-LLM-Wiki checkout>"       # knowledge sources + converted queries
$env:KG_COSMOS_ACCOUNT = "<gremlin account>"; $env:KG_COSMOS_RG = "<resource group>"; $env:KG_COSMOS_SUB_NAME = "<subscription>"
$env:KG_MSAL_HELPER_DIR = "<folder with _databricks_session.py>"   # MSAL cache used for the ARM call
cd tools
python catalog.py          # live catalogs of every site            -> benchmark/catalog.json
python mappings.py         # harvest + validate (V1 exists, V2 type, V3 live values) -> benchmark/mapping_validation.json
python gold_extract.py     # engine plan + result-set lineage       -> benchmark/gold.json
python build_graph.py      # entity recognition + graph (gate: catalog) -> relationships/
python load_cosmos.py --graph rtcis_prime                          # one graph per theme in database whs_kg
python benchmark.py        # T1 entity recognition, T2 Text2KGBench, T3 conversion on Cosmos -> benchmark/RESULTS.md
python export_ui_snapshot.py --ui "<config-drift-governance>\UIUX"
python export_public.py "<repo>\RTCIS-PrIME Knowledge Graph"       # sanitise + publish check
```
Database access: the signed-in user's Azure AD token (device code on first use). Cosmos: the account key is read through ARM
at run time and kept in memory only. Nothing in this folder holds a secret, a host name or a user name — the publish check
(`tools/check_publish.py`, GitHub Action) blocks any.

## Benchmark method
Gold comes from the engines, not from our parser: `SET SHOWPLAN_XML` gives the tables/columns a query reads,
`sys.dm_exec_describe_first_result_set` gives the column behind each output field. Metrics follow
[Text2KGBench](https://github.com/cenguix/Text2KGBench) (P / R / F1, ontology conformance, subject / relation / object
hallucination), measured before and after the catalog gate, plus conversion accuracy of live Gremlin lookups on Cosmos.
