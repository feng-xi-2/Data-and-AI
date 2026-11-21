---
title: Overview — RTCIS to PrIME 2022 conversion
type: overview
status: verified
sources: [raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md, raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md]
evidence: [results/summary.csv, results/compare.json, results/expert_rules.json]
updated: 2026-10-20
---
# Overview

## The problem
P&G warehouses are moving from **RTCIS** (custom legacy WMS, Oracle; replicated to Azure SQL MI as schema `live3`)
to **PrIME 2022** (Blue Yonder WMS 2022, "Puma"; SQL Server schema `dbo`). Every site has reports, labels, RPA and
Power BI feeds written against RTCIS. They must return **the same columns with the same meaning** on PrIME. RTCIS and
PrIME are different products: the conversion is semantic, not syntactic. `[DOC]` (raw/reference §1, §7 rules 10–12)

Three systems must not be confused: RTCIS (`live3`/`esiliv1`, UPPERCASE), PrIME 2014 (`prodwms`), PrIME 2022 (`dbo`).
"Pomezia RTCIS DR 2014.xlsx" is RTCIS — the 2014 is a date. `[DOC]`

## What has been done (and is reusable)
| Work | Site | Result | Page |
|---|---|---|---|
| RPM query set R01–R17 | Euskirchen RTCIS → DE08, Athens witness | 51/51 runs, columns identical, 0 expert-rule FAIL; 5 B, 12 C | [rpm-status](queries/rpm-status.md) |
| Label-printing set Q01–Q18 | Euskirchen → DE08, Athens / Crailsheim / London witnesses | All main bodies execute on both PrIME replicas; expert remediation adopted | [euskirchen-label-set](queries/euskirchen-label-set.md) |
| Pomezia set (34 + 3 vendor queries) | Pomezia → Athens validation | 34/34 PASS (Mar–Apr 2026) | [complete-reference](sources/complete-reference.md) |
| Timbr ontology extension (offline) | Amiens BB/KH, Mataro, NPI | Proposal only, not deployed | [timbr](timbr.md) |

## How knowledge is organised here
- **Ground truth** (measured in databases): [endpoints](ground-truth/endpoints.md), [mappings](ground-truth/mappings.md), [data facts](ground-truth/data-facts.md).
- **Criteria**: [criteria](criteria.md). **Method**: [method](method.md). **Objectives**: [objectives](objectives.md).
- **Experts**: [RUIZ.RS / Gino OBS1–8](experts/ruiz-rs-obs.md). **Learnings**: [conversion lessons](learnings/conversion-lessons.md), [verification discipline](learnings/verification-discipline.md), [PrIME anti-patterns](learnings/prime-anti-patterns.md).
- **Concepts / entities**: see [index](../index.md).

## The one-line lesson
Measure on the same physical pallet / item / lot / location in both systems before accepting any mapping, and never
call a query converted because it runs.
