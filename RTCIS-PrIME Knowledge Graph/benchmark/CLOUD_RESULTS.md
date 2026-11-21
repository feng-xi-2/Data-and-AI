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

Open: the inventory difference above; references for the 6 unscored questions; a larger held-out question set (BIRD-style) before
any production use.
