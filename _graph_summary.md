# Neo4j Knowledge Graph Summary

**Exported:** 2026-07-06 (from live Neo4j `bolt://localhost:7687`) | **Nodes:** 20,738 | **Relationships:** 33,138 | **Node types:** 47 | **Relationship types:** 211

> This summary is generated directly from the live graph export (`_neo4j_export.json`), so the counts and labels below reflect the **actual current graph** — the RTCIS/PrIME translation KB + SDC + M&M audit + Timbr ontology layers, unified.

## Node Types

| Type | Count |
|------|-------|
| SourceColumn | 8,442 |
| ViewColumn | 3,433 |
| DocumentConcept | 2,653 |
| SystemSynonym | 1,950 |
| SiteObjectProfile | 912 |
| DocumentSource | 664 |
| MMQuestion | 438 |
| POLCODStandard | 410 |
| SourceObject | 283 |
| TimbrProperty | 270 |
| ConfigArtifact | 155 |
| SystemView | 141 |
| ReferencedObject | 138 |
| SDCSubFlow | 99 |
| EvidenceRule | 91 |
| Site | 83 |
| PrIMEConfigScreen | 65 |
| TimbrClass | 58 |
| LineageExpression | 46 |
| SDCDeviation | 42 |
| PMActivity | 39 |
| ConfigMapping | 30 |
| PrIMEColumn | 29 |
| PrIMETable | 29 |
| RTCISColumn | 28 |
| TrainingModule | 28 |
| RTCISTable | 23 |
| Learning | 21 |
| SystemSchema | 19 |
| SiteValidationProfile | 18 |
| KBRule | 14 |
| RTCISValue | 13 |
| RTCISConfigTable | 12 |
| PrIMEConfigCookbook | 11 |
| GraphQuery | 10 |
| PrIMEValue | 10 |
| SDCFlowModule | 10 |
| WMSDomain | 8 |
| PMModule | 7 |
| PMProcess | 7 |
| Query | 3 |
| WMSSystem | 3 |
| Architecture | 1 |
| ConfidenceModel | 1 |
| ExternalSystem | 1 |
| MMAuditFramework | 1 |
| PrIMEConfigTable | 1 |

## Relationship Types

