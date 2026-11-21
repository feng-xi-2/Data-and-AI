# How to update the PRIME ELS Hypercare KPI report

Who does what:

| You want to... | Do this | Rebuild? |
|---|---|---|
| Change an alert target / warning / critical | Edit the **Alert targets** tab of `Hypercare_KPI_Inputs.xlsx` (PRIME ELS SharePoint folder). Site = `All sites` for everyone, or a site code for one site | **Yes** - targets are copied into the file at build (`config/build_options.csv` Embed_Inputs = 1, so the file needs no Excel): `py tools/build_pbip.py` then re-share. Embed_Inputs = 0 = read at every (hourly) refresh instead |
| Change the refresh interval | `config/refresh_policy.csv` HOT Every_Minutes (now 60 = hourly), then `py tools/auto_refresh.py --install` and rebuild (banner 'next refresh') | Yes for the banner |
| Publish the shared report (.pbix WITH data - what users open) | Automatic: the scheduled task at `Snapshot_Hour_1/2` (config/desktop_refresh.csv, 07 / 19 PC time) and the *on unlock* task (copy older than 10 h, or report rebuilt) run `tools/snapshot_pbix.py`: refresh, save the .pbix, upload to SharePoint PRIME ELS / Hypercare KPI, new START HERE page. By hand: `py tools/snapshot_pbix.py --publish` (after a rebuild: `--from-pbip`). Log: `tools/_auto_refresh.log` (`snapshot |`) | No |
| A locked or sleeping PC | Power BI Desktop cannot renew its replica sign-in on a locked screen (measured 5-Nov), so a timed copy is deferred (`snapshot | deferred`) and the unlock task publishes ~10 min after the next unlock. Fully unattended copies need the Power BI Service + gateway connections (replica owners) | No |
| A refresh / publish takes very long | Look at `tools/_auto_refresh.log` (`snapshot |` lines: every progress line, free memory at start). Usual cause: the PC is out of memory (< 2 GB free = the run is deferred and names the biggest apps; a run is stopped after 45 min). Close browsers / VS Code windows you don't need; the next snapshot hour or unlock publishes | No |
| Try a target without saving | Config & Health > *Alert threshold inputs*: type a value + Enter | No (only for you, not saved) |
| Add a site (max 6) | Add a row to the **Sites** tab, then `py tools/add_site.py <CODE>` | Yes - the command builds it |
| Remove a site | Delete its row in Sites, then `py tools/apply_inputs.py --apply --confirm` and `py tools/build_pbip.py` | Yes |
| Fix a location pattern / area / flag of a site | Edit the column in `config/site_config.csv` (meaning: Settings reference in the skill `hypercare-site-setup`) | Yes |
| Change a query | Edit `sql/new/<Table>.sql` (new feeds) or `sql/extracted/<Table>.m` (BD original feeds) - use tokens, never site values | Yes |
| Change a KPI formula | Edit `tools/measures_*.py` (one place per measure; thresholds always via `thr("KEY")`) | Yes |
| Change a page / visual | Edit `tools/report_pages.py` (Home, Cockpit, Alerts, Daily, Users, Config) or `tools/report_diag.py` (diagnosis pages) | Yes |
| Change page order / sections / page help text | `config/page_guide.csv` (Section, Purpose, How_Calculated, How_To_Configure) | Yes |
| Change colours / fonts | `theme/palette.json` -> `py tools/build_theme.py` | Yes |
| Change the refresh frequency | `config/refresh_policy.csv` (tier minutes), then `py tools/auto_refresh.py --install` | No |
| Change the office hours without Desktop refresh | `config/desktop_refresh.csv` (Quiet_From_Hour / Quiet_To_Hour, PC clock) | No (task); yes for the banner text |
| Change what Copilot knows (AI instructions) | `config/copilot_instructions.md` (text, written to Microsoft's AI-instruction guidance: themed sections, explicit table / column per question, ambiguity rules; `{{SITES}}` / `{{KPIS}}` / `{{QUESTIONS}}` are filled from site_config / kpi_thresholds / copilot_questions - max 10,000 characters, checked), `config/copilot_questions.csv` (question templates: template, example = Copilot starter question, answer steps), `config/copilot_descriptions.csv` (measure descriptions), `config/copilot_fields.csv` (the only tables / fields Copilot sees - everything else is hidden in the shared .pbix; visuals keep working), `config/site_aliases.csv` (names users type for a site - BD, local spelling, country; code / name / WH ID / SAP plant are added automatically; typos are matched by the fuzzy rule in the instructions), `config/copilot_kpi_words.csv` (users' words per KPI) and the answer tables 'KPI Scorecard' / 'Site Summary' (`ANSWER_TABLES` in `tools/copilot_ai.py`). Preview: `py tools/copilot_ai.py`. Into the shared .pbix without refresh: `py tools/snapshot_pbix.py --copilot`; every snapshot also applies them; `py tools/copilot_ai.py --service` checks the workspace copy | No for instructions / descriptions / fields (next snapshot); starter questions (PBIP `Copilot/examplePrompts.json`) need a rebuild + `--from-pbip` |
| Leave a site out of the shared report (lighter file) | `config/build_options.csv` AllSites_Exclude (e.g. `XIQING|ATHENS`); its config row stays and its single-site file still builds. Remove the code to bring it back | Yes: `py tools/build_pbip.py --all-only`, then `py tools/snapshot_pbix.py --from-pbip` |
| SAP tables / pages in or out | `config/build_options.csv` Include_SAP_CDL: 0 (default since 20-Nov) = no SAP tables, measures or pages (Production SAP vs PrIME, Predicted Plt/h) - every object that reads them is removed at build; 1 = built for sites with Has_SAP_Plan / Has_SAP_Prod = 1 (needs Databricks access) | Yes: rebuild + `--from-pbip` |

