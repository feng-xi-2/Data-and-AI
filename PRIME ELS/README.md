# PRIME ELS Hypercare KPI kit (Power BI)

One configurable Power BI dashboard for **PrIME 2014 and PrIME 2022** data replicas, built from:

* **BD Throughput as of October.pbix** (Binh Duong) - all pages, tables and measures kept, BD-only values removed
* **Macro BD Report v5 Macro.xlsm** - the 13 Power Query queries + CONFIG / ALERTS / LTA_RCA / HOURLY_ALERT / VALIDATION / FLOW_ANALYTICS / DAILY_REPORT logic re-implemented as config tables + DAX
* the hypercare KPI list: 1 Production pallets/h, 2 Inbound TTAT, 3 Outbound TTAT, 4 Location utilisation, 5 User productivity, 6 Daily health checks - each with **target, warning, critical and prediction**

**One model, every site, one site on screen.** Each replica table has one partition per configured site (static server / database per site = Service-safe) plus a hidden `SiteCode` column; `Cfg_Site` filters every table. The **Site slicer in the banner of every page** (synced, single select, forced) picks the site - no setup menu, no parameters, no refresh to switch. Everything else - SQL tokens, thresholds, RCA texts, page help - lives in `Cfg_*` tables inside the model and in `config/*.csv` here.

| Site | WMS | Replica (server / db) | Status |
|---|---|---|---|
| BINHDUONG | PrIME 2022 | <replica-server> / BINHDUONG_REPLICA | validated, reference (LTA take-away production) |
| MINHANG | PrIME 2022 | <replica-server> / MINHANG_REPLICA | auto-profiled: production ON (work-order receipts, 25 lines), Level A `_0%A` in BR01-FW, no HOFF, inbound TTAT per trailer - confirm with site |
| JAKARTA | PrIME 2014 | <replica-server> / JAKARTA (PROD) | Karawang DC **ID01** (client B665): trucks, picking, Level A pick faces `C%A`, shifts 00/08/16. Production (plant A410, warehouse ID12) is not in the PROD replica yet -> production pillar OFF, SAP A410 volume shown from CDL - confirm with site |
| AKASHI | PrIME 2022 | <replica-server> / AKASHI_REPLICA | PrIME live since 30-Oct 08:47, outbound only so far; SAP plant 4527 shows the production (not yet received in PrIME) - confirm with site |
| XIQING | PrIME 2014 | <replica-server> / XIQING | auto-profiled: production ON (work-order receipts, ~1.2-2.6k plt/day on XQH*/XQI*/BC* lines), Level A `A0%A` in pick area CP1, zones = areas (RPMPCK / QAQC-IM excluded), no HOFF - confirm with site |
| ATHENS | PrIME 2022 | <replica-server> / ATHENS_REPLICA | auto-profiled: distribution centre - production / Level A / HOFF OFF; RDT area RDTS000015; inbound GR linked on receipt actions only (ASN_TRUST / ASN_NONTRUST / RCV); UTC+2 in winter (+3 summer) - confirm with site |

Auto-profiled values were found by comparing each replica with the BD reference (put-away destination of produced pallets, `F0%A`-style level-A locations, HOFF location names, RPM / problem zones, check-in locations, work-order receipts, trailer actions). The evidence is in `Cfg_Site[Notes]`; `Config_Status` stays *AUTO-PROFILED - confirm with site* until the site signs off.

## Folder map

