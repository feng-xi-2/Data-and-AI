---
title: "Source: RTCIS-TO-PRIME-COMPLETE-REFERENCE.md + conversion agent"
type: source
status: documented
sources: [raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md, raw/reference/rtcis-to-prime-sql.agent.md]
evidence: []
updated: 2026-10-20
---
# Source: complete reference (last updated 2026-07-06)

**What it is:** the consolidated translation reference from the Pomezia work (34/34 Pomezia PASS + 3 vendor queries,
validated on Athens). `rtcis-to-prime-sql.agent.md` is the agent prompt that used it.

**Authoritative for** `[DOC]`: three-systems distinction (§1); expert-verified critical corrections (§2: TRUKIO→`trlr`,
ITMCLS→`prtmst.TYPCOD`, keep CASPIK/CASXFR but flag, no `__b`, APTDAT→`appt.start_dte`); 52 table + 64 column mappings
with HIGH/MED confidence (§3–4); value mappings for filter constants (§4); join paths incl. ORDDTL→TRUKIO 5-hop bridge
and ORDNUM path (§5, §17); concept maps and footprint hierarchy (§6); SQL translation rules incl. output equivalence and
9-pass column matching (§7); PrIME 2014→2022 changes, areas→zones (§8); Athens schema quirks and view catalogue (§9);
29 active learnings (§11); pre-flight checklist and column decision tree (§14); DBA questions (§16).

**Stale / superseded:**
- Pipeline sections (§12, §18) describe archived scripts (`_translate_universal.py`, PS1 retry) — the active path is
  this wiki's [method](../method.md) + tools.
- Column-name-based "no equivalent" verdicts predate the [verification-discipline](../learnings/verification-discipline.md)
  absence rule — re-check by value domain / synonym space.
- Euskirchen-measured rules in [mappings](../ground-truth/mappings.md) win for Euskirchen (e.g. receiving UOM vs
  footprint `UNTCAS`, line = location type).

The older copy at `RTCIS-PrIME-Remediation/agent/` (49 KB) is superseded by this one (50 KB, `.github/agents`).
