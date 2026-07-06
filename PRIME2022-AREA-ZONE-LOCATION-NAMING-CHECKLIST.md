# PrIME 2022 — Area / Zone / Location / Assignment / Naming Rules Checklist

**Purpose:** Complete, citation-backed checklist of every rule governing **Areas, Zones,
Locations, their Assignment, and Naming** in PrIME 2022 (Blue Yonder / "Puma").
Built for the Minhang RTCIS → PrIME 2022 migration, grounded in the live Athens
reference site (the only P&G PrIME 2022 replica available to us).

**Citation legend**
- `[DB-ATHENS]` = verified by live query on `ATHENS_REPLICA` (server `sqlwrhathensprod…`, schema `dbo`, `wh_id='WMD1'`), July 2026.
- `[TRAIN]` = *PrIME 2022 Capability DB Model Change Training.docx* (P&G, 26-Sep-2024), distilled in [RTCIS-PrIME-Remediation/knowledge/training-transcript-knowledge.md](../RTCIS-PrIME-Remediation/knowledge/training-transcript-knowledge.md).
- `[WI-FAC]` = *WI 02-01-01 Facility Configuration Module.pptx* (Sample Data RTCIS PRIME/SDC/).
- `[WI-ZON]` = *WI 02.01.10 Zoning Category Configuration.pptx*.
- `[SDC-ZON]` = *SDC Op Std 2.1.1A Zoning General.docx*.
- `[SDC-STD]` = SDC Configuration Standards (distilled in repo memory `mm-bot-sdc-security-deployment.md`).
- `[RECAP]` = Minhang M&M meeting transcripts, `MM Toolbox/Minhang_M&M/07_M&M Video, Transcript and Recap/` (6.15–6.18, 2026).
- `[GLOSS]` = Expert domain glossary (repo memory `mm-bot-rtcis-prime-glossary.md`, Mar 2026).
- `[GENERAL]` = general WMS/domain knowledge (not a workspace doc).
- `[INFERRED]` = logical inference from the cited facts.

> **Scope note:** PrIME 2022 replaced the single, all-powerful 2014 **Area** with a
> 5-framework split (Storage Zones, Pick Zones, Movement Zones, Work Zones,
> Location Types) + Pick Methods. Any rule that says "the area used to…" now points
> at one of those frameworks. `[TRAIN §1]`

---

## 0. The 2014 → 2022 structural change (read first)

- [ ] **0.1** In 2014, `aremst` held ~105 fields and drove storage, picking, put-away and movement all at once. In 2022 `aremst` keeps only ~11 information-only fields; area is now largely a **grouping / SAP-movement tag**. `[TRAIN §1]` `[DB-ATHENS: aremst has 14 cols, all admin/flags]`
- [ ] **0.2** Area functionality was split into **4 zone frameworks + Location Types**: `[TRAIN §1]`
  | 2014 Area attribute set | 2022 framework | PrIME table |
  |---|---|---|
  | Storage attributes | **Storage Zones** | `sto_zone` |
  | Picking attributes | **Pick Zones** | `pck_zone` |
  | Movement / staging / hand-off / PND / consolidation | **Movement Zones** | `mov_zone` |
  | Work balancing / congestion / travel-seq | **Work Zones** | `zonmst` |
  | General flags (~41 area flags) | **Location Types** | `loc_typ` |
  | Area UOMs + pick release + pick verification | **Pick Methods** | `pck_mthd` |
- [ ] **0.3** **SAP movements stay at AREA level, NOT zone level.** Areas remain the key used to send inventory-movement (IM) transaction types (e.g. 309/311) to SAP. `[TRAIN §1]` `[RECAP 6.15_2 @1:04–1:08 – Lachica]`
- [ ] **0.4** The 2014 "Picking area" concept (grouping areas for FIFO) **disappears** → replaced by Pick Zones. The "List-pick flag" leaves the allocation search path → now a **work-assignment** attribute in **Pick Methods**. `[TRAIN §1, §3]`
- [ ] **0.5** Put-away & allocation strategies are now **2-level hierarchies** (Put-away: source Move Zone + item family → destination Storage Zone; Allocation: destination → source referencing Pick Zones + Pick Methods). `[TRAIN §2, §3]`
- [ ] **0.6** Platform changed **Oracle → Microsoft SQL Server**; `SELECT *` will break because location/area tables gained new zone columns — always list columns explicitly. `[TRAIN §5, §9]`

---

## 1. Building rules (`aremst.BLDG_ID` / Building Maintenance)

- [ ] **1.1** Every area and location belongs to a **Building** (`BLDG_ID`). At Athens all areas are `B1`. `[DB-ATHENS: aremst.BLDG_ID='B1']` `[WI-FAC slide 4]`
- [ ] **1.2** Buildings carry **Storage Building Sequences** (where the system tries to store, in order, spilling to the next building when full) and **Pick Building Sequences** (where the system tries to find stock to fill an order). `[WI-FAC slide 5]`
- [ ] **1.3** Building has an **Allow Fluid Loading** flag (pick directly onto trailer without staging). `[WI-FAC slide 4]`
- [ ] **1.4 (Minhang)** Physical footprint = **3 buildings** (B1/B2/B3 on Wu Chen Rd) + a remote WH + a dangerous-goods remote WH (~3 km away). Building sequences must reflect this multi-building layout. `[RECAP 6.15_1 @5:37]`