```
BD_Hypercare_KPI/
  Hypercare_KPI_Inputs.xlsx  <- THE ONE INPUTS FILE, in the PRIME ELS SharePoint folder (Data Projects/PRIME ELS/Hypercare KPI) (path: config/inputs_source.csv):
                             tab Sites (max 6 rows, 16 columns a site owner knows) + tab Alert targets ('All sites' = BD defaults,
                             a SiteCode row overrides). Targets are copied into the model at build (config/build_options.csv
                             Embed_Inputs = 1: the file never reads the workbook); sites -> py tools/add_site.py
  inputs/Hypercare_KPI_Inputs_TEMPLATE.xlsx   empty template (py tools/make_inputs_template.py)
  config/                  <- EDIT THESE (or the Cfg_* tables in Power BI Desktop)
    build_options.csv        what a built file may depend on: Include_SAP_CDL (0 = replica only, default) / Embed_Inputs (1 = targets built in) /
                             AllSites_Exclude (sites left out of the shared all-sites report, now XIQING|ATHENS)
    site_config.csv          one row per site: replica, wh_id, shift hours, feature flags, SQL tokens, CDL
    engine_profiles.csv      PrIME 2022 vs 2014 differences (schema dbo/prodwms, sto_zone vs area, loc_typ)
    kpi_thresholds.csv       target / warn / crit per KPI (Site='*' default, add a row per site to override)
    kpi_explain.csv          per KPI: how it is calculated, the numbers behind it ({DAX|format} template), prediction method, diagnosis
    stock_age_bands.csv      stock age bands (days since receipt; FIFO date when no receipt date) of the Inventory page (also generates the SQL band)
    stock_old_causes.csv     Inventory: likely cause + action of old stock per location class (on trailer / receiving / shipping / line / storage)
    alert_rules.csv          the 23 alert rules (17 from the Excel ALERTS sheet + 6 new) with owner + action
    rca_rules.csv            line root-cause, verdict and narrative TEXTS with {placeholders}
    copilot_instructions.md  Copilot AI instructions (Prep data for AI): {{SITES}} / {{KPIS}} filled from site_config, kpi_thresholds, alert_rules
    copilot_descriptions.csv descriptions of the measures Copilot should use (KPI Actual / Status, Alert Action, Narrative ...)
    copilot_fields.csv       the ONLY tables / fields Copilot sees in the shared .pbix (answer tables + site + date + history measures)
    copilot_questions.csv    question templates: template + example (= Copilot starter question) + how to answer -> instructions + examplePrompts.json
    site_aliases.csv         other names users type per site (BD, local spelling, country) -> Copilot fuzzy site match + Site Summary[Also Called]
    copilot_kpi_words.csv    users' words per KPI (throughput, space, labour ...) -> the KPI DEFINITIONS block of the Copilot instructions
    health_checks.csv        daily data-health checks (Excel VALIDATION, generic part)
    line_map.csv             production source (LTA lane, or work-order line) -> production line + category per site
    market_colors.csv        shipping market colours (Predicted Plt/h)
    page_guide.csv           'how it is calculated / how to configure' footer of every page
    measure_units.csv        unit shown with every numeric measure (plt, plt/h, min, h, locs, users...) - applied as format string
    column_units.csv         unit rules (regex on Table|Column) for every numeric column (min, h, plt, cs, BUoM, locs, cm, hh:00...)
    threshold_inputs.csv     which KPI targets get an input box on the Config & Health page (range, step, unit)
    refresh_policy.csv       refresh tiers HOT 30 min / WARM 60 / PLAN 240 / COLD daily - which tables in which tier
    incremental_policy.csv   incremental tables: partition date column, SQL anchor, recent days, Service rolling window
    kpi_reference.csv        KPI accuracy test: model measure <-> independent reference SQL (sql/reference) + tolerance
    table_basis.csv          time basis of every table (DAY / SNAPSHOT / WINDOW / PLAN / MASTER) for the intent checks
    visual_expectations.csv  explained empties for the intent check: Page / Visual regex + DAX condition proven per site and day
    field_expectations.csv   verified, explained field patterns (expected empties, negatives, look-ahead dates) with the reason
    bd_reference_changes.csv documented, intended differences vs the original BD Throughput queries
    measure_types.csv        engine return type of every measure (tools/sync_measure_types.py) - standard number formats
    dax_reserved_words.txt   words the engine refuses as DAX variable names, measured by tools/sync_dax_reserved.py (gate C6)
    process_stages.csv       PROCESS MODEL: every stage inbound -> production -> storage -> outbound (trucks / pallets / shipments),
                             pallet location rules (site tokens), warning / critical age, action, owner (Site=<code> rows override '*')
    trailer_status.csv       WMS trailer status (trlr_stat) -> process stage, per direction (descriptions come live from dscmst)
    shipment_status.csv      WMS shipment status (shpsts) -> order stage, open flag, which timestamp starts the stage age
    movement_classes.csv     RF activity / operation codes + location rules -> process step (Receive, Put-away, Pick, Load...) + colour;
                             Counts_As_Move = 0 rows = status / system events excluded from pallets moved
    time_bands.csv           time bands of the TTAT distribution and the time-in-stage heat maps
    field_guide.csv          every field of the diagnosis pages: meaning, unit, grouping / colour, source (page + measure tooltips)
  sql/new/*.sql            SQL templates of the replica feeds (Location Utilisation, User Activity, Data Health, Outbound TTA,
                           Open Trailers, Shipments, Pallets In Flow); {{BLOCKS}} are generated from config/*.csv at build
  sql/cdl/*.sql            CDL (Databricks SAP silver) feeds: SAP Production = FG goods receipts (MATDOC 101/102) per plant / day
  sql/extracted/*.m        tokenised M of every original table (review / diff)
  sql/reference/*.sql      independent KPI reference queries (written from the KPI definitions) used by reconcile_kpis.py
  tools/
    build_pbip.py            builds dist/ALL_SITES/WH Hypercare KPI.pbip (every site of site_config.csv) from source + config
                             gates: relationship types, best practice (model_gate.py C1-C6 / R1-R6: C4 visual type, C5 duplicate
                             field label, C6 reserved DAX variable name), tokens, query-rewrite rules
    validate_sql.py          renders every query per site and compiles + runs it on the live replica (--inc-check: incremental split)
    compare_replica_pbi.py   the SAME SQL as the model on each live replica vs the rows the open model holds per site x table
                             (MATCH / LIVE_DRIFT / M_TRANSFORM / FEATURE_OFF / DIFF) -> docs/REPLICA_VS_PBI.md + the query catalog
                             queries/replica/<SITE>/*.sql and queries/pbi/*.dax
    export_public.py         sanitized copy for a PUBLIC repo (placeholders for hosts, ids, people, paths; no data / .pbix)
    check_publish.py         publish gate: no secret, token, user access info, internal host, unknown id or binary (also the
                             repository's GitHub Action on every PR)
    site_config_check.py     live config gate per site (WH_ID, work orders, history, trailers, robot users, location patterns)
    run_full_tests.ps1       test chain with heartbeat: field audit -> visual replay per site / day -> filter replay ->
                             KPI reconciliation (reconcile_kpis.py) -> report intent (report_intent.py); docs/*.md results
    bd_reference_compare.py  original BD queries vs generated BD queries on the replica, row by row
    profile_refresh.ps1 / trace_partition.ps1   refresh time per table / engine trace
    watch_refresh.ps1        runs a refresh while querying the model like a visual every second - proves no "Error fetching data"
    make_packages.py         share zips (dist/_share: site files + Service variants) and the kit zip (no source data, no secrets)
    validate_cdl.py          runs the CDL queries per site (SAP Plan PO when Has_SAP_Plan = 1, sql/cdl/*.sql when Has_SAP_Prod = 1)
    data_gaps.py             docs/DATA_GAPS.md from the open model: today vs previous day per site, PrIME vs SAP production,
                             live 'where is it stuck' snapshot, replica coverage; exit 1 when a site has no previous-day activity
    allqueries_compare.py    the site's own PrIME reports (allqueries.xlsx) vs the kit on the same replica and day -> docs/ALLQUERIES_COMPARE.md
    apply_measures_live.py   push corrected measures from a fresh build into the model open in Desktop (DAX-only fixes, no reload)
    sync_partitions.py       push changed queries (sql/ + config/ -> partition M, per-site partitions too) into the open model and
                             dist/ALL_SITES, then refresh only those tables - e.g. `py tools/sync_partitions.py <PID> "Inventory"`
    sync_dax_reserved.py     asks the open engine which words it refuses as VAR names -> config/dax_reserved_words.txt (re-run after
                             a Desktop update)
    apply_inputs.py          Hypercare_KPI_Inputs.xlsx -> config (dry run by default; --apply writes; --confirm also removes sites)
    add_site.py              ONE command for a new site: apply -> profile -> site check -> validate SQL -> build -> docs/ONBOARDING_<SITE>.md
                             (--dry-run restores config; --server/--db tries a replica that is not in the file yet)
    profile_site.py          proposes every technical setting from the replica with evidence + confidence (--compare / --write);
                             rules in docs/PROFILER_REGRESSION.md, production templates in config/production_models.csv
    run_dax_batch.ps1        DAX batch runner of the tests (heartbeat, per-query timeout, reconnect, <out>.lock: one batch per output)
    replica_auth.py          Entra ID (MSAL device-code) token helper for replica / CDL / Power BI APIs - no secrets stored
    publish.py               publishes the model + report to a Power BI / Fabric workspace (Fabric REST) + binds each site's gateway
    auto_refresh.py / refresh_desktop.ps1   30-minute refresh (HOT tier Every_Minutes, Desktop + Service), see 'Refresh speed'
    probe_replica_schema.py  replica connection + schema probe
    make_handbook.py         ONE package: skills + queries for PrIME 2014 / 2022 + how to update + how to build -> dist/_share/PRIME_ELS_Hypercare_Handbook.html + .zip
    make_copilot_bundle.py   bundle for colleagues (GitHub Copilot): how to use + scripts + skills + site files -> zip; --upload = PRIME ELS SharePoint folder
    copilot_ai.py / apply_copilot_live.ps1   Copilot in Power BI: AI instructions (<= 10,000 chars) + key measure descriptions into every
                             build (culture linguistic metadata) and into the open .pbix (--live / --verify <PID>; snapshot_pbix --copilot)
    layout_preview.py        layout gate (overlap / off-page / clipped text) + wireframe PNG per page (runs in every build)
    m_tokenizer.py / dax_patch.py / measures_*.py / report_pages.py / report_diag.py / kpi_strips.py   generator modules
                             (kpi_strips.py = the KPI strip registry: every strip value shows "–" instead of "(Blank)")
  _src_oct/                BD Throughput (October) model as TMDL + report definition (no data) - input of build_pbip.py
  dist/ALL_SITES/          ready-to-open PBIP with every site (open the .pbip in Power BI Desktop)
  docs/FLOW.md             architecture + data flow
  theme/                   PRIME_ELS_Theme.json (built by build_theme.py from the public-domain snippets in theme/downloaded + palette.json), howto/*.png Home guides (tools/render_howto.py)
  skill/wh-hypercare-kpi/  Copilot skill (SKILL.md) to onboard / validate / publish a site
  skill/hypercare-site-setup/  Copilot skill: explore a replica, fill the site settings with evidence, thresholds, add / remove a site
```

