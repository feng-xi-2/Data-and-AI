# PBI Standard Kit - warehouse reports on PrIME 2014 / PrIME 2022 replicas

Standard building blocks for a Power BI report on a warehouse Data Replica, taken from the PRIME ELS Hypercare KPI kit (see the
`PRIME ELS` folder of this repo for the full generator).

| Folder | What |
|---|---|
| `queries/PrIME_2014/` | every replica query of the kit for PrIME 2014 sites (schema `prodwms`, zoning by area code) |
| `queries/PrIME_2022/` | the same queries for PrIME 2022 sites (schema `dbo`, `sto_zone` / `loc_typ` tables) |
| `queries/TOKENS.md` | the site tokens (`{WH_ID}`, `{LOC_LTA}`, ...) each query needs and where their values come from |
| `skills/pbi-build-standards/` | how to build, gate, test, publish and refresh a report so it works the first time in the Service |
| `skills/hypercare-site-setup/` | add / configure / remove a site: profile the replica, fill the settings with evidence |
| `skills/wh-hypercare-kpi/` | build, validate and publish the Hypercare KPI dashboard |
| `skills/data-replica-latency/` | how fresh a site's replica is (HVR watermark, newest transaction) |

## Use a query template
1. Pick the folder of the site's WMS version (2014 or 2022).
2. Replace the `{TOKENS}` listed in the file header with the site's values (`TOKENS.md`); `{WH_ID}` is the warehouse id.
3. Run read-only on the site's replica with a bounded date range (`TOP n`, `trndte >= DATEADD(day, -14, ...)`).

Server names, tenants and workspace ids are replaced by placeholders; no data and no credentials are in this folder.
