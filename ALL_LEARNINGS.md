# All Learnings — Consolidated Knowledge Base

> **Generated:** 2026-05-14 | **Source:** 25 repo memory files
> **Purpose:** Physical copy of all accumulated learnings from the M&M / RTCIS-to-PrIME / IRA Query / SQL Translation work

---

# TABLE OF CONTENTS

1. [IRA Query V7 Learnings](#ira-query-v7-learnings)
2. [IRA Query V5/V8/V9 Validation Learnings](#ira-query-v5v8v9-validation-learnings)
3. [London IRA Query Evolution](#london-ira-query-evolution)
4. [Athens 2022 Schema Findings](#athens-2022-schema-findings)
5. [SSMS Connection & Session Reuse](#ssms-connection--session-reuse)
6. [M&M Bot — Design Overview](#mm-bot--design-overview)
7. [M&M Bot — Architecture & Code Rules](#mm-bot--architecture--code-rules)
8. [M&M Bot — Data Context & Schema Reference](#mm-bot--data-context--schema-reference)
9. [M&M Bot — Derivation Rules](#mm-bot--derivation-rules)
10. [M&M Bot — Field Specs & Q&A Engine](#mm-bot--field-specs--qa-engine)
11. [M&M Bot — SDC Standards, Security & Deployment](#mm-bot--sdc-standards-security--deployment)
12. [M&M Bot — Workspace File Inventory](#mm-bot--workspace-file-inventory)
13. [RTCIS / PrIME / SAP — Domain Glossary](#rtcis--prime--sap--domain-glossary)
14. [RTCIS ↔ PrIME Codebook Mappings](#rtcis--prime-codebook-mappings)
15. [PrIME 2022 Footprint & Translation Rules](#prime-2022-footprint--translation-rules)
16. [PrIME 2022 Training Transcript Knowledge](#prime-2022-training-transcript-knowledge)
17. [Sakar Q1-Q12 Base-Table Queries](#sakar-q1-q12-base-table-queries)
18. [SQL Translation Quality & Accuracy Rules](#sql-translation-quality--accuracy-rules)
19. [SQL Translation Output Format Standards](#sql-translation-output-format-standards)
20. [SQL Translation Feedback & Corrections](#sql-translation-feedback--corrections)
21. [Pomezia 34-Query Fix Findings](#pomezia-34-query-fix-findings)
22. [Pomezia Deep Audit Summary](#pomezia-deep-audit-summary)
23. [Pomezia Final Derivation Results](#pomezia-final-derivation-results)
24. [Pomezia Final Reclassification](#pomezia-final-reclassification)
25. [Pomezia Zero-Row Diagnosis](#pomezia-zero-row-diagnosis)

---

<a id="ira-query-v7-learnings"></a>
# 1. IRA Query V7 Learnings (from WMS expert)

## AI Diagnosis vs AI Prescription — IMPORTANT LESSON
- **AI diagnosis was CORRECT**: multiple poldat entries tied at rank 1 = root cause of inflation
- **AI prescription was WRONG**: "just pick one with a tiebreaker" is NOT the right fix
- **WHY**: The z-subquery finds the MAJORITY plant code in an area as a DEFAULT
  for empty locations (location is shared, was empty when counted, can't determine plant).
  Picking an arbitrary winner may pick the WRONG plant code. The fix must ensure
  the majority calculation correctly reflects actual inventory ownership.

## Two Types of Multi-Client Configuration
1. **Multi-client at LOAD NUMBER level** (conventional, e.g., Xiqing)
   - Each lodnum belongs to a specific client via prt_client_id
   - V6 fix (`d.wh_id_tmpl = a.wh_id`) solved this correctly
   - poldat has multiple wh_id_tmpl entries (CN66/CN74/CN88) but same rtstr1 → no tie

2. **Multi-client at ITEM FAMILY level** (rare, e.g., Mandideep — maybe the only one)
   - prtmst.prt_client_id = '----' for ALL parts (no client differentiation at load level)
   - Plant code is determined by ITEM FAMILY (vc_itmgrp on prtmst), not by load
   - poldat has 5 different rtstr1 values (6531/6533/7665/7980/D848)
   - Without vc_itmgrp: every part maps to ALL 5 poldat rows → 5-way GROUP BY explosion → tied RANK

## V7 Fix: prtmst.vc_itmgrp (the patch for item-family multi-client)
- `vc_itmgrp` is a column on prtmst that holds the item group / SAP plant code per part
- V7 uses `COALESCE(c.vc_itmgrp, d.rtstr1, e.rtstr1)` instead of `ISNULL(d.rtstr1, e.rtstr1)`
- At Mandideep: even though prt_client_id = '----', vc_itmgrp gives the CORRECT plant per part
- GROUP BY on COALESCE(vc_itmgrp, ...) collapses to the true majority → correct default plant
- This is a PATCH for the rare item-family config; conventional sites unaffected (vc_itmgrp = NULL, falls through to poldat)

## Other V7 Differences vs V6/2-Step
1. **poldat d has NO wh_id_tmpl filter** — safe because vc_itmgrp takes priority via COALESCE
2. **Uses RANK()** not ROW_NUMBER() — OK because vc_itmgrp resolves the plant correctly
3. **Single inline query** — no temp table, no 2-step
4. **Uses `inventory_view`** not invlod/invsub/invdtl direct joins
5. **Uses `dbo.getdate2()`** — site-specific timezone-aware date function
6. **No OPTION(RECOMPILE)** and no 7-day pre-filter on cnthst

## GROUP BY Change
- V5/V6/2-Step: `GROUP BY ... d.rtstr1, e.rtstr1` (separate poldat values = multiple groups)
- V7: `GROUP BY ... COALESCE(c.vc_itmgrp, d.rtstr1, e.rtstr1)` (single resolved value = 1 group)

## V8 Update — NULL Plant Code Fix (May 13, 2026)

### Problem V8 Solves
At Mandideep, some areas have NO inventory at all (empty areas). CTE z returns NULL
for those areas because there are no lodnums to count. When a count happens in an
empty area, both z.def_plt and p.prt_client_id are NULL → PLANT_CODE = NULL.

### V8 Fix: CTE y — warehouse-level fallback
V8 adds a second CTE `y` that aggregates z UP to the warehouse level:
```sql
y AS (
  SELECT wh_id, typcod, def_plt, SUM(lodnums) lodnums,
    RANK() OVER (PARTITION BY wh_id ORDER BY SUM(lodnums) DESC) rnk
  FROM z GROUP BY wh_id, typcod, def_plt
)
```
This gives the dominant plant code for the ENTIRE warehouse (across all areas).

### Three-tier plant code fallback (V8)
```
COALESCE(a.prt_client_id, z.def_plt, y.def_plt)
```
1. **prt_client_id** — if the count record has a real client ID, use it
2. **z.def_plt** — area-level majority (from inventory in that specific area)
3. **y.def_plt** — warehouse-level majority (fallback when area has no inventory)

Similarly for typcod: `COALESCE(p.typcod, z.typcod, y.typcod)`

### Why this matters
- Empty areas have counts but no inventory → z returns no rows → NULL plant
- y provides a sensible warehouse-wide default (the globally dominant plant)
- Only affects count records where BOTH prt_client_id and area inventory are missing

### V8 CTE structure
- z: area-level plant lookup (same as V7 with vc_itmgrp COALESCE)
- y: warehouse-level plant lookup (aggregated from z)
- LocationCounts: joins both z (rnk=1) and y (rnk=1) for fallback

## Open Questions
- Does vc_itmgrp exist in both PrIME 2014 and 2022?
- Is vc_itmgrp always populated at item-family sites, or can it be NULL?
- Performance: does the inline subquery still time out at sites like Cairo/Athens?
- Why no OPTION(RECOMPILE)? May still need it for read-replica stale plans.

---

<a id="ira-query-v5v8v9-validation-learnings"></a>
# 2. IRA Query V5/V8/V9 Validation Learnings (2026-05-13)

## Version Summary
- **V5**: Original baseline — `ISNULL(d.rtstr1, e.rtstr1)`, RANK, no `vc_itmgrp`
- **V8**: Expert original — `COALESCE(c.vc_itmgrp, d.rtstr1, e.rtstr1)`, CTE y warehouse fallback, no `wh_id_tmpl` on poldat d
- **V9**: Expert optimised — `COALESCE(NULLIF(UPPER(c.vc_itmgrp),'NULL'), d.rtstr1, e.rtstr1)`, CTE y with `WHERE def_plt IS NOT NULL`

## 3-Way Validation Results (All 7 Sites)

| Site | V5 | V8 | V9 | V5=V9? | V8=V9? | Notes |
|------|-----|-----|-----|--------|--------|-------|
| XIQING | 1097/3.5s | 1097/4.8s | 1097/5.8s | EXACT | EXACT | No vc_itmgrp data |
| AMIENS_BB | 432/7.6s | 432/5.3s | 432/4.2s | EXACT | EXACT | No vc_itmgrp data |
| AMIENS_KH | 425/1.5s | 425/6.7s | 425/3.9s | EXACT | EXACT | No vc_itmgrp data |
| MANDIDEEP | 3240/4.4s | 648/6.5s | 648/8.6s | DIFFER | EXACT | V5 inflated 5x (RANK ties), V8/V9 correct |
| JIJONA | 50/1.7s | 50/3.1s | 50/3.6s | EXACT | DIFFER | V8 has 5 'null' plants, V9 fixes to '6415' |
| CAIRO | TIMEOUT | 233/3.0s | 233/3.4s | V5 timeout | EXACT | No vc_itmgrp data |
| ATHENS | TIMEOUT | 315/5.0s | 315/5.5s | V5 timeout | EXACT | No vc_itmgrp data, 2022 schema |

## Key Findings

### 1. V8 Bug — Literal 'null' String in vc_itmgrp
- Jijona `prtmst` has 1,197 parts with `vc_itmgrp = 'null'` (literal string, not SQL NULL)
- Plus 1 part with `vc_itmgrp = 'NULL'` (uppercase)
- V8's `COALESCE(c.vc_itmgrp, ...)` treats 'null' as valid → becomes plant code
- Affected 4 areas: PESTOBGLUE, PESTOFBOB1, PESTOFMULB, PESTOGRMIX
- In those areas, parts with vc_itmgrp='null' had MORE loads than poldat-resolved parts → 'null' won RANK 1

### 2. V9 Fix — NULLIF(UPPER()) Pattern
- `NULLIF(UPPER(c.vc_itmgrp), 'NULL')` — single NULLIF with UPPER handles all case variations
- More elegant than double NULLIF: `NULLIF(NULLIF(c.vc_itmgrp, 'null'), 'NULL')`
- UPPER approach is future-proof against 'Null', 'nULL', etc.

### 3. V9 CTE y — WHERE def_plt IS NOT NULL
- Prevents null plant codes from entering the warehouse-level fallback ranking
- Safety net: if z produces NULL def_plt for some areas, those won't pollute y

### 4. Mandideep — Expected Difference
- V5 produces 3,240 rows (5 × 648) due to RANK ties
- V8/V9 produce 648 rows (correct) because vc_itmgrp resolves the dominant plant per area
- Mandideep has 15,638/39,706 parts with vc_itmgrp populated (no 'null' strings)
- V8=V9 at Mandideep confirms: no dirty vc_itmgrp data there

### 5. vc_itmgrp Data Quality by Site
| Site | Total Parts | Has vc_itmgrp | Has 'NULL' String |
|------|------------|---------------|-------------------|
| XIQING | 668,188 | 0 | 0 |
| AMIENS_BB | 99,987 | 0 | 0 |
| AMIENS_KH | 55,849 | 0 | 0 |
| MANDIDEEP | 39,706 | 15,638 | 0 |
| JIJONA | 9,148 | 1,197 | **1,197** (ALL are 'null'!) |
| CAIRO | 19,394 | 0 | 0 |
| ATHENS | 39,818 | 0 | 0 |

### 6. Performance — V5 vs V8/V9
- V5 times out at Cairo (300s) and Athens (300s)
- V8/V9 run in 3-9s at ALL sites including Cairo/Athens
- V8/V9 CTE approach (inline inventory_view) actually performs better than V5 inline subquery
- No wh_id_tmpl filter on poldat d in V8/V9 doesn't hurt performance

### 7. V9 is the Recommended Production Version
- Matches V5 exactly at all non-multi-plant sites
- Fixes V5 inflation at Mandideep (vc_itmgrp resolves correct plant)
- Fixes V8 'null' string bug at Jijona
- Runs without timeout at Cairo/Athens where V5 fails
- CTE y with def_plt IS NOT NULL provides safety net for future dirty data

## Expert's V9 SQL Key Snippet
```sql
COALESCE(NULLIF(UPPER(c.vc_itmgrp), 'NULL'), d.rtstr1, e.rtstr1)
-- ... in CTE y:
FROM z WHERE def_plt IS NOT NULL
```

---

<a id="london-ira-query-evolution"></a>
# 3. London IRA Query Evolution — Learnings

> **Date**: 2026-04-17
> **Context**: Comparing transaction-based CTE approach vs snapshot-based LOCATN approach

## Previous Approach (v2 — April 15, 2026)

**Source**: `_london_ira_query_v2.py`
**Data Source**: `live3.LOCATN` (location master — snapshot)
**Strategy**: Read final state per location

### Key Characteristics:
- **Single snapshot per location** — CYCDAT = last count timestamp only
- **All subsites included** — Fixed SUBSIT=0 limitation
- **ARECOD visible** — Exposed area code to explain RPM mismatches
- **Re-touch detection** — Flagged locations where CTRL_DATE > CYCDAT+5min
- **Date filter**: Full-day boundary (00:00 to 00:00)

### Limitations Identified:
1. **Cannot distinguish first-count vs last-count** — BM "yellow" issue
2. **Missing transaction history** — No STKCMP/STKCOR intermediate states
3. **No TRNTYP visibility** — london.SYSTRN has only 2 cols (TRNSEQ, SYSDAT)
4. **No re-count sequence** — Cannot show scan sequence

## New Approach (Transaction-Based CTEs)
- **Transaction-level granularity** — EVERY STKCNT/STKMIS event visible
- **Dual CTEs**: STKCNT (stock count) + STKMIS (stock miscount)
- **IRA calculation** — `(STKCNT - STKMIS) / STKCNT * 100`

## IRA PrIME Query Version Evolution (May 2026)

| Ver | Window Fn | poldat d filter | Plant derivation | Inventory source | Performance |
|-----|-----------|-----------------|------------------|------------------|-------------|
| V5 | RANK() | No wh_id_tmpl | ISNULL(d.rtstr1, e.rtstr1) | inventory_view | Inflates at multi-client-item-family sites |
| V6 | ROW_NUMBER() | d.wh_id_tmpl = a.wh_id | ISNULL(d.rtstr1, e.rtstr1) | inventory_view | Timeouts at 0 site-specific poldat |
| 2-Step | ROW_NUMBER() | d.wh_id_tmpl = il.wh_id | ISNULL(d.rtstr1, e.rtstr1) | invlod/invsub/invdtl | Universal perf, non-deterministic |
| **V7** | RANK() | No wh_id_tmpl | **COALESCE(vc_itmgrp, d.rtstr1, e.rtstr1)** | inventory_view | Correct for all multi-client types |
| **V8** | RANK() | No wh_id_tmpl | COALESCE(vc_itmgrp, d.rtstr1, e.rtstr1) + **CTE y warehouse fallback** | inventory_view | Fixes NULL plant in empty areas |

## Key Learnings
- Data Model: LOCATN=snapshot (1 row/loc), SYSTRN=transaction (N rows/loc)
- STKCNT = Stock count, STKMIS = Stock miscount
- PLANT_CODE Filter issue: `s.PLANT_CODE = '4856'` needed in both CTEs
- Missing London columns: SYSTRN needs TRNTYP/GENDAT, SYSDTL needs DTLTYP/SUBSIT

---

<a id="athens-2022-schema-findings"></a>
# 4. Athens 2022 Schema Findings (Verified May 11, 2026)

## Connection
- Server: sqlwrhathensprod.b05aaf70da1f.database.windows.net
- Database: ATHENS_REPLICA
- wh_id: WMD1
- Schema: dbo

## Architecture: Synonym-Based
- Core tables (locmst, trlr, aremst, etc.) are **SYNONYMS**
- INFORMATION_SCHEMA returns EMPTY for synonyms — must use `SELECT TOP 0 *` or `sys.all_objects`
- Only 1 actual base table in dbo: `UC_CUSTOM_PARAMETERS`
- 14 pre-built views: inventory_view, pckwrk_view, prtftp_view, prtmst_view, etc.

## Critical Flag Migration: aremst → locmst
| Flag | PrIME 2014 | PrIME 2022 (Athens) |
|------|-----------|---------------------|
| pckflg | aremst.pckflg | locmst.PCKFLG |
| pdflg | aremst.pdflg | REMOVED |
| stoare_flg | aremst.stoare_flg | locmst.STOFLG |
| shp_dck_flg | aremst.shp_dck_flg | Check locmst |
| cntflg | aremst.cntflg | REMOVED |

## aremst in 2022
- MINIMAL: only ARECOD, WH_ID, BLDG_ID, LOST_LOC, LOGIC_FLG, BU_ID, IS_PURGED
- NO flags at all

## locmst in 2022
- Extended: has PCKFLG, STOFLG, REPFLG
- Zone columns: PCK_ZONE_ID, STO_ZONE_ID, MOV_ZONE_ID (with _ID suffix)
- LOC_TYP_ID (not loc_typ)

## Tables that exist (as synonyms)
- dscmst, prtdsc, trlr_note, rplcfg, invsum, dlytrn — all exist
- dbo.getdate2() works
- untinp NOT in prtftp_dtl — use untlay via prtftp_view

---

<a id="ssms-connection--session-reuse"></a>
# 5. SSMS Connection & Session Reuse — How It Works

## Server Naming Convention
```
sqlwrh{sitename}prod.b05aaf70da1f.database.windows.net
```

## Authentication
- **SSMS UI**: Azure Active Directory - Universal with MFA
- **pyodbc**: MSAL device code flow with 3-layer token caching

## Three-Layer Token Strategy
```
Layer 1: Raw token file (.access_token.json) — fastest, ~1hr validity
Layer 2: MSAL cache (.msal_cache.json) — refresh tokens, silent renewal
Layer 3: Device code flow — interactive, last resort
```

## In-Process Connection Cache
```python
_conn_cache = {}  # {(server, database): connection}
```
- Tests with `SELECT 1` before reuse, `close_all()` for cleanup

## Known Site Configs
| Variable | Site | Schema | wh_id | Version |
|----------|------|--------|-------|---------|
| CRAILSHEIM | Crailsheim, DE | prodwms | DE29 | 2014 |
| ATHENS | Athens, GR | dbo | WMD1 | 2022 |
| JIJONA | Jijona, ES | prodwms | ES06 | 2014-hybrid |

---

<a id="mm-bot--design-overview"></a>
# 6. M&M Auto-Fill AI Bot — Design Document Summary

## Project: PrIME WMS Implementation: RTCIS → PrIME 2022
- **Version:** 3.3.0 | **Date:** 19-20 March 2026 | **Owner:** OSS WHS AI AND DATA TEAM
- **Design Doc:** `WH_MM_Process_Input.ipynb` (24 markdown cells, ~5200 lines)
- **HTML App:** `WH_MM_Flow.html` (~4500+ lines, single-page interactive dashboard)

## Purpose
AI bot that pre-fills four M&M (Match & Mapping) workshop documents for warehouse management system migration from RTCIS (legacy WMS) to PrIME 2022 (target WMS).

## The 4 Output Documents (D1–D4)
| # | Document | Template File | Owner |
|---|---|---|---|
| D1 | SAT BP Template (Site Assessment) | `Microsoft_Excel_Worksheet4.xlsx` | BPX |
| D2 | Site Configuration Model | `Microsoft_Excel_Worksheet5.xlsx` | BPX/GSE |
| D3 | PrIME PE Choices (Production Execution) | `Microsoft_Excel_Macro-Enabled_Worksheet.xlsm` | PE BPX |
| D4 | Automation Flows & Message Specs | `Worksheet5.xlsx` + D3 PATH tabs | SAM |

## Fill-Tier System
| Tier | Name | Rule |
|---|---|---|
| T1 | Auto-fill | Value exists directly in named source table+field |
| T2 | Auto-propose | Derived via rule/convention |
| T3 | Interactive Q | Not derivable → generate specific question |
| T4 | Workshop only | Cross-functional agreement required |

## Coverage Estimates
| Document | Auto-Fill % | Total after Q&A |
|---|---|---|
| D1: SAT BP Template | ~60-65% | ~89% |
| D2: Site Config Model | ~40-45% | ~89% |
| D3: PE Choices | ~60-65% | ~89% |
| D4: Automation Flows | ~50% | ~89% |

## HTML App — 6 Tab Structure (v3.3.0)
0. **Who Does What** — 19 AI roles, 5 human stakeholders
1. **Pipeline** — Dashboard with synced fill %, pipeline cards
2. **Flow** — Interactive SVG flow diagram (13 SDC modules)
3. **Data & Knowledge** — Quality Gate, Knowledge Sources hub
4. **Bot** — Role selector, Smart Fill (87 rules), Q&A panel (47 questions)
5. **Sheet** — Pre-filled data with fill-rate dashboard

## 19-Role AI Bot Team (v3.3.0)
- **Supervisor Agent** + **HITL Bridge**
- **Data Intelligence** (5): Data Lead, RTCIS/PrIME/SAP Specialists, Schema Architect
- **Knowledge & Research** (5): Knowledge Lead, RTCIS/PrIME Knowledge, Standards Analyst, Toolbox Specialist
- **Processing & Inference** (3): Auto-Fill, Q&A Coordinator, Answer Integrator
- **Output & Quality** (4): Document Writer, Gap Analyst, QA Auditor, Audit Specialist

---

<a id="mm-bot--architecture--code-rules"></a>
# 7. M&M Bot — Architecture & Code Rules

## Framework: LangGraph Agentic Architecture
- LangGraph StateGraph with specialised agent nodes
- LangChain @tool functions for data access and derivation
- Persistent memory via SqliteSaver (dev) / PostgreSQL (prod)
- Human-in-the-loop interrupts for Q&A rounds

## Graph State: `MMBotState` TypedDict
Key fields: site_name, plant_code, session_id, databricks_config, rtcis_data, prime_schema, prime_config, prime_design_docs, sap_exports, sdc_standards, schema_index, d1-d4_fields, questions, gap_register

## 8 Graph Nodes
1. `data_reader` → 2. `fill_engine` → 3. `qa_generator` → 4. `human_reviewer` (interrupt)
→ 5. `answer_mapper` → 6. `output_writer` → 7. `gap_reporter` → 8. `validator`

## Memory Architecture (4 tiers)
| Tier | Scope |
|---|---|
| In-graph state | Current graph run |
| Short-term thread | One site×role session |
| Long-term role | (site, role) namespace |
| Long-term site | (site,) shared |
| Global standards | All sites |

## Key Code Rules
1. Every T1 field MUST cite `source_ref` as `SOURCE.Table.Column`
2. Every T2 field MUST cite `source_ref` + `rationale`
3. All parsing goes through LLM readers
4. Schema_index used at runtime: `df[schema_index["RTCIS"]["SLOC_CODE"]]`
5. Connectors are read-only
6. Secrets via env vars or Azure Key Vault
7. LLM calls use ≤5 sample rows
8. PE Choices xlsm: write raw values only; user runs macro
9. Thread-per-site isolation
10. Schema corrections auto-promote after ≥2 sites confirm

---

<a id="mm-bot--data-context--schema-reference"></a>
# 8. M&M Bot — Data Context & Schema Reference

## RTCIS Data (Legacy WMS)
- **Database:** Pomezia RTCIS DR 2014, schema `esiliv1`, 410 tables

### 33 RTCIS Tables Used in D1 Auto-Fill
WH, LOCATN (76 cols), INVACT (26 cols), I_INVACT, POLDAT, PRTMST, ITMMST, ZONCOD, PWZON, WRKZON, TSKTYP, ORDHDR, ORDDTL, RCPHDR, RCPDTL, SHPHDR, SHPORD, MVT_MVTTYP, REPLEN, PRDLIN, AP3_SHIPMENT, AP3_CASPIK, TRLREQ, BLDING, CASPIK, CARRIER, PICK_METHOD, WAVHDR, TRAILER, TRLMOV, EXTSYS, CGHOLD, CUSTMR

## PrIME Data (Target WMS)
- **Database:** Pomezia PrIME DR 2022, schema `dbo`, 148 tables
- **IMPORTANT**: `__b` suffix synonyms are BROKEN at Athens. Use non-`__b` names
- **Inventory 3-tier model**: invlod.LODNUM → invsub.LODNUM/SUBNUM → invdtl.SUBNUM
- **17 live views** confirmed on ATHENS_REPLICA

## 23 Sample SQL Queries (Q-01 to Q-23)
Q-01: Pallet positions, Q-02: Dock doors, Q-03: Case pick zones, Q-04: Staging areas, Q-05..Q-23

---

<a id="mm-bot--derivation-rules"></a>
# 9. M&M Bot — Derivation Rules (10 Rule Sets)

1. **Plant Identity Fields**: plant_code, company_code, rtcis_wh_number, prime_wh_id, prime_partner
2. **Storage Location List**: SLoc from RTCIS LOCATN + type classification
3. **Work Center / Resource List**: WC from RTCIS PRDLIN + resource type
4. **PMC Compliance Pre-Scoring**: per-SKU overrides, workaround codes, deviations
5. **Operational Volume Estimates**: inbounds/day, peak periods from INVACT
6. **SAP Movement Types**: standard (101,102,261,262,309,311,931,932) + non-standard flagged
7. **Item Family Proposal**: ROH→RPM-RAW, VERP→RPM-PACKAGING, HALB→INTERMEDIATE, FERT→FINISHED
8. **Policy Deviation Detection**: 3-way comparison RTCIS vs PrIME ref vs SDC standard
9. **PrIME Design Doc Cross-Reference**: comparable site values
10. **PRFC vs Standard-Config Coverage**: SDC → reference site → PRFC → genuine gap

---

<a id="mm-bot--field-specs--qa-engine"></a>
# 10. M&M Bot — D1-D4 Field Specifications & Q&A Engine

## D1: SAT BP Template
- Enterprise structure (SAP codes, PrIME WH IDs, partner numbers)
- Operational data (inbounds/day, pallets/day, shifts, peaks, carriers, pick methods)
- SAT Assessment (PMC compliance pre-scoring)

## D2: Site Configuration Model
- Sections 1-7: Facility Setup, Directed Work, Controlling WH, Storage & Flow, Item/Material

## D3: PrIME PE Choices
- General Info, Site SLocs, Resources, Origin Groups, Staging Models, Material Groups, Background Jobs

## D4: Automation Flows
- External Systems, SAP Interface, Events, Configuration Objects, Flow Details

## Q&A Engine — 5 Rounds, 40+ Questions
- R1: Site IT (6-10 Qs), R2: BPX (8-14 Qs), R3: PE BPX + Ops (10-16 Qs), R4: SAM + IT (4-8 Qs), R5: Workshop (T4 items)

---

<a id="mm-bot--sdc-standards-security--deployment"></a>
# 11. M&M Bot — SDC Standards, Security & Deployment

## SDC Configuration Standards
- 13+ config sections with General Rules, Column Info, Pre-Loaded Values
- Policy Types 0-6 (POLDAT classification)
- Audit Severity: High → must match, Medium → drift reported, Low → informational

## Security & Authentication
- SharePoint/Graph: Azure AD OAuth 2.0
- Databricks: PAT or OAuth
- LLM: API key (Azure OpenAI or Anthropic)
- All connectors read-only — bot never writes to source systems
- No credentials in code — env vars or Azure Key Vault

## Implementation Backlog (5 Phases)
- Phase 1: Data Reader (Sprint 1-2)
- Phase 2: Fill Engine (Sprint 3-4)
- Phase 3: Q&A Generator & Engine (Sprint 5-6)
- Phase 4: Output Writer (Sprint 7-8)
- Phase 5: Validation & Testing (Sprint 9-10)

---

<a id="mm-bot--workspace-file-inventory"></a>
# 12. M&M Bot — Workspace File Inventory

## Core Files
- `WH_MM_Process_Input.ipynb` — Design document (28 cells, ~5400 lines)
- `WH_MM_Flow.html` — Interactive dashboard (~5220 lines, 6 tabs)
- `Sample Data RTCIS PRIME/Prime 2022 Data Model V4 (WIP).xlsx` — 1,661 tables, 22,867 fields

## Notebook Cells (28 total)
Cells 1-16: Overview → Architecture → Data → Rules → D1-D4 specs → Q&A → Outputs → Coverage → Sheet Logic → Backlog → Security → Glossary → Field Addresses
Cells 17-22: Appendices A-F
Cells 23-28: Who Does What spec, Change Log

## SQL Translations Tools
- `_translate_universal.py` — 7-phase universal translator
- `_batch_translate.py` — batch translator
- `neo4j_kb_api.py` — Knowledge Graph API
- Neo4j DBMS: 230 nodes, 222 relationships

## Database Connections
| Database | Server |
|---|---|
| ATHENS_REPLICA | sqlwrhathensprod...database.windows.net |
| POMEZIA (Prod) | sqlwrhpomeziaprod...database.windows.net |
| POMEZIA (Non-Prod) | sqlwrhminonprod01...database.windows.net |

---

<a id="rtcis--prime--sap--domain-glossary"></a>
# 13. RTCIS / PrIME / SAP — Domain Glossary & Context

## System Definitions
| System | Description |
|--------|-------------|
| **PrIME** | Blue Yonder WMS (P&G's warehouse management system) |
| **PrIME 2014** | Legacy version |
| **PrIME 2022** (Puma) | Target upgrade version |
| **RTCIS** | Real Time Control Information System (older custom WMS) |

## Product/Material Terminology
- FG/FP/SKU = Finished Goods (SAP: FERT)
- RM = Raw Materials (SAP: ROH, sometimes HALB)
- PM = Packaging Materials (SAP: ROH, sometimes HALB)
- RPM = RM + PM combined

## Cross-System Term Mappings
| PrIME | SAP | RTCIS |
|---|---|---|
| Shipment/Ship ID | Outbound Delivery/DN | Similar to SAP |
| Carrier Move ID | SAP Shipment | — |
| prtnum | Material Code | Item Code (ITMCOD) |
| Footprints | — | Item Config |
| wh_id | — | Subsite (subsit) |
| prtfam | — | Item Group (itmgrp) |
| arecod | — | Zone Code (ZONCOD) |

## Footprint Hierarchy
```
Pallet (PL) → Layer (LY) → Case (CS) → [SW/SP] → Item (IT)
```

## SQL Translation Guidelines
- `untinp` REMOVED in 2022 → use `untlay`
- Division safety: `CASE WHEN ISNULL(divisor,0)=0 THEN dividend ELSE dividend/divisor END`
- Schema prefixes: PrIME 2022=`dbo.`, RTCIS=`live3.`, PrIME 2014=`prodwms.`
- HAVING without aggregate → move to WHERE

---

<a id="rtcis--prime-codebook-mappings"></a>
# 14. RTCIS ↔ PrIME Codebook Value-Level Mappings

## 1. ITMCLS (Item Class) → typcod
| RTCIS | PrIME | Meaning |
|---|---|---|
| F | FERT | Finished Product |
| P | ZPAL | Packaging |
| R | ROH | Raw Materials |
| S | HALB | Semi-finished |
| U | UNBW | Non-valuated |

## 2. CTLGRP → LOTNUM (NOT frinvs!)
- Common mistake: `frinvs AS CTLGRP` — WRONG (frinvs = inventory status)
- Correct: `lotnum AS CTLGRP`

## 3. DTLTYP → No direct PrIME column
- Derivation: `CASE WHEN prtnum IS NOT NULL THEN 'F' ELSE 'T' END`

## 4. TRNTYP → ACTCOD (completely different codebook)
| RTCIS | PrIME | Description |
|---|---|---|
| CASPIK | PALPCK | Case Pick → Pallet Pick |
| DEPSUL | PUT_DRCT | Deposit UL → Putaway |
| LINTAK | LSTPCK | Line Takeaway → List Pick |
| PICKUL | FL_XFR | Pickup UL → Full Inventory Move |
| (+ 9 more) | | |

## 5. QASTAT → invsts
- RTCIS RL → PrIME U (Unrestricted) — RL does NOT exist in PrIME!

## 6-10. Other Mappings
- ULPALL → asset_typ (collapsed to single character in PrIME)
- ARECOD → arecod (same column name, completely different value sets!)
- ZONCOD → velzon (PrIME single char)
- CTRL_USER → different user accounts (no mapping possible)
- SYSDAT → trndte (different time windows)

**Key takeaway**: Same column name does NOT mean same codebook.

---

<a id="prime-2022-footprint--translation-rules"></a>
# 15. PrIME 2022 Footprint & Translation Rules

## Footprint Hierarchy
PL (Pallet) → LY (Layer) → CS (Case) → IT/SW/SP (items)

## PrIME 2022 Footprint Columns
- `prtftp_view` (flattened view): untpal, untlay, untcas, ftpcod, def_asset_typ
- `prtftp_dtl` (detail table): untqty + uomcod (PL/LY/CS) — NO untpal/untcas/untlay!
- CRITICAL: step 5b subqueries MUST target `dbo.prtftp_view`, NOT `dbo.prtftp_dtl`

## Footprint Calculations
- CASLAY = `untlay / untcas` (with division safety)
- LAYPUL = `untpal / untlay` (with division safety)
- CASQTY = `untpal / untcas` (with division safety)

## Key Mappings
- subsit → wh_id, itmgrp → prtfam, ZONCOD → arecod
- ULPALL → `ISNULL(asset_typ, ftpcod)`
- untinp → untlay (renamed in 2022)

---

<a id="prime-2022-training-transcript-knowledge"></a>
# 16. PrIME 2022 Training Transcript Knowledge

## 1. Areas → Zones (BIGGEST 2014→2022 Change)
- Area master in 2014 had 105 fields; in 2022 retains only ~11 (information-only)
- Split into: **Storage Zones**, **Movement Zones**, **Pick Zones**, **Location Types**, **Pick Methods**

## 2. Putaway Strategy — 2-level hierarchy (Source mov zone → Destination sto zone)
## 3. Allocation/Picking — 2-level hierarchy (Destination → Source)
## 4. Movement Zones — ALL locations MUST have one in 2022
## 5. Database Platform — Oracle → Microsoft SQL Server
## 6. Views NOT deprecated — still available for backward compatibility
## 7. Custom Parameters (uc_custom_parameters) — deprecated, migrating to policies
## 8. HCL Data Model Change Document — 22,403 entries with transition remarks

---

<a id="sakar-q1-q12-base-table-queries"></a>
# 17. Sakar Q1-Q12: Validated Base-Table Queries

> **Status**: 18/18 queries PASS | **Validated at**: Athens PrIME + Pomezia RTCIS

## Architecture
- Athens has 1 real table + 17 views + 1972 synonyms
- `__b` suffix synonyms BROKEN at Athens (error 5313) — use non-`__b` names

## Inventory Model (3-tier)
```
invlod (LPN/pallet) → invsub (sub-LPN) → invdtl (SKU detail)
```

## Key Query Patterns
- Q1: ZONCOD → 4-way zone JOIN (pck_zone, sto_zone, mov_zone, zonmst)
- Q4: RRNUMB → rcvlin JOIN; ULTYPE → ASSET_TYP
- Q5: TRNTYP → ACTCOD crosswalk
- Q6: AGV_INV → full invlod+invsub+invdtl+locmst chain
- Q7: ITMMST → prtmst + prtftp (ITMDSC is description, NOT ITMDES)
- Q9: single LOCATN → FRSTOL + TOSTOL (from/to split)

---

<a id="sql-translation-quality--accuracy-rules"></a>
# 18. SQL Translation Quality & Accuracy Rules

## Core Principles
- NOT a 1:1 translation — semantic equivalence of OUTPUT
- JOIN paths are valid resolutions
- Alias PrIME columns to RTCIS names for downstream compatibility

## Iterative Column Matching (9-pass)
exact name → dictionary → reverse dict → suffix → partial tail → substring → keyword → domain → NO EQUIVALENT

## Live Validation Findings
- prtdsc join key: `colnam = 'prtnum|prt_client_id|wh_id_tmpl'` (NOT wh_id)
- `palflg` → use `PAKFLG` (Int32); `prt_class_name` is empty at Athens
- prtftp_dtl multiple ftpcod → use OUTER APPLY TOP 1
- prtmst dedup: filter `wh_id_tmpl = '{SITE_WH_ID}'`
- ITMMST is SPLIT: prtmst + prtdsc in PrIME

## Mandatory Verification Checklist
Phase 1: Schema Verification FIRST → Phase 2: Translation → Phase 3: Documentation

## Error Iteration Rule (MANDATORY)
If ANY query fails validation → diagnose → auto-fix → re-validate → repeat (max 3 attempts)

---

<a id="sql-translation-output-format-standards"></a>
# 19. SQL Translation Output Format Standards

## Per-query sections (numbered 1-6)
1. Confidence Check (gate + syntax & accuracy check)
2. Original RTCIS Query
3. Translated PrIME 2022 Query (+ Expert vs Auto comparison)
4. What Changed (Table + Column Mapping)
5. DBA Verification Required
6. Live Validation Results

## Summary sections
Overview, All Queries at a Glance, DBA Questions, Live Validation, Query Insights, Validation Report

## Confidence badges: EXPERT-VALIDATED, READY, REVIEW, BLOCKED

---

<a id="sql-translation-feedback--corrections"></a>
# 20. SQL Translation Feedback & Corrections

## CRITICAL CORRECTIONS
- **QASTAT='RL' → invsts='U'** (NOT 'RL') — Learning #49, #56
- **DTLTYP='F' → oprcod='F'** (same value, NOT ITMCLS→typcod) — Learning #58
- **ITMCLS='F' filter silently dropped** from Q28/Q29 — Learning #59
- **__b suffix is WRONG** — use logical names
- **TRUKIO → trlr** (NOT trlract)
- **ITMCLS → prtmst.typcod** (NOT prt_class_name, which is empty at Athens)
- **CASPIK/CASXFR are correct actcod values** — expert override

## Verified Table Mappings
- TRUKIO → trlract (5-hop join: ord_line → shipment_line → shipment → stop → car_move → trlract)
- ORDDTL → ord_line (ordnum, prtnum)
- trlract.ordnum = VERIFIED ABSENT (33 cols checked)
- TRUKIO.APTDAT → trlract.appt_id (NOT stop.appt_dte)

## Footprint Architecture
- RTCIS: UNTPAL/UNTCAS/UNTINP all on PRTMST
- PrIME 2022: SPLIT across prtmst + prtftp + prtftp_dtl
- FP_PL/FP_CS/FP_LY are TABLE ALIASES for prtftp_dtl, not column names

---

<a id="pomezia-34-query-fix-findings"></a>
# 21. Pomezia 34-Query Fix: Ground Truth (April 2026)

## RTCIS Side
- `ITMMST` has 48 cols — NO UOMCOD/LENGTH/WIDTH/HEIGHT/WEIGHT
- `vw_SYSTRN_per_PACKMAT` does NOT exist → Q8 must inline
- `Picking_MissCback` does NOT exist → Q17 drop
- `SAP_LIB_F6P_HANA` does NOT exist → Q20 drop SAP joins

## PrIME Side (POMEZIA_RTDS)
- `dlytrn` has 37,750 rows, 7 days only
- `dlytrn.oprcod`: 99.9% NULL — oprcod='F' returns 0 rows
- `locmst` has NO `STO_ZONE_ID` → replace with VELZON
- `inventory_view` & `prtftp_view` in `POMEZIA_REPLICA.dbo` (NOT POMEZIA_RTDS)
- `trlr` has NO `SHIPID`

## Key Diagnosis
1. actcod mapping CANNOT be 1:1 — many RTCIS TRNTYPs have no PrIME equivalent
2. `oprcod='F'` filter is wrong — PrIME has no DTLTYP concept
3. `sto_zone_id` doesn't exist in PrIME locmst

---

<a id="pomezia-deep-audit-summary"></a>
# 22. Pomezia Deep Audit (2026-04-30)

## What Was Done
1. **Live audit**: 670/671 sources verified against INFORMATION_SCHEMA
2. **Deep audit**: 326 VALUE-MISMATCH, 98 ALL-NULL-PM, 29 ALL-NULL-RT
3. **Best-match finder**: 0 strong, 5 weak PM-side; confirms most NULLs are genuine schema gaps
4. **Injected findings**: 23 deep-audit DBA escalations into final reports

## Key Actionable Findings (RT-side)
- Q23 trailer fields → `AS_RTCIS_TRUKIO` view
- Q5/Q14/Q15 ZONCOD/BLDING → AP3 tables
- Q35 ITMNUM/COST → `RTCIS_ITMMST_VIEW`

## Not Actionable (genuine PrIME schema gaps)
- Q3/Q4/Q16 prtmst flags (PALFLG, PICFLG, etc. — RTCIS-only)
- Q22/Q25-Q27 BUOMNUM (RTCIS ITEM_UOM absent from PrIME)

---

<a id="pomezia-final-derivation-results"></a>
# 23. Pomezia Final Derivation Results (2026-04-30)

## V7 Final Status
- Total CAST(NULL) remaining: **76** (down from ~200+)
- All 34 queries PASS on live PrIME
- All 76 confirmed as genuine structural gaps with no PrIME equivalent

## Key Derivations
- **STOLOC format mismatch**: RTCIS `001A01002A` ↔ PrIME `A01002A` — strip leading `001`
- **LOCMST.LOCSTS** has F/P values — exact match for location-status filter

## Final Stats
- PM-side: 98 NULL columns → 22 resolved, 17 KB hints, ~30 remain as confirmed gaps
- RT-side: 29 NULL columns → 4 resolved, 20 KB hints, ~5 remain as confirmed gaps

---

<a id="pomezia-final-reclassification"></a>
# 24. Pomezia Q1-Q37 Final Reclassification (2026-05-06)

## Final Accounting
Total output columns audited: **609**

| Group | Count | % | Meaning |
|---|---|---|---|
| OK | 250 | 41% | Translation correct |
| EXPECTED-GAP | 301 | 49% | RTCIS-only column; CAST(NULL) correct |
| MAPPED-INTENTIONAL | 58 | 10% | Different real columns by design |
| **Real bugs** | **0** | **0%** | Nothing left to fix |

## Honest Summary
The Pomezia RTCIS→PrIME translation is **structurally complete and correct**:
- 41% map cleanly, 10% use intentional remapping, 49% legitimately emit NULL (RTCIS-only), 0% residual bugs

---

<a id="pomezia-zero-row-diagnosis"></a>
# 25. Pomezia Zero-Row PrIME Query Diagnosis (April 2026)

## Fixed (now returning rows)
- Q10: `actcod='LINTAK'` → `'LSTPCK'` (1 row)
- Q17: `RELABEL` → `SLCHG`; relaxed filters (1139 rows)
- Q19: `actcod='CUTSUB'` → `'CRT_ITM_LOT'` (75 rows)
- Q31, Q34: wh_id, staging areas, ulpall, Turno CASE fixes (80 rows each)

## Final State: 27 PASS / 7 PM-EMPTY / 2 EMPTY-BOTH / 1 RT-EMPTY (out of 37)

## Still-Empty Root Causes
- Q6: ARECOD='CP' — RTCIS coarse code, no PrIME equivalent
- Q7: actcod combo genuinely 0 rows
- Q11: usr_id='HSTINB' + actcod='LSTPCK' = 0 rows at Pomezia
- Q18, Q28, Q29: needs longer data window
- Q32: requires ORDNUM on FL_XFR — semantic gap

## Key Pomezia Connection Facts
- PrIME `wh_id = 'IT01'` (NOT 'WMD1')
- Staging area prefixes: VSTG, EMU-, DISP, ST1, ST2, CR03
- `ulpall` = `prtftp.FTPCOD` (B1/B2/P2), NOT `def_asset_typ`
- ARECOD: PrIME has 100+ codes vs RTCIS 9 — no codebook crosswalk possible

---

# Live-Database Validation Requirement (Governance — Learning #74)

> **Added:** 2026-07-02 | **Severity:** CRITICAL | **Category:** validation-fix
> **Source:** User feedback during ontology/KG agent + query remediation session

## The Rule
- Every ontology/KG assertion and every generated query MUST be validated against the **LIVE database** with **captured evidence** (row counts + sample rows).
- **Executable ≠ accurate.** A query that runs is not proof it answers the intended question.
- Static KB assertions, prior mappings, and assumptions are insufficient on their own — always prove the claim against real data on the target replica before asserting it.

## Target Replicas (where proof is captured)
- **LONDON** → RTCIS, schema `live3`
- **XIQING** → PrIME 2014, schema `prodwms`
- **ATHENS** → PrIME 2022, schema `dbo`

## Enforcement
- `ontology_kg_agent.py` exposes `validate_live()`: every asserted mapping/query is run against the live replica, capturing `row_count` and `sample_rows` as evidence.
- Queries returning 0 rows, or reusing shared catch-all SQL across unrelated questions, are demoted to **honest N/A** rather than presented as accurate.
- **No claim without evidence.**

## Evidence (remediation outcome)
- 1,773 catalogued queries audited.
- 69 live-validated retargets — each proven with row counts + sample rows.
- 387 honest N/A markers where no faithful target existed.
- 0 remaining generic/inaccurate queries.

---

*End of consolidated learnings — 25 files merged into one physical document.*