## Two kinds of file

| File | Loads | Switch site | Needs | Use it for |
|---|---|---|---|---|
| `dist/<SITE>/WH Hypercare KPI - <SITE>.pbip` | **one site** | open the other site's file | read access to **that** replica only (no Excel / SharePoint / SAP-CDL source: `config/build_options.csv`) | **sharing**, publishing in anyone's workspace, fastest refresh |
| `dist/ALL_SITES/WH Hypercare KPI.pbip` | every configured site | Site slicer on any page (instant) | read access to **every** replica | hypercare lead who follows all sites |

In Import mode a page slicer can only filter data that is already loaded, so "load one site" = the site file. `py tools/build_pbip.py` builds both kinds from the same config.

## Share with colleagues (their own Power BI workspace)

1. Send the site's ready-made zip `dist/_share/WH Hypercare KPI - <SITE>.zip` (unzip, open the `.pbip`) - or open the `.pbip` and **File > Save as** a `.pbix` and send that one file.
2. The recipient needs read access to that replica (e.g. AD group `<ad-group>-<SITE>-READONLY`) and Power BI Desktop. In Desktop: File > Options > Security: untick *Require user approval for new native database queries*; **Refresh** -> **Microsoft account** -> Sign in -> Connect.
3. Publish: Home > **Publish** > choose *their* workspace. In the Service: semantic model > Settings > **Gateway and cloud connections** -> map the replica to `MI-<SITE>_REPLICA-PROD-FULL-PaaS-ADHOC` (the recipient must be a user of that connection; ask the replica owner), BD file also: Databricks (CDL) credential = OAuth2. Then **Scheduled refresh** (Pro: 8 / day; every 15 min needs Premium / PPU / Fabric capacity).
4. Thresholds typed on **Config & Health** are saved with the file / report; the kit config (`config/*.csv`) stays the source of the defaults.

