# How the report is built (generator pipeline)

The Power BI file is **generated**: nothing in `dist/` is edited by hand. One command turns the config, SQL and DAX sources into a
PBIP (Power BI Project: TMDL semantic model + PBIR report) that opens in Power BI Desktop and publishes to the Service.

```
config/*.csv  (sites, engines, thresholds, pages, stages, colours, units ...)      Hypercare_KPI_Inputs.xlsx (SharePoint, read live)
sql/extracted/*.m  (BD original feeds, tokenized)        sql/new/*.sql  (new feeds)
tools/measures_*.py  (all KPI measures, DAX)              tools/report_pages.py + report_diag.py (pages, visuals, layout)
_src_oct/  (BD Throughput source model + report, no data)
                │
                ▼   py tools/build_pbip.py
    1. copy the BD source model; replace BD constants by Cfg_* lookups (tools/dax_patch.py)
    2. one partition per site and table (server / database baked per site = Service-safe); tokens resolved at refresh (fnSiteSql)
    3. config tables (Cfg_*), calculated tables, Shift_No columns, relationships, 600+ measures with units and formats
    4. pages: copy the BD pages under the standard header, add the generated pages, tab order by process section
    5. gates (build stops on any finding): DAX syntax / reserved words, relationship columns + data types, units, page guide,
       Home buttons on every page, no config names in titles, layout (overlap / off-page / clipped text), best-practice rules
                │
                ▼
dist/ALL_SITES/WH Hypercare KPI.pbip       every site, Site slicer          (hypercare lead)
dist/<SITE>/WH Hypercare KPI - <SITE>.pbip one site, smaller, faster         (share / publish per site)
dist/_service/<SITE>/                      Service variant with incremental refresh policies
```

## Prerequisites (once per PC)

* Power BI Desktop (current version), Python 3.11+ (`py`), packages: `pip install pyodbc msal openpyxl pillow markdown`
* ODBC Driver 18 for SQL Server; read access to the replicas (AD group `<ad-group>-<SITE>-READONLY`); Entra sign-in (no passwords stored)
* Optional: Databricks (CDL) access for the SAP plan / production feeds - only when `config/build_options.csv` Include_SAP_CDL = 1. With 0 (default) the SAP tables, measures and the pages Production SAP vs PrIME / Predicted Plt/h are left out of the file entirely
  (default 0: every built file reads its data replica only, the alert targets are copied in at build - Embed_Inputs = 1)

## Commands

| Step | Command | Output / check |
|---|---|---|
| Validate every query on the replica | `py tools/validate_sql.py <SITE ...>` | compile + run per table and site, row counts, `tools/_validate_<SITE>.json` |
| Check site config against the replica | `py tools/site_config_check.py <SITE>` | `docs/SITE_CONFIG_CHECK.md` |
| Profile a new replica | `py tools/profile_site.py <SITE> --compare` | settings + evidence + confidence, `docs/PROFILER_REGRESSION.md` |
| Build everything | `py tools/build_pbip.py` | `dist/ALL_SITES` + site files, `docs/MODEL_CHECK.md`, `docs/LAYOUT_CHECK.md` |
| Build only some site files | `py tools/build_pbip.py JAKARTA MINHANG` | `dist/<SITE>` |
| Build the Service variant | `py tools/build_pbip.py <SITE> --service` | `dist/_service/<SITE>` |
| Open in Desktop | `py tools/open_model.py "<path>.pbip"` | prints `READY <pid>` |
| Refresh in Desktop | `powershell -File tools\refresh_desktop.ps1 -Tables "*"` | per site / partition, heartbeat, stall detection |
| Full test chain | `powershell -File tools\run_full_tests.ps1 -SkipOpen -Sites "A,B"` | field audit, visual replay, filter replay, reconciliation, report intent |
| Layout wireframes | `py tools/layout_preview.py` | one PNG per page in `_uitest/layout`, `docs/LAYOUT_CHECK.md` |
| Publish | `py tools/publish.py [--workspace "<name>"]` | model + report in the workspace, gateway binding |
| Automatic refresh | `py tools/auto_refresh.py --install` | scheduled task, tiers from `config/refresh_policy.csv` |
| Share packages | `py tools/make_packages.py` | `dist/_share/*.zip`, `PRIME_ELS_Hypercare_KPI_Kit.zip` |
| This handbook | `py tools/make_handbook.py` | `dist/_share/PRIME_ELS_Hypercare_Handbook.html` + `.zip` |

## PrIME 2014 vs 2022 - how one query serves both

| Difference | PrIME 2014 | PrIME 2022 | Where |
|---|---|---|---|
| Schema | `prodwms` | `dbo` | token `{S}` (`config/engine_profiles.csv`) |
| Storage zones | location area (`arecod`) | `sto_zone` table (`sto_zone_id`) | `{ZONE_COL}`, `{STO_ZONE_JOIN}` |
| Location types | not used | `loc_typ` join | `{LOC_TYP_JOIN}` |
| Inbound truck -> receipt | `rcvtrk` link | `rcvtrk` link | `{TTAT_IN_SRC}`, `{TTAT_IN_RCPT_COND}` (site override possible, e.g. Athens ASN actions) |
| Production model | per site, not per engine: LTA take-away or work-order receipt | | `config/production_models.csv` templates -> `PROD_*` site tokens |

The handbook's *Queries* section lists every query with the engine tokens already resolved for 2014 and for 2022; the remaining
`{TOKENS}` are site settings (Token reference). The *Example* files show one fully rendered site per engine.

## Changing the generator safely

1. Make the change in the source (config / sql / tools) - generically, for every site.
2. `py tools/build_pbip.py <ONE SITE>` first: the gates catch DAX, relationship and layout problems in about a minute.
3. Push DAX-only changes into an open model without a refresh: `py tools/apply_measures_live.py <pid> "Measure A|Measure B" --tmdl dist/<SITE>/.../_KPI.tmdl`.
4. Push a changed query: `py tools/sync_partitions.py <pid> "<Table>"` then refresh that table.
5. Rebuild all + run the test chain before publishing; record the result in `docs/VALIDATION.md`.
