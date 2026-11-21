---
name: pbi-build-standards
description: "Standard way to build, test and publish a warehouse Power BI report (PrIME 2014 / PrIME 2022 replicas) that works the first time in the Service: generated PBIP/TMDL from config, build gates, a test pyramid that ends with an on-screen check of the DEPLOYED report on REAL data, refresh-speed rules for gateway sources, Copilot readiness and a Config & Health page that says the cause and who fixes it. USE WHEN building or changing any PBI report or semantic model, publishing to a workspace, setting up refresh / incremental refresh, testing visuals, or when a report shows errors, empty visuals, collapsed slicers, slow refresh or failed health checks. Trigger phrases: 'build a PBI report', 'copy the dashboard for another site', 'publish to the workspace', 'refresh is slow', 'visuals are empty', 'error fetching data', 'test every visual', 'health checks failed'."
---

# Power BI build standards (warehouse reports)

## 1. Build from config, never by hand
- One generator writes the PBIP (TMDL model + PBIR report) from `config/*.csv` + SQL templates. A fix goes into config or the
  generator so it reaches every site and every page - never patch one visual or one site.
- Query templates per engine: `queries/PrIME_2014/` (schema `prodwms`, zoning by area `arecod`) and `queries/PrIME_2022/`
  (schema `dbo`, five zone frameworks on `locmst`). Site settings are `{TOKENS}` measured from the replica (profiler), each with
  evidence; weak evidence = feature OFF, never a guess.

## 2. Build gates (the build fails, nothing is published)
| Gate | Catches |
|---|---|
| Model best practice (BPA rules + own rules) | missing formats / descriptions, RETURN without VAR, summarised keys, MDX on hidden columns |
| Layout | overlap, off-page, tiny visuals, text overflow, **COLLAPSED_SLICER** (a responsive slicer under 50 px tall shows only a funnel icon in the Service, which draws pages at < 100 % zoom - set `general.responsive = false`) |
| Titles / config names | no config token names or "(config/...)" in what users read |
| Measures | every measure valid before a .pbix is saved |

## 3. Test pyramid - "done" means deployed AND retested on the deployed version
1. SQL on the replica (`validate_sql`): every query, row counts, time.
2. Every measure / field (`audit_fields --service`): empty / negative / future values per column, explained or a defect.
3. Every visual x day and every slicer value (`visual_replay --service`, `--filters`), 0 errors.
4. Alerts (`alert_test`): each KPI status recomputed from actual vs limits.
5. Same as the template site (`compare_site_bd`).
6. **On screen, on the deployed report**: open every page in the browser at the real window size, count error boxes,
   collapsed slicers (`.slicerResponsiveIcon`), empty visuals; screenshot. Query tests alone pass while users see broken boxes.
7. **On real data**: a site that is not live yet makes every test "pass" on empty data. Keep a TEST environment with real
   activity (`tools/test_env.py <SITE>`: Desktop refresh -> .pbix with data -> workspace import, or a TEST model on a rehearsal
   replica) and run steps 2-6 there too.
Record each run (cases, passed, evidence file) in the tracker (Jira test-run item, PR description).

## 4. Refresh speed with an on-premises / VNet gateway
Time is spent per gateway query (~30 s fixed overhead each on a shared gateway, measured: a 2-row query = 1.9 s on SQL, 38 s as a
Service refresh), not per row. So:
- Count the gateway queries per refresh and cut them: config tables as DAX `DATATABLE` (no source), shared M as non-loaded
  staging expressions, **features that are OFF for the site left out at build** (no query that returns an empty table every hour).
- Incremental refresh: refresh only the last 1-2 days; archive old data in month partitions (> 62 days) - daily partitions over a
  year = hundreds of gateway queries on the first load.
- `maxParallelismPerRefresh` / `dataSourceDefaultMaxConnections` ~12; schedule off the hour (:30) when the gateway is shared.
- Expensive calculated tables are paid every refresh: time each one (`EVALUATE ROW("n", COUNTROWS(<expr>))`).
- Variance that stays after this is gateway load: send the evidence (direct SQL time vs refresh time) to the gateway owner.

## 5. Config & Health page that a user can act on
- One verdict on top with ONE cause, first match: refresh failed > nothing loaded > site not live > replica behind > single checks.
- A site that is not live (< 3 days of transactions) shows its activity checks as "NOT LIVE" (wait), not FAIL - nothing to fix.
- Every check row has "What to do" in plain words and "Who" (owner). Numbers without "0." artefacts.
- Input boxes that try a threshold show the value in use next to them (an empty what-if box shows 0).

## 6. Copilot readiness
Descriptions for every table / measure / visible column (meaning first, then formula), a Field Dictionary table, AI instructions
(< 10,000 characters) with fuzzy site / KPI words, AI data schema, example prompts with the file's own sites; then Q&A on +
"Approved for Copilot" in the model settings.

## Lessons from the first builds (why it went wrong)
- Tests checked data, not the screen -> collapsed input boxes reached users. Fixed by gate COLLAPSED_SLICER + on-screen test.
- The first site was not live -> visuals empty, 6 health checks "failed", users had no way to tell why. Fixed by the verdict +
  NOT LIVE status + a real-data TEST environment.
- Refresh judged by data volume -> it was gateway query count. Fixed by counting and cutting queries.
- Publish while a refresh runs fails; calculated tables need a recalculation after publish -> publish waits, then reloads.