| Relationship | Count |
|-------------|-------|
| HAS_SOURCE_COLUMN | 8,442 |
| HAS_COLUMN | 3,433 |
| HAS_DOCUMENT_CONCEPT | 2,653 |
| DERIVED_FROM | 2,331 |
| DOCUMENT_SUPPORTS_DOMAIN | 2,258 |
| MENTIONS_PRIME_TABLE | 2,000 |
| HAS_SYNONYM | 1,950 |
| MENTIONS_RTCIS_TABLE | 1,849 |
| COVERED_BY_RULE | 1,263 |
| APPLIES_TO_SYSTEM | 1,106 |
| STORED_IN | 475 |
| BELONGS_TO_SDC_MODULE | 438 |
| BELONGS_TO_SDC_SUBFLOW | 438 |
| HAS_STANDARD_DOCUMENT | 428 |
| DOCUMENT_MENTIONS | 427 |
| HAS_PROFILE_EVIDENCE | 283 |
| REFERENCES_OBJECT | 272 |
| HAS_PROPERTY | 270 |
| QUERIES_VIEW | 166 |
| BACKED_BY_PRIME_OBJECT | 149 |
| EXPOSES_VIEW | 140 |
| PROVIDES_VIEW | 140 |
| IMPLEMENTS | 123 |
| SUPPORTS_CONCEPT | 123 |
| COVERS_SDC_SUBFLOW | 119 |
| STANDARDIZES_DOMAIN | 107 |
| HAS_SUBFLOW | 99 |
| REFERENCES | 97 |
| COVERED_BY_CONFIG_MAPPING | 82 |
| RUNS_WMS | 81 |
| DEFINED_BY | 79 |
| DEFINED_IN | 66 |
| MAPS_TO | 63 |
| ENCOMPASSES | 60 |
| ALIGNS_WITH | 57 |
| BELONGS_TO | 57 |
| BACKED_BY_KB_TABLE | 55 |
| SUBCLASS_OF | 55 |
| RESOLVES_TO_KB_TABLE | 52 |
| DERIVED_BY_EXPRESSION | 46 |
| RAISED_FOR_QUESTION | 42 |
| REALISED_BY | 39 |
| APPLIED_TO | 33 |
| COVERS_SDC_MODULE | 28 |
| AFFECTS | 24 |
| EXTENDS | 21 |
| HAS_SCHEMA | 19 |
| MAPS_RTCIS_TABLE | 15 |
| APPLIES_TO_EXTERNAL_SYSTEM | 14 |
| EXPOSED_AS | 14 |
| OBSERVED_AT | 14 |
| OF_SYSTEM | 14 |
| CONTEXTUALIZES | 11 |
| PRODUCES | 11 |
| REMAPS_TO | 11 |
| USES | 11 |
| SDC_PROCESS_FLOWS_TO | 10 |
| QUERIES_CONFIG_TABLE | 8 |
| HAS_SUBPROCESS | 7 |
| MENTIONS_VIEW | 7 |
| SDC_GOVERNS | 6 |
| USES_ARCHITECTURE | 3 |
| TIMBR_REL_ALTERNATE_FOR | 1 |
| TIMBR_REL_ARE_IN_OUTBOUND_TRAILER | 1 |
| TIMBR_REL_ARRIVING_AT | 1 |
| TIMBR_REL_AT | 1 |
| TIMBR_REL_AT_SITE | 1 |
| TIMBR_REL_AT_STORAGE_LOCATION | 1 |
| TIMBR_REL_AUTHORIZED | 1 |
| TIMBR_REL_BATCHES_AT | 1 |
| TIMBR_REL_BEING_DISPATCHED_FROM | 1 |
| TIMBR_REL_BEING_FULFILLED_AT | 1 |
| TIMBR_REL_BEING_SHIPPED_TO | 1 |
| TIMBR_REL_BELONGS_TO | 1 |
| TIMBR_REL_BILLED_FOR | 1 |
| TIMBR_REL_BILLED_USING | 1 |
| TIMBR_REL_BILL_FOR_DELIVERY | 1 |
| TIMBR_REL_CAN_BE_SUBSTITUTED_WITH | 1 |
| TIMBR_REL_CARRIER_FOR | 1 |
| TIMBR_REL_CARRYING_PRODUCT_PARTS | 1 |
| TIMBR_REL_CHANGES_FOR | 1 |
| TIMBR_REL_COMPONENTS_RESERVED | 1 |
| TIMBR_REL_COMPONENTS_RESERVED_FOR | 1 |
| TIMBR_REL_COMPOSED_OF | 1 |
| TIMBR_REL_CONTAINED_IN_TRAILER | 1 |
| TIMBR_REL_CONTAINS_MATERIALS | 1 |
| TIMBR_REL_CONTAINS_PURCHASES | 1 |
| TIMBR_REL_CONTAINS_SALES | 1 |
| TIMBR_REL_CONTRACTED_FOR | 1 |
| TIMBR_REL_CONTRACTED_TARIFF | 1 |
| TIMBR_REL_CUSTOMER_REQUESTED | 1 |
| TIMBR_REL_CUSTOMER_SHIP_TO_FOR_SALES | 1 |
| TIMBR_REL_DELIVERED | 1 |
| TIMBR_REL_DELIVERED_FROM | 1 |
| TIMBR_REL_DELIVERED_PO | 1 |
| TIMBR_REL_DELIVERED_PO_USING | 1 |
| TIMBR_REL_DELIVERED_PRODUCT | 1 |
| TIMBR_REL_DELIVERED_USING | 1 |
| TIMBR_REL_DELIVERIES_MADE | 1 |
| TIMBR_REL_DELIVERY_FOR_BILL | 1 |
| TIMBR_REL_DELIVERY_REQUESTED | 1 |
| TIMBR_REL_DEMAND_FORECAST_FOR | 1 |
| TIMBR_REL_DEMAND_FORECAST_FOR_SITE | 1 |
| TIMBR_REL_DEPLOYMENT_DELIVERY_FOR | 1 |
| TIMBR_REL_DEPLOYMENT_DELIVERY_TO | 1 |
| TIMBR_REL_DEPLOYMENT_DEMAND_FOR | 1 |
| TIMBR_REL_DEPLOYMENT_PLAN_FOR | 1 |
| TIMBR_REL_DISPATCHING | 1 |
| TIMBR_REL_FOR | 1 |
| TIMBR_REL_FOR_EQUIPMENT | 1 |
| TIMBR_REL_FOR_INBOUND_TRAILER | 1 |
| TIMBR_REL_FOR_OUTBOUND_TRAILER | 1 |
| TIMBR_REL_FOR_PRODUCT | 1 |
| TIMBR_REL_FOR_SENSOR | 1 |
| TIMBR_REL_FULFILLED | 1 |
| TIMBR_REL_FULFILLED_BY | 1 |
| TIMBR_REL_FULFILLING_SALES_ORDER | 1 |
| TIMBR_REL_HAD_CHANGES | 1 |
| TIMBR_REL_HAD_MOVEMENTS | 1 |
| TIMBR_REL_HAS | 1 |
| TIMBR_REL_HAS_ALTERNATES | 1 |
| TIMBR_REL_HAS_DEMAND_FORECAST | 1 |
| TIMBR_REL_HAS_DEPLOYMENT_DEMAND | 1 |
| TIMBR_REL_HAS_EQUIPMENT | 1 |
| TIMBR_REL_HAS_INBOUND_TRAILER | 1 |
| TIMBR_REL_HAS_INVENTORY | 1 |
| TIMBR_REL_HAS_INVENTORY_BY_BATCHES | 1 |
| TIMBR_REL_HAS_PURCHASES | 1 |
| TIMBR_REL_HAS_SENSOR | 1 |
| TIMBR_REL_HAS_STORAGE_LOCATION | 1 |
| TIMBR_REL_HAS_TRUCK_HANDLING_CAPACITY | 1 |
| TIMBR_REL_HAS_UNITS | 1 |
| TIMBR_REL_INCLUDES_CUSTOMERS | 1 |
| TIMBR_REL_INSPECTED | 1 |
| TIMBR_REL_INSPECTED_PROCESS_ORDER | 1 |
| TIMBR_REL_INSPECTED_PURCHASES | 1 |
| TIMBR_REL_INSPECTED_USING | 1 |
| TIMBR_REL_INSPECTION_DONE | 1 |
| TIMBR_REL_INSPECTION_DONE_USING | 1 |
| TIMBR_REL_INSPECTION_MOVED | 1 |
| TIMBR_REL_IN_INBOUND_TRAILER | 1 |
| TIMBR_REL_IS_AT | 1 |
| TIMBR_REL_IS_AUTHORIZED | 1 |
| TIMBR_REL_IS_INCLUDED_IN | 1 |
| TIMBR_REL_IS_IN_TRAILER | 1 |
| TIMBR_REL_IS_STORAGE_LOCATION_FOR | 1 |
| TIMBR_REL_LINKED_TO_TRUCK | 1 |
| TIMBR_REL_MANUFACTURE_USING | 1 |
| TIMBR_REL_MATERIALS_RESERVED | 1 |
| TIMBR_REL_MATERIAL_RESERVED_AT | 1 |
| TIMBR_REL_MEASURES | 1 |
| TIMBR_REL_MOVED | 1 |
| TIMBR_REL_MOVED_FOR_CUSTOMER | 1 |
| TIMBR_REL_MOVED_FOR_DELIVERY | 1 |
| TIMBR_REL_MOVED_FOR_PROCESS_ORDER | 1 |
| TIMBR_REL_MOVED_FOR_PURCHASES | 1 |
| TIMBR_REL_MOVED_FOR_SALES | 1 |
| TIMBR_REL_MOVED_FOR_SUPPLIER | 1 |
| TIMBR_REL_MOVED_FROM_LOCATION | 1 |
| TIMBR_REL_MOVED_MATERIAL | 1 |
| TIMBR_REL_MOVED_MATERIAL_AT | 1 |
| TIMBR_REL_MOVED_MATERIAL_USING | 1 |
| TIMBR_REL_MOVED_PRODUCT | 1 |
| TIMBR_REL_MOVEMENT_FOR_INSPECTION | 1 |
| TIMBR_REL_OF_CARRIER | 1 |
| TIMBR_REL_ORDERED_BY | 1 |
| TIMBR_REL_ORDERED_USING | 1 |
| TIMBR_REL_OUTBOUND_TRAILER_RELATED | 1 |
| TIMBR_REL_PLANNED_DEPLOYMENT | 1 |
| TIMBR_REL_PROCESSED_AT | 1 |
| TIMBR_REL_PROCESSED_USING | 1 |
| TIMBR_REL_PROCESS_ORDER_INSPECTED_USING | 1 |
| TIMBR_REL_PROCESS_ORDER_REQUESTED | 1 |
| TIMBR_REL_PRODUCED | 1 |
| TIMBR_REL_PRODUCED_USING | 1 |
| TIMBR_REL_PRODUCT_DELIVERED_USING | 1 |
| TIMBR_REL_PRODUCT_MOVED | 1 |
| TIMBR_REL_PURCHASED | 1 |
| TIMBR_REL_PURCHASED_USING | 1 |
| TIMBR_REL_PURCHASES_INSPECTED_USING | 1 |
| TIMBR_REL_PURCHASES_REQUESTED | 1 |
| TIMBR_REL_RECEIVED_MOVEMENT | 1 |
| TIMBR_REL_RECEIVING_TRAILER | 1 |
| TIMBR_REL_RECIEVING | 1 |
| TIMBR_REL_RELATIONSHIP_CARRIER | 1 |
| TIMBR_REL_REQUESTED | 1 |
| TIMBR_REL_REQUESTED_FOR | 1 |
| TIMBR_REL_REQUIREMENTS_FOR | 1 |
| TIMBR_REL_REQUIRES | 1 |
| TIMBR_REL_RESERVATIONS_FOR | 1 |
| TIMBR_REL_RESERVED | 1 |
| TIMBR_REL_SALES_REQUESTED | 1 |
| TIMBR_REL_SENDING_SITE_FOR | 1 |
| TIMBR_REL_SENT_TO_LOCATION | 1 |
| TIMBR_REL_SHIPPED | 1 |
| TIMBR_REL_SHIPPED_USING | 1 |
| TIMBR_REL_SHIP_TO | 1 |
| TIMBR_REL_SITE_DEMAND_FORECAST | 1 |
| TIMBR_REL_SOLD | 1 |
| TIMBR_REL_SOLD_USING | 1 |
| TIMBR_REL_SUBSTITUTED_FOR | 1 |
| TIMBR_REL_SUPPLIER_REQUESTED | 1 |
| TIMBR_REL_TRAILER_ARRIVING_AT | 1 |
| TIMBR_REL_TRAILER_BELONGS_TO | 1 |
| TIMBR_REL_TRUCK_FOR | 1 |
| TIMBR_REL_TRUCK_HANDLING_CAPACITY_FOR | 1 |
| TIMBR_REL_TRUCK_LEAVING_SITE | 1 |
| TIMBR_REL_UNITS_FOR | 1 |
| TIMBR_REL_USED_TO_MANUFACTURE | 1 |
| TIMBR_REL_WAS_FROM_LOCATION | 1 |
| TIMBR_REL_WAS_MOVED | 1 |