## Use it

1. Open `dist/ALL_SITES/WH Hypercare KPI.pbip` in Power BI Desktop (File > Options > Security: untick *Require user approval for new native database queries*).
2. Sign in to the replicas when asked: choose **Microsoft account** -> *Sign in* -> **Connect** (once per replica server; Xiqing / Athens / Akashi each ask the first time), then **Refresh**.
   *Cannot sign in / tables stay empty?* File > Options and settings > **Data source settings** > Global permissions: every `<replica-server>` entry must say *Type: Organizational account*. A **Windows** credential fails with "Login failed. The login is from an untrusted domain and cannot be used with Integrated authentication" (Azure SQL accepts only Microsoft Entra) - *Clear Permissions* on that entry and refresh again. Refresh from the Desktop ribbon (not from a script) the first time, because only the ribbon can show the sign-in prompt.
3. Use the **filter bar** under the navy title strip (the same on every page, synced): **Site**, **Day** (blank = today's shift day, or the last day with activity) and **Shift** (blank = the whole shift day; a shift limits every day KPI, hourly chart, truck list and productivity to that shift's hours). The text on the right says which window every page shows (site time). Then read **Hypercare Cockpit** -> **Alerts** -> the section of the process that is red; check **Config & Health** first if the banner says checks failed.
4. Alert thresholds: type them on **Config & Health > 2. Alert threshold inputs** (Target / Warning at / Critical at for production pallets/h, inbound TTAT, outbound TTAT, location utilisation, user productivity). The boxes are synced to every page, override `Cfg_Threshold` immediately, and the *Source* column of table 3 shows `page input` vs `Cfg_Threshold`. Empty box (eraser) = the saved per-site value. Desktop: save the file to keep them; Service: they are kept with the report view (persistent filters) - *Reset to default* clears them. Permanent per-site values stay in `Cfg_Threshold` (no write-back without Fabric / Power Apps).

## Switch / add a site

* Switch: the **Site** slicer in the banner (every page, synced). The title becomes *<Site> PRIME ELS Dashboard*; a page the site does not run (e.g. SAP plan, Level A, RPM) shows *⚠ NOT USED AT <site>* in the banner (`Cfg_PageGuide[Requires]` vs the `Cfg_Site` flags). Health check #13 = exactly one site selected, #16 = the site's replica rows were loaded at the last refresh.
* Production model per site (`Cfg_Site`): **LTA take-away** sites (BD, Jakarta, Akashi) count a pallet when it leaves the LTA lane (`PROD_SRC_EXPR` / `PROD_SCOPE` / `PROD_ARRIVED_COND` / `PROD_LEFT_COND` use `{LOC_LTA}`); **work-order receipt** sites (Minhang, Xiqing) count the UID/RCV receipt from `wkohdr` and take the line from `wkohdr.prdlin`. Inbound TTAT key / receipt link: `TTAT_IN_SRC` / `TTAT_IN_RCPT_COND` (engine default = BD logic; Minhang groups per trailer and links receipts through `rcvtrk`; Athens links only receipt actions because pallets keep the truck id in EXPR for days).
* Add (at most 6 sites in the report): add a row to the **Sites** tab of `Hypercare_KPI_Inputs.xlsx`, then
  ```powershell
  py tools/apply_inputs.py               # dry run: what would change, any input problem
  py tools/add_site.py <SITE>            # apply -> profile replica -> site check -> validate every query -> build -> docs/ONBOARDING_<SITE>.md
  py tools/publish.py                    # -> My workspace (or --workspace "<name>")
  ```
  Confirm the LOW / CHECK settings of `docs/ONBOARDING_<SITE>.md` with the site (LTA lines of an LTA site: `line_map.csv`).
  Alerts follow the 'All sites' (BD) targets until the site gets its own rows in the *Alert targets* tab.
* Remove: delete the row in the Sites tab -> `py tools/apply_inputs.py --apply --confirm` -> `py tools/build_pbip.py` -> publish.
  Server / database are compiled into the site's partitions (static literals - the Service refuses dynamic sources), so a new site = CSV row + rebuild. SQL tokens (location patterns, zones, flags...) can still be edited in Desktop: *Transform data > Cfg_Site > Source (gear)* -> Refresh.

## Process diagnosis - where is it stuck, since when, what to do

Pages follow the site process left to right: **Hypercare Cockpit** (KPI tiles: report day, previous day, prior-days average,
target, prediction) -> **Process Flow** -> **Process Mining** -> **Trucks & TTAT** -> **Pallet Flow** -> **Inventory** ->
**Orders & Shipments** -> **People** -> Daily & Hourly / Alerts -> BD pages -> **Field Guide** -> **Ask Copilot**
(Production SAP vs PrIME and Predicted Plt/h are built only with build_options Include_SAP_CDL = 1).