## The update loop (every change that needs a rebuild)

```powershell
cd BD_Hypercare_KPI
# 1. check the change against the replicas (every query compiles + runs, per site)
py tools/validate_sql.py MINHANG JAKARTA            # or the sites you changed
# 2. build: model + report + gates (DAX, relationships, layout, config names, Home buttons)
py tools/build_pbip.py                               # dist/ALL_SITES + one file per site
py tools/build_pbip.py <SITE> --service              # Service variant (incremental refresh policies)
# 3. open + refresh in Power BI Desktop (sign in with your Microsoft account when asked)
py tools/open_model.py "dist\ALL_SITES\WH Hypercare KPI.pbip"
powershell -File tools\refresh_desktop.ps1 -Tables "*"
# 4. test field by field, visual by visual, filter by filter, KPI vs replica SQL, report intent
powershell -File tools\run_full_tests.ps1 -SkipOpen -Sites "MINHANG,JAKARTA,AKASHI"
# 5. publish + share
py tools/publish.py                                  # -> My workspace (or --workspace "<name>")
py tools/make_packages.py                            # site zips + kit zip
py tools/make_handbook.py                            # this handbook (HTML + zip)
```

Every step prints a heartbeat at least every 30 s and stops with a clear message on any problem - nothing fails silently.
Never patch one visual by hand in Desktop: the next build overwrites it. Fix the config / query / measure / page builder instead.

## Deploy from Git (planned: the workspace refreshes itself from the replicas)

**Access (Data Replica Authentication and Integration Standards v4, section 5 PowerBI):** the Power BI **Service** connects with a
**Service Principal** (App Registration `prime-els-hypercare-prod-sp`, secret in a Key Vault only); a personal / ION account is
for Desktop only. Process: create the SP -> approval of each site key user -> iDecide Ops (idecideoperations.im, approval attached)
raises an RITM, adds the SP read-only to the site replica and shares the Data Replica gateway connection. E-mail drafts:
`Email_draft_replica_SP_access.txt` (M&M folder).

Once the Service can reach the replicas (the 4 `MI-<SITE>-PROD-FULL-PaaS-ADHOC` gateway connections shared with you), the
workspace refreshes the model itself and the PC snapshot is no longer needed. The report is then deployed from Git:

