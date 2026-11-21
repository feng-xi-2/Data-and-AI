---
title: Sites and warehouse IDs
type: entity
status: documented
sources: [raw/memories/whid_site_map.md, raw/memories/timbr_api.md, raw/kb/WH_Data_Replica_Servers.md, raw/memories/euskirchen_rtcis_prime2022.md]
evidence: []
updated: 2026-10-20
---
# Sites

| Site | wh_id | Engine | Role in this wiki |
|---|---|---|---|
| Euskirchen | RTCIS DE07 (RPM, subsit 0) + DE08 (FP, subsit 1) → PrIME `DE08` | RTCIS prod + PrIME 2022 DEV-FULL | Conversion target (RPM R01–R17, label Q01–Q18) |
| Athens | `WMD1` | PrIME 2022 live | Live witness; Pomezia set validated here |
| Crailsheim | `DE29` | PrIME 2022 live | Pick-work / list-pick witness |
| London | GB47 | RTCIS | 4th engine; exposed the setup-denominator defect (257/811 wrong) |
| Pomezia | IT01 (2022) | RTCIS → PrIME | 34 + 3 vendor queries (raw/reference) |
| Amiens BB / KH | FR57 / FR88 (same SAP plant 4106) | PrIME | Timbr ontology work — different sites, split by SLoc |
| Mataro | ES30 (plant 5683) | PrIME | Timbr test site |

Other codes `[LEARNED]` (raw/memories/whid_site_map.md): AD/BU/CV/CW/CX/GU/GX/PG/RT = Cape Girardeau; VN07 = Binh Duong;
RO15 (letter O) = Urlati; DE29 Crailsheim; ES06 Jijona; ES08 Mequinenza; FR09 Blois; PH03 Cabuyao; BE88 Mechelen;
EG00 Cairo; HU26 Gyongyos; PL21 Targowek; RU04 Novo; TH06 Bangkok; … (full list in the raw note).
wh_id is embedded in Config-Drift free text as `Warehouse ID <CODE>` (angle brackets) — one regex will miss the
`Warehouse ID=CODE` variant.

**Rule:** the RTCIS original can be right at one site and wrong at a sister site (4 instances: `itmcod<>'B2'`,
`subsit='1'`, setup denominator, `@locale`). Always run the original at a second site before trusting it as the reference.
Endpoints: [endpoints](../ground-truth/endpoints.md).
