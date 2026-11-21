---
title: Conversion lessons (RPM + Euskirchen)
type: learning
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md, raw/kb/ALL_LEARNINGS.md, raw/schema/translation-learnings.json]
evidence: [results/compare.json, results/map_inventory_fields.json]
updated: 2026-10-20
---
# Conversion lessons

1. **Measure, don't name-match.** `rcvtrk.TRKREF` looked like a load reference; it is the supplier name. The load
   reference is `rcvinv.WAYBIL`. ([data-facts](../ground-truth/data-facts.md) #13)
2. **Receiving UOM, not STKUOM.** ([receiving-uom](../concepts/receiving-uom.md))
3. **Euskirchen subsites collapse** into one PrIME warehouse; old subsite = building. ([building-subsit](../concepts/building-subsit.md))
4. **The area code carries the hall.** `LEFT(ARECOD,2)` = RTCIS pick zone / hall; infix `FP`/`PM` = item class.
5. **Line = location type, not area.** ([line-supply](../concepts/line-supply.md))
6. **Status vocabularies differ.** Return PrIME codes and document the translation. ([inventory-status](../concepts/inventory-status.md))
7. **Some RTCIS concepts do not exist in PrIME** (after a synonym-space search): pre/post-count flags, item category,
   group FIFO window, SU factor, put-away zone list per building, MANLID event. Return NULL `[ELIMINATED]` and raise
   the decision ([open-decisions](../open-decisions.md)) — do not approximate.
8. **ODBC -155** is a driver limit, not a SQL error. ([connect](../connect.md))
9. **Wrappers hide Oracle.** `SYS_get_RTCIS`/`SYS_get_DAS`/`OpenQuery` carry Oracle text with `{n}` placeholders and
   doubled quotes; transliterate before judging. DAS is a history archive, not on the replica. ([method](../method.md))
10. **Downstream queries** (R12 on `RPM_System`) need no rewrite once their feeders are converted.
11. **Execution ≠ equivalence.** Graded only after same-object comparison. ([criteria](../criteria.md))
12. **Every RTCIS original file may have a second statement after `/*END*/`** — convert it too, and check the
    deliverable contains what the report claims (analysed-in-report ≠ shipped-in-artefact).
13. **Two queries were delivered the wrong way round** (Euskirchen Q02/Q11): verify header/item roles from the Oracle source.
14. **Scalar aggregates invent answers** (Q06 `IsPartial`): an aggregate over zero rows returns a row.
15. **`subsit='1'` is a site number, not a constant** — parameterise as warehouse.
16. **`CONCAT()` turns NULL into ''** — a missing setup printed a bare `/`; guard with CASE.
17. **Scanned-pallet queries need LEFT JOIN** for new joins, or a pallet with no list-pick work vanishes from the label run.
18. **Never hard-code a measured count into prose** — row counts are perishable snapshots; regenerate.
19. **The HTML may render cached SQL** — rebuild the data JSON after editing delivered SQL.
20. **Pass must be graded**, never boolean ([criteria](../criteria.md)).
21. **Match the original's data type, not just its value.** RTCIS quantities are `numeric(22,0)`; a correct division
    still disagrees when PrIME keeps 1/1000 units. Read `sys.columns` precision/scale of every original output.
22. **Measure the unit before declaring absence.** Pallet height was declared unmappable after assuming metres; PrIME
    dims are cm and the mapping exists. Test the unit on an item class with real data (FERT), then check placeholders
    (`1 × 1 × 1`) on the class you need ([pallet-dimensions](../concepts/pallet-dimensions.md)).
23. **Use the house reference queries** (CL_LATEST, IRA) as a second witness for location/count logic — they gave R17 a
    better item-class rule ([cl-ira-references](../sources/cl-ira-references.md)).
24. **A new join can wreck the plan**: two pre-aggregated CTEs joined into a 28k-row query took >5 min at DE08 until
    `LEFT HASH JOIN` — time every changed query on the target, not only the probe.
25. **Check every field, not every query** (2026-10-21): `field_check.py` lists 212 output fields with source, fill % and
    agreement. 44 were empty or mismatched; probing each found 3 real defects the query-level checks missed.
26. **"Filled" is not "right"**: R05/R06 door was 100% filled with `trlr.STOLOC` = the trailer's own id (TRL0000302, type
    DSPCH). The door is `trlr.YARD_LOC` (DOOR16/17, type RSDK). Always read sample values next to the percentages.
27. **Pick a column that is actually populated**: R16 `invlod.LSTDTE` is set on 303 of 97,793 DE08 pallets (only after a
    move) → `COALESCE(LSTDTE, ADDDTE)`. Probe the fill rate of the chosen column and its alternatives before mapping.
28. **Two blanks are not a match**: R07 Vendor Lot "agreed" 8,792/8,792 because both sides were empty. Agreement now
    excludes both-blank pairs.
29. **Test like for like**: the R06 PrIME test load held a FERT item, so the packaging-only fields came back NULL — exactly
    as the original would. Choosing a packaging receipt at a door (as RTCIS did) filled them.
30. **Location differences are mostly naming, not moves**: 11,142 of 13,588 differing Euskirchen pallets sit in CIMAT
    automated-store bins that do not exist as PrIME locations; only 1,692 moved.

See also [verification-discipline](verification-discipline.md), [prime-anti-patterns](prime-anti-patterns.md),
[ruiz-rs-obs](../experts/ruiz-rs-obs.md). Older learnings (IRA V5–V9, London, Athens schema, M&M bot, codebook value
maps) are summarised in [kb](../sources/kb.md).