1. **Repo:** <workspace> is already connected to `<company-org>/pbi-fabric-recovery`, branch `Development`, folder `/`
   (last sync 12-Nov). Use that private org repo for the deployable project - the model holds replica server names, so never a
   public repo. Every build writes `.platform` files (stable logicalId, display name = build_options `Fabric_DisplayName`).
2. **Once per person:** set your Git credentials for the workspace (workspace > Source control > settings, GitHub connection).
   Without them every Git call returns `GitCredentialsNotConfigured` (measured 20-Nov).
3. **Change -> deploy:**
   ```powershell
   py tools/build_pbip.py --all-only        # dist/ALL_SITES: .pbip + WH Hypercare KPI.SemanticModel + .Report (+ .platform, Copilot/)
   # copy dist/ALL_SITES/WH Hypercare KPI.* into the repo folder, commit, push to Development (PR as usual)
   py tools/fabric_git_update.py --workspace "<workspace>" --status   # what Git would change
   py tools/fabric_git_update.py --workspace "<workspace>" --bind     # pull the commit + bind the gateway connections
   ```
   In a pipeline (GitHub Action on push) the same script runs as a service principal: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
   `AZURE_CLIENT_SECRET` as repository secrets, SPN = Contributor on the workspace.
4. **First deploy only:** in the model settings set the refresh schedule (hourly), Q&A on, *Approved for Copilot* on. A Git-deployed
   model has no data until its first refresh; its Copilot starter questions (`Copilot/examplePrompts.json`) work there, unlike the
   .pbix copy.
5. **Then** stop the PC snapshot: `py tools/auto_refresh.py --uninstall` (or keep it as a fallback while the Service refresh is new).

`py tools/publish.py --workspace "<workspace>" --bind-only` alone re-binds the connections of an existing model
(prints per site: bound / not shared yet).

**One site first (e.g. Jakarta while the other connections are not shared yet):** a single-site model needs only its own connection.
```powershell
py tools/build_pbip.py JAKARTA --service                                              # dist/_service/JAKARTA (incremental refresh)
py tools/publish.py --workspace "<workspace>" --site JAKARTA --service      # model + report "WH Hypercare KPI - JAKARTA"
py tools/publish.py --workspace "<workspace>" --bind-only --site JAKARTA   # once MI-<SITE>-PROD-FULL-PaaS-ADHOC is shared
```
Then in the Service: model settings > refresh now + schedule hourly; Q&A on; *Approved for Copilot* on.

**Load and test in the workspace (no Desktop needed, measured 20-Nov on Jakarta):**
```powershell
# refresh: ONE enhanced refresh, tables in parallel, per-table progress every 30 s (or table by table: drop --all)
py tools/service_refresh.py --site JAKARTA --workspace "<workspace>" --all --parallel 6
py tools/service_refresh.py --site JAKARTA --workspace "<workspace>" --status      # what is running now
# test every visual / day / slicer value on the PUBLISHED model (executeQueries API, 4 queries in parallel)
py tools/visual_replay.py --service <workspaceId>/<modelId> --report "dist/_service/JAKARTA/WH Hypercare KPI - JAKARTA.Report/definition" --sites JAKARTA --overrides --days 3
# a site that is not live yet: the same model on its rehearsal / non-prod replica, as a separate "... (TEST)" model + report
py tools/build_pbip.py JAKARTA --service --test-server <replica-server>.database.windows.net
py tools/publish.py --workspace "<workspace>" --site JAKARTA --service --test-server <replica-server>.database.windows.net
py tools/service_refresh.py --site JAKARTA --test --workspace "<workspace>" --all
```
- Right after a publish the calculated tables (Cfg_Threshold, KPI Scorecard, Site Summary, Site Activity ...) are empty: every visual
  shows *"calculated table ... needs to be recalculated or refreshed"* and the header cards draw white error boxes over the banner
  until the first refresh completes. Not a defect - refresh first, then test.
- **After a REpublish** (model already loaded) imported data is kept: run `py tools/service_refresh.py --site <SITE> --config`
  (reloads the embedded tables - Cfg_*, Input *, Field Dictionary: new RCA texts / thresholds / descriptions - then recalculates;
  ~4 min, no replica query). A full reload is only needed when a replica query changed.
