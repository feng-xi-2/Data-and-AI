---
title: Tools catalog
type: tool
status: verified
sources: []
evidence: [results/summary.csv]
updated: 2026-10-20
---
# Tools (`tools/`)

All read-only against databases. Run from `tools/` (they resolve paths from the folder root).

| Tool | Purpose | Writes |
|---|---|---|
| `db_session.py` | MSAL device-code auth, token cache, ODBC Driver 18 connection | `tools/.access_token.json`, `.msal_cache.json` (git-ignored) |
| `sites.py` | Site keys → server/database; `connect(key)` | — |
| `discover.py` | `python discover.py PRIME_DE08 invlod invdtl` — columns via `SELECT TOP 0 *` (works through synonyms) | stdout |
| `run_queries.py` | `python run_queries.py <SITE> <rtcis_tsql\|prime> [Rnn]` — binds `queries/params.json`, refuses DML/EXEC, -155 converter | `results/<SITE>__<folder>__<Rnn>.json`, `summary.csv` |
| `compare.py` | `python compare.py [Rnn]` — column contract + value agreement on matched keys (`KEYS` dict per query) | `results/compare.json/.csv` |
| `map_inventory_fields.py` | Same-pallet field agreement RTCIS vs PrIME (the mapping evidence) | `results/map_inventory_fields.json` |
| `map_subsit_building.py`, `probe_open_mappings*.py`, `probe_facts3.py`, `probe_r17_r01.py` | Probes used to measure specific mappings — copy the pattern for new ones | stdout |
| `probe_casqty_height.py` | Same-pallet CASQTY classes (integer / FLOOR / snapshot) and RTCIS u_height vs PrIME HGT per level and unit scale | `results/probe_casqty_height.json` |
| `probe_sap_pallet_height.py` | RTCIS packaging heights vs SAP marm (CDL f6p via `timbr_ontology_ext/dbsql.py`, Databricks auth) | `results/probe_sap_pallet_height.json` |
| `audit_expert_rules.py` | RUIZ.RS OBS1–8 + WHT/FAN/LOC/VIEW; exit 1 on FAIL | `results/expert_rules.json` |
| `field_check.py` | Field mapping + empty-field rule E1–E3 per output column (sources parsed from both SQLs, fill % per engine, agreement excl. both-blank, sample-format check); reasons from `queries/field_notes.json`; exit 1 if undocumented | `results/field_check.json` |
| `probe_empty_fields.py`, `probe_field_gaps.py` | Read-only probes behind the field notes (PO, trailer door, count dates, zones, serflg, units, ctrl_date) | `results/probe_*.json` |
| `build_report.py` | Tabbed HTML report from `raw/queries/rpm`, `queries/`, `results/`, `templates/report_template.html`; self-checking | `output/RTCIS_PrIME_RPM_Tabbed_Report.html` |
| `gen_query_pages.py` | Refresh the generated evidence block of `wiki/queries/Rnn.md` | `wiki/queries/R*.md` (gen block only) |
| `wiki_lint.py` | Wiki health: links, orphans, index coverage, frontmatter, log format, raw immutability; `--seal`, `--selftest` | `raw/MANIFEST.json` (only with `--seal`) |

To add a site: one entry in `sites.py`. To add a query: original into `raw/queries/…` (seal), baseline + conversion
into `queries/`, params into `params.json`, a key in `compare.py` `KEYS`, `WHAT`/`STATUS` in `build_report.py`.
Report details: [report](report.md).
