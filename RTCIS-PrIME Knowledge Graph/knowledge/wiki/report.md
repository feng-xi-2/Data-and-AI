---
title: Tabbed HTML report (template and build)
type: tool
status: verified
sources: [templates/report_template.html]
evidence: [results/compare.json, results/expert_rules.json]
updated: 2026-10-20
---
# Tabbed HTML report

`python tools/build_report.py` → `output/RTCIS_PrIME_RPM_Tabbed_Report.html`. Never hand-edit the output.

**Template** `templates/report_template.html` — placeholders `{{GENERATED}}`, `{{TABS}}`, `{{INTRO}}`, `{{PANES}}`;
CSS for badges (`b-ok`, `b-zero`, `b-bad`, `b-na`), mapping-tag chips (`k-map`, `k-inf`, `k-eli`, `k-par`, `k-dev`),
copy buttons on SQL blocks, vertical tab bar.

**Intro tab:** summary of all queries (rows per engine, column contract, grade, open points), expert-rule matrix,
connections used, grade legend.

**One tab per query, six steps:** (1) what the query does (`WHAT`), open points (`STATUS`); (2) before/after — original
as supplied, RTCIS T-SQL baseline, PrIME conversion, mapping tags from the SQL header; (3) expert rules for this
query; (4) results on all three engines (rows, columns, seconds, params, run time); (5) RTCIS vs PrIME on the same
pallets/items/locations with difference examples; (6) first 5 sample rows per engine.

**Self-checks** (build fails loudly): pane ids = INTRO + every query; one tab per query; 3 copy blocks per query; no
unreplaced `{{`; all six step headings present in each pane.

To reuse for another query set: change `ENGINES`, `WHAT`, `STATUS` in `build_report.py` and the originals folder
(`ORIGINALS`).