- `publish.py` waits and retries while a scheduled refresh runs ("Can't deploy as target because model is refreshing").
- Timings measured 20/21-Nov through iDecide's PROD gateway (shared with other teams): ~13 s per table alone, several minutes per
  batch of 6 when two models load at once - load one model at a time. `--all` = plain tables with **partialBatch** (each table usable
  as soon as it is loaded), the incremental tables **transactional** (the Service refuses partialBatch for refresh-policy tables),
  then calculate. Incremental history > 62 days is kept in **monthly** partitions (a 397-day window in daily partitions = ~800
  gateway queries on the first load), the last `Recent_Days` days daily.
- **Refresh speed (21-Nov).** The scheduled refreshes took 1,484-1,869 s every hour although the model is only
  ~11 MB (memory check below) - the time went into gateway round trips (~35-60 s per Power Query table, also for config tables that
  never touch the replica) at the busiest slot of the shared gateway. Best-practice fixes, all in the generator:
  1. config tables that Power Query does not need are **DAX calculated tables** (`DATATABLE`, `build_pbip.dax_config_table`;
     16 tables + the Field Dictionary) - computed in the engine, no gateway query. Only Cfg_Site / Cfg_Engine / Cfg_LineMap /
     Cfg_TargetInput / Cfg_ThresholdBase stay Power Query (the site SQL tokens read them): 46 -> 31 gateway queries;
  2. **refresh parallelism 12** (model property `maxParallelismPerRefresh` = Desktop *Options > Current file > Data load > Maximum
     number of concurrent jobs*; the Service default is 6) - `config/build_options.csv Refresh_Max_Parallelism`;
  3. schedule at **:30** every hour (not the top of the hour when every model on the gateway refreshes);
  4. **staging queries**: Cfg_Site / Cfg_Engine / Cfg_LineMap / Cfg_TargetInput M lives in non-loaded `<table>_Src` expressions that
     every M query references (`build_pbip.stage_config_queries`, Service builds) - Power Query best practice: never reference a
     loaded table from another query;
  5. **12 connections per data source** (model property `dataSourceDefaultMaxConnections`, build option Source_Max_Connections) -
     every replica table shares one source.
  Measured (TEST model, 21-Nov): before = 1,458 s for one whole-model refresh; after = 88 s / 495 s / 1,030 s for three schedule-style
  refreshes in a row (same model, minutes apart). The same SQL run directly on the replica: 1 - 3 s per query - **the remaining time
  and its variation are queueing in iDecide's shared gateway**, not the model or the replica. Evidence + request to iDecide:
  `Email_iDecide_gateway_refresh_performance.txt` (M&M folder).
  6. **Features that are OFF for the site are left out at build** (Service builds; `build_pbip.per_site_bodies`): the site settings
     are fixed in the model, so a Level A / hand-off table of a site without Level A no longer sends a query through the gateway every
     hour just to return an empty table (Jakarta: 33 -> 23 replica queries per refresh).
  Measured after 6 (21-Nov): on-demand full refresh TEST **44 s**, PROD **39 s**; the scheduled run at :30 took 432 s - the same
  model, so the rest is the shared gateway at schedule time. Scheduled refreshes only start at :00 / :30; a quieter minute (e.g. :45)
  needs a Power Automate flow (Recurrence -> "Refresh a dataset") instead of the built-in schedule.
- **Real-data TEST environment** (a site that is not live, or a replica the Service cannot reach): `py tools/test_env.py BINHDUONG
  [--tests] [--min-free-gb 1]` builds the site file, refreshes it in Desktop from the replica, saves the .pbix (answers the tenant's
  *sensitivity label* question with "Business Use"), imports it WITH data into the workspace as *WH Hypercare KPI - BINHDUONG (TEST
  data)* and, with `--tests`, runs alerts / every visual x day / every slicer value / every field on it. Not refreshed by the
  Service (snapshot) - rerun to update. Needs ~2 GB free memory for the Desktop refresh.
