---
title: Pallet ID (ULID / LODNUM / SSCC)
type: concept
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/expert_verification_rules.md]
evidence: [results/map_inventory_fields.json]
updated: 2026-10-20
---
# Pallet ID

- RTCIS `AGV_INVENTORY_VIEW.ULID20` = PrIME `invlod.LODNUM` **exactly** (20 chars). `[DB]`
- Raw RTCIS `ULID` is **19** chars — the difference is the GS1 mod-10 check digit → `LEFT(LODNUM,19) = ULID`
  (`LODNUM = ULID` gave 0 matches; the fix gave 261/400 — nearly wrote off a whole replica).
- SSCC18 = LODNUM without the leading `00`; a harness that rebuilds `'00' + @sscc18` must assert the round trip.
- 5,211 RTCIS line pallets exist in DE08 `invlod` (migrated) — the same physical pallet exists on both systems,
  which is what makes value-level comparison possible.

Join keys for same-object comparison: `LODNUM = ULID20`, `PRTNUM = ITMCOD`, `LOTNUM = CTLGRP`, `STOLOC = LOCATN`.
Mixed pallets (one pallet, many items) exist on both sides — compare on pallet + item + lot.
