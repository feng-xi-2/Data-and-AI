---
name: rtcis-prime2022-masterdata
description: "Transform / migrate / validate warehouse master data from RTCIS (2014, Oracle) into PrIME 2022 (Blue Yonder / Puma, SQL Server) — items, locations, areas, zones, location types, lots, policies. USE WHEN: migrating a site's master data to PrIME 2022; building or fixing the RTCIS→PrIME 2022 transform; designing or validating Areas / Storage Zones / Pick Zones / Movement Zones / Work Zones / Location Types; mapping RTCIS ARECOD/ZONCOD/LOCTYPE to the 2022 5-framework model; reconciling a mechanical transform against a team-filled Site Configuration Model; questions about the Minhang (BR01) or Athens (WMD1) master-data transform. Trigger phrases: 'transform Minhang masterdata', 'RTCIS to PrIME 2022', 'area zone location transform', 'PrIME 2022 zones', 'Site Configuration Model', 'validate the transform', 'loc_typ / sto_zone / pck_zone / mov_zone / zonmst'."
---

# RTCIS → PrIME 2022 Master-Data Transformation

Domain skill for migrating warehouse master data from **RTCIS** (2014, Oracle) to
**PrIME 2022** (Blue Yonder / "Puma", SQL Server). Covers items, locations, areas,
the 5-framework zone model, lots, and policies — plus the hard-won lesson that a
mechanically-correct transform is **not** a business-correct one.

> **Authoritative references (read these for detail):**
> - Full rule checklist (13 sections, citation-backed): [kb/PRIME2022-AREA-ZONE-LOCATION-NAMING-CHECKLIST.md](../../../kb/PRIME2022-AREA-ZONE-LOCATION-NAMING-CHECKLIST.md) (+ `.html`)
> - Repo memory: `/memories/repo/minhang-rtcis-masterdata-to-prime2022.md`
> - Codebook value maps: `/memories/repo/mm-bot-rtcis-prime-codebook-mappings.md`

---

## 0. THE #1 LESSON — read before doing anything

**A transform can be 100% structurally valid yet ~0% consistent with the business design.
Structural validity ≠ design correctness.**

The Minhang mechanical transform (areas/zones/loc-types derived straight from RTCIS
`ARECOD`/`ZONCOD`/`PIKZON`) passed **100% structural validation** (all FKs resolve, 8,299
locations, VELZON clean) but scored **near-zero overlap** with the team-authored design:
**AREA 0/11, LOC_TYPE 0/43, STORAGE-ZONE 1/23 (~4%)**.

**The 2022 taxonomy is a BUSINESS REDESIGN, not a field-rename of RTCIS codes.**

### The correct path
1. Use **RTCIS only to populate MEMBERS** — which physical locations exist and their dims.
2. Take the **TAXONOMY (areas / zones / loc-types) from the site's Site Configuration Model** —
   that workbook is the **target ground truth**. Athens + RTCIS are references only.
3. **Map each RTCIS location onto the business codes** by *building + material + handling intent*,
   not by carrying the old code across.
4. **Validate the generated taxonomy against the site's filled Site-Config workbook**, not just
   against Athens structure + RTCIS values.

> Before prescribing any fix, ask: *"Does this produce the CORRECT answer, or just A consistent
> answer?"* Consistency without correctness is wrong (Diagnosis-vs-Prescription rule).

---

## 1. The 2014 → 2022 structural model

PrIME 2022 replaced the single all-powerful 2014 **Area** with a **5-framework split +
Pick Methods**. Any 2014 rule that said "the area used to…" now points at one of these:

| 2014 Area attribute set | 2022 framework | PrIME table | Surrogate-ID base (Minhang) |
|---|---|---|---|
| Storage attributes | **Storage Zones** | `sto_zone` | 40001 |
| Picking attributes | **Pick Zones** | `pck_zone` | 50001 |
| Movement / staging / hand-off / PND | **Movement Zones** | `mov_zone` | 30001 |
| Work balancing / congestion / travel-seq | **Work Zones** | `zonmst` | 60001 |
| General flags (~41 area flags) | **Location Types** | `loc_typ` | 20001 |
| Area UOMs + pick release + verification | **Pick Methods** | `pck_mthd` | — |