## Latest Learnings — Minhang RTCIS → PrIME 2022 masterdata (area / zone / location)

The knowledge graph now carries the Minhang masterdata transform learnings (loaded via `neo4j_rtcis_prime_loader.py`). Key lessons captured as `:Learning` nodes:

| id | severity | learning |
|----|----------|----------|
| 80 | critical | PrIME 2022 area/zone/loc-type taxonomy is a BUSINESS REDESIGN, not a 1:1 rename of RTCIS ARECOD/ZONCOD. Use RTCIS LOCATN/ZONCOD for MEMBERS only; take the taxonomy from the site's Site Configuration Model and map each location by building+material+handling intent |
| 81 | critical | Structural validity != design correctness. A transform can pass 100% FK/structure validation yet be ~0% consistent with the business design. Validate generated taxonomy against the FILLED Site-Config workbook, not just Athens structure + RTCIS values |
| 82 | important | PrIME 2022 splits the single 2014 area into 5 frameworks: sto_zone, pck_zone, mov_zone, zonmst (work), loc_typ. Route ZONCOD/PIKZON/LOCTYPE to the correct framework, not all to zonmst |
| 83 | important | LOCATION TYPES must come from the STANDARD PrIME 43-code catalog (ADJS,ASRS,IMAR,IMQM,PND,PROD,PRST...). Never invent (RACK/STAGING/HANDOFF) — invented codes do not bind to PrIME behaviour flags/strategies |
| 84 | important | PrIME 2022 dual-row pattern: each part/ftp/policy is written TWICE — a TEMPLATE row (WH_ID/WH_ID_TMPL='----') plus a WAREHOUSE row (='BR01'). Must be reproduced |
| 85 | important | Minhang go-live WH_ID = BR01 (confirmed by Site Config Model 2026-06-14, SAP Storage Location=BR01). NOT the WMH1 placeholder, NOT Athens WMD1 |
| 86 | important | At Minhang LOCTYPE and WRKZON are 100% NULL in RTCIS LOCATN; derive loc_typ/work-zone from ARECOD class + Site-Config instead of mapping the empty columns |
| 87 | important | IM (inventory-management) locations use dedicated IMAR + IMQM loc-types and are the only ones that emit SAP movement-type adjustments (309/311); normal storage sends nothing. SAP movements stay at AREA level, not zone level |

