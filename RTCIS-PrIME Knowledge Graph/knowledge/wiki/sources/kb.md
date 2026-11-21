---
title: "Source: knowledge base (kb/) and remediation knowledge"
type: source
status: documented
sources: [raw/kb/, raw/remediation-knowledge/]
evidence: []
updated: 2026-10-20
---
# Source: KB documents

## raw/kb (15 files)
| File | Use it for |
|---|---|
| `ALL_LEARNINGS.md` (71 KB) | IRA V5–V9 learnings (multi-client via `prtmst.vc_itmgrp`, NULL plant fix), London IRA evolution, Athens 2022 schema (synonyms, aremst→locmst flags), SSMS/token strategy, M&M bot design, **codebook value maps** (ITMCLS→typcod, CTLGRP→LOTNUM not frinvs, TRNTYP→ACTCOD, QASTAT→invsts) |
| `RTCIS_DATABASE_REFERENCE.md`, `RTCIS_QUERY_REFERENCE_GUIDE.md` | RTCIS tables/columns and query idioms |
| `LIVE-VIEW-DEFINITIONS.md` | Definitions of RTCIS `live3` views (what a view really joins) |
| `RTCIS-TO-PRIME-ARCHITECTURE.md`, `RTCIS-PRIME-INDEX.md` | Earlier architecture + index of the remediation tooling |
| `FLOW-1/2/3-*.md` | Process flows: RTCIS IRA query (M&M), RTCIS→PrIME remediation, PrIME 2014→2022 remediation |
| `PRIME-2014-TO-2022-REMEDIATION-GUIDE.md`, `PRIME2014-QUERY-TEMPLATE-LIBRARY.md` | PrIME 2014 → 2022 (not RTCIS) |
| `PRIME2022-AREA-ZONE-LOCATION-NAMING-CHECKLIST.md` | 2022 zone model and naming |
| `WMS-BUSINESS-ONTOLOGY-AND-STANDARDS.md`, `ONTOLOGY-DISCOVERY-KB.md` | Business ontology, Timbr discovery |
| `WH_Data_Replica_Servers.md` | ~77 replica endpoints (incomplete — see [endpoints](../ground-truth/endpoints.md)) |

## raw/remediation-knowledge (15 files, from `RTCIS-PrIME-Remediation/knowledge`)
Glossary (`rtcis-prime-glossary.md`), derivation rules, data-schema reference, remediation quality/feedback/output
standards, SDC security & deployment, training-transcript knowledge (PrIME 2022 changes), architecture code rules.

## raw/schema (machine-readable)
`verified-mappings.json` (33 KB), `translation-learnings.json` (69 KB), `knowledge-registry.json`, `open-questions.json`,
`prime-datamodel.json` (7 MB, full PrIME 2022 model), `erd-index.json` (1 MB), `README-SchemaVerification.md`.
Query them with Python/`jq` rather than reading whole.

**Caveat:** these predate the Oct-2026 Euskirchen measurements; where they disagree with
[ground truth](../ground-truth/mappings.md), record the contradiction on the ground-truth page.
