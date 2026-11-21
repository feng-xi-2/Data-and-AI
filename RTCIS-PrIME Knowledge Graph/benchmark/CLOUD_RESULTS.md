# Cloud benchmark — ask / convert through the live API (2026-11-21)

Path tested = the path the UI uses: `knowledge-graph.html` tab → `kg_api.py` → Cosmos DB (Gremlin) graph + GenAI platform model
(GPT-5.2) → read-only guard → dry-run + execution on the replica. Runner: `tools/cloud_batch.py 8`. Raw results:
`cloud_batch_results_round1.json`, `cloud_batch_results_round2.json`, `cloud_batch_results.json` (round 3). No data rows are
stored — only status, row counts, errors, empty fields and the generated SQL.

## Questions → SQL (11 questions, 3 engines, 5 sites)

| | Round 1 (baseline) | Round 2 | Round 3 (current) |
|---|---|---|---|
| Validated (dry-run + executed) | 9 / 11 | 11 / 11 | **11 / 11** |
| Execution accuracy vs reference (5 scored) | — | — (Xiqing "pallets per area" returned 0 rows; reference: 79 areas) | **3 / 5 strict, 4 / 5 after roll-up** |

Execution accuracy (EX) = same result set as a hand-written reference query run on the same database (Spider / BIRD metric;
lenient on row order, column order, names and extra columns — `kg_core.exec_match`). References were run on their database
before scoring.

| Site | Question | Round 3 | EX |
|---|---|---|---|
| PrIME 2022 DE08 | pallets (loads) per location area | 185 groups | ✅ identical (185 / 185) |
| PrIME 2022 Athens | pallets (loads) per location area | 32 groups | ✅ identical (32 / 32) |
| PrIME 2014 Xiqing CN74 | pallets (loads) per location area | 79 groups | ✅ identical (79 / 79) — was 0 rows in round 2 (wrong join `invlod.stoloc = pck_area.pck_arecod`) |
| RTCIS Euskirchen | unit loads per location zone | 149 groups | ⚠️ finer grain (sub-site × zone); rolled up to zone: **identical on all zones** |
| PrIME 2022 DE08 | inventory quantity per part and status | 4,545 groups | ❌ open: 32 of 4,544 part/status groups differ (0.7 %) — model used `inventory_view`, reference `invdtl → invsub → invlod`; cause not yet determined |

Not scored (no reference yet, "it ran" only): parts without footprint detail (0 rows), open pick work per wave (0 rows at DE08),
latest 20 movements, locations per area with empty count, Xiqing top-20 parts, RTCIS top-20 items.

## RTCIS → PrIME 2022 conversions (8 real R-queries, source validated on RTCIS Euskirchen, target on DE08)

| | Round 1 | Round 2 | Round 3 |
|---|---|---|---|
| Validated with identical column contract | 6 / 8 | 8 / 8 | **8 / 8** |
| Source ran on its own engine | 7 / 8 | 8 / 8 | 8 / 8 |

R08–R12 return 0 rows on DE08 — the **expert-validated** PrIME versions of the same queries also return 0 rows on DE08
(DEV data), so 0 rows agrees with the ground truth there; Athens is the site with rows for R08 (6) and R12 (1).

## What changed between rounds (each change test-first)

| Finding | Fix | Test |
|---|---|---|
| Keyword linking picked unrelated tables; tables had no descriptions | table descriptions from query intents, concepts, learnings, data facts, SDC module names, TRANSFORMS_TO rules; IDF-weighted ranking; tables read by a matched validated query join the schema | `test_table_descriptions_*`, `test_retrieve_weights_rare_words_above_common_ones`, `test_ask_adds_the_tables_a_matched_validated_query_reads` |
| Valid RTCIS query (AT TIME ZONE) reported as failing: pyodbc cannot fetch `datetimeoffset` | output converter for ODBC type -155 | `test_validate_fetches_datetimeoffset_columns` (cloud) |
| Repair round repeated the error, model guessed another non-existent column | repair message lists the real columns of the tables the failed SQL used | `test_repair_round_lists_the_real_columns_of_the_tables_the_failed_sql_used` |
| Xiqing had no wh_id → `Must declare @wh_id` | site defaults (CN74; Xiqing hosts CN66 / CN74 / CN88) + editable wh_id in the UI | — |
| SQL that ran but answered wrongly (0 rows from a wrong join) | validated join paths mined from the expert-validated SQL (`kg_core.join_paths`, `JOINS_WITH` edges), given to the model; PrIME 2014 borrows PrIME 2022 joins only where its catalog has both columns | `test_join_paths_*`, `test_ask_gives_the_validated_join_paths_*`, `test_prime2014_borrows_*`, `test_convert_gives_validated_joins_*` |
| "Validated" ≠ correct | execution accuracy against reference answers | `test_exec_match_*` |