**Headline lesson (L80/L81):** the PrIME 2022 area/zone/location-type taxonomy is a **business redesign**, not a 1:1 rename of RTCIS `ARECOD`/`ZONCOD`. Use RTCIS only to populate MEMBERS (which locations exist + dims); take the taxonomy from the site's Site Configuration Model and map by building + material + handling intent. A transform can be 100% structurally valid yet ~0% consistent with the business design.

### 5-framework + masterdata table mappings now in the graph

| RTCIS source | PrIME 2022 target |
|---|---|
| locatn | aremst |
| zoncod | aremst |
| locatn | loc_typ |
| locatn | locmst |
| zoncod | mov_zone |
| zoncod | pck_zone |
| poldat | poldat |
| syspar | poldat |
| item_uom | prtftp |
| ctlgrp | prtlot |
| itmmst | prtmst_wh |
| zoncod | sto_zone |
| zoncod | zonmst |

> PrIME 2022 splits the single 2014 area into **5 frameworks** — `sto_zone` (storage), `pck_zone` (pick), `mov_zone` (movement), `zonmst` (work), `loc_typ` (location types) — plus Pick Methods. RTCIS `ZONCOD`/`PIKZON`/`LOCTYPE` must route to the correct framework, not all to `zonmst`.

## All translation learnings (`:Learning`)

