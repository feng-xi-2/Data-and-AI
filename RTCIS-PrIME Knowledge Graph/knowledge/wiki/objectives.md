---
title: Objectives
type: objective
status: documented
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/kb/RTCIS-TO-PRIME-ARCHITECTURE.md, raw/kb/FLOW-2-RTCIS-TO-PRIME-REMEDIATION.md]
evidence: []
updated: 2026-10-20
---
# Objectives

## Business objective
Keep every site report, label and downstream feed working when a warehouse moves from RTCIS to PrIME 2022, with the
**same output contract** (columns, order, meaning, units, grain) so consumers (SSRS, Power BI, RPA, label printers,
`RPM_System`) need no change. `[DOC]` raw/reference §7 rule 12.

## Objectives of this wiki
1. **Reuse** — any colleague opens this folder in VS Code and an agent can connect, convert and prove a query without
   re-discovering endpoints, gotchas or mappings.
2. **Ground truth first** — every mapping carries a measured agreement rate on the same physical objects
   ([mappings](ground-truth/mappings.md)); untested mappings are visibly tagged.
3. **Expert knowledge captured as rules** — site-expert reviews become automated checks
   ([ruiz-rs-obs](experts/ruiz-rs-obs.md), `tools/audit_expert_rules.py`).
4. **Honest status** — grade A/B/C/D ([criteria](criteria.md)); list business decisions the site must take
   ([open-decisions](open-decisions.md)).
5. **Compounding** — each conversion, question and lint adds to the wiki ([log](../log.md)).

## Success criteria for one converted query
- Runs on the PrIME target and a live PrIME witness; identical column contract; 0 expert-rule FAIL.
- Value agreement ≥ 95% on matched keys for grade A, or each gap explained with numbers.
- Tabbed HTML report regenerated; query page in `wiki/queries/` updated; learnings filed.

## Out of scope
Business sign-off (site key user owns it), writing to any database, Timbr DDL deployment without owner approval.