- **SAP movements stay at AREA level, not zone level.** Areas remain the tag used to send
  inventory-movement (IM) transaction types (309/311) to SAP. Only **IM locations** emit them;
  normal storage sends nothing.
- **Area now holds only ~11 info-only fields** (`aremst`: `ARECOD, WH_ID, BLDG_ID, LOST_LOC,
  LOGIC_FLG, BU_ID, IS_PURGED` + audit). Storage/pick flags moved to `locmst` / zones / `loc_typ`.
- **Platform Oracle → SQL Server.** `SELECT *` breaks — always list columns explicitly.

---

## 2. The correct taxonomy — each framework's real design intent

Derived from the Minhang Site Configuration Model (the RIGHT way). Never invent codes.

- **AREAS = physical/plant dimension** (buildings/floors/plants): `P1MAINWH`主仓, `P1TC9`,
  `P1DGWH`周转仓, `P1RESIN`树脂仓, `P1CHEMICAL`化学品仓, `P3HWCK`恒温恒湿仓, `P3F1/F2/F3`三厂1/2/3层,
  `REMOTEWH`外仓, `REMOTEDGWH`危险品外仓. **NOT** RTCIS functional `ARECOD` (`RO`/`ST`/`HP`/`RF`/`DO`).
  Do **NOT** map `ARECOD` 1:1 to a PrIME Area — that conflates two orthogonal dimensions.
- **LOCATION TYPES = STANDARD PrIME catalog (43 codes)**: `ADJS, ASRS, AUDIT, DKIT, DSPCH, EXPR,
  HFPE, IMAR, IMQM, NEAR, NSTO, PND, PROC, PROD, PRST, PSTA, PSTD…`. Never invent (`RACK`,
  `STAGING`, `HANDOFF`) — invented codes don't integrate with PrIME behaviour flags/strategies.
- **STORAGE ZONES = storage strategy + material handling**: `SZ-VNA` (堆高车), `SZ-CSPICK`
  (固定拣货), `SZ-M-RESIN` (塑料粒子), `SZ-*-WIP`, `SZ-CHEMICAL`, `SZ-DG`, `SZ-P3-1F/2F/3F`,
  `SZ-REMOTE`. **NOT** RTCIS product-zone clones (`SZ-M1..M9`) — only `SZ-DG` matched by luck.
- **PICK ZONES = a small set of picking-method zones (~3)**: 散拣区 (case-pick), 补货区
  (replenishment), 整板区 (full-pallet). Do **NOT** clone one `PZ-*` per `ZONCOD`.
- **MOVEMENT ZONES = equipment-transition / deposit flows**: "PnD from VNA forklift to pallet",
  "PnD from pallet jack to VNA", "receiving staging". See the *Movement Zone Next Move* sheet.
  **NOT** 1:1 area mirrors.

---

## 3. Naming conventions (quick reference)

- **Area codes** (`ARECOD`, ≤10 chars): product names (`LIQUID, PAPER, POWDER`), functional
  mnemonics (`ADJS, SHIP, DSPCH, EXPR, XDDR, DKIT, DOCK, YARD`), or building-scoped suffix `|B1`.
- **Zone codes** mirror the area: `SZ-<AREA>` (storage), `PZ-<AREA>` (pick), `MZ-<AREA>` (move);
  work zone `WZ<rowNN>-<sub>`. Logical zones reuse the mnemonic directly.
- **Location codes** (`STOLOC`): rack pattern `<row2+letter><pos3>L<level><depth>` e.g.
  `05B052L3BB`; depth/face suffixes `BB/SR/GF/GR/LP` (GF/GR = pickable forward faces, VELZON `Z`);
  logical `L`+19 zero-padded chars.

---

## 4. Assignment order & rules