---

## 2. AREA rules (`aremst`)

### 2a. Definition & mandatory attributes
- [ ] **2.1** `aremst` PK = `ARECOD` + `WH_ID`. Columns are minimal: `ARECOD, WH_ID, BLDG_ID, LOST_LOC, LOGIC_FLG, BU_ID, IS_PURGED` (+ audit). **No storage/pick flags live on the area anymore** — they moved to `locmst` / zones / `loc_typ`. `[DB-ATHENS: aremst 14 cols]` `[athens-2022-schema-findings memory]`
- [ ] **2.2** Athens has **94 areas** for one warehouse. Expect a comparable order of magnitude per site. `[DB-ATHENS: COUNT(aremst)=94]`
- [ ] **2.3** Flags that were on 2014 `aremst` now live elsewhere: `pckflg → locmst.PCKFLG`, `stoare_flg → locmst.STOFLG`, `shp_dck_flg → loc_typ.SHP_DCK_FLG`; `pdflg`, `cntflg` **removed**. `[athens-2022-schema-findings memory]`

### 2b. Area purpose classes (what an area is *for*)
- [ ] **2.4** Areas are defined for: **Storage, Production Operation, Controlling, Staging, Dock-Door Operations, ESI (logical) Locations, and Project-Specific Locations.** `[WI-FAC slide 6]`
- [ ] **2.5** The 2014 area "General Attributes" (now realized via Location Type category) enumerate the valid area purposes: Storage, Pickup-and-Deposit (PnD), Processing, Ship Staging, Receiving Staging, Receiving Dock, Shipping Dock, Production Line, Production-Line Staging, WIP, WIP Supply, Put-to-Store, Distribution Processing, Pre-Stage, Cross-Dock, Storage Trailer, Yard, Shipment, Dispatch, Expected Receipts, Adjustments. `[WI-FAC slides 9-11]`
- [ ] **2.6** **`LOGIC_FLG = 1` ⇒ logical area** (no physical footprint — used only to *display* inventory in a state). At Athens the logical areas are: `ADJS, CADJ, DADJ, SADJ` (adjustments), `SHIP, DSPCH` (shipment/dispatch), `EXPR, WEXP` (expected receipts), `SXFR, XDDR, DKIT, SACO, WRKS, STOTRLR, RDTS000015`. `[DB-ATHENS: aremst WHERE LOGIC_FLG=1]` `[WI-FAC slide 11]`
- [ ] **2.7** Each area may declare a **Lost Location** (`LOST_LOC`) — the logical bucket for its adjusted-out / lost inventory. `[DB-ATHENS: aremst.LOST_LOC]` `[WI-FAC slide 18]`

### 2c. Area governance / audit
- [ ] **2.8** Areas allow **new records** and are **audited** by SDC; deviations are tracked per-record (Areas + Policies are the only two config sections complex enough to have a "Deviations Allowed" sheet). `[SDC-STD]` `[PrIME config 2022/Configuration Standards.txt L10-11]`
- [ ] **2.9** Standard PrIME area **type** codes (SDC baseline): `ADJS, ASRS, CADJ, FUPA, LINSTG, RVCSTG, SADJ, SDCK, SHIP, SHST, SSAL, STOT, SUBP, SXFR`. `[SDC-STD]`
- [ ] **2.10 (Minhang decision)** Keep **areas only for the SAP movement-type grouping** (which locations emit which IM transaction to SAP); use **zones for functional behaviour**. "All the areas we described are storage areas and don't send any movement to SAP — only IM locations should send the adjustment movement type." `[RECAP 6.15_2 @1:04–1:08, @1:07:54]`
- [ ] **2.11 (Minhang decision)** The old RTCIS habit of using an "error/ERR" area was **dropped**; ERR is not what 2022 needs. `[RECAP 6.15_2 @1:08:25]`
- [ ] **2.12 (Minhang decision)** Minhang was found to **follow the standard configuration** with no site-specific area changes at the high level. `[RECAP 6.16_1 @1:07:23]`

---

## 3. STORAGE ZONE rules (`sto_zone`)

