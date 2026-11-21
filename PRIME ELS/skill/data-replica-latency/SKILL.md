---
name: data-replica-latency
description: Measure Data Replica (Azure SQL Managed Instance) freshness / lag for ANY P&G warehouse site across ALL THREE WMS engines — PrIME 2022, PrIME 2014, and RTCIS. USE WHEN checking how fresh / how behind a site's replica is, HVR replication watermark / capture latency, whether HVR is blocked or flowing, or how far behind the newest business transaction (dlytrn / SYSTRN) has landed. Trigger phrases 'replica latency', 'data replica lag', 'HVR watermark', 'how fresh is the data', 'how far behind is the replica', 'is HVR blocked', 'replication delay', 'data freshness', 'capture latency', 'latest transaction time', 'is the replica up to date'. Also USE WHEN you must resolve which replica DB is live vs a stale facade (e.g. Crailsheim), which schema/db holds the HVR control tables per engine, or the correct site-local vs UTC comparison.
---

# Data Replica Latency Check (2022 / 2014 / RTCIS)

Measure two independent, fact-grounded latency numbers for a warehouse Data
Replica, on any of the three WMS engine generations, read-only.

## When to use
- "How fresh / how far behind is <site>'s replica right now?"
- "What is the HVR watermark latency? Is HVR blocked?"
- "What's the newest transaction time in the replica, and how old is it?"
- Comparing latency across a 2022, a 2014, and an RTCIS site in one pass.

## The two numbers (never conflate them)
1. **HVR CAPTURE LATENCY** = `SYSUTCDATETIME() − trailer_cap_begin`.
   `trailer_cap_begin` is the HVR **capture watermark (UTC)** from the integrate
   state table `hvr_is*`. It says *how far behind the SOURCE the replication
   capture is*. Seconds = healthy.
2. **DATA LATENCY** = `site_local_now − MAX(<txn>.<date>)`. The newest business
   transaction that actually landed in the replica. The txn date is **site-local**,
   so compare against **site-local now** (apply the UTC offset), never UTC.
3. **integ_blocked** flag from `hvr_ic*`: `0` = flowing; non-zero = **HVR ALERT**.

> CAVEAT: `last_integ_end` in `hvr_is*` sits ~8–9 min AHEAD of now — it is an HVR
> heartbeat marker, NOT a latency source. Do NOT use it. Use `trailer_cap_begin`.

## Where each engine keeps its tables (the crux)

| Engine | Replica DB | Txn source (date col) | HVR control db.schema |
|--------|-----------|-----------------------|-----------------------|
| **PrIME 2022** | `<SITE>_REPLICA` | `dbo.dlytrn.trndte` | `<SITE>_RTDS.hvr` → `hvr_is*` / `hvr_ic*` |
| **PrIME 2014** | `<SITE>` (or `<SITE>_simp`) | `prodwms.dlytrn.trndte` | `<SITE>_simp.dbo` → `hvr_is<site>` / `hvr_ic<site>` |
| **RTCIS** | `<SITE>` | `live3.SYSTRN.SYSDAT` | `<SITE>_simp.simp_repl_live` → `hvr_is<site>` / `hvr_ic<site>` |

Engine detection is by where `dlytrn` resolves: schema `dbo` → 2022, schema
`prodwms` → 2014, no `dlytrn` but `SYSTRN` present → RTCIS.

### RTCIS date-column gotcha
`live3.SYSTRN` and `dlytrn` are **synonyms**, so `sys.columns` is empty for them —
you must probe candidate column names with `MAX()`. On RTCIS the correct column is
**`SYSDAT`** (real system-transaction time). Do NOT pick `APTDAT` or `LRDATE`:
those are **future appointment dates** (hours ahead) and would falsely report the
replica as "ahead of now". Always prefer by business meaning, not newest value.

### Crailsheim DB trap
`<replica-server>` hosts a **stale 2014 facade** DB named `CRAILSHEIM`
(frozen). The live 2022 feed is **`CRAILSHEIM_REPLICA`**. Always target
`_REPLICA`; the tool auto-avoids `_RTDS` / `_SIMP` / `_ARCH` facades.

## Timezone offsets (summer 2026, site-local minus UTC)
Crailsheim +2 · Athens +3 · Pomezia +2 · Xiqing/Cabuyao +8 · SMO/Vallejo (LA) −6.

## How to run
Companion script: [replica_latency_check.py](replica_latency_check.py)

```powershell
$py = "<user-home>/AppData/Local/Python/pythoncore-3.14-64/python.exe"
cd ".github/skills/data-replica-latency"
& $py replica_latency_check.py                          # demo: one of each engine (ATHENS SMO POMEZIA)
& $py replica_latency_check.py ATHENS CRAILSHEIM POMEZIA
& $py replica_latency_check.py --server <replica-server> --db XIQING --offset 8   # unknown site
```

The tool is self-discovering: it lists databases, resolves the freshest WMS db,
locates `hvr_is*`/`hvr_ic*` by name across `_RTDS` → `_simp` → other dbs, and
auto-detects the transaction source + engine. It writes `_replica_latency.txt`
and `_replica_latency.csv` beside itself, prints a 5-second heartbeat, wraps every
step in try/except, and suppresses nothing (per the no-silent-failure rule).

Auth reuses `SQL_Translations/_mm_audit/_prfc3957_db.py` (MSAL AAD device-code,
token cached in `~/.sql_session`). The path resolver in the script finds the
helper from either the OneDrive or the Local Desktop workspace copy; if neither,
set the `SQLT_MM_AUDIT` env var to the `_mm_audit` folder.

## Interpreting output (validated 2026-09-01)
```
SITE        ENGINE     HVR cap lat    data latency  blocked
ATHENS      2022          0h 0m 8s       0h 31m 2s        0
SMO         2014          0h 0m 6s        0h 0m 5s        0
POMEZIA     RTCIS        0h 1m 36s       0h 1m 44s        0
CRAILSHEIM  2022         0h 0m 52s       0h 0m 35s        0
```
- Both latencies in **seconds/low minutes** and `blocked=0` → healthy, real-time.
- `blocked != 0` → HVR integrate stopped: escalate, the replica is diverging.
- Large **data latency** but small **HVR latency** → source WMS itself is quiet
  (few transactions), not a replication problem.
- **data latency = n/a** → the txn source wasn't resolvable; fall back to HVR
  capture latency (the authoritative replication-freshness signal).

## Add a new site
Add an alias to the `SITES` dict in the script:
`"NAME": ("<replica-server><site>prod", "<WMS_DB>", <utc_offset_h>, "<engine_hint>")`.
`engine_hint` is advisory only — the script re-detects the engine live. Or skip
the registry and pass `--server/--db/--offset` directly. A server on another domain than the default
suffix (e.g. BINHDUONG / MINHANG on `.<mi-dns-zone>`) goes in as the full host name — it is used as given.
