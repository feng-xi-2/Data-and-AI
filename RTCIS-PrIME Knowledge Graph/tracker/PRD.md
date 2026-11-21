# RTCIS / PrIME knowledge graph, semantic layer and SQL Remediation agent — delivery status (2026-11-22 02:05)

A story is Done only when built, deployed and retested after deploy are yes (or n/a).

## Requirements

| Id | Requirement | Built | Unit tested | E2E tested | Deployed | Retested after deploy | Status |
|---|---|---|---|---|---|---|---|
| FR-KG-01 | Live catalogs + validated mappings of RTCIS, PrIME 2014, PrIME 2022 in Cosmos | yes 2026-11-21 (build_graph.py) | yes 2026-11-21 (check_ontology 0 violations) | yes 2026-11-21 (test_cloud views) | yes 2026-11-21 (Cosmos whs_kg/rtcis_prime 30,915 v / 45,597 e) | yes 2026-11-21 (load_cosmos --check exact) | Done |
| FR-KG-02 | SDC module / PMC process layer validated on live catalogs + data presence | yes 2026-11-21 | yes 2026-11-21 (test_sdc_pmc 6) | yes 2026-11-21 (test_cloud sdc views) | yes 2026-11-21 (Cosmos) | yes 2026-11-21 (exact check) | Done |
| FR-KG-03 | Semantic layer (Timbr concepts) combined with the knowledge graph | yes 2026-11-21 (semantic_layer.py) | yes 2026-11-21 (test_semantic_layer 3) | yes 2026-11-21 (test_cloud semantic 2, UI semantic test) | yes 2026-11-21 (Cosmos 37 concepts, 117 MAPPED_FROM) | yes 2026-11-21 (exact check) | Done |
| FR-KG-04 | Validated join paths from expert SQL (JOINS_WITH) | yes 2026-11-21 | yes 2026-11-21 (test_join_paths) | yes 2026-11-21 (cloud benchmark) | yes 2026-11-21 (Cosmos 91 edges) | yes 2026-11-21 | Done |
| FR-AG-01 | Deep Agent: AGENTS.md + 2 skills + scoped tools, guard, run cap, read-only files | yes 2026-11-21 (kg_deep_agent.py) | yes 2026-11-21 (test_deep_agent 9) | yes 2026-11-21 (cloud batch round 4: NL 11/11, EX 4/5, convert 7/8 -> R08 fixed) | no (local API only; uvawh deploy pending) | no | In Progress |
| FR-AG-02 | One box routes question / SQL / convert / batch (/rp/chat) | yes 2026-11-21 | yes 2026-11-21 (test_route 10, test_chat 4) | yes 2026-11-21 (UI E2E one-box 4/4) | no (local) | no | In Progress |
| FR-AG-03 | Replica endpoint you host (KG_REPLICA_ENDPOINT) + configurable sites / hosts | yes 2026-11-21 (HttpReplicaDB) | yes 2026-11-21 (test_http_replica, test_sites, test_cloud_host) | no (endpoint not set up yet - DEP-02) | no | no | In Progress |
| FR-UI-01 | Semantic Layer & Knowledge Graph as one Knowledge page (graph templates incl. semantic) | yes 2026-11-21 | n/a | yes 2026-11-21 (UI E2E graph 3/3) | n/a (desktop static UI) | n/a | Done |
| FR-UI-02 | SQL Remediation assistant page with the live one-box dialog | yes 2026-11-21 (sql-remediation-dialog.js) | n/a | yes 2026-11-21 (UI E2E 7/7 via Deep Agent API, after review fixes) | n/a (desktop static UI) | n/a | Done |
| FR-IDE-01 | iDecide: Knowledge page (semantic layer + knowledge graph) and SQL Remediation dialog, backend proxy | yes 2026-11-21 (PR #9: c6cbeaa, 7028e62) | yes 2026-11-21 (BE 78/78, FE 91/91) | partial 2026-11-21: desktop UI E2E 7/7 against the live service; iDecide E2E needs the deployed service URL | no (needs SQL_REMEDIATION_API_URL = deployed agent service, DEP-02/DEP-03) | no | In Progress |
| FR-UVA-01 | uvawh workflow for the SQL Remediation agent on the AIF AKS (Cosmos reachable) | n/a (on hold: aiapp in-process chosen, FR-IDE-02 - no platform dependency approval needed) | no | no | no | no | To Do |
| FR-CD-01 | Config Drift code published without site data (PR #5) | yes 2026-11-21 | n/a | n/a | n/a | n/a | Done |
| FR-AG-04 | Concept-first routing: theme (Domain) + Timbr concept -> directly linked catalog-checked tables (concept_context) | yes 2026-11-21 | yes 2026-11-21 (kg_core + deep agent, 127 offline) | yes 2026-11-21 (cloud benchmark round 5, before/after) | no (agent service not deployed: FR-UVA-01) | no | In Progress |
| FR-KG-05 | Ontology tab from the Cosmos graph (/rp/schema, /rp/sample) in desktop UI and iDecide | yes 2026-11-21 | yes 2026-11-21 (API + services + iDecide vitest) | yes 2026-11-21 (desktop UI E2E 7/7; cloud test on real Cosmos) | n/a desktop; iDecide not deployed | no | In Progress |
| FR-IDE-02 | iDecide hosts the SQL Remediation agent in-process (SQL_REMEDIATION_MODE=inprocess, vendored kit + 1 MB bundle) | yes 2026-11-22 (in-process adapter; key from Key Vault with the pod identity; GenAI userid = signed-in user; DEV defaults; image hook) | yes 2026-11-22 (iDecide adapter + routes 27/27 incl. the import test with the pinned packages; kit 138 offline; hook guard tested with a stub uv) | partial 2026-11-22: iDecide router + DevelopmentAppSettings + only the pod identity + pinned packages on Python 3.12: health 200, Cosmos verified 30,915/45,597, Deep Agent answer as the signed-in user in 41 s; no replica connected; not yet in the deployed app | no (merge PR #9 to main runs Deploy image; DEP-06 Cosmos firewall) | no | In Progress |

## Bugs

| Id | Title | Status | Details |
|---|---|---|---|
| BUG-01 | SQL guard let 'SELECT 1 DELETE FROM t' and OPENQUERY through | Done | found by: builder (code review); fix: statement keywords as names + remote functions rejected; test_kg_core |
| BUG-02 | Parameter-name injection into DECLARE | Done | found by: builder (code review); fix: PARAM_NAME check; test_services_offline |
| BUG-03 | Gremlin query built by string concatenation (graph view key) | Done | found by: builder (code review); fix: bindings; test_query_view_passes_the_key_only_as_a_binding |
| BUG-04 | Local API with CORS * could be driven by any web page | Done | found by: builder (code review); fix: host/origin allow-list, JSON-only POST; test_api |
| BUG-05 | pyodbc connection shared across API threads | Done | found by: builder (code review); fix: per-site lock; test_validate_never_uses_one_connection_from_two_threads_at_once |
| BUG-06 | RTCIS SDC edges carried the PrIME table's data presence | Done | found by: builder (code review); fix: annotate_presence keyed by engine; 11 edges corrected in Cosmos |
| BUG-07 | Valid RTCIS query with AT TIME ZONE failed (ODBC -155 datetimeoffset) | Done | found by: builder (cloud benchmark); fix: output converter; test_validate_fetches_datetimeoffset_columns |
| BUG-08 | Xiqing answer joined invlod.stoloc to pck_area and returned 0 rows (reference 79 areas) | Done | found by: builder (execution accuracy); fix: validated join paths in the prompt; EX now identical |
| BUG-09 | Deep Agent ended with prose and no SQL (R08) | Done | found by: builder (cloud benchmark); fix: fallback to last successful run; R08 re-run validated |
| BUG-10 | RTCIS unit loads per zone answered at a finer grain (sub-site x zone) | Done | found by: builder (execution accuracy); fix: generic output-grain rule in warehouse-query-writing step 5; zone grain 0/2 -> 5/5, strict EX 0/3 -> 4/5 (n=5, fresh API); full set no regression (EX 10/12 same as round 5, conversions 8/8) |
| BUG-11 | Knowledge page ignored later evidence links / semantic<->graph route (keep-alive panel) | Done | found by: independent code review; fix: fixed 2026-11-21: effect on ?view/&key/initialView; test |
| BUG-12 | Approval state moved to another answer (cards keyed by index, newest first) | Done | found by: independent code review; fix: fixed 2026-11-21: stable turn ids; test proves RED with index key |
| BUG-13 | CSV export could carry spreadsheet formulas (=, +, -, @) | Done | found by: independent code review; fix: fixed 2026-11-21: csvCell / q prefix '; tests |
| BUG-14 | Approve stored any client SQL without identity or schema | Done | found by: independent code review; fix: fixed 2026-11-21: typed bodies, verified approver forwarded, service re-runs SQL on the replica; tests + live DE08 refusal |
| BUG-15 | Cosmos context query failed when a MAPS_TO target lacked a property; request returned 500 | Done | found by: benchmark run; fix: fixed 2026-11-21: coalesce every projection, read mappings at their own level, graph tool reports failures |
| BUG-16 | Concept routing offered RTCIS tables inferred through mapping hops (agv_inventory_view) | Done | found by: benchmark before/after; fix: fixed 2026-11-21: offer only directly linked tables; skip themes with none in the engine |
| BUG-17 | Benchmark reference used pckqty for 'picked quantity' (data shows picked_qty) | Done | found by: data check; fix: fixed 2026-11-21: reference corrected, all stored SQL re-scored |
| BUG-18 | Ontology tab: slower reply for an earlier partition overwrote the current one | Done | found by: code review; fix: fixed 2026-11-21: stale replies ignored (test), same in desktop page |
| BUG-19 | Desktop Knowledge page: config tab waited on the Cosmos call; no request timeout; offline fallback showed the config-drift snapshot as Cosmos | Done | found by: code review; fix: fixed 2026-11-21: independent config load, timeouts, Cosmos-only fallback, quotes escaped |
| BUG-20 | Stability mode could overwrite round-3 evidence and kept only the last repeat | Done | found by: code review; fix: fixed 2026-11-21: own output file, list per question |
| BUG-21 | Cloud test test_genai_model_answers checked nothing since the Deep Agent default | Done | found by: cloud suite; fix: fixed 2026-11-21: tests the platform client directly |

## Dependencies

| Id | Title | Status | Details |
|---|---|---|---|
| DEP-01 | Jira access for automatic sync (API token or signed-in Jira tab in the session) | To Do | owner: builder |
| DEP-02 | Replica endpoint for the cloud agent (KG_REPLICA_ENDPOINT contract in kg_services.HttpReplicaDB) | To Do | owner: builder (will set up) |
| DEP-03 | Cosmos keys in the app / uvawh Key Vault: MM-KG-GREMLIN-KEY refreshed, MM-KG-GREMLIN-READONLY-KEY added (2026-11-21); workflow registration not needed for the in-process host | Done | owner: platform / builder |
| DEP-04 | GenAI gateway: multi-turn Responses API for GPT-6.x tool calls | To Do | owner: GenAI platform |
| DEP-05 | Agent packages in the iDecide image without regenerating uv.lock (image hook, pinned with hashes) | Done | fix: project-owned build hook installs 70 hashed pins --no-deps after uv sync --frozen; base packages keep uv.lock versions (certifi excepted); langchain-google-genai excluded (unused, needs pydantic>=2.12.5); build fails if an installed package changes; owner: builder |
| DEP-06 | AI Apps DEV cluster aks-aif-mt-np-12 -> Cosmos: its subnet is not in the Cosmos firewall (np-14 is); check /sql-remediation/schema after the DEV deploy | To Do | owner: Cosmos admin (firewall rule; the builder's role excludes firewall writes) / builder (check) |
| DEP-07 | AZURE-CLIENT-SECRET in the app Key Vault is invalid (AADSTS7000215) - not used by SQL Remediation (uses AML-APP-SP); tell the app owner | Done | fix: not blocking: neither the app nor the agent uses AZURE-CLIENT-SECRET; the pod's identity is AML-APP-SP; owner: app owner |
| DOC-01 | Product PRD, architecture (hosting, operations) and user guide of the query convertor | Done | evidence: docs/PRD.md, docs/ARCHITECTURE.md sections 11-15, docs/USER_GUIDE.md; iDecide ARCHITECTURE.md SQL Remediation section |

## Test runs

| Id | Title | Status | Details |
|---|---|---|---|
| TR-CLOUD-R1 | Cloud batch round 1 (pipeline GPT-5.2) | Done | evidence: benchmark/cloud_batch_results_round1.json; cases: 11 NL + 8 conversions; passed: NL 9/11, conversions 6/8 |
| TR-CLOUD-R3 | Cloud batch round 3 (pipeline + join paths) | Done | evidence: benchmark/cloud_batch_results.json; cases: 11 NL + 8 conversions; passed: NL 11/11, EX 3/5, conversions 8/8 |
| TR-CLOUD-R4 | Cloud batch round 4 (Deep Agent GPT-5.6 Sol) | Done | evidence: benchmark/cloud_batch_results_deep_agent.json; cases: 11 NL + 8 conversions; passed: NL 11/11, EX 4/5, conversions 7/8 (R08 fixed after) |
| TR-UNIT-1121 | Unit suite (offline, fakes) | Done | evidence: pytest -m 'not cloud'; cases: 127; passed: 127 |
| TR-UIE2E-1121 | Browser E2E (Edge, live API + Cosmos + replicas) | Done | evidence: tests/test_ui_e2e.py; cases: 7; passed: 7 |
| TR-IDE-FE-1121 | iDecide frontend vitest (base) + eslint + vite build | Done | evidence: vitest --run; eslint changed files; vite build OK; cases: 91; passed: 91 |
| TR-IDE-BE-1121 | iDecide backend route tests + flake8 + mypy | Done | evidence: pytest base/backend/tests/unit/routes; cases: 78; passed: 78 |
| TR-CLOUD-R5 | Cloud benchmark round 5: theme set before/after concept routing (18 Q, 8 conversions) | Done | evidence: benchmark/cloud_batch_results_theme_*.json; cases: 26; passed: EX 11/12 (before 10/12), conversions 8/8 (before 7/8) |
| TR-CLOUD-1121b | Cloud suite (real Cosmos, GenAI, replicas) | Done | evidence: tests/test_cloud.py; cases: 17; passed: 17 |
| TR-BENCH-R6 | Benchmark round 6 (output-grain rule): 18 questions + 8 conversions on the replicas | Done | evidence: benchmark/cloud_batch_results_round6.json, cloud_batch_results_bug10_{before,after}.json; cases: 18 questions (12 scored) + 8 conversions; zone item n=3 before / n=5 after; passed: 18/18 validated, EX 10/12, conversions 8/8; zone grain 5/5 |

## Pull requests

| Id | Title | Status | Details |
|---|---|---|---|
| PR-DAI-3 | Data-and-AI PR #3 RTCIS-PrIME knowledge graph (Deep Agent, one box, semantic layer: 2376667, 737475d, e205615, 57ec964) | In Review | link: https://github.com/feng-xi-2/Data-and-AI/pull/3 |
| PR-DAI-5 | Data-and-AI PR #5 Config Drift Governance (UI: 8a408b2, 49257ce) | In Review | link: https://github.com/feng-xi-2/Data-and-AI/pull/5 |
| PR-IDE-9 | iDecide PR #9 SQL Remediation one box + Semantic Layer & Knowledge Graph page (draft) | In Review | link: https://github.com/procter-gamble/ds-gbs-aiapps-idecide-ai-assistant/pull/9 |

## Epics

| Id | Title | Status | Details |
|---|---|---|---|
| EP-KG | Knowledge graph in Cosmos (3 engines, mappings, semantic layer, SDC/PMC) | To Do |  |
| EP-AGENT | SQL Remediation agent (LangGraph Deep Agent) | To Do |  |
| EP-UI | WHS GenAI desktop UI | To Do |  |
| EP-IDE | iDecide front end + back end | To Do |  |
| EP-UVAWH | Ultimate Platform uvawh workflow on AIF | To Do |  |
| EP-CD | Config Drift Governance publication | To Do |  |
| EP-QA | Benchmarks and test evidence | To Do |  |