Order for a new location: **Building → Area → Location Type → (Storage/Pick/Movement/Work)
Zones → velocity/aisle/flags.**

- Group **by area** when the driver is the **SAP IM transaction type**; group **by zone** when
  the driver is **functional behaviour**.
- One **storage zone per storage area**, assigned to every storage/case-pick location in it.
- **Pick zone only on pickable locations**; storage-only bulk gets none.
- **Work zone only on directed-work locations**; logical/dock may have none.
- **Logical locations** (`LOGIC_FLG=1`: `ADJS, DKIT, DSPCH, EXPR, SADJ, SHIP, WEXP, XDDR`) get
  **no `MOV_ZONE_ID`** (mirrors Athens' 561 null-mov-zone pattern).
- **Put-away** = source move-zone + item family → destination storage-zone (2-level).
  **Allocation/pick** = destination → source via pick zones + pick methods (2-level).

---

## 5. Pipeline (scripts in `SQL_Translations/_mm_audit/`)

| Stage | Script | Output |
|---|---|---|
| Discover RTCIS | `_md_01_discover_rtcis.py` | `_md_rtcis_catalog.json` (292 tables, test3) |
| Extract Athens target | `_md_02_extract_athens.py` | `_md_athens_prime2022.json` (21/26 targets) |
| Probe values | `_md_03_probe_values.py` | `_md_rtcis_values.json` |
| Crosswalk config | (hand-authored) | `_md_crosswalk.json` |
| **Transform** | `_md_04_transform.py` | `output/PRIME2022_MINHANG/*.csv` + `_manifest.json` |
| Structural validate | `_md_validate.py` | FK coverage, orphans, VELZON, WH_ID sweep |
| Accuracy audit vs RTCIS | `_md_accuracy_check.py` | source-of-truth audit (100%) |
| Business-design consistency | `_md_consistency_vs_siteconfig.py` | `_consistency_vs_business.csv` |
| Side-by-side w/ team | `_md_transform_vs_team.py` | `_transform_vs_team.csv` |
| WH_ID sweep | `_md_verify_whid.py` | confirms BR01, 0 legacy WMH1 |
| Dump business design | `_md_dump_siteconfig.py` | Site-Config taxonomy |

**Note:** `_db_minhang.py` lives in `_MM_TRANSFER_PACK/05_tools_engine/` — add to `sys.path`.
The Pylance MCP tends to hang; run Python via the terminal interpreter instead
(`C:/Users/feng.xi.2/AppData/Local/Python/pythoncore-3.14-64/python.exe`).

---

## 6. Domain crosswalk (RTCIS → PrIME 2022)

| RTCIS source | PrIME 2022 target |
|---|---|
| `ITMMST + ITEM_UOM(base) + ITEM_CONFIG + SUBITM + ITMGRP` | `prtmst` (item head; `VC_ITMGRP←ITMGRP`) |
| `ITEM_UOM` (each UoM tier) | `prtftp` (footprint per UoM; `CASLVL←BUOMNUM`, dims) |
| `ITMMST/BLDITM` activity | `prtmst_wh` (item×wh) |
| `ITMDSC / ITMGRP.GRPDSC` | `prtdsc` |
| `CTLGRP` (lot/control) | `prtlot` (`MANDTE, EXPDTE, DEF_INVSTS`) |
| `LOCATN` | `locmst` (`ARECOD, STOFLG, PCKFLG`, dims) — **members only** |
| `ARECOD` (distinct) + `BLDING` | `aremst` — **members only, NOT the taxonomy** |
| `ZONCOD` (split by `ZONE_TYPE`) | `zonmst` / `pck_zone` / `sto_zone` |
| `SYSPAR` | `poldat` |
| `CARRIER / CUSTMR / VNDCOD` | `car_move / cstmst+adrmst / vendor` (NOT yet transformed) |

**Value maps:** `ITMCLS F/P/R/S/U → TYPCOD FERT/ZPAL/ROH/HALB/UNBW`;
`QASTAT RL/HD/QU → DEF_INVSTS A/H/Q`; `HAZMAT → flag`.
RTCIS and PrIME area/zone value sets differ entirely — **no 1:1 value crosswalk**, remap by intent.

---

## 7. CRITICAL structural pattern — TEMPLATE + WAREHOUSE dual rows

PrIME 2022 stores each part / ftp / policy **TWICE**:
- a **TEMPLATE** row (`WH_ID_TMPL='----'` or `WH_ID='----'`) = global default
- a **WAREHOUSE** row (`WH_ID_TMPL='BR01'` / `WH_ID='BR01'`) = site override

So 1 RTCIS item → 2 `prtmst`, 2 `prtmst_wh`, 2 `prtftp` (per FTP tier) rows.
`PRT_CLIENT_ID='----'` = single-client. **This dual-row model MUST be reproduced.**

---

## 8. Site facts (Minhang / BR01)

| Fact | Value |
|---|---|
| **Go-live `WH_ID`** | **`BR01`** (confirmed; Site Config Model 2026-06-14, SAP Storage Location = BR01) |
| SAP Plant / Ship Point / Legal Entity | 8493 / CN93 / 2008 |
| Source DB | Oracle **19c Enterprise Edition 19.0.0.0.0**, schema `TEST3`, python-oracledb 4.0.1 thin |
| Source connect | `connect_minhang("rtcis", env="test3")` |
| Target reference | Athens `ATHENS_REPLICA`, `wh_id=WMD1`; `connect_athens()` (tables are SYNONYMS → use `SELECT TOP 0 *` for columns) |
| Business design (GROUND TRUTH) | `MM Toolbox/Minhang_M&M/01_ Site Data/PrIME202X Site Configuration Model - MH - 2026.6.14.xlsx` |
| Filled MDL templates | `MM Toolbox/Minhang_M&M/01_ Site Data/Master Data - PrIME 2022/` |

**Resolved open confirmations** (meeting record + Site Config Model 2026-06-14):
1. Go-live `WH_ID = BR01`.
2. Split `ZONCOD` → storage + pick zones = **YES** (23 storage zones + 3 picking-method pick zones).
3. IM locations = dedicated `IMAR` + `IMQM` location types.
4. Logical-location mov-zone exemption = **YES** (single building BR01).

**Note:** `14_Location Template` is NOT filled for Minhang (only 2 ES30 examples). The team's real
deliverable is the **taxonomy** in the Site Config Model, not per-location assignments.

---

## 9. Current transform output (validated 2026-07-06, `wh_id=BR01`)

Output dir: `SQL_Translations/_mm_audit/output/PRIME2022_MINHANG/`. **309,494 total rows.**

| Table | Rows | | Table | Rows |
|---|---|---|---|---|
| prtftp | 136,264 | | prtmst / prtmst_wh | 45,048 each |
| prtlot | 51,430 | | prtdsc | 22,524 |
| locmst | 8,299 | | poldat | 818 |
| aremst / zonmst / loc_typ | 7 each | | sto_zone / pck_zone | 19 each |
| mov_zone | 4 | | | |

**Validation status:** structural = PASS (0 orphan FKs, WH_ID=BR01 everywhere, 0 legacy WMH1);
accuracy vs RTCIS = **100.00%** (8,299/8,299); business-design consistency = **~0% (EXPECTED)** —
the transform is technically correct but still needs the semantic remap of §0/§2 before load.

---

## 10. Validation checklist (run in this order)

1. `_md_validate.py` — FK coverage, orphans, VELZON, WH_ID sweep → all resolve.
2. `_md_accuracy_check.py` — every generated row traces back to RTCIS source → 100%.
3. `_md_verify_whid.py` — confirm target `WH_ID` everywhere, 0 legacy placeholder.
4. `_md_consistency_vs_siteconfig.py` — **the real gate**: compare taxonomy to the Site-Config
   workbook. If overlap is low, the transform is structurally right but **design-wrong** — do the
   §0 semantic remap before declaring it load-ready.

> Passing 1–3 but failing 4 is the classic trap. Structural validity ≠ design correctness.
