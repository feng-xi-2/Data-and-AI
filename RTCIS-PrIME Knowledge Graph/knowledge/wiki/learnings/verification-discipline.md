---
title: Verification discipline (how not to fool yourself)
type: learning
status: verified
sources: [raw/memories/expert_verification_rules.md, raw/memories/euskirchen_rtcis_prime2022.md]
evidence: []
updated: 2026-10-20
---
# Verification discipline

Hard-won rules from the Euskirchen conversions (Sep–Oct 2026). Each one cost a wrong claim before it was learned.

## Absence claims
- Never declare a field "does not exist" after searching only **column names**. PrIME stores concepts as **rows**
  discriminated by a value (GTIN = `alt_prtmst` row with `ALT_PRT_TYP='GTIN'`).
- Before claiming absence: (1) column names, (2) **value domains** (`SELECT typcol, COUNT(*) GROUP BY typcol`),
  (3) KB / `raw/schema/verified-mappings.json`, (4) the **synonym space** (`REL_GRP`, `ALT_`, `VC_` prefixes,
  `_TMPL`/`_ID` suffixes — kits are `VC_PALLET_REL_GRP`), (5) the platform's own documentation vocabulary.
  Then say "not found with method X".
- **Absence in a live system is evidence**: if Athens prints labels daily without column X, X is not the mechanism.

## Counts, grain and zeros
- **A row count is not a fact until you know its grain**: 1,740 `dscmst lblfmt` rows = 116 codes × 15 locales.
  Run `COUNT(*), COUNT(DISTINCT key), COUNT(DISTINCT locale)` first. Read the key before the count.
- **"No rows" usually means wrong join**: compare key length/case/padding/prefix/check digit (ULID 19 vs LODNUM 20).
  `SELECT LEN(key), COUNT(*) GROUP BY LEN(key)` on both sides.
- **EMPTY vs BLOCKED vs SKIP** are three different zeros ([criteria](../criteria.md)).
- Sampling `ORDER BY id DESC` surfaces test rows (TM…, 0012345678…) — use a shape filter.

## Test harnesses
- **A test that cannot fail is not evidence** — prove each check with a negative control.
- If a harness constructs a key, **assert the round trip**. Discovery must mirror the predicates of the query it feeds.
  Never judge fallback data against the intended expectation — mark SKIP.
- A **0-byte script exits 0** — check file size after creating scripts; add a "NOTHING RAN" guard.
- A regression guard must **own its evidence** (deterministic ORDER BY), not depend on drifting live data.
- A **live witness drifts**: A/B on one connection seconds apart; compare row **sets**, not counts.
- **Compiling is not executing** (`SET NOEXEC ON` hides real defects; ODBC -155).
- A green check proves only what it **covers** — print its scope and what it cannot check. A phantom failure is
  worse than no check. Mis-scoped checks create false gaps.
- **Shape-based sweeps miss shapeless defects** — only column-by-column comparison finds a wrong ordinary column.

## Fixing
- **Reapply a fix as a rule, not a text substitution**: ask where the same *mistake* appears in other clothes; report
  where the rule did **not** apply, and why.
- **Diagnosis ≠ prescription**: a tiebreaker that makes a tie disappear may pick the wrong value; find the missing
  attribute (IRA V7: `prtmst.vc_itmgrp`). Consistency without correctness is wrong.
- **A fabricated runtime input is worse than a fabricated value** — it silently narrows scope.
- **Placeholders must be impossible to mistake for data** (`'<UNMAPPED>'`, typed NULL), never `'0/0'`.
- `int/int` truncates on SQL Server where Oracle NUMBER does not — cast before dividing.
- **Never sanitise data** (`encode('ascii','replace')` turned Greek addresses into `?????`). Sanitise only the console.
  Watch NBSP (U+00A0) in master data.
- **Never hand-edit a generated artefact** — fix builder + data, rebuild, re-verify.

## Citing
Every answer cites file + section (+ line). Distinguish `[DB]`, `[EXPERT]`, `[DOC]`, `[LEARNED]`, `[INFERRED]`, `[GENERAL]`
(see [AGENTS.md](../../AGENTS.md) §2).
