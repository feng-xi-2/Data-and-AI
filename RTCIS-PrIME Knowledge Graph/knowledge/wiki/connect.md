---
title: Connecting to SQL MI replicas
type: method
status: verified
sources: [raw/memories/rtcis_prime_conversion_kit.md, raw/kb/WH_Data_Replica_Servers.md, raw/kb/ALL_LEARNINGS.md]
evidence: [results/summary.csv]
updated: 2026-10-20
---
# Connecting to the databases

## Prerequisites
- Python 3.11+ with `pyodbc` and `msal`; **Microsoft ODBC Driver 18 for SQL Server**.
- Your own P&G Azure AD account with read access to the replica servers.

## How it works (`tools/db_session.py`, `tools/sites.py`)
MSAL public client, **device-code flow**, scope `https://database.windows.net/.default`, ODBC Driver 18 with the access
token (connection attribute 1256). Access token cached ~1 h in `tools/.access_token.json`, refresh token in
`tools/.msal_cache.json` — both git-ignored; never print or share. `RTCIS_PRIME_TOKEN_DIR` points the cache elsewhere
(one login per hour across folders). In SSMS: *Azure AD – Universal with MFA*, same server/database.

```python
import sys; sys.path.insert(0, "tools")
from sites import connect
cur = connect("PRIME_DE08").cursor()
cur.execute("SELECT TOP 5 LODNUM FROM dbo.invlod")
```

Site keys and servers: [endpoints](ground-truth/endpoints.md). Add a site by adding one entry to `tools/sites.py`
(server, database, label) — check [sites](entities/sites.md) and `raw/kb/WH_Data_Replica_Servers.md` (~77 endpoints,
known to be incomplete).

## Client-side gotchas
- **ODBC type -155**: `AT TIME ZONE` / `SYSDATETIMEOFFSET()` return DATETIMEOFFSET, which pyodbc cannot fetch. Valid
  SQL; register `conn.add_output_converter(-155, …)` (done in `run_queries.py`). Compiling is not executing.
- **Multi-line PowerShell commands desync the VS Code terminal** — use single-line commands or a here-string piped to `python -`.
- **Runner DECLARE stripping**: keep DECLAREs of runner-bound parameters on one line.
- Long/remote calls need a timeout, retry with backoff and visible heartbeat logs; never swallow errors.

Database-side facts (synonyms, collation, retention, freshness) are ground truth: [data-facts](ground-truth/data-facts.md).