| id | severity | learning |
|----|----------|----------|
| 55 | important | Filter value consistency: actcod must match site-specific values |
| 56 | critical | QASTAT='RL'→invsts='U' (not 'RL') |
| 57 | important | All hardcoded filter values must be in site-specific section |
| 58 | important | DTLTYP='F' → oprcod='F' (NOT itmcls='F'→typcod='FERT') |
| 62 | critical | Subquery WHERE must reference OUTER alias, not self (alias tautology) |
| 63 | important | prtdsc concat join key: concat(prtnum,'\|',prt_client_id,'\|',wh_id) |
| 64 | important | CSTNAM via shipment→adrmst.adrnam (not cstmst) |
| 68 | critical | prtdsc.colnam must be 'prtnum\|prt_client_id\|wh_id_tmpl' (not wh_id) |
| 69 | important | palflg→PAKFLG (Int32); max_unt_per_unt & qa_sts don't exist on prtmst |
| 70 | critical | prtftp_dtl dedup requires OUTER/CROSS APPLY (SELECT TOP 1) not LEFT JOIN |
| 71 | important | Athens prtfam uses text values (LIQUID, PAPER...) not numeric codes (682) |
| 72 | critical | prtmst has dual wh_id_tmpl rows ('----' and 'WMD1') — must filter to specific warehouse |
| 73 | important | ITMMST SPLITs in PrIME; RTCIS comma-join = INNER → CROSS APPLY dedup |
| 80 | critical | PrIME 2022 area/zone/loc-type taxonomy is a BUSINESS REDESIGN, not a 1:1 rename of RTCIS ARECOD/ZONCOD. Use RTCIS LOCATN/ZONCOD for MEMBERS only; take the taxonomy from the site's Site Configuration Model and map each location by building+material+handling intent |
| 81 | critical | Structural validity != design correctness. A transform can pass 100% FK/structure validation yet be ~0% consistent with the business design. Validate generated taxonomy against the FILLED Site-Config workbook, not just Athens structure + RTCIS values |
| 82 | important | PrIME 2022 splits the single 2014 area into 5 frameworks: sto_zone, pck_zone, mov_zone, zonmst (work), loc_typ. Route ZONCOD/PIKZON/LOCTYPE to the correct framework, not all to zonmst |
| 83 | important | LOCATION TYPES must come from the STANDARD PrIME 43-code catalog (ADJS,ASRS,IMAR,IMQM,PND,PROD,PRST...). Never invent (RACK/STAGING/HANDOFF) — invented codes do not bind to PrIME behaviour flags/strategies |
| 84 | important | PrIME 2022 dual-row pattern: each part/ftp/policy is written TWICE — a TEMPLATE row (WH_ID/WH_ID_TMPL='----') plus a WAREHOUSE row (='BR01'). Must be reproduced |
| 85 | important | Minhang go-live WH_ID = BR01 (confirmed by Site Config Model 2026-06-14, SAP Storage Location=BR01). NOT the WMH1 placeholder, NOT Athens WMD1 |
| 86 | important | At Minhang LOCTYPE and WRKZON are 100% NULL in RTCIS LOCATN; derive loc_typ/work-zone from ARECOD class + Site-Config instead of mapping the empty columns |
| 87 | important | IM (inventory-management) locations use dedicated IMAR + IMQM loc-types and are the only ones that emit SAP movement-type adjustments (309/311); normal storage sends nothing. SAP movements stay at AREA level, not zone level |

## Example Cypher (works against the current schema)

```cypher
// All RTCIS -> PrIME table mappings
MATCH (r:RTCISTable)-[m:MAPS_TO]->(p:PrIMETable)
RETURN r.name AS rtcis, m.type AS kind, p.name AS prime ORDER BY p.name;

// Minhang masterdata / 5-framework learnings
MATCH (l:Learning) WHERE l.id >= 80
RETURN l.id, l.severity, l.finding ORDER BY l.id;

// Value remaps (e.g. QASTAT, WH_ID=BR01)
MATCH (rv:RTCISValue)-[:REMAPS_TO]->(pv:PrIMEValue)
RETURN rv.key AS rtcis_value, pv.key AS prime_value;
```
