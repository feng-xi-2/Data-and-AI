# Index

Catalog of every wiki page. Read this first, then open what you need. Conventions: [AGENTS.md](AGENTS.md). History: [log.md](log.md).
Tiers: `[DB]` ground truth › `[EXPERT]` › `[DOC]` › `[LEARNED]` › `[INFERRED]`.

## Start here
- [Overview](wiki/overview.md) — the problem, what has been done, how knowledge is organised.
- [Objectives](wiki/objectives.md) — business goal, wiki goals, success criteria for one query.
- [Open decisions](wiki/open-decisions.md) — 10 business decisions the site key user must take.

## Ground truth (measured in the databases)
- [Endpoints](wiki/ground-truth/endpoints.md) — servers, databases, schemas per site key; one replica = one warehouse.
- [Mappings](wiki/ground-truth/mappings.md) — RTCIS → PrIME columns/values with agreement % on the same pallets.
- [Data facts](wiki/ground-truth/data-facts.md) — 21 measured facts: synonyms, collation, retention, DEV data, integer quantities, cm dims.

## Criteria and method
- [Criteria](wiki/criteria.md) — hard criteria, mapping tags, grades A/B/C/D, EMPTY/BLOCKED/SKIP.
- [Method](wiki/method.md) — 10-step conversion, wrapper classification, Oracle→T-SQL, house SQL rules.
- [Connect](wiki/connect.md) — MSAL device-code auth, ODBC 18, token cache, client gotchas.
- [Tools](wiki/tools.md) — catalog of `tools/` (run, compare, audit, report, lint).
- [Report](wiki/report.md) — tabbed HTML template, six-step tab layout, self-checks.

## Experts and learnings
- [RUIZ.RS (Gino) OBS1–8](wiki/experts/ruiz-rs-obs.md) — expert rules, how they were applied, declared deviation.
- [Conversion lessons](wiki/learnings/conversion-lessons.md) — 20 lessons from RPM + Euskirchen label work.
- [Verification discipline](wiki/learnings/verification-discipline.md) — absence claims, grain, zeros, harness traps, fixing, citing.
- [PrIME anti-patterns](wiki/learnings/prime-anti-patterns.md) — discriminated dimension rows (locale, UOM, WH_ID_TMPL).

## Concepts
- [Receiving-UOM factor](wiki/concepts/receiving-uom.md) — `RCV_FLG=1` reproduces RTCIS UOM/qty; FLOOR to RTCIS integers.
- [Line supply](wiki/concepts/line-supply.md) — line = location type `PROD`; 43/43 ULIN map.
- [Building / subsite](wiki/concepts/building-subsit.md) — DE07/DE08 → B1/B2; hall = `LEFT(ARECOD,2)`.
- [Inventory status](wiki/concepts/inventory-status.md) — QASTAT RL/HD/QU vs INVSTS U/B/Q.
- [Pallet ID](wiki/concepts/pallet-id.md) — ULID20 = LODNUM; 19 vs 20 chars (GS1 check digit).
- [Grain and fan-out](wiki/concepts/grain-and-fanout.md) — dual rows, OUTER APPLY TOP 1, OBS8 aggregation.
- [Site-local time](wiki/concepts/site-local-time.md) — UTC replica vs local WMS dates; ODBC -155.
- [Synonyms and facades](wiki/concepts/synonyms-facades.md) — `_REPLICA` synonyms, `_simp` base tables.
- [Pallet dimensions](wiki/concepts/pallet-dimensions.md) — dims in cm, pallet HGT incl. base, DE08 `NONE` placeholders, PAL_STCK_HGT = stack count.

## Entities
- [Tables](wiki/entities/tables.md) — RTCIS → PrIME 2022 table map.
- [Sites](wiki/entities/sites.md) — sites, wh_id codes, roles as target/witness.

## Queries
- [RPM status R01–R17](wiki/queries/rpm-status.md) — rows on 3 engines, agreement, grades, open points.
- [R01](wiki/queries/R01.md) · [R02](wiki/queries/R02.md) · [R03](wiki/queries/R03.md) · [R04](wiki/queries/R04.md) ·
  [R05](wiki/queries/R05.md) · [R06](wiki/queries/R06.md) · [R07](wiki/queries/R07.md) · [R08](wiki/queries/R08.md) ·
  [R09](wiki/queries/R09.md) · [R10](wiki/queries/R10.md) · [R11](wiki/queries/R11.md) · [R12](wiki/queries/R12.md) ·
  [R13](wiki/queries/R13.md) · [R14](wiki/queries/R14.md) · [R15](wiki/queries/R15.md) · [R16](wiki/queries/R16.md) ·
  [R17](wiki/queries/R17.md) — per-query evidence pages (generated block + notes).
- [Euskirchen label set Q01–Q18](wiki/queries/euskirchen-label-set.md) — label-printing conversion, expert remediation, state.

## Sources (summaries of raw/)
- [Complete reference](wiki/sources/complete-reference.md) — Pomezia-era 52 tables / 64 columns, rules, what is stale.
- [KB and schema JSON](wiki/sources/kb.md) — kb/, remediation knowledge, verified-mappings / data-model JSON.
- [Queries](wiki/sources/queries.md) — RPM originals, Euskirchen label originals + deliverables, PrIME 2022 house samples.
- [Expert SQL](wiki/sources/expert-sql.md) — RUIZ.RS review files.
- [CL / IRA references](wiki/sources/cl-ira-references.md) — house countable-location and IRA queries per engine; rules reused in R17.
- [Memories](wiki/sources/memories.md) — dated session learnings (newer supersedes older).
- [Timbr](wiki/timbr.md) — semantic layer: files, API facts, traps, no-touch rule, link to converted SQL.