- **On-screen test** (what the query tests cannot see): open every page of the published report at the real window size and count
  error boxes and collapsed slicers (`.slicerResponsiveIcon`), screenshot each page. Build gate `layout_preview.py` COLLAPSED_SLICER
  stops a responsive slicer under 50 px tall before it is published.
- **Model health (Microsoft rules).** The Service's *Best practice analyzer* / *Memory analyzer* buttons create a Fabric notebook -
  refused in <workspace> ("Creating Notebook is not currently supported in this workspace" - a Fabric admin setting). Same
  checks without notebooks:
  - **BPA:** Tabular Editor 2 (free, portable) with the community rules `microsoft/Analysis-Services/BestPracticeRules/BPARules.json` on
    the built TMDL: `TabularEditor.exe "<...SemanticModel>\definition" -A BPARules.json -V`. Fixed in every build by `tools/bpa_fixes.py`
    (hidden non-key columns `isAvailableInMdx: false`, no default summarisation on visible numbers, helper measures hidden, thousands
    separators on counts). Known false positives of the offline run: relationship / date-table type rules (calculated columns have no
    declared type in TMDL - all 9 relationship pairs verified equal in the live model), 'Remove unnecessary measures' (TE does not see
    the report visuals), 'Whole numbers ... #,0' (unit formats such as `#,0 "plt"` are intentional).
  - **Memory (VertiPaq):** Service > model > DAX query view: `INFO.STORAGETABLECOLUMNS()` / `INFO.STORAGETABLECOLUMNSEGMENTS()`
    (the INFO functions work there, not through the executeQueries API). Jakarta: 9.7 MB dictionaries + 1.2 MB data.
- **Tests on the published model** (no Desktop): `visual_replay.py --service` (every visual x day; `--filters 3` = every slicer value),
  `audit_fields.py --service <ws>/<model> --model <...SemanticModel>` (every column of every site table: empty / negative / future /
  old values), `alert_test.py --service <ws>/<model> --site <SITE>` (every KPI status recomputed from actual vs limits, every alert
  rule = its KPI, breached rules carry action + owner, 'What to do now' lists exactly the breached rules).
- `publish.py` reloads the embedded tables and recalculates by itself after a REpublish (`--no-reload` to skip) - no 'needs refresh'
  warning icons in the model view and no 'calculated table ... needs to be recalculated' visuals after a publish.
- Refresh schedule: hourly at :30 (24 slots, SE Asia Standard Time, mail on failure) set on the workspace model with the REST API
  (`refreshSchedule`); F2048 capacity allows 48 a day. A scheduled refresh = whole model with the incremental policy (only the
  recent partitions re-read).
- At a fractional fit-to-width zoom (e.g. 84 % in a narrow window) the Service can clip the first characters of axis labels; at
  100 %+ they are complete (measured: 124 % shows '40 plt/h' in full). Not a report defect.
- The binding picks the gateway connection by name (Cfg_Site Gateway_Connection) or else by replica server + database
  (TEST builds: e.g. `MI-JAKARTA-DEV-FULL-PaaS-ADHOC`).

**Copilot readiness (every build, Microsoft 'Prep data for AI' guidance):**
- every table / measure / visible column gets a description - meaning and unit first (Copilot reads ~200 characters), then the
  formula: `tools/ai_descriptions.py`, words from `config/column_glossary.csv` (WMS codes, site settings) + field guide; gate C8
  fails the build when one is missing;
- **'Field Dictionary'** table (same tool): one row per table / measure / visible column / site setting with Meaning and Formula -
  Copilot answers "what does LOC_LTA mean / how is X calculated" from these rows (Microsoft: descriptions mainly steer DAX
  generation, Copilot answers from data); tested 21-Nov in the workspace;
- AI data schema `Copilot/schema.json` from `config/copilot_schema.csv`: helper measures (strip copies, colours, labels, Card / Thr /
  Rows) and parameter tables hidden from Copilot, everything a visible measure depends on kept;
