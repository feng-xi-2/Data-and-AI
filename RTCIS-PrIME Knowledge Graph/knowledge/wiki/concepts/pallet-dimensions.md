---
title: Pallet dimensions, footprint and stacking
type: concept
status: verified
sources: [raw/memories/timbr_api.md, raw/queries/rpm/R01_CBO_P_CLASS_INVENTORY_DE07_VIEW.txt, raw/queries/rpm/R06_Beladeschein.txt]
evidence: [results/probe_casqty_height.json, results/probe_sap_pallet_height.json]
updated: 2026-10-20
---
# Pallet dimensions, footprint and stacking

| Concept | RTCIS | PrIME 2022 | Evidence `[DB]` |
|---|---|---|---|
| Pallet type | `item_config.ulpall` / `unitld.ulpall` | `invdtl.FTPCOD` (footprint) | 90% same pallets |
| Dimensions per unit | `item_uom.u_length/u_width/u_height` + `dimuom` (CM) | `prtftp_dtl.LEN/WID/HGT` per UOM level, **centimetres** | FERT CS height = RTCIS 1,718/1,761 (97.6%), DE08 |
| Pallet height | `u_height` of the warehouse unit (+15 cm base when `itmmst.PALFLG='Y'`) | pallet level `HGT` (`PAL_FLG=1`), **base included** | PL HGT = LY HGT × layers + 15 on 15,145/20,141 FERT |
| Pallet footprint L × W | `item_config.udepth` × `uwidth` (80 × 120) | pallet level `WID` × `LEN` (80 × 120) — **orientation swapped** | 17,119/20,257 (udepth = WID, uwidth = LEN) |
| Stacking | `item_config.maxstk` / `ul_maxstk` | `prtftp.PAL_STCK_HGT` = how many pallets may be stacked (≥2 = double-stack) — a **count, not a height** | NPI/Timbr Amiens: user flag vs PAL_STCK_HGT≥2 |

## Traps
- **Units:** an earlier mapping assumed PrIME dims were metres (`HGT*100`) and declared pallet height "no source"; R06
  checked `LEN*100 BETWEEN 120 AND 140`, which can never be true. Both were wrong — dims are cm. Measure the unit on
  an item class that has real data before declaring absence.
- **Placeholders:** at Euskirchen DE08 every packaging (ROH) pallet has footprint `NONE` with `LEN=WID=HGT=1` at all
  levels (4,857 pallet rows, 100%). Treat `<= 1` as missing (NULL / NOK), never as a height. Athens (live) ROH has real
  pallet heights (473 of 539 rows, 10–200 cm) — so it is a DE08 master-data gap, not a PrIME limitation.
- **SAP is not a fallback:** CDL `silver_sap_f6p.marm` (plant 4830 is in f6p) has a `PAL` unit for 3 of 1,624 Euskirchen
  packaging items, and `hoehe` matches RTCIS height on ~1% of rows. marm is the place for pallet **quantity**
  conversion (`umrez/umren`, never umrez alone — Amiens learning), not for packaging heights.
- **Stack height ≠ height:** `PAL_STCK_HGT` drives truck fill (double-stackable pallets) in the NPI/DO work; it is not
  RTCIS `u_height`.

Used by: [R01](../queries/R01.md) (calculated_pal_height), [R06](../queries/R06.md) (Stammdaten check). Related:
[receiving-uom](receiving-uom.md), [mappings](../ground-truth/mappings.md).
