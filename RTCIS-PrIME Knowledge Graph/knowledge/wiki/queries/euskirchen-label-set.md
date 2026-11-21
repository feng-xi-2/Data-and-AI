---
title: Euskirchen label-printing set Q01–Q18
type: query
status: verified
sources: [raw/queries/euskirchen-label/, raw/euskirchen/CONVERSION_REPORT.md, raw/euskirchen/mapping_by_field.csv, raw/euskirchen/mapping_by_query.csv, raw/memories/euskirchen_rtcis_prime2022.md, raw/experts/00_EXPERT_RUIZ_RS_ORIGINAL_vs_SHIPPED.sql]
evidence: []
updated: 2026-10-20
---
# Euskirchen label-printing set (Q01–Q18)

**Source:** 14 Oracle/RTCIS files (`raw/queries/euskirchen-label/`, originally `Desktop\Query Sep`) + line-supply Q15
and conveyor plugins Q16–Q18. **Deliverables:** `raw/euskirchen/01_GetAllData_prime.sql`, `02_GetDefaultData_prime.sql`,
`03_14_remaining_prime.sql`, `15_post_END_prime.sql`, `16_LineSupply_prime.sql`, `17_Conveyor_Plugins_prime.sql`.
Full narrative: `raw/euskirchen/CONVERSION_REPORT.md`; field map `mapping_by_field.csv`, per query `mapping_by_query.csv`.
The full working pipeline (`_eu_3way.py` → `_eu_facts.py` → `_eu_tabbed.py` → `_eu_tabcheck.py`) and the tabbed report
stay in `M&M/SQL_Translations/` (not copied — heavy and machine-specific).

## State (2026-10-08 / 10-14) `[LEARNED]`
- All 18 delivered main bodies execute on both PrIME replicas (DE08, WMD1); RTCIS London Q02/Q08/Q10 fail on missing `PALLETS_VIEW`.
- Expert remediation (RUIZ.RS 16/17 Sep) adopted and verified — [ruiz-rs-obs](../experts/ruiz-rs-obs.md).
- Q15–Q18 marked **NOT VERIFIED / AWAITING REVIEW**: Q17 26,675 matched pallet-items, 371 differ; Q18 1,958 common items,
  1,006 pick-face differences; Q16 stacked witness B/S vs B; Q15 DE08 0 rows (no line supply), Athens 23/133.
- Learning-capture audit 39/39 — validates capture coverage, not semantic accuracy or expert approval.

## Key findings specific to this set
- GTIN exists (`alt_prtmst`), chosen by receiving UOM; pinning `'CS'` blanked 35%.
- Setup = list pick (`LIST_ID`); shipid = carrier move; where setupids/shipid are populated per query is fixed by the
  originals (Q01 carmove + n/N; Q02 both; Q11 both blank; Q12 carmove; Q13 carmove; Q14 ORDNUM by design).
- Every original has a second statement after `/*END*/` (4 files: GetAllData, GetCustCenterData, GetEdekaData,
  GetEdekaDataMixed) — whether the caller runs it is an [open decision](../open-decisions.md).
- Q02 and Q11 were delivered inverted (fixed). Q06 `IsPartial` scalar aggregate invented an answer (fixed).
- `@locale` pinned to GERMAN blanked 50% of descriptions — use caller locale + fallback.
- Label routing / layout does not live in WMS tables (`dscmst` is a code × locale catalogue); layout is a query family + router.
- The RTCIS original Q09 `IsComplete` is defective at London (`itmcod<>'B2'`), and the setup denominator is wrong for
  257/811 London orders — audit the source too.
- Q01 returns 0 rows at DE08 — correct (no list-pick work at the DEV site), not a defect.

See [conversion-lessons](../learnings/conversion-lessons.md), [prime-anti-patterns](../learnings/prime-anti-patterns.md).