- AI instructions `config/copilot_instructions.md` (limit 10,000 characters, the build fails above): EXPLAIN section = field meaning,
  how a KPI is calculated ([How Calculated] / [Numbers Behind]), root cause ([Meaning If Breached], [What To Check], Cfg_AlertRule),
  fuzzy matching of site / KPI / field words; example questions use the sites of the file (`copilot_ai.questions_for`).

## Publish the code to GitHub (public copy - code, queries, skills, docs; never data or access)

```powershell
py tools/compare_replica_pbi.py <PBIDesktop PID>     # refreshes queries/ (replica SQL + PBI DAX) and docs/REPLICA_VS_PBI.md
py tools/export_public.py "<repo>\PRIME ELS"         # sanitized copy + tools/check_publish.py gate (exit 1 = do not commit)
cd "<repo>"; git checkout -b <branch>; git add "PRIME ELS"; git commit; git push   # then open a pull request
```

* **Never in the public repo:** tokens, passwords, connection strings, Git or Power BI credentials, e-mail addresses, user names,
  workspace / model / tenant ids, replica host names, SharePoint links, `.pbix` / `.abf` / Excel files. `export_public.py` replaces
  them with placeholders (`PUBLIC_EXPORT.md` lists them) and writes a `.gitignore` that blocks data and state files.
* **Gate:** `tools/check_publish.py` runs at export and again in the repository Action `.github/workflows/prime-els-publish-check.yml`
  on every pull request touching `PRIME ELS/` - a finding fails the check. Sign-in happens at run time (MSAL token cache in the user
  profile, Windows credential manager for Git) - nothing of it is ever written into the kit.
* The **deployable** PBIP (real server names) goes to the private org repo of the Fabric workspace (section above), not here.

## Rules that keep it working for every site (PrIME 2014 and 2022)

* **No site values in code.** Queries use tokens (`{WH_ID}`, `{LOC_LTA}`, `{S}` ...): site tokens from `config/site_config.csv`,
  engine differences (schema `prodwms` vs `dbo`, zones, footprints, inbound truck link) from `config/engine_profiles.csv`.
* **No hard-coded thresholds.** Measures read `Cfg_Threshold` (inputs file > config site row > All sites > default).
* **Units on every field** (`config/measure_units.csv`, `config/field_guide.csv`); users see numbers, never config names (build gate).
* **Report window:** day measures use `[Win Start]` .. `[Win End]` (shift day or the selected shift); hourly measures use the `_HV` helper.
* **Empty is explained:** a new empty field or visual must get a reason in `config/field_expectations.csv` or
  `config/visual_expectations.csv` (with a DAX condition proven per site) - otherwise the tests fail.

## Troubleshooting

| Symptom | Why | What to do |
|---|---|---|
| "Working on it" box in Power BI Desktop for several minutes | The scheduled task *PRIME ELS Hypercare refresh* refreshes the open Desktop model (HOT tier ~4-5 min, HOT + WARM ~10 min, daily full ~18-20 min); Desktop shows the box while the engine refreshes | **Office hours are quiet**: `config/desktop_refresh.csv` (default 08:00-19:00, PC clock) - no automatic Desktop refresh then, the Service keeps refreshing; the banner says when the next Desktop refresh comes. Change the hours in that file (no rebuild needed for the task; rebuild for the banner text) |
| A button does nothing in Desktop | Desktop editing view selects the button on a click | **Ctrl + click** in Desktop; a single click in the Service |
| Tables empty after opening the .pbip | The PBIP stores no data | Home > Refresh (sign in: Microsoft account -> Connect) |
| "Login failed ... untrusted domain" | A Windows credential is stored for the replica | File > Options > Data source settings > the `<replica-server>` entry > Clear permissions, refresh, choose Microsoft account |
| A site shows N/A pages | Feature flag off (`Has_Production`, `Has_LevelA` ...) or the replica is not live yet | Config & Health shows why; `py tools/profile_site.py <SITE> --compare` |
| Numbers differ from the BD Excel | Different time window / late postings | `docs/BD_ORIGINAL_COMPARE.md` and `docs/RECONCILIATION.md` explain each difference |
