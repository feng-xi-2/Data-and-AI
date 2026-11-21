---
title: Open business decisions
type: decision
status: open
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md, raw/schema/open-questions.json]
evidence: [results/compare.json]
updated: 2026-10-20
---
# Open decisions (owner: Euskirchen key user, with RUIZ.RS)

| # | Decision | Affects | Evidence so far |
|---|---|---|---|
| 1 | Item category (`itmnum` "Categorie"), SU factor, PO number per lot: PrIME source or drop? | R07, R14, R15, R16 | 15 prtmst columns tested 0%; no SU level; PONUMB empty at DE08 |
| 2 | RA vs RO distinction for IRA | R17 | area types PSTO/LOAP/FUPA hold both |
| 3 | Equipment code list | R04 | RTCIS equip classes ≠ PrIME vehicle types |
| 4 | Confirm "move out of a PROD location" is the PrIME return-from-line (MANLID) | R10, R11, R12 | not observable at DE08 |
| 5 | Which building / hall labels reports should show (`B1`/`B2`, `00xx`, `Halle n`) | R01, R07, R17 | `'00'+LEFT(ARECOD,2)` 43% |
| 6 | Group FIFO window (per group in RTCIS, per part in PrIME) | R13 | FIFWIN = 30 everywhere at DE08 |
| 7 | Does the label caller execute the statement after `/*END*/`? | Euskirchen Q01/GetCustCenterData/GetEdeka* | 4 files affected |
| 8 | setupids padding (`001/29` vs `1/29`) | Euskirchen label set | RTCIS prints padded |
| 9 | Quantity: keep receiving-UOM factor (94%) or revert to expert UNTCAS (85%)? And keep RTCIS integer truncation (FLOOR, now shipped) or report the exact PrIME decimal (4250.4 M2)? | R01, R07, R08–R12, R14–R16 | [receiving-uom](concepts/receiving-uom.md) |
| 10 | Packaging footprints at DE08 are `NONE` with 1×1×1 dims: who loads real pallet dimensions (needed for R01 height, R06 Stammdaten) before go-live? | R01, R06 | [pallet-dimensions](concepts/pallet-dimensions.md) |

Older DBA questions (8 answered + 3 new) from the Pomezia work: raw/reference §16 and `raw/schema/open-questions.json`.
When a decision is taken: update this page, the affected [mappings](ground-truth/mappings.md) row, the query SQL, re-run,
regrade and log it.
