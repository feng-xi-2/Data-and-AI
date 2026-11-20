---
name: hypercare-site-setup
description: 'Add, explore, configure or remove a warehouse site in the PRIME ELS Hypercare KPI Power BI (PrIME 2014 or PrIME 2022 data replica). Use when: onboarding a new site, filling the Sites tab of Hypercare_KPI_Inputs.xlsx, profiling a replica to find WH_ID / Level A / LTA / hand-off / RF area / door / FG part settings, deciding the production model (work-order receipt vs LTA take-away), setting or reviewing alert thresholds (BD defaults for every site), removing a site (max 6), or explaining why a site shows empty / N/A visuals. Trigger phrases: add new site, configure site, onboard site, site settings, profile replica, which wh_id, alert threshold for site, remove site, site shows no data, add_site.'
argument-hint: 'SITE code, e.g. MINHANG, and optionally the replica server / database'
---

# Hypercare KPI – site setup (explore → configure → verify)

Kit root: the folder with `config/`, `tools/`, `dist/` (open it as the VS Code workspace). Run tools from the kit root with `py`.
The one inputs file is `Hypercare_KPI_Inputs.xlsx` in the PRIME ELS SharePoint folder `Data Projects/PRIME ELS/Hypercare KPI` (synced: `%OneDriveCommercial%\Shortcuts\OSS warehousing data and GenAI - PRIME ELS\Hypercare KPI\`). PRIME ELS is not PRISM 2 ELS - never use the PRISM 2 folders. Its path is in `config/inputs_source.csv`.

## Principles (do not break)
- **Evidence, not guesses:** every technical setting comes from the site's own replica (`tools/profile_site.py`), shown with its evidence and confidence. Weak evidence means the feature is OFF (`~NA~`); the report then shows "not configured", never a wrong number.
- **No site-specific code:** fix rules in config, queries or tools so that they work for every site. Never patch one visual.
- **Alerts:** a site without its own rows in the **Alert targets** tab uses the **All sites** rows, which are the BD thresholds.
- **At most 6 sites** in the Sites tab (`Max_Sites` in `config/inputs_source.csv`). Removing a site needs `--confirm`.
- Print a heartbeat at least every 30 s on long work; stop and report on any failure.

## Procedure – add a site
1. **Sites tab:** add one row to the Sites tab: SiteCode, SiteName, Region, WMS_Version, ReplicaServer, ReplicaDatabase, UTC_Offset_h, the shift start hours, Hypercare_Start, SAP_Plant, Has_Production, Is_Default.
   - WH_ID may be left blank; the profiler picks the busiest warehouse.
   - Replica naming: `<replica-server><site>prod.<id>.database.windows.net`; the database is `<SITE>` or `<SITE>_REPLICA`.
2. **Preview:** run `py tools/apply_inputs.py`. This is a dry run that lists the changes and any problems.
3. **Add:** run `py tools/add_site.py <CODE>`, which does everything:
   - apply → profile (`--write`) → `site_config_check` → `validate_sql` (every query on the replica) → build the site file, ALL_SITES and the Service file;
   - writes `docs/ONBOARDING_<CODE>.md`.
   - To try it first: `py tools/add_site.py <CODE> --dry-run` (the config is restored afterwards).
   - For a replica that is not in the file yet: `--server S --db D --utc 8 --dry-run`.
4. **Review** `docs/ONBOARDING_<CODE>.md`:
   - confirm every LOW / CHECK setting with the site (see [settings reference](./references/settings.md));
   - edit `config/site_config.csv` and re-run `py tools/add_site.py <CODE>`.
5. **Verify:**
   - open `dist/<CODE>/WH Hypercare KPI - <CODE>.pbip` in Power BI Desktop → sign in → Refresh;
   - run `powershell -File tools/run_full_tests.ps1 -Sites <CODE>` (field audit, visual replay, filter replay, reconciliation, report intent). Every test must show 0 errors; EMPTY or ZERO flags need a reason in `config/field_expectations.csv` / `visual_expectations.csv`.
6. **Publish:** `py tools/publish.py`. The Service reads the inputs file from SharePoint; sign in once with OAuth2.

## Procedure – alert thresholds
- Change targets in the **Alert targets** tab.
  - Site = `All sites` sets the default for every site; Site = `<CODE>` overrides it for one site.
  - Direction: Higher, Lower or Band. % values are entered as 0.85.
- The report reads the file at every refresh. The Config & Health page shows the targets in use and an **Input issues** table (typos, unknown KPI or site, warning beyond critical).
- The "try a value" boxes on Config & Health are for testing only and are not saved.

## Procedure – remove a site
1. Delete the site's row in the Sites tab.
2. Run `py tools/apply_inputs.py --apply --confirm`.
3. Rebuild with `py tools/build_pbip.py`, then `py tools/build_pbip.py <CODE> --service`, and publish.

## Explore a replica by hand (when the profiler is not enough)
- Connect: `from probe_replica_schema import connect; connect(server, db)` (Entra token, read-only).
  - PrIME 2014 uses schema `prodwms`; PrIME 2022 uses `dbo`.
- Always bound scans: `trndte >= DATEADD(day, -14, (SELECT MAX(trndte) FROM <S>.dlytrn))`, `TOP n`, a 110 s timeout.
- **Check the history first:** `MIN` / `MAX(trndte)` per `wh_id`.
  - Under 72 h means the site is not live (for example an inventory load with `IDNTFY` only). Keep the peer defaults and re-profile after go-live.
- Queries, the meaning of each setting and the probe SQL: [settings reference](./references/settings.md).

## Diagnose "empty / N/A" for a site
1. `py tools/profile_site.py <CODE> --compare`: lists the settings whose replica evidence disagrees with the config, with that evidence.
2. `py tools/site_config_check.py <CODE>` writes `docs/SITE_CONFIG_CHECK.md`: freshness, WH scope, robot users, history depth.
3. `py tools/validate_sql.py <CODE>`: the row count of each query on the replica. 0 rows with the feature ON means a setting is wrong or the site has no such activity.
4. Look up past findings in `docs/PROFILER_REGRESSION.md`.
