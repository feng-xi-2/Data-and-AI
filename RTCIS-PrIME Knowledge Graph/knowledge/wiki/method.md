---
title: Conversion method
type: method
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md]
evidence: [results/compare.json, results/expert_rules.json]
updated: 2026-10-20
---
# Conversion method

## Steps
1. **Freeze the original** in `raw/queries/<set>/` (immutable; it is the reference). Run `tools/wiki_lint.py --seal`.
2. **Classify the wrapper** (table below).
3. **Baseline**: transliterate to T-SQL on the RTCIS replica (`queries/rtcis_tsql/Rnn_*.sql`). Keep output names,
   order, filters, DISTINCT, GROUP BY. Note dead code / bugs of the original in the header — do not silently fix.
   Parameters go to `queries/params.json` (literal, or `{"sql": …}` discovered on the site). It must return rows.
4. **Inventory RTCIS objects** the query reads; look each up in [mappings](ground-truth/mappings.md) and
   [tables](entities/tables.md), then in `raw/schema/verified-mappings.json` and [complete-reference](sources/complete-reference.md).
5. **Measure unknown mappings** on the same physical objects: `LODNUM = ULID20` (or `LEFT(LODNUM,19) = ULID`),
   `PRTNUM = ITMCOD`, `LOTNUM = CTLGRP`, `STOLOC = LOCATN` ([pallet-id](concepts/pallet-id.md)). Accept a mapping
   only with a measured rate; code correlation is not a mapping (QASTAT ≠ INVSTS vocabularies).
6. **Write PrIME SQL** (`queries/prime/`): original column contract; `@wh_id` (+ `@locale`) bound by caller; mapping
   header tagged; untranslatable fields `CAST(NULL AS …)` `[ELIMINATED]` with the reason.
7. **Execute** on target (DE08) and live witness (Athens WMD1, or Crailsheim DE29) — `run_queries.py`.
8. **Compare** (`compare.py`): row counts, column contract, value agreement on matched keys, diff examples.
9. **Diagnose each weak column**: wrong mapping → fix & re-run; different code set → document; snapshot/test-data →
   document with numbers; no source → NULL + [open decision](open-decisions.md).
9b. **Field check** (`field_check.py`, exit 0): every empty (E1) or mismatched (E2) field is probed in the database and
   gets a categorised reason in `queries/field_notes.json` ([criteria](criteria.md) item 9). Look at the sample values,
   not only the percentages: R05/R06 door was filled 100% but held the trailer id, not the door.
10. **Audit expert rules** (`audit_expert_rules.py`, 0 FAIL), add `WHAT`/`STATUS` in `build_report.py`, build report,
    run `gen_query_pages.py`, update [criteria](criteria.md) grade, ground truth and learnings, log it.

## Classify the source wrapper
| Source shape | Meaning | Action |
|---|---|---|
| Plain T-SQL on `live3.*` / `LIVE3.AGV_INVENTORY_VIEW` | Already SQL Server on the RTCIS replica | Schema-qualify ([data-facts](ground-truth/data-facts.md)) |
| `EXEC [CS_DataWarehouse].[dbo].[SYS_get_RTCIS] null, '<oracle>', p1..p5` | Oracle text to live RTCIS; `{0}`..`{4}` = p1..p5 | Transliterate |
| `EXEC …SYS_get_DAS …` | Same, against DAS history archive (not on replica) | Use `live3.systrn/sysdtl` (~40 days) |
| `SELECT * FROM OpenQuery(RTCIS\|LIVE, '…')` | Linked-server Oracle text, `''` = one quote | Transliterate |
| Reads `RPM_System.*` / other app DB | Downstream of other queries | Convert the feeders; recompute for testing |

Oracle → T-SQL: `decode`→`CASE`, `nvl`→`ISNULL`, `to_char`→`FORMAT/CONVERT`, `substr`→`SUBSTRING`, `sysdate`→ site-local
now ([site-local-time](concepts/site-local-time.md)), `sysdate - n/24/60`→`DATEADD(minute,…)`, `(+)`→`LEFT JOIN`,
`||`→`CONCAT` (beware NULL→''), `to_date(x,'mm/dd/yyyy hh24:mi:ss')`→`CONVERT(datetime,x,101)`.

## House SQL rules `[DOC]` (raw/reference §7)
Division safety `CASE WHEN ISNULL(d,0)=0 …` and **cast to decimal** (int/int truncates on SQL Server); `untinp`
removed in 2022 (use `untlay`); no `__b` suffix; no `AS` on table aliases; `/* */` comments for inline notes;
`/* VERIFY: … */` on site-specific filter literals; HAVING without aggregate → WHERE; never blind `SELECT *`.

## Evidence beats prose
Every claim in this wiki points at a tool in `tools/` or a file in `results/` / `raw/`.