- [ ] **3.1** PK = `STO_ZONE_ID` (surrogate) + code `STO_ZONE_COD`; scoped by `WH_ID`, `BLDG_ID`. Athens = **30 storage zones**. `[DB-ATHENS: sto_zone 19 cols, 30 rows]`
- [ ] **3.2** Storage zone carries put-away/consolidation behaviour: `CONFLG` (auto-consolidate), `CON_PAL_FLG`, `FIFFLG` (FIFO / date-controlled), `PCKCOD` (pick code S/M/N/D), `PROX_PUT_COD` (proximity put-away), `RNWL_STO_FLG`, `VRT_STCK_FLG` (virtual stacking). `[DB-ATHENS: sto_zone cols]`
- [ ] **3.3** A storage zone is defined **per storage area** and named `SZ-<AREA>` (e.g. `SZ-LIQUID`, `SZ-BEAUTY`, `SZ-GILLETTE`, `SZ-PAPER`). Confirmed by the 1:1 join area→storage-zone on storage locations. `[DB-ATHENS: locmst⋈sto_zone]`
- [ ] **3.4** **Every storage location should still be given a storage zone** — even case-pick locations that are *not* linked to any storage strategy — for standardization and future functionality. `[RECAP 6.15_2 @1:17:01–1:17:24 – Lachica]`
- [ ] **3.5** Storage zones are used for **allocation search**, so they are kept **separate** from staging zones (don't reuse a storage zone as a staging destination). `[RECAP 6.16_1 @2:31:00 – Lachica]`
- [ ] **3.6** SDC: Storage-Zone config **allows new records** and is **not audited**. `[SDC-STD]`

---

## 4. PICK ZONE rules (`pck_zone`)

- [ ] **4.1** PK = `PCK_ZONE_ID` + code `PCK_ZONE_COD`; scoped by `WH_ID`, `BLDG_ID`. Athens = **23 pick zones**. `[DB-ATHENS: pck_zone 26 cols, 23 rows]`
- [ ] **4.2** Pick zone carries pick behaviour: `CTNGRP` (cartonization group A/D), `DTLFLG` (detail pick), `SUBFLG` (sub-load pick), `LODFLG` (load pick), `PCK_STEAL_FLG` (pick stealing), `START_PAL_FLG`, `GRP_PCK`, `MAXPCK`, `MIX_LOTSTS_ALLOC_FLG`. `[DB-ATHENS: pck_zone cols]`
- [ ] **4.3** Pick zone naming = `PZ-<AREA>` (e.g. `PZ-CSRE`, `PZ-LYPK`), **or a grouped pick zone** across several areas: `PZ-FUPA-ALL`, `PZ-PAPA-ALL` (multiple product areas share one forward-pick zone). Non-prefixed operational pick zones: `XDCK`, `XDDR`, `STOTRLR`. `[DB-ATHENS: pck_zone + locmst join]`
- [ ] **4.4** Pick zones only exist on **pickable** locations (see coverage rule 8.4). For outbound flow, the **pick zone is the outbound grouping**. `[RECAP 6.15_2 @1:06:04 – Lachica]`
- [ ] **4.5** SDC: Pick-Zone config **does not allow new records** and is **not audited** (`NA/NA`). `[SDC-STD]`

---

## 5. MOVEMENT ZONE rules (`mov_zone`)

- [ ] **5.1** PK = `MOV_ZONE_ID` + code `MOV_ZONE_COD`; scoped by `WH_ID`, `BLDG_ID`. Athens = **92 movement zones**. `[DB-ATHENS: mov_zone 45 cols, 92 rows]`
- [ ] **5.2** Movement zone holds staging / hand-off / PND / consolidation / replenishment-default behaviour: `CLR_DSTLOC_FLG`, `SPLIT_TRN`, `DEF_RPLCFG_INVSTS/MAXUNT/MINUNT/PCTFLG`, `DYN_SLOT_FLG`, `RECALC_PUTAWAY`, `PRE_STAGE_FLG`, `VC_CONS_LOT_FLG`, `AUTO_CLOSE_FLG`. Attachment strategy is defined at the movement-zone level. `[DB-ATHENS: mov_zone cols]` `[TRAIN §4]`
- [ ] **5.3** **RULE: every location MUST have a movement zone** (needed to raise move requests); a **1:1 map of current areas → movement zones** is expected for lift-and-shift. `[TRAIN §4]`
- [ ] **5.4** Movement zone naming = `MZ-<AREA>` (e.g. `MZ-LIQUID`, `MZ-BEAUTY`, `MZ-3PL`) for the 1:1 area map, **plus** short operational zones reused as-is: `ADJS, CADJ, DADJ, DKIT, DSPCH, EXPR, SACO, SADJ, SHIP, SXFR, WEXP, WRKS, XDCK, XDDR, STOTRLR, RDT-B1, SRSTG_MZ`. `[DB-ATHENS: mov_zone]`
- [ ] **5.5** ⚠️ **Reality vs. rule:** at Athens **561 / 16,100 locations (~3.5%) have a NULL movement zone** — these are logical/dispatch/expected-receipt locations that never physically move. Treat 5.3 as "all *physical* locations must have a move zone"; logical locations may be exempt. `[DB-ATHENS: COUNT(locmst WHERE MOV_ZONE_ID IS NULL)=561]` `[INFERRED]`
- [ ] **5.6** SDC: Movement-Zone config **allows new records** and is **not audited**. Standard pre-loaded movement zones include `ADJS, ASRS, AUDIT, CADJ, DADJ, DKIT, DRPP, DRPR, DSPCH, DTLP, EXPR, FUPA` + site zones. `[SDC-STD]`

---

## 6. WORK ZONE rules (`zonmst`)

- [ ] **6.1** PK = `WRK_ZONE_ID` + code `WRKZON`; scoped by `WH_ID`, `BLDG_ID`. Athens = **108 work zones**. `[DB-ATHENS: zonmst 23 cols, 108 rows]`
- [ ] **6.2** Work zones balance labour & limit congestion: `WRKARE` (parent work-area group), `TRVSEQ` (travel sequence), `PRITHR`/`MAXPRITHR` (priority thresholds), `MAXDEV` (max devices), `OOSFLG`, `PCK_EXP_ARE`. `[DB-ATHENS: zonmst cols]` `[WI-FAC slide 2]` `[PMC 02-01-06 Work Areas & Work Zones]`
- [ ] **6.3** Work zones are grouped under **Work Areas** (`WRKARE`). Athens work-areas: `WABC` (ABC/rack storage), `WAHOM` (home/aisle 01), `WASTG` (staging), `WLOGICAL` (logical), `WRKA`, `WAWMD1B1`. `[DB-ATHENS: zonmst.WRKARE distinct]`
- [ ] **6.4** Work-zone **naming** convention (Athens): `WZ<rowNN>-<sub>[-<rackType>]` e.g. `WZ05-B-BB`, `WZ01-A`, `WZ10-C-SR`; staging return zones `WZRSTG001…035`; out-lanes `WZ05AOUT`; logical `99`/`NONE`. Travel sequence (`TRVSEQ`) increases along the pick path. `[DB-ATHENS: zonmst.WRKZON]`
- [ ] **6.5** Work Areas / Work Zones both specify **absolute and delta priorities** (used to offer/limit work per zone). `[WI-FAC slide 2]`
- [ ] **6.6** SDC velocity-zoning **hard points** (site process, not table config): follow **velocity-based zoning**; base on BOP forecast if accuracy > 90 % else historical; run a productivity/travel-distance assessment; re-assess **monthly** if slow-mover volume > 10 % of total, else **quarterly** (integrated sites daily/weekly); **always relocate slow movers sitting in the fast zone**. `[SDC-ZON Hard Points 1-5]`
- [ ] **6.7** Coverage: **1,341 / 16,100** Athens locations have NULL work zone — work zones are only on **directed-work** locations, not every location. `[DB-ATHENS: COUNT(WRK_ZONE_ID IS NULL)=1341]`

---

## 7. LOCATION-TYPE rules (`loc_typ`)

- [ ] **7.1** PK = `LOC_TYP_ID` + code `LOC_TYP`, grouped by `LOC_TYP_CAT`; scoped by `WH_ID`. Location Type is the template that inherited the ~41 general area flags. Athens = **49 location types across 8 categories**. `[DB-ATHENS: loc_typ 57 cols, 49 rows]` `[TRAIN §1]`
- [ ] **7.2** The **8 Location-Type categories** and their codes (Athens): `[DB-ATHENS: loc_typ GROUP BY LOC_TYP_CAT]`
  | Category | Count | LOC_TYP codes |
  |---|---|---|
  | `DOCK` | 4 | RDCK, RSDK, SDCK, STOTRLR |
  | `LOGICAL` | 8 | ADJS, DSPCH, EXPR, RDTS, SADJ, SHIP, WEXP, XDDR |
  | `PND` | 14 | AUDIT, DKIT, EXPR4W, HFPE, IMAR, IMQM, MNFST, NSTO, PND, PNDN, PNDS, PRST, SACO, WRKS |
  | `PROC` | 1 | PROC |
  | `PROD` | 6 | PELIN, PLIN, PROD, PSTA, PSTD, WIPSUP |
  | `STAGING` | 7 | PSTG, RCST, SHST, SRSTG, SRSTG_LT, VSTG, XDCK |
  | `STORAGE` | 8 | ASRS, NEAR, PPST, RSTO, SXFR, VSTO_LSTS, VSTO_PCKSTL, VSTO_PUT |
  | `YARD` | 1 | YARD |
- [ ] **7.3** Location-Type flags drive per-location behaviour: `STOARE_FLG` (storage), `PDFLG` (PnD), `PRAFLG` (processing), `RCV_STGFLG`/`RCV_DCK_FLG` (receive stage/dock), `SHP_DCK_FLG`/`SHPFLG` (ship dock/stage), `PROD_FLG`/`PRD_STGFLG` (production), `WIPFLG`/`WIP_SUPFLG`, `XDAFLG` (cross-dock), `YRDFLG` (yard), `STGFLG`, `DISPATCH_FLG`, `EXPFLG` (expected). `[DB-ATHENS: loc_typ cols]` `[WI-FAC slides 9-19]`
- [ ] **7.4** **RULE: every location MUST have a Location Type** — Athens has **0 NULL** `LOC_TYP_ID` across 16,100 locations. `[DB-ATHENS: COUNT(LOC_TYP_ID IS NULL)=0]`

---

## 8. LOCATION rules (`locmst`) — mandatory attributes & assignment coverage

- [ ] **8.1** `locmst` PK = `STOLOC` + `WH_ID`. It is a wide table (**118 columns** at Athens) that now carries the storage/pick flags + all five zone FKs. `[DB-ATHENS: locmst 118 cols]`
- [ ] **8.2** Locations are **maintained per area** (Location Maintenance is scoped to an area). `[WI-FAC slide 3]`
- [ ] **8.3** **Mandatory on every location (0 NULL at Athens):**
  - `ARECOD` — area (required). `[DB-ATHENS: 0 null]`
  - `LOC_TYP_ID` — location type (required). `[DB-ATHENS: 0 null]`
- [ ] **8.4** **Conditional zone assignment (NULL where not applicable):** `[DB-ATHENS null counts of 16,100]`
  | Zone FK | NULL count | Applies to |
  |---|---|---|
  | `MOV_ZONE_ID` | 561 | all physical (move-capable) locations |
  | `WRK_ZONE_ID` | 1,341 | directed-work locations only |
  | `STO_ZONE_ID` | 2,967 | storage-capable locations only |
  | `PCK_ZONE_ID` | 2,988 | pickable locations only |
- [ ] **8.5** Behavioural flags now sit on the location: `STOFLG` (storage), `PCKFLG` (pick), `REPFLG` (replenishment), `ASGFLG` (assignable), `USEFLG` (in use), `LOCSTS` (status), `PERM_ASGFLG` (permanent assign). `[DB-ATHENS: locmst cols]` `[athens-2022-schema-findings memory]`
- [ ] **8.6** **Velocity zone** (`VELZON`) on each location — Athens uses `A` (fast, 1,228), `B` (785), `C` (bulk/slow, 10,965), `D` (219), `Z` (ground pick-face, 2,903). Velocity codes are defined in **Code Maintenance** together with ABC and location-access codes. `[DB-ATHENS: locmst GROUP BY VELZON]` `[WI-FAC slide 2]`
- [ ] **8.7** **Aisle** (`AISLE_ID`, e.g. `AISLE001…004`) is a defined code (Aisle Maintenance) referenced by rack locations. `[DB-ATHENS: locmst.AISLE_ID]` `[WI-FAC slide 3]`
- [ ] **8.8** **Permanent / re-usable** locations get a Permanent Load number (Permanent Load Maintenance); `PERM_ASGFLG=1`. Standard pre-loaded permanent locations: `PERM-ADJ-LOC, PERM-CRE-LOC, PERM-CNT-LOC, PERM-DKT-*-LOC, PERM-EXP-LOC, PERM-SHP-*, PERM-SHIP-LOC, PERM-WEXP-LOC, LSTS_LOST, RDT001, VOC01`, etc. `[WI-FAC slide 3]` `[SDC-STD]`
- [ ] **8.9** Override-Location codes (why an RF operator overrode the system-suggested location, and whether to trigger a cycle count) are defined in **Override Location Code Maintenance**. `[WI-FAC slide 3]`
- [ ] **8.10** **Dock ↔ Aisle ↔ Lane** associations (which dock doors map to which staging lanes/aisles for shipping & receiving) are maintained in Dock-Aisle-Lane Association Maintenance. `[WI-FAC slide 3]`

---

## 9. NAMING conventions (consolidated)

### 9a. Area codes (`ARECOD`, ≤10 chars, descriptive) `[DB-ATHENS: aremst]`
- [ ] **9.1** **Product/velocity storage areas** use plain product names: `LIQUID, PAPER, POWDER, POWDER PAR, BEAUTY, BEAUTY PAR, GILLETTE, AEROSOL, CSRE, CSUN, CSWG, LYPK, 3PL, 3PL FUPA, UNBW, UNBW PAR, PAPA PAR, SHST`.
- [ ] **9.2** **Functional / logical areas** use 3-5 letter mnemonics: adjustments `ADJS/CADJ/DADJ/SADJ`; ship/dispatch `SHIP/DSPCH`; expected receipts `EXPR/WEXP`; cross-dock `XDCK/XDDR`; transfer `SXFR`; kitting `DKIT`; sort-consolidate `SACO`; work-station `WRKS`; storage-trailer `STOTRLR`; dock/yard `DOCK/YARD`; audit/damage/scrap/return/lost `AUDIT/DMGE/SCRP/RETR/LOST`.
- [ ] **9.3** **Production-Execution (RPM) areas** carry a `PE`/`PEL`/`PST`/`PEWX`/`PEPND` prefix: `PELINAGR, PELINDGR, PELINQMR, PESTOB1, PESTACOM, PEPCKSTLB1, PEPNDCLOB1, PEPNDLTAB1, PEWXAB1…`. `[INFERRED from code stems]`
- [ ] **9.4** **Building-scoped areas** append the building: suffix `B1` (`PEWXAB1`, `PESTOB1`, `EXPR4W|B1`) or `|B1` delimiter (`PSTMX|B1`, `PSTDM|B1`). `[DB-ATHENS]`

### 9b. Zone codes (prefix = zone framework)
- [ ] **9.5** **Storage zone** = `SZ-<AREA>`; **Pick zone** = `PZ-<AREA>` (or grouped `PZ-…-ALL`); **Movement zone** = `MZ-<AREA>`. The suffix mirrors the area code exactly, giving a traceable area↔zone lineage. `[DB-ATHENS]`
- [ ] **9.6** **Work zone** = `WZ<rowNN>-<sub>[-<rackType>]`; return-staging `WZRSTG###`; out-lane `WZ…OUT`. `[DB-ATHENS]`
- [ ] **9.7** Operational/logical zones bypass the prefix and reuse the mnemonic directly (`XDCK`, `XDDR`, `STOTRLR`, `ADJS`, `SHIP`, …). `[DB-ATHENS]`

### 9c. Location codes (`STOLOC`)
- [ ] **9.8** **Rack storage** pattern: `<AisleBlock: 2-digit row + letter><position: 3-digit>L<level><depth suffix>`. Example `05B052L3BB` = row 05, block B, position 052, Level 3, depth `BB`. `[DB-ATHENS: locmst.STOLOC]`
- [ ] **9.9** **Rack depth / face suffixes** and their volume at Athens: `BB` (7,925), `SR` (2,598), `GF` (2,151 — ground floor pick face, VELZON `Z`), `GR` (282 — ground rack), `LP` (138). The ground `GF/GR` faces are the pickable forward locations. `[DB-ATHENS: RIGHT(STOLOC,2)]` `[INFERRED: GF/GR ↔ VELZON Z]`
- [ ] **9.10** **Logical locations** use a long zero-padded token: `L` + 19 chars, e.g. `L000000000000000013Y` (ADJS logical). `[DB-ATHENS]`
- [ ] **9.11** **Staging / manipulation locations** use short descriptive codes: `SSTG14`, `ZMANIP19`, `PND1`, `PND2`, `A5/A6` (pass-through PND lanes referenced in ops). `[DB-ATHENS]` `[RECAP 6.17_3]`
- [ ] **9.12** Location code fields that *can* carry structure but are blank at Athens (site may use them): `SECTION, BAY, LVL, LOCPOS`. Athens encodes level/position inside the `STOLOC` string instead. `[DB-ATHENS: those cols NULL on samples]`

---

## 10. ASSIGNMENT rules (how a location gets its area, zones, type)

- [ ] **10.1** Assignment order of operations for a new location: **Building → Area → Location Type → (Storage/Pick/Movement/Work) Zones → velocity/aisle/flags**. `[WI-FAC slides 2-3, 6]` `[INFERRED]`
- [ ] **10.2** Group locations **by area** when the driver is the **SAP IM transaction type** to emit; group **by zone** when the driver is **functional behaviour** (put-away, pick, flow). `[RECAP 6.15_2 @1:04–1:08]`
- [ ] **10.3** Map current areas **1:1 to movement zones** for a lift-and-shift migration. `[TRAIN §4]` ⚠️ **But Minhang did NOT lift-and-shift** — the site redesigned areas by building/plant and movement zones by equipment-transition flow. Use 1:1 only when the site explicitly chooses a lift-and-shift; otherwise follow the Site-Config design. `[see §13.1, §13.5]`
- [ ] **10.4** Define **one storage zone per storage area** (`SZ-<AREA>`) and assign it to every storage/case-pick location in that area, even if no storage strategy is attached. `[DB-ATHENS]` `[RECAP 6.15_2 @1:17]`
- [ ] **10.5** Assign a **pick zone only to pickable locations**; storage-only bulk locations get none. Forward-pick faces across product areas may share a grouped pick zone (`PZ-FUPA-ALL`). `[DB-ATHENS: PCK_ZONE_ID null on 2,988]`
- [ ] **10.6** Assign a **work zone only to directed-work locations** (rack aisles, staging); logical/dock locations may have none. `[DB-ATHENS: WRK_ZONE_ID null on 1,341]`
- [ ] **10.7** **Put-away strategy** links **source move-zone + item family → destination storage-zone** (2-level "storage search path"). **Allocation/pick strategy** links **destination → source** referencing pick zones + pick methods (2-level). `[TRAIN §2, §3]`
- [ ] **10.8** **IM (inventory-management) locations** are the ones authorised to send SAP movement types (adjust in/out, 309/311); normal storage locations do not. Assign IM locations deliberately. `[RECAP 6.15_2 @1:07–1:08]`
- [ ] **10.9** For **RPM / production supply** where there isn't space for per-material fixed pick locations, assign/replenish **by area** rather than per-item location. `[RECAP 6.17_2 @1:04–1:04:29 – Shi]`
- [ ] **10.10** **Directed vs. undirected put-away** is a per-location/area choice: with PND enabled the system suggests a directed location; without it, receipt goes straight to a station (undirected). `[RECAP 6.17_3 @20:10–20:29]`

---

## 11. SDC governance & audit summary (for sign-off)

- [ ] **11.1** Audit posture per config section: **Storage Zones** (new records ✔, not audited), **Pick Zones** (no new records, not audited), **Movement Zones** (new ✔, not audited), **Locations** (matching, audited), **Items/Item Families** (audited medium), **Task/Pick Methods/Production Lines** (audited). `[SDC-STD]`
- [ ] **11.2** Audit severity meaning: **High** = must match SDC (blocker); **Medium** = drift must be justified; **Low** = informational; **NA** = not audited. `[SDC-STD]`
- [ ] **11.3** Areas & Policies are the only sections with a **"Deviations Allowed"** register (per-record allowed variations) because of their complexity. `[PrIME config 2022/Configuration Standards.txt L10-11]`
- [ ] **11.4 (Minhang)** Confirm the placeholder **`WH_ID`** before go-live (transform used `WMH1`; Athens reference is `WMD1`). `[minhang-rtcis-masterdata-to-prime2022 memory]`

---

## 12. Migration cross-reference (RTCIS → PrIME 2022)

- [ ] **12.1** RTCIS `LOCATN` → PrIME `locmst` (`ARECOD, STOFLG, PCKFLG, dims`). `[minhang…memory]` `[GLOSS §6]`
- [ ] **12.2** RTCIS `ZONCOD` → split by `ZONE_TYPE` into `zonmst` / `pck_zone` / `sto_zone`. At Minhang `ZONE_TYPE` is null, so **all `ZONCOD` map to `zonmst`** (no pck/sto split there yet). `[minhang…memory]`
- [ ] **12.3** RTCIS `ARECOD` (distinct from LOCATN) + `BLDING` → PrIME `aremst`. `[minhang…memory]` ⚠️ **Members only, not the taxonomy** — Minhang's PrIME areas are building/plant zones authored in the Site-Config Model, *not* RTCIS `ARECOD` values. Map each RTCIS location onto the business area codes by building + material intent. `[see §13.1, §13.7]`
- [ ] **12.4** RTCIS area/zone **value sets differ entirely** from PrIME — same column name, different codebook; there is **no 1:1 value crosswalk**, remap by business intent. `[mm-bot-rtcis-prime-codebook-mappings §7, §8]`
- [ ] **12.5** Field variants to re-point when translating 2014/RTCIS queries: `arecod, frmarea, toarea, dstare` → assess which 2022 zone framework applies. `[TRAIN §9]`

---

### Open confirmations — RESOLVED per meeting record + team-filled Site Config Model (2026-06-14)

1. **Go-live `WH_ID` → `BR01`** (not the `WMH1` placeholder). The team's Site Config Model uses **`BR01`** as the Warehouse ID throughout (Areas & Work-Area sheets), and Site Overview lists **SAP Storage Location = `BR01`** and **Building(s) = `BR01`**. Update the transform `WH_ID` from `WMH1` → `BR01`. `[SITE-CFG: Site Overview r8/r10; Areas wh_id col]`
2. **Split `ZONCOD` into storage + pick zones → YES (confirmed).** Site defines storage zones for receiving/put-away and pick zones for outbound; areas kept only for SAP transaction grouping. Team design: **23 storage zones** + **3 picking-method pick zones** (散拣/补货/整板). `[RECAP 6.15_2 @1:06 "for receiving we will be having the storage zones, for outbound the picking zone… define the zones instead of the areas"]` `[SITE-CFG: Storage Zones (23), Pick Zones]`
3. **IM locations → dedicated IM location types.** Only IM locations emit SAP movement-type adjustments; normal storage sends nothing. Team catalog defines the standard **`IMAR`** and **`IMQM`** IM location types. `[RECAP 6.15_2 @1:07 "only IM locations should send the movement type adjustment to SAP… normal storage areas don't"]` `[SITE-CFG: Location Types IMAR/IMQM]`
4. **Logical-location movement-zone exemption → YES (applies at Minhang).** Site runs a **single building (`BR01`)** with logical/in-transit locations (adjust, dispatch, expected-receipts, shuttle/hand-off) that never physically move — the same intended exemption as the 561 no-move-zone Athens locations. Team catalog defines the **`LOGICAL`** location-type category (`ADJS, DKIT, DSPCH, EXPR, SADJ, SHIP, WEXP, XDDR`); assign no `MOV_ZONE_ID` to these. `[RECAP 6.15_2 @1:11 single-building + in-transit shuttle locations]` `[SITE-CFG: Site Overview Building(s)=BR01; Location Types LOGICAL]` `[DB-ATHENS 561 null mov-zone]`

---

## 13. LEARNINGS — mechanical RTCIS transform vs. business Site-Config design (Minhang case study)

> **Context.** A mechanical transform derived areas/zones/location-types straight from RTCIS
> (`ARECOD`, `ZONCOD`/`PIKZON`) and was compared to the business-authored **PrIME202X Site
> Configuration Model – MH – 2026.6.14.xlsx** (`wh_id BR01`, the target design ground truth).
> Result: near-zero overlap — **AREA 0/11 match, LOC_TYPE 0/43 match, STORAGE-ZONE 1/23 match (~4%)**.
> The 2022 taxonomy is a **business redesign**, not a field-rename of RTCIS.
> `[SITE-CFG: Areas/Location Types/Storage Zones/Pick Zones/Movement Zones sheets]`
> `[_md_consistency_vs_siteconfig.py → _consistency_vs_business.csv]`

- [ ] **13.1 — AREAS are a physical/plant dimension, not the RTCIS functional dimension.** Business areas are **buildings/floors/plants** (`P1MAINWH`主仓, `P1TC9`, `P1DGWH`周转仓, `P1RESIN`树脂仓, `P1CHEMICAL`化学品仓, `P3HWCK`恒温恒湿仓, `P3F1/F2/F3`三厂1/2/3层, `REMOTEWH`外仓, `REMOTEDGWH`危险品外仓). RTCIS `ARECOD` is **functional** (`RO`=rack, `ST`=staging, `HP`=hand-off, `DO`=dock). **Do NOT map `ARECOD` 1:1 to PrIME Area** — that conflates two orthogonal dimensions. `[SITE-CFG: Areas]`
- [ ] **13.2 — LOCATION TYPES must come from the STANDARD PrIME catalog, never invented.** Business used **43 standard `loc_typ` codes** (`ADJS, ASRS, AUDIT, DKIT, DSPCH, EXPR, HFPE, IMAR, IMQM, NEAR, NSTO, PND, PROC, PROD, PRST, PSTA, PSTD…`). Invented codes (`RACK, STAGING, HANDOFF…`) do not integrate with PrIME behaviour flags/strategies and score 0% match. `[SITE-CFG: Location Types]`
- [ ] **13.3 — STORAGE ZONES are designed by storage strategy & material handling, not by RTCIS product code.** Business zones encode **handling method + material class**: `SZ-VNA` (堆高车/VNA), `SZ-CSPICK` (固定拣货/fixed case-pick), `SZ-M-RESIN` (塑料粒子/resin pellet), `SZ-*-WIP`, `SZ-CHEMICAL`, `SZ-DG`, `SZ-P3-1F/2F/3F`, `SZ-REMOTE`. RTCIS-code clones (`SZ-M1..M9, SZ-B1..B3, SZ-XX`) are semantically wrong (only `SZ-DG` coincidentally matched). `[SITE-CFG: Storage Zones]`
- [ ] **13.4 — PICK ZONES are a small set of picking-method zones, not a per-product clone.** Business modelled **~3 method zones**: 散拣区 (case-pick — plastic pellets/imported brush heads), 补货区 (replenishment — PCB/Plant 2&3 injection), 整板区 (full-pallet). Codes were left **blank pending assignment** (descriptions filled first). Cloning one `PZ-*` per `ZONCOD` (19 zones) over-fragments the design. `[SITE-CFG: Pick Zones]`
- [ ] **13.5 — MOVEMENT ZONES model equipment-transition / deposit flows, not 1:1 area mirrors.** Business descriptions are **PnD/equipment transitions**: "PnD from VNA forklift to pallet", "PnD from pallet jack to VNA", "receiving staging", "receiving staging-P3" — i.e. where material changes handling equipment (see also the *Movement Zone Next Move* sheet). One-per-area `MZ-*` mirrors miss this intent. `[SITE-CFG: Movement Zones / Movement Zone Next Move]`
- [ ] **13.6 — The Site Configuration Model is the TARGET ground truth; Athens+RTCIS are references only.** Validate any generated taxonomy **against the site's filled Site-Config workbook**, not just against Athens structure + RTCIS values. A transform can be 100% structurally valid (all FKs resolve, all rules pass) yet ~0% consistent with the business design. Structural validity ≠ design correctness. `[SITE-CFG]` `[Diagnosis-vs-Prescription lesson]`
- [ ] **13.7 — The correct RTCIS→2022 path is a semantic remap through the Site-Config design, not a code carry-over.** Use RTCIS only to *populate members* (which physical locations exist, their dims); take the **area/zone/loc-type taxonomy from the Site-Config Model** and map each RTCIS location onto the business codes by **building + material + handling intent**. `[SITE-CFG]` `[§12.4 no 1:1 value crosswalk]`
- [ ] **13.8 — Deliverable.** Business-vs-transform consistency export: `output/PRIME2022_MINHANG/_consistency_vs_business.csv` (per-framework summary + per-code MATCH / BUSINESS_ONLY / TRANSFORM_ONLY). Regenerate via `_md_consistency_vs_siteconfig.py`. `[deliverable]`
