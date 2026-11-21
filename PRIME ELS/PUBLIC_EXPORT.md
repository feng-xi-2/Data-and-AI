# PRIME ELS Hypercare KPI kit - public copy

This folder is a **sanitized** copy of the PRIME ELS (Early Life Support) Hypercare KPI Power BI kit: generators, configuration,
SQL templates, theme, skills and how-to docs. It holds **no data and no built report** (.pbix / PBIP output are left out).

Placeholders replace every installation-specific value:

| Placeholder | Stands for |
|---|---|
| `<replica-server>.database.windows.net` | the site's Data Replica (Azure SQL Managed Instance) host |
| `MI-<SITE>-PROD-FULL-PaaS-ADHOC` | the on-premises / VNet gateway connection name for the site |
| `<databricks-host>`, `<warehouse-id>` | the Databricks SQL warehouse used for SAP data |
| `<sharepoint-url>`, `<user-home>`, `<user>@<company>`, `<ad-group>`, `<company-org>` | internal locations, people and groups |
| `<id>` | workspace / model / report / tenant ids of an installation |

Empty in `config/site_config.csv`: Notes, SAP_Plant and the RPM file columns.

To use it: fill the placeholders in `config/site_config.csv` (and `config/build_options.csv`), then follow
`docs/HOW_TO_BUILD.md` and `docs/HOW_TO_USE.md`. Deploy the built PBIP to a **private** repository connected to the Fabric workspace
(see "Deploy from Git" in `docs/HOW_TO_UPDATE.md`) - never commit real server names or data here.