## Round 4 — LangGraph Deep Agent (GPT-5.6 Sol), same questions and conversions

`tools/kg_deep_agent.py` (`deepagents.create_deep_agent`): AGENTS.md + two curated skills, tools scoped to the request
database, `run_sql` with the read-only guard and a 3-run cap, read-only agent files, deterministic re-validation of the final
SQL. Raw: `cloud_batch_results_deep_agent.json`.

| | Pipeline round 3 (GPT-5.2, single shot + 1 repair) | Deep Agent round 4 (GPT-5.6 Sol) |
|---|---|---|
| Questions validated | 11 / 11 | 11 / 11 |
| Execution accuracy (5 scored) | 3 / 5 | **4 / 5** — DE08 inventory per part/status now identical (4,544 / 4,544) |
| RTCIS unit loads per zone | finer grain (149 groups), equal after roll-up | finer grain again (204 groups) — still open |
| Conversions validated, identical contract | 8 / 8 | 7 / 8 in the batch (R08 ended with prose and no SQL) → fixed test-first: fall back to the last successful run; R08 re-run: validated, identical contract |
| Time per item | 15–30 s | 35–95 s |

Model choice: the platform's newest models (GPT-6.1 Sol / Terra, GPT-6 Sol / Astra) only do tool calls on the Responses API,
and the gateway rejects the multi-turn Responses input (assistant `phase` items, `different Azure OpenAI resource` on stored
items). GPT-5.6 Sol is the newest model that does tool calls on Chat Completions; it is the Deep Agent default
(`KG_AGENT_MODEL`). The single-shot pipeline stays available (`KG_ASSISTANT=pipeline`).

## Round 5 — concept-first routing (themes + Timbr concepts), before / after on a theme set

Change: a `concept_context` tool the agent calls first. It finds the question's business theme (graph `Domain`) and Timbr
concept, and lists their **directly linked** tables in the request engine, checked against the live catalog. Table
descriptions now include the official PrIME descriptions and their theme and concept words. The agent sees no column
hints and no benchmark tables. Benchmark: 7 theme questions were added (shipment, outbound, receiving ×2, trailer,
counting, automation), each with a reference SQL run on DE08 before use. Total: 18 questions (12 with references) and
8 conversions, same model (GPT-5.6 Sol).
Raw: `cloud_batch_results_theme_{before,after,after2,stability,v3_changed,v3_zone}.json`.

| | Before | After (final code) |
|---|---|---|
| Questions validated | 18 / 18 | 18 / 18 |
| Execution accuracy (12 scored) | 10 / 12 | **11 / 12** |
| Conversions validated, identical contract | 7 / 8 (R09 returned no SQL) | **8 / 8** (two runs) |
| SQL runs for the 18 questions / time | 23 / 802 s | 23 / 841 s |

Every item that changed, with all runs:

| Question | Before | After runs | Cause |
|---|---|---|---|
| Configured WCS ids (automation) | 0/1: used `wcs_evt_map` / `wcs_inv_rec_config`, 1 row | **5/5**: `wcsmst`, 8 rows | the theme lists `wcsmst`, and its PrIME description ("The main Warehouse Control System table") is now searchable |
| Picked + shipped quantity per shipment status | 0/1 | 3/6 (one run returned no SQL) | **the reference was wrong**: it used `pckqty` (still to pick: 0 on completed shipments) instead of `picked_qty` (picked: 64,268,802 ≈ shipped 64,268,880 on completed). The reference was fixed and all stored SQL re-scored. The agent still varies between the two columns. |
| RTCIS unit loads per zone | 1/1 | 1/8 | the known finer-grain issue (BUG-10: sub-site × zone, also open in rounds 3–4). Version 1 offered RTCIS tables inferred through two mapping hops (`agv_inventory_view`), and the agent used one. Fixed: only tables linked directly to the theme or concept are offered, and themes with no table in the engine are not shown. Still unstable at n=3 (1/3). |

Fixed on the way (tests first):
- `CosmosGraph.context` failed the whole Gremlin query when a `MAPS_TO` target lacked `table`, and the request returned 500. Every projection is now `coalesce`d, and graph tools report a failure to the model instead of raising.
- Theme descriptions made of the Domain name alone could not route ("shipments" did not reach `outbound`). Generic tables found in every theme (`wh`) are left out.

Limits: one run per item for **before**, and n=2–8 per changed item for **after**. The 12 references cover 9 of the 10
themes (master data and picking have none). Next: references for the 6 unscored questions, more questions per theme
(BIRD-style held-out set), n ≥ 3 for every item, and RTCIS zone grain as a rule in the query-writing skill (BUG-10).

## Round 3 detail

Open: the inventory difference above; references for the 6 unscored questions; a larger held-out question set (BIRD-style) before
any production use.
