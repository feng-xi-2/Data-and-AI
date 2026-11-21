---
title: Endpoints (servers, databases, schemas)
type: ground-truth
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/whid_site_map.md, raw/kb/WH_Data_Replica_Servers.md]
evidence: [results/summary.csv]
updated: 2026-10-20
---
# Endpoints `[DB]`

All Azure SQL Managed Instance, AAD auth ([connect](../connect.md)). Verified by 51/51 successful runs on 2026-10-20.

| Key (`tools/sites.py`) | Engine | Server | Database | Schema to use |
|---|---|---|---|---|
| `RTCIS_EUS` | RTCIS Euskirchen (prod replica) | `<replica-host>` | `EUSKIRCHEN` | base tables `[EUSKIRCHEN_simp].live3.*`; views `EUSKIRCHEN.live3.AGV_INVENTORY_VIEW`, `EUSKIRCHEN.live3.USERS`, `EUSKIRCHEN.euskirchen.CBO_*` |
| `PRIME_DE08` | PrIME 2022 Euskirchen (**DEV-FULL**) | `<replica-host>` | `EUSKIRCHEN_REPLICA` | `dbo` (synonyms) |
| `PRIME_DE08_RTDS` | same, technical | same | `EUSKIRCHEN_RTDS` | `dbo` base tables, `hvr` (replication state), `archprime` (archive) |
| `PRIME_WMD1` | PrIME 2022 Athens (live) | `<replica-host>` | `ATHENS_REPLICA` | `dbo` |

Other witnesses used in earlier work `[LEARNED]`:
- **Crailsheim DE29** (live PrIME 2022): `<replica-host>`, `CRAILSHEIM_REPLICA`
  (`CRAILSHEIM_RTDS`: `dbo` live, `archwms` archive). A far better pick-work witness than DE08.
- **RTCIS London** — 4th engine when Euskirchen RTCIS cannot serve a case (`PALLETS_VIEW` missing for Q02/Q08/Q10).
- Cape Girardeau RTCIS prod `<replica-host>…` db `CAPEGIRARDEAU_RTCIS` schema `live3`; Urlati PrIME 2014
  `<replica-host>…` (base tables `URLATI_simp.prodwms`). See [sites](../entities/sites.md).

## Facts about these endpoints
- **One PrIME replica = exactly one warehouse.** `EUSKIRCHEN_REPLICA` = DE08 only; `ATHENS_REPLICA` = WMD1;
  `CRAILSHEIM_REPLICA` = DE29. Binding DE29 on EUSKIRCHEN_REPLICA silently returns nothing.
- Euskirchen RTCIS DE07 (RPM, `subsit 0`) + DE08 (FP, `subsit 1`) = **one** PrIME warehouse `DE08` ([building-subsit](../concepts/building-subsit.md)).
- Power BI gateways `MI-EUSKIRCHEN_REPLICA-DEV-FULL-PaaS-ADHOC`, `MI-EUSKIRCHEN_RTDS-DEV-FULL-PaaS-ADHOC`; the ad-hoc
  schema name `euskirchen_replica` is a reporting label, not a database schema.
- `raw/kb/WH_Data_Replica_Servers.md` lists ~77 endpoints but is **incomplete** (Urlati missing; Binh Duong / Ben Cat
  have no documented replica).
- **Not reachable** from the replicas: DAS (`DASLIV1.*_RTCIS_CUR`, `das_rcphst`), `RPM_System`, `CS_DataWarehouse`.
