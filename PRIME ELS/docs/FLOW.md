# PRIME ELS Hypercare KPI - flow

```mermaid
flowchart LR
  subgraph CFG[config/*.csv  =  Cfg_* tables in the model]
    S[Cfg_Site\nreplica, wh_id, shifts,\nlocation patterns, flags, CDL]
    E[Cfg_Engine\nPrIME 2022 vs 2014]
    T[Cfg_Threshold\ntarget / warn / crit]
    A[Cfg_AlertRule]
    R[Cfg_RCA\nroot cause / verdict texts]
    H[Cfg_HealthCheck]
    L[Cfg_LineMap]
    G[Cfg_PageGuide / Cfg_Market]
  end
  B[build_pbip.py\none partition per site\nstatic server / db / CDL literals] --> TOK
  S --> TOK[SiteTokens(site) + fnSiteSql\nrender {TOKENS} in SQL]
  E --> TOK
  L --> TOK
  TOK --> RQ[(Data replica\nPrIME 2022 dbo / 2014 prodwms)]
  TOK --> CDL[(CDL Databricks\nSAP plaf / afko / zr3ortec)]
  RQ --> F[Feed tables\nProduced / Shipped / TTAT / Outbound TTA /\nLevel A / HOFF / Pallets Location /\nShort PO / User Activity / Data Health ...]
  CDL --> F
  F --> K[_KPI measures\nactual - status - prediction]
  SL[Site slicer - every page, synced\nfilters Cfg_Site -> every table] --> F
  IN[Threshold input boxes\nConfig & Health, synced] --> K
  T --> K
  A --> K
  R --> K
  H --> K
  K --> PG[Pages\nHome - Cockpit - Alerts & RCA -\nBD detail pages - User Productivity -\nConfig & Health]
  G --> PG
```

## One model, all sites

* Every replica table has one import partition per site (`<Table> - <SITE>`) built from the same tokenised query; the partition adds `SiteCode`.
* `Cfg_Site[SiteCode]` 1 -> * every site table (single direction). The Site slicer (banner, synced on every page, single select + forced) filters them.
* Measures read the site with `SELECTEDVALUE(Cfg_Site[...])`; thresholds with `LOOKUPVALUE(Cfg_Threshold[...], KPI_Key, SiteCode)`; any `REMOVEFILTERS(<site table>)` is followed by `VALUES(Cfg_Site[SiteCode])` (added by the build) so clearing a fact never drops the site.
* Shared calendars (DimDate, DimBucket, DimHour, DimShiftDate) are built once; labels use the `Is_Default` site. Fact calculated columns use their own row's site.
* Lookup tables shared by facts (`RPM Masterdata`) use `<SITE>|key` relationship keys; the both-ways WorkLine <-> Produced Pallet link is inactive (it was only used on its own page).

## KPI logic (thresholds = page input box if typed, else Cfg_Threshold of the selected site)

| # | KPI | Actual | Prediction |
|---|---|---|---|
| 1 | Production pallets / h | pallets leaving LTA on the shift day / elapsed hours | pallets so far + run rate of the last RUN_RATE_HOURS x remaining hours |
| 2 | Inbound TTAT | avg check-in -> dispatch per truck dispatched on the day | FORECAST_DAYS linear trend -> next day |
| 3 | Outbound TTAT | avg check-in -> close per trailer closed on the day | FORECAST_DAYS linear trend -> next day |
| 4 | Location utilisation | occupied / usable storage locations (locmst useflg & stoflg) | + net (in - out) pallets/h x PRED_HORIZON_H |
| 5 | User productivity | distinct pallets moved / active RF user-hours (dlytrn) | - |
| 6 | Daily health | failed checks of Cfg_HealthCheck | - |

Status: *Higher* KPIs are CRITICAL below `Crit_At`, WARNING below `Warn_At`; *Lower* KPIs the opposite; *Band* KPIs (80/20 splits) by distance from target. `Warn_At / Crit_At = Target x Warn_Pct / Crit_Pct` (Higher) or `Target x (1 + pct)` (Lower), or the absolute `Warn_Abs / Crit_Abs`.

## PrIME 2014 vs 2022 (Cfg_Engine)

| Item | PrIME 2022 | PrIME 2014 |
|---|---|---|
| Replica db | `<SITE>_REPLICA` | `<SITE>` |
| Schema `{S}` | dbo | prodwms |
| Storage zone `{ZONE_COL}` | locmst.sto_zone_id (+ sto_zone join) | locmst.arecod (no sto_zone) |
| Location type | loc_typ flags | area prefixes (PE* line, RS*/RCV* receiving, SHST* shipping) |
| Footprint `{T_FOOTPRINT}` | prtftp_view (BD: binhduong_replica.footprint_md) | prtftp_view |

## Onboarding a site (≈ 30 min)

1. `py tools/probe_replica_schema.py <SITE>` / `py tools/profile_site.py <SITE>` -> engine, wh_id, areas, oprcod, trailer codes, LTA locations.
2. Add the row to `config/site_config.csv` + lines to `config/line_map.csv` (flags OFF for pillars the site does not run).
3. `py tools/validate_sql.py <SITE>` (all OK) -> `py tools/build_pbip.py` -> open `dist/ALL_SITES/WH Hypercare KPI.pbip`, refresh, pick the site in the Site slicer, check **Config & Health**.
4. `py tools/publish.py` and map the data-source credentials / gateway connection of the new server in the Service.
