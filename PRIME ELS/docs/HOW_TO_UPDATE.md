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
