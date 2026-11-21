---
title: Synonyms, facades and base tables
type: concept
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/timbr_api.md, raw/memories/whid_site_map.md]
evidence: []
updated: 2026-10-20
---
# Synonyms and facades

| Engine | Site-facing object | Real object | How to read columns |
|---|---|---|---|
| PrIME 2022 | `<SITE>_REPLICA.dbo.X` (synonym) | `<SITE>_RTDS.dbo.X` | `SELECT TOP 0 * FROM dbo.X` (`tools/discover.py`) |
| RTCIS | `EUSKIRCHEN.live3.X` (trimmed view facade) | `[EUSKIRCHEN_simp].live3.X` | query the `_simp` base table |
| PrIME 2014 | `URLATI.dbo` (16 views + 482 synonyms) | `URLATI_simp.prodwms` | metadata from `_simp` |

`INFORMATION_SCHEMA` and `sys.columns` are **blind** through synonyms; list synonyms with
`SELECT name, base_object_name FROM sys.synonyms`. `[DB]` Some objects exist only in the facade
(`AGV_INVENTORY_VIEW`, `USERS`), and `CBO_*` views live in schema `EUSKIRCHEN.euskirchen`. The view layer may
hold `*_VIEW` objects that the `_simp` DB lacks — inventory views before declaring a field absent.
The `dbo` schema of some RTCIS DBs holds HVR control tables (493), not business data.
