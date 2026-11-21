---
title: Acceptance criteria, mapping tags and grades
type: criteria
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/expert_verification_rules.md]
evidence: [results/compare.json, results/expert_rules.json, results/field_check.json]
updated: 2026-10-21
---
# Criteria

## Hard criteria (every conversion)
1. Runs on the PrIME target **and** on a live PrIME site without error (`run_queries.py`).
2. **Identical output column names and order** as the original (`compare.py` → `columns_identical: true`).
3. No invented runtime inputs; only `@wh_id` / `@locale` added (caller-bound); original parameters kept by name ([OBS4](experts/ruiz-rs-obs.md)).
4. Read-only; no DML; no hard-coded test values in the deliverable.
5. Every mapping in the header carries a tag and, if measured, its agreement rate.
6. Original grain preserved: DISTINCT / GROUP BY / UNION semantics, no fan-out from 1:n PrIME tables ([grain-and-fanout](concepts/grain-and-fanout.md)).
7. Units comparable: same UOM as the original ([receiving-uom](concepts/receiving-uom.md)), dates site-local ([site-local-time](concepts/site-local-time.md)).
8. `audit_expert_rules.py` reports 0 FAIL.
9. **Field mapping and empty-field check** (`field_check.py` → `results/field_check.json`, exit 0). For every output
   column: RTCIS source, PrIME source, filled % per engine, agreement on the same keys **with both-blank pairs excluded**.
   - **E1 empty** — PrIME column is a constant NULL, or < 5% filled on a PrIME site that returned rows while RTCIS is ≥ 50% filled.
   - **E2 mismatch** — agreement < 95% over ≥ 10 keys that have a value on at least one side.
   - **E3 unresolved** — the column's source expression cannot be traced on both engines.
   Every E1/E2/E3 field needs a reason in `queries/field_notes.json` as `CATEGORY: measured reason (evidence file)`.
   Empty categories: `NO_SOURCE`, `DATA_NOT_MIGRATED`, `TEST_DATA`, `SITE_CONVENTION`, `FAITHFUL_TO_ORIGINAL`,
   `NOT_CONFIGURED`, `SMALL_SAMPLE`. Mismatch categories: `TIMING`, `CODE_SET`, `NAMING`, `NO_SOURCE`, `DATA_NOT_MIGRATED`,
   `INFERRED`, `TEXT_VARIANT`, `CONFIG_DIFF`, `MORE_PRECISE`, `NOT_CONFIGURED`. A reason is only accepted after the PrIME
   source was **probed for data** (fill rate of the column in the table, and of alternative columns) — "no source" is a
   finding, not an assumption. `build_report.py` refuses to build while any field is undocumented.
10. **Test inputs are like-for-like**: the PrIME test parameter selects the same kind of object as the RTCIS one (e.g. a
   packaging receipt at a door for R06), otherwise fields that only fill for that kind look empty.

## Mapping tags
| Tag | Meaning |
|---|---|
| `MAPPED` | Measured on the same physical objects, ≥ 95% agreement (or differences explained) |
| `[INFERRED]` | Structurally plausible, not (fully) measurable on current data; needs owner confirmation |
| `[PARTIAL]` | Maps part of the value domain only (e.g. RA vs RO not separable) |
| `[ELIMINATED]` | No PrIME source; column returned typed NULL; business decision required |
| `DEVIATION` | Knowingly differs from an expert rule, with `[DB]` numbers justifying it |

## Status grades
| Grade | Criteria |
|---|---|
| **A — verified** | Hard criteria met + all non-NULL columns ≥ 95% on matched keys (differences explained) |
| **B — runs, mapped, data-limited** | Hard criteria met; mappings measured, but target data (DEV) too thin for value equality |
| **C — runs, open decisions** | Hard criteria met; ≥ 1 `[ELIMINATED]`/`[INFERRED]` column that changes business meaning |
| **D — blocked** | Cannot run or source unreachable |

No grade means business approval — the site key user signs off.

## Three different zeros `[LEARNED]`
- **EMPTY** — valid input, no rows → defect, FAIL.
- **BLOCKED** — site lacks the data the query depends on (e.g. DE08 has no line supply) → unproven, not a pass.
- **SKIP** — no row of the required shape to test with.
A pass must be graded (DATA EQUIVALENT / SHAPE ONLY / NO INPUT / FAIL), never boolean. See [verification-discipline](learnings/verification-discipline.md).
