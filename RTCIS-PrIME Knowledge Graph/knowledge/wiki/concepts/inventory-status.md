---
title: Inventory / QA status
type: concept
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/kb/ALL_LEARNINGS.md]
evidence: [results/map_inventory_fields.json]
updated: 2026-10-20
---
# Inventory status

RTCIS lot QA status `QASTAT` and PrIME inventory status `invdtl.INVSTS` are **different vocabularies** on different
objects (RTCIS: on the lot; PrIME: on the inventory detail).

| RTCIS QASTAT | PrIME INVSTS | Agreement (same pallets, DE08) |
|---|---|---|
| RL (released) | U (unrestricted) | 97% |
| HD (hold) | B (blocked) | 88% |
| QU (quality) | Q | — |

Return the **PrIME code** and document the translation in the header; `compare.py` translates before comparing.
Correlation of codes is not proof of equivalence. Sites may have further statuses; profile with
`SELECT INVSTS, COUNT(*) FROM dbo.invdtl GROUP BY INVSTS` and read `dscmst` `COLNAM='invsts'`. No damage INVSTS was
found at Amiens (only U/B/Q).
