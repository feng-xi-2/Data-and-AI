---
title: "Source: original queries and samples"
type: source
status: documented
sources: [raw/queries/rpm/, raw/queries/euskirchen-label/, raw/queries/prime2022-samples/, raw/euskirchen/]
evidence: []
updated: 2026-10-20
---
# Source: queries

| Folder | Content | Converted? |
|---|---|---|
| `raw/queries/rpm/` | 17 RPM originals R01–R17 (SSRS / `SYS_get_RTCIS` / `SYS_get_DAS` / OpenQuery / `RPM_System`) | yes → `queries/prime/`, [rpm-status](../queries/rpm-status.md) |
| `raw/queries/euskirchen-label/` | 14 Oracle label-printing originals (GetAllData, GetDefaultData, GetCustCenterData, GetEdeka*, …) | yes → `raw/euskirchen/*.sql`, [euskirchen-label-set](../queries/euskirchen-label-set.md) |
| `raw/euskirchen/` | Delivered PrIME SQL for the label set + CONVERSION_REPORT.md + mapping CSVs | — (deliverables as of 2026-10-14) |
| `raw/queries/prime2022-samples/` | 16 house PrIME 2022 queries (outbound item delivery, inbound expected, inventory details, staging lanes, % loaded, MAESTRO RFC209/274, dscmst order types / status progressions…) | reference for **house style** and join paths |

Larger corpora not copied (too big / machine-specific): `allqueries.xlsx` (2,228 site PrIME queries, 68 sites — the
house-convention corpus), `Sample Data RTCIS PRIME/RTCIS Query`, `SQL Diamond`, `PRIME 2014-2022`, `SDC`, data-model
xlsx/docx — all under `M&M/Sample Data RTCIS PRIME/`. Ingest them when needed ([AGENTS.md](../../AGENTS.md) §4).