* **Process Mining (order -> pick -> load -> truck)** - measured from the WMS event logs of the last `MOVEMENT_DAYS` days
  (`sql/new/Process Edges.sql`, refreshed every cycle): case = order (shipment created -> pick released -> picked & staged ->
  loaded -> truck dispatched, linked shipment -> stop -> car_move -> trailer as in the site PrIME report *Loaded Turn Time*),
  pallet (LPN through the process steps of `movement_classes.csv`) and truck (check-in -> (un)loading -> closed -> dispatched).
  Every hand-off is **Forward** (main sequence), **Storage** (put-away -> next step = stock waiting for demand, never called the
  bottleneck), **Back** (to an earlier step = rework / return), **Side** (a transfer / other move = extra handling: `Flow_Role`
  SIDE in `movement_classes.csv`) or **Open** ('Open: waiting after X' = orders / trucks stuck now). The first move after a pallet
  arrives counts as its put-away whatever code the site books it with (FL_XFR at Minhang / Athens), and median / p95 are taken
  over cases (a dummy LPN that bounced 1,390x between two steps at Minhang counts once). Two **Sankey** charts (Microsoft
  certified AppSource visual, registered in report.json) show the main flow (Forward + Storage + Open, distinct cases per link -
  no loops); Side and Back hand-offs stay in the **hand-off table**, which ranks every
  hand-off by total waiting time (cases x median) - the top Forward hand-off is the measured **bottleneck** (e.g. Jakarta 31-Oct:
  picked pallets wait a median 13.6 h for loading over 4,062 pallets; orders wait 12.8 h before pick release). The **truck Gantt**
  puts the completed trucks of the report shift day on one timeline (wait / unload-load / close-out) - before the first truck of
  the day completes it shows the last shift day with completed trucks, and the subtitle says which day (same rule on Trucks &
  TTAT). The flow alerts table shows the inbound / outbound alert rules with status, actual vs limit and target. Hand-offs below
  `PM_MIN_CASES` (30 cases) are hidden; the subtitles show the window and noise floor in numbers, or why a Sankey is empty ('not traceable at this site: shipments stay Ready', 'too few orders: 1 in the last 7 days').
* **Inventory** (every site, finished goods AND materials - `sql/new/Inventory.sql`): pallets by area, location class, WMS status
  and age band now (age = days since receipt, FIFO date when no receipt date), storage space occupied vs free by area, old stock
  (older than `STOCK_OLD_DAYS`) with the **likely cause and action** per location class (`config/stock_old_causes.csv` - e.g.
  Jakarta 31-Oct: 16,276 pallets still 'on trailer' in DSPCH, 7,184 of them older than 30 days = trailers never dispatched in
  WMS). *Why the inventory tab
  looked missing:* the original **Inv KPIs** page is the Level A view (only sites with `Has_LevelA = 1`; Akashi / Athens see
  'not used'), and its *Pallets Location* feed excludes finished goods (BD materials view), so a finished-goods DC (Jakarta 111
  rows, Xiqing 2) looked empty.
