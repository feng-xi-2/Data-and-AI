---
title: Subsite → building, hall and pick zone
type: concept
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md]
evidence: [results/map_inventory_fields.json]
updated: 2026-10-20
---
# Subsite, building, hall

- RTCIS Euskirchen has two subsites: `subsit 0` = DE07 (RPM / packaging), `subsit 1` = DE08 (finished goods). PrIME has
  **one** warehouse `DE08`; the old subsite is the building `aremst.BLDG_ID` `B1` / `B2` (99.2% / 98.9%). `[DB]`
  Filters on `subsit` become building filters (`tools/map_subsit_building.py`).
- `subsit='1'` in originals is a **site number**, not a constant.
- RTCIS hall / pick zone = `LEFT(ARECOD,2)`: X1–X5 → 01–05, P6 → 06, P7 → 07, 2P–4P → 12–14, H2 → 15 (95–100%).
- RTCIS BLDING `0001…0015` ≈ `'00' + LEFT(ARECOD,2)` — 43% overall, 100% on packaging `[INFERRED]`.
- Area infix `FP` → item class F, `PM`/`RP` → P (98%).
- PrIME 2022 moved areas to the 5-framework zone model (storage / pick / movement / work zones, location types) —
  see `raw/kb/PRIME2022-AREA-ZONE-LOCATION-NAMING-CHECKLIST.md`.

Open: which label (`B1`/`B2`, `00xx`, `Halle n`) reports should show → [open-decisions](../open-decisions.md).