* **Alerts explain themselves:** every rule shows its status and *why it is an alert* in one column (actual vs the breached limit
  and the target, e.g. "🔴 CRITICAL: actual 219 min is above the critical limit 54 min (target <= 45 min) -> probable cause: ...")
  next to the target; clicking a rule fills the detail panel with *the numbers behind it* (e.g. inbound vs outbound: "in 1,234
  plt vs out 987 plt -> difference 247 plt"), how it is calculated, the prediction and its method, the diagnosis and the action
  (`config/kpi_explain.csv`). Speed rule behind this layout: every measure column of a table re-runs the KPI chain for each of the
  23 rules, so the control tower has ONE heavy column (34 s -> 5-10 s per site) and the cockpit "What to do now" one measure
  `Open Alert Text` (status + actual vs target + action: 13-32 s -> 4-6 s), all proven value-identical to the old columns.
* **Every chart shows its numbers** (data labels on all charts, stack totals on stacked charts); KPI strips show "–" for no
  value, never "(Blank)".

* **One process model** (`config/process_stages.csv` -> `Cfg_Stage`, one row per site x stage): 19 stages in 4 flows
  (1 Inbound, 2 Production, 3 Storage, 4 Outbound), each with object (truck / pallet / shipment), warning and critical age,
  action and owner. A stage whose token is `~NA~` or whose flag is 0 is N/A for the site (resolved at build).
* **Three live snapshot feeds** (HOT tier): `Open Trailers` (trailers checked in, not dispatched; stage from
  `trailer_status.csv`), `Pallets In Flow` (every pallet in a non-storage location; stage = first matching location rule;
  pallets on dispatched trailers are dropped), `Shipments` (status from `shipment_status.csv`, open flag, minutes in status).
  WMS status descriptions come from `dscmst`, so the codes need no translation table. The calculated table `Flow Items`
  unions them (Cfg_Site -> Cfg_Stage -> Flow Items).
* **Live vs stale:** an item past its stage warning / critical age is a live blockage (verdict, Stuck now list). An item older
  than `STALE_HOURS` (Cfg_Threshold, 72 h) is a **stale record** (ghost / forgotten WMS stock: pallets left on a closed
  trailer, end of line or staging for weeks). It is counted separately in purple with an inventory-accuracy action, so
  bad records never hide the real blockage.
* **Pallet movement by process step:** `User Activity[Move_Class]` from `movement_classes.csv` (activity / operation codes +
  location rules; status events excluded) - stacked by hour and by day with one fixed colour per step on every site.
* **Colour segmentation in one place:** `theme/palette.json` -> `diagnosis` (status colours CRITICAL / WARNING / STALE / OK /
  CLEAR / N/A, heat-map fills, inbound / outbound, SAP / PrIME, truck-time segments); movement-step colours in
  `movement_classes.csv`. Heat maps colour a cell by the stage limits (green below warning, amber from warning, red from
  critical, purple = stale), the People heat map by the USER_PROD limits.
* **Default report day:** no day picked = today's shift day once it has activity, otherwise the last shift day with activity
  (the banner says "no activity yet today - showing the last day with activity"). Every KPI strip shows the previous day
  next to the report day; the cockpit tiles add the prior-days average.
* **Truck time decomposition:** wait (check-in -> first scan), work (unload / load), close-out (rest of the TTAT) per truck of
  the report day, a TTAT distribution per band and trucks completed / TTAT by hour. Every truck visual of the page uses the
  KPI basis - a truck belongs to the shift day (and hour) it was completed: inbound at dispatch, outbound at close - so a truck
  that waited overnight shows on the day its TTAT is reported. Arrivals by check-in hour are on the Daily & Hourly Report.
* **SAP vs PrIME production** (`sql/cdl/SAP Production.sql`, CDL `silver_sap_a6p.matdoc` 101/102 for FERT materials of
  `Cfg_Site.SAP_Plant`): pallets = quantity / MARM `SAP_PALLET_UOM` factor, otherwise one GR line = one pallet (HU plants).
  Validated on Binh Duong: GR lines 1,082 / 568 / 45 / 305 vs PrIME produced pallets 1,090 / 568 / 45 / 304. The page says
  in words why PrIME production is empty or low (texts in `rca_rules.csv` `SAP_*`).
* **Data gaps:** `py tools/data_gaps.py` writes `docs/DATA_GAPS.md` (today vs previous day per site, the previous-day rule,
  PrIME vs SAP, live snapshot, replica coverage). `py tools/allqueries_compare.py <SITE>` compares the site's own PrIME
  reports (allqueries.xlsx) with the kit on the same replica and day (`docs/ALLQUERIES_COMPARE.md`).
* **New replica server = one sign-in in Desktop.** The first refresh of a server Desktop never connected to waits for a
  credential that a scripted refresh cannot show. `refresh_desktop.ps1` detects it (no data-source activity for `-StallSec`,
  default 240 s), stops with `STALLED: <site> ... no stored credential for <server>` and exit code 4. Fix once: *Transform data >
  Data source settings > the server > Edit Permissions > Edit... > Microsoft account > Sign in > Save*.

## Thresholds, RCA and verdicts (no hard-coded values)

* Every number used by a KPI, alert, RCA rule, prediction or model constant (sync cap, bucket hours, horizons, look-back days) is a row in `Cfg_Threshold`.
* Every root-cause / action / verdict / narrative sentence is a row in `Cfg_RCA` (`{idle}`, `{free_short}`, `{queue}`... are filled by DAX).
* Every site value (wh_id, location patterns, zones, areas, shift hours, CTMZ line, end-of-line locations, production model, RPM files, CDL connection) is a column of `Cfg_Site`; engine differences are in `Cfg_Engine`.
* Every numeric value carries its unit: KPI texts append `Cfg_Threshold[Unit]`, measures use the format string from `config/measure_units.csv` (e.g. `23.2 plt/h`, `104 min`) and every visible numeric column gets one from `config/column_units.csv` (e.g. `TTAT (Minutes)` -> `45 min`, `Hour_Of_Day` -> `14:00`, technical sort keys hidden). The build lists any numeric column without a rule.
* `tools/build_pbip.py` fails the build if any BD literal (VN07, F0%A, 9772, binhduong, 2026-07..., sto_zone on 2014...) is left in a query, or a DAX patch does not apply.

## Excel -> Power BI mapping (nothing duplicated)

| Excel (Macro BD Report v5) | Power BI |
|---|---|
| Query11 LTA pallets / line / hour | `Produced Pallet` (already in BD pbix) |
| Query12 inbound TTAT | `TTAT` (Inbound) |
| Query13 outbound loading | `Outbound TTA` (new, also fixes the broken 'Outbound TTA' visuals of the BD pbix) |
| Query1/7/8/10 Level A spots | `Level A Available Pallet Spot` + `Location Utilisation` |
| Query2 bin-A clean-up | `Pallet cleaned up from bin A` |
| Query3 outbound allocation | `Outbound Pallet from Inv` |
| Query4 LTA -> Level A | `Pallet From LTA To Level A` |
| Query5 Level A idle stock | `Pallet in Level A not active shipment` (bin-to-bin list on Alerts & RCA) |
| Query6 HOFF / PROBLEM / FLOOR A | `Pallet From HOFFIN` + `Level A Occupied Pallet` |
| Query9 LTA queue SHORT / TALL | `Pallet from LTA to short/tall location` |
| CONFIG (20 thresholds) | `Cfg_Threshold` |
| ALERTS (17 rules) | **Alerts** page (`Cfg_AlertRule` x `Cfg_Threshold`) |
| LTA_MONITOR / LTA_RCA | not shown (LTA takeaway is BD-specific) - measures kept in the model (`Line Status`, `Line Root Cause`) for later |
| HOURLY_ALERT | **Daily & Hourly Report** page (right) - generic: RF pallets moved / users / trucks / TTAT per hour vs baseline + verdict |
| FLOW_ANALYTICS (80/20 rules, bin-to-bin) | `KPI Store A Split`, `KPI Pick A Split`, `KPI Idle A`, bin-to-bin table |
| VALIDATION | `Cfg_HealthCheck` + Config & Health page |
| DAILY_REPORT | **Daily & Hourly Report** page (left) + Hypercare Cockpit (tiles + verdict + outlook + what-to-do-now table) |
| REFRESH_LOG / INDEX | Home page (tab index) + Data freshness cards |

Removed because they duplicated other pages: the empty hidden *Page 1*, *Duplicate of Inv Status*, the hard-coded market legend textbox (now the `Cfg_Market` legend on *Predicted Plt/h*), the original Landing content (Home now = 2 how-to guides), the separate Config / Health pages (merged) and the LTA line-RCA / bin-to-bin tables (BD-specific).

Page order follows the site process (config/page_guide.csv **Section**): **Overview** (Home, Cockpit, Alerts, Daily & Hourly, Process Flow) - **Inbound & Trucks** (Trucks & TTAT, TTAT Details) - **Production & Lines** (SAP vs PrIME, Produced / Predicted Plt/h, Line RCA & Shifts, Pallet Synchronization, Short PO, RPM, Activity Tracking) - **Storage & Inventory** (Pallet Flow, Inventory, Inv KPIs) - **Outbound & Orders** (Orders & Shipments, Process Mining) - **People** (User Productivity: by hour, per user, user x hour) - **Admin** (Config & Health, Field Guide). Every page: navy strip (Home button, '<Site> PRIME ELS Dashboard', section + page name, refresh info) + filter bar + KPIs on top, then where -> why -> detail (Z-pattern); every item has one home (no duplicated visuals between pages: truck Gantt and truck list on Trucks & TTAT, shipment list on Orders & Shipments, pallet list on Process Flow, alert list on Alerts); production pages and the Cockpit say 'No production planned' when the site has no work-order / SAP plan; long pages (Trucks & TTAT, User Productivity) scroll (Fit to width) so the Gantt and lists get full height. Theme: `theme/PRIME_ELS_Theme.json`.

## Inputs - what to edit (recommendation)

* **One file:** `Hypercare_KPI_Inputs.xlsx` in the PRIME ELS SharePoint folder (Data Projects/PRIME ELS/Hypercare KPI) (Read me / Sites / Alert targets tabs, drop-downs).
  * **Alert targets are built in** (`config/build_options.csv` Embed_Inputs = 1, default): the build copies the *Alert targets* tab into
    the model, so a shared file needs nothing but its replica; change a target = edit the workbook + rebuild. Embed_Inputs = 0 = the
    model reads the tab at every refresh instead (Desktop: the OneDrive-synced copy, Service: SharePoint, OAuth2 once). Priority: file
    site row > config site row > file 'All sites' row > BD default. Typos / unknown KPI /
    warning beyond critical appear in *Config & Health > Input issues* and the BD default is kept - nothing fails silently.
  * **Sites need a rebuild** (the Service refuses dynamic sources): Sites tab -> `py tools/add_site.py <SITE>` (new) or
    `py tools/apply_inputs.py --apply [--confirm]` (changes / removal) -> build -> publish.
* **Technical settings** (~55 location patterns, areas, flags) are not typed by people: `tools/profile_site.py` proposes them from
  the replica with evidence; they live in `config/site_config.csv` (versioned, reviewable).
* **Try a threshold without saving:** Config & Health > *Alert threshold inputs* (report-time override, NOT saved).

## How to check empty values per site

1. **In the report:** Config & Health > *4. Feed completeness* - rows of every replica source in the last 24 h for **all sites
   side by side** (red = empty: the pages using that source are empty for that site), plus the 17 daily health checks of the
   selected site. Every page banner says when a page is not used at the site or when the day has no activity.
2. **Every visual x site x day:** `py tools/visual_replay.py <PID> --days 1` (each visual's own DAX query; ERROR / EMPTY /
   NO VALUE per site) then `py tools/report_intent.py <PID>` - an EMPTY is accepted only when the data proves it (no rows that day,
   or a rule of `config/visual_expectations.csv` such as `NOT [Orders Flow Used]`), otherwise it fails (exit 1).
3. **Column level:** `py tools/audit_fields.py` (empty / constant / out-of-range columns, `config/field_expectations.csv`).
4. **Previous day / source comparison:** `py tools/data_gaps.py` (every site must show trucks / moves / production on the
   previous day) and `py tools/allqueries_compare.py <SITE>` (site PrIME reports vs the kit).

## Refresh speed and automatic refresh every 30 minutes

**Why it was slow and what changed (Binh Duong, measured on the replica):**

| Item | Before | After | Fix |
|---|---|---|---|
| Planned PO RPM Breakdown | 208 s | 1.7 s | `OPTION (HASH JOIN)` - the original final join ran as nested loops over the CTEs |
| WorkLine Activities | 52 s, 116k rows since go-live | ~20-40 s, last `DETAIL_DAYS` (14) days | `Cfg_Site.DETAIL_DAYS` |
| Pallets Movement | all history | last `MOVEMENT_DAYS` (7) days | `Cfg_Site.MOVEMENT_DAYS` |
| 42 hidden auto date/time tables | rebuilt every refresh | removed | no visual used them (auto date/time OFF) |
| Full model refresh in Desktop | several minutes, memory errors | **38 s** | parallelism capped at 3 (`refresh_desktop.ps1 -MaxParallel`) |
| 15-minute refresh (17 live tables) | - | **23 s** | `config/refresh_policy.csv` HOT tier |

**Automatic refresh** - `config/refresh_policy.csv` decides what refreshes when (data-driven: a tier runs when its
`Every_Minutes` divides the 15-minute slot of the day):

| Tier | Every | Tables |
|---|---|---|
| HOT | 30 min | KPIs, TTAT, user activity, inventory / space, process snapshots + process mining, data health - **ALL_SITES incremental cycle 216 s** (31-Oct 14:30, 22 tables: BD 47 s, Minhang 21, Jakarta 35, Akashi 39, Xiqing 41, Athens 27 + 4 s calc; 342 s in the morning when the replicas were busier) |
| WARM | 60 min | movements, work-line activity, replica plans |
| PLAN | 240 min | SAP plan + shipping market from Databricks (CDL) |
| COLD | daily 05:00 | full model (config tables, calendars, incremental history) - 9.5-11 min (572 s on 31-Oct 14:20) |

*Why 30 minutes:* a 15-minute cycle kept Desktop refreshing 40-70 % of the time on this laptop (342 s every 15 min, more on the
hour with WARM); 30 min keeps the data fresh enough for hypercare and leaves the machine responsive. The banner of every page shows
*refreshed hh:nn · next ≈ hh:nn · now hh:nn (site time)* - next = last + the HOT interval of `config/refresh_policy.csv`, and
"⚠ refresh overdue" when a cycle was missed. `py tools/auto_refresh.py --install` creates the task with the same interval, repeating on
the grid from 00:00 (every 30 min -> :00 / :30, so :00 runs also do WARM and every 4 h PLAN); a run off the grid refreshes HOT.

**Incremental refresh** (measured 30-Oct, details in [docs/REFRESH_PROFILE.md](docs/REFRESH_PROFILE.md)):
* Desktop / site files: the 5 append-only tables in `config/incremental_policy.csv` have two partitions per site -
  `'<table> - <SITE>'` (history, before site-local midnight of yesterday) and `'<table> - <SITE> - recent'`. Every cycle refreshes
  only *recent*; *history* is added automatically when the site's day rolls over, and in the daily full refresh.
  Lossless: `py tools/validate_sql.py --inc-check` proves history + recent = full on every replica.
* Power BI Service: `py tools/build_pbip.py <SITE> --service` -> `dist/_service/<SITE>` with real refresh policies
  (`RangeStart` / `RangeEnd`) - publish that variant once the gateway connections are shared with you.
* Result: BD site file 15-min cycle 45-60 s -> **30 s**; hourly cycle ~120 s -> 34 s; ALL_SITES full refresh 951 s -> 451 s.
* `tools/profile_refresh.ps1 -Site <SITE>` (time per table) and `tools/trace_partition.ps1` (engine trace) show where time goes.
* Visuals stay usable during a refresh: each site's data **and** the recalculation of calculated tables / columns /
  relationships commit in ONE transaction (before 31-Oct the data was committed first and every visual showed
  "Error fetching data" / "calculated objects need to be refreshed" until the end of the cycle). Proof: `tools/watch_refresh.ps1`.

* `py tools/auto_refresh.py --install` creates the Windows scheduled task **PRIME ELS Hypercare refresh** (every HOT interval = 30 min) - it refreshes the open `WH Hypercare KPI` model in Power BI Desktop (local engine, all site partitions) and sends an enhanced refresh of the same tables to the published model. `--uninstall` removes it; log in `tools/_auto_refresh.log` (each cycle logs startup / connect / per-site / calculate timings).
* Desktop: leave the .pbip open (e.g. on the second screen) - visuals update by themselves after each cycle. **A locked or sleeping laptop stops the Desktop refresh**: asleep = the task does not run (30-Oct 19:50-21:05); locked = the task runs, but as soon as a replica sign-in token must be renewed (Windows Hello / passwordless) the query cannot connect (31-Oct 16:05, screen locked at 16:02 - Athens). The watchdog stops the cycle after 4 min with 'STALLED ... WORKSTATION IS LOCKED' in `tools/_auto_refresh.log`; the first cycle after unlocking refreshes again. Keep the laptop unlocked during hypercare hours, or use the Service (gateway) for unattended refresh.
* Service: the API refresh needs the replica gateway connection (see below); until then the task logs "waiting for gateway access" and retries once a day. A daily safety-net schedule (8 slots, the Pro limit) is set on every model. **15-minute refresh in the Service needs a Premium / PPU / Fabric workspace** (shared capacity = 8 refreshes / day).

## Power BI Service refresh (verified 2026-10-29)

One model + report (all sites) is published in **My workspace** (`dist/ALL_SITES/_published.json` has the links). The earlier per-site items (`WH Hypercare KPI - <SITE>`) are superseded and can be deleted.

| Source | What the Service needs |
|---|---|
| Data replica (all sites) | The replica managed instances are **private** - a cloud connection times out (verified). Refresh must go through the gateway connection in `Cfg_Site.Gateway_Connection` (`MI-<SITE>_REPLICA-PROD-FULL-PaaS-ADHOC`, Jakarta non-prod `MI-JAKARTA-DEV-FULL-PaaS-ADHOC`). Ask the replica owner to add you as a **user** of that connection, then re-run `py tools/publish.py` - it binds every site whose connection you can see. |
| CDL Databricks (SAP plan, `Has_SAP_Plan = 1`) | cloud connection, OAuth2 (verified OK with the owner's CDL warehouse `adb-3125606391614073 / WH`). In the dataset settings enable *Allow cloud data sources to refresh through the gateway* when the replica uses a gateway. |
| RPM master files (`Has_RPM_Master = 1`) | static file paths from `Cfg_Site.RPM_*` compiled into the site's partition; the files must be on SharePoint or behind the gateway. |

Sources of features that are OFF for a site (`Has_SAP_Plan = 0`, `Has_RPM_Master = 0`) are left out of that site's partitions at build time, so the Service never asks for those credentials.

Desktop: the first refresh of a new replica server asks once for a sign-in (Microsoft account) - after that the refresh runs unattended.