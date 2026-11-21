# PrIME 2014 → PrIME 2022 SQL Remediation Guide

**Version:** 1.0 | **Date:** May 11, 2026 | **Last Updated:** 2026-07-06  
**Purpose:** Comprehensive methodology for remediating PrIME 2014 SQL queries to PrIME 2022, with configurable batch validation across any WMS site.  
**Audience:** WMS Engineers, Data Analysts, Site Implementation Teams

---

## Table of Contents

1. [Overview](#1-overview)
2. [Remediation Rules (Governing Principles)](#2-remediation-rules-governing-principles)
3. [Key Structural Changes: 2014 vs 2022](#3-key-structural-changes-2014-vs-2022)
   - [3.7 Worked Example: Loading Dock Dashboard](#37-worked-example-loading-dock-shipment-progress-dashboard) — Original query, remediated query, column mapping with NULL/empty classification
4. [Knowledge Base (KB)](#4-knowledge-base-kb)
5. [Agent Flow → 7-Phase Remediation Workflow](#5-agent-flow--7-phase-remediation-workflow)
6. [3-Tier Lookup & Iteration Method](#6-3-tier-lookup--iteration-method)
7. [Site Configuration & Schema Discovery](#7-site-configuration--schema-discovery)
8. [Batch Remediation of Multiple Queries](#8-batch-remediation-of-multiple-queries)
9. [Database Validation → Live Execution](#9-database-validation--live-execution)
10. [Two-Phase Comparison Approach (Go-Live Strategy)](#10-two-phase-comparison-approach-go-live-strategy)
11. [Output Format](#11-output-format)
12. [Batch Validation Script](#12-batch-validation-script)
13. [Validation Results (Reference)](#13-validation-results-reference)
14. [Quick-Start Checklist](#14-quick-start-checklist)

---

## 1. Overview

The PrIME WMS platform is being upgraded from **PrIME 2014** (Oracle-origin, SQL Server) to **PrIME 2022** (native SQL Server). This affects ~99+ production QuickView/NEMC reports across all WMS domains: inventory, cycle count (IRA), shipping, receiving, work orders, picking, replenishment, AGV, trailer/yard, and configuration.

The remediation is **NOT a 1:1 find-and-replace**. Key architectural changes (Areas → Zones, `cntflg` removal, `untinp` → `untlay`, flag migration from `aremst` to `locmst`, synonym-based architecture) require understanding the **business intent** of each query FIRST, then rebuilding it for the 2022 data model.

> **Core Principle:** Read the query context first — understand WHAT the query does for warehouse operations, WHAT business question it answers — then produce the best possible 2022 remediation. Never mechanically replace table/column names.

### Validation Strategy

| Version | Validate On | Example |
|---------|------------|----------|
| Original 2014 | A site still on 2014 (e.g. Crailsheim) | `prodwms.locmst` |
| Remediated 2022 | A reference 2022 site (Athens) | `dbo.locmst` |

**Critical:** Crailsheim is still PrIME 2014 — do NOT validate 2022-remediated queries there. Use Athens (`ATHENS_REPLICA`) for all 2022 validation.

### Three WMS Systems

| System | Schema | Example | Status |
|--------|--------|---------|--------|
| **RTCIS** | `esiliv1` (live3) | `esiliv1.LOCATN` | Legacy → being decommissioned |
| **PrIME 2014** | `prodwms` (or `dbo`) | `prodwms.locmst` | Current at most sites |
| **PrIME 2022** | `dbo` | `dbo.locmst` | Target → being rolled out |

### Two Conversion Scenarios

- **Scenario A:** RTCIS → PrIME 2022 (cross-platform)
- **Scenario B:** PrIME 2014 → PrIME 2022 (version upgrade) → **this guide**

---

## 2. Remediation Rules (Governing Principles)

These rules govern **every** remediation task. They are non-negotiable and must be followed by any human or AI agent performing query remediation.

### Rule 1: Context First — Never Do 1:1 Translation

Remediation is **NOT** a mechanical find-and-replace of table/column names. Before touching a single line of SQL:
1. **Read the full query** and understand its business purpose (e.g., "find locations with multiple lots in pickfaces").
2. **Identify the warehouse workflow** it serves (inventory audit, replenishment trigger, IRA accuracy, shipping manifest, etc.).
3. **Then** produce the best possible 2022 equivalent that preserves the same business answer — even if the SQL structure changes significantly.

> A query that filters `aremst.pckflg=1` is not asking "give me rows where pckflg is 1" — it is asking "give me pick locations." In 2022, pick locations are identified by `locmst.PCKFLG=1` because flags migrated from `aremst` to `locmst`.

### Rule 2: Iterate Against the Real Database

Do your best to **dig into the live database** to get accurate results through iteration:
1. **Run the remediated query** on the target database (e.g., Athens for 2022).
2. **If it fails**, analyze the error — probe the schema (`SELECT TOP 0 * FROM dbo.{table}`), check column existence, verify join paths.
3. **Fix and re-run** until the query executes successfully and returns meaningful data.
4. **Never guess** column names or assume schema matches documentation — always verify against the live database.
5. Target up to **3 iterations** per query before escalating to manual review.

### Rule 3: Capture Feedback as Knowledge

Every iteration produces learnings. **Capture them immediately** so the next task benefits:
- If a column was discovered to have migrated (e.g., `aremst.pckflg` → `locmst.PCKFLG`), record it in the KB.
- If a site has a unique schema variation, log it as a site-specific finding.
- If a query pattern works for one domain, generalize and apply it to similar queries.
- Feedback from users, DBAs, or validation failures → update `remediation-learnings.json` and session memory.
- **Cross-query learning:** If Q1's fix reveals a flag migration, apply that knowledge immediately to Q2, Q3, etc. without re-discovering it.

### Rule 4: Configurable Inputs — Site, Connection, and Query Source

The remediation solution must be **configurable**, not hardcoded:
- **Database connection:** Server URL, database name, schema, and credentials may differ per site. Others may provide different connection context. Support Azure AD Interactive, service principal, or connection string.
- **Query input:** Accept queries from multiple sources:
  - **Batch file:** Excel (`.xlsx`), CSV, JSON, or a folder of `.sql` files.
  - **Single query:** Pasted directly in a dialogue or chat.
  - **Mixed:** A batch file with some queries overridden by dialogue input.
- **Site parameters:** `wh_id`, schema prefix, version (2014/2022/hybrid) — all discoverable via probe or provided by the user.
- **Reference site:** The 2022 validation target (e.g., Athens) should be configurable, not assumed.

### Rule 5: Accuracy First — Native Columns Before Casts

The output must be **accurate and transparent**:
- If a column returns `NULL`, show the **native column name** or the **transformed column** first — not the `CAST` or `COALESCE` wrapper.
  - **Good:** `locmst.PCKFLG` returns `NULL` → report as `PCKFLG = NULL`.
  - **Bad:** `CAST(PCKFLG AS VARCHAR)` returns `NULL` → hides which column is actually null.
- When displaying results or debugging, always indicate:
  - Which column is the **native source column** (from the base table).
  - Which column is a **derived/calculated column** (via CASE, COALESCE, CAST, etc.).
- If a `NULL` placeholder is used (e.g., for a removed column like `cntflg`), explicitly state: "This column no longer exists in 2022; NULL is a placeholder."

### Rule 6: Reuse Database Sessions

To avoid repeated authentication prompts:
- **Use MSAL device code flow** with file-based token caching — authenticate once, reuse token for ~1 hour across all processes.
- **Cache connections** in a module-level dict so subsequent queries in the same process reuse the same connection.
- The shared session module `_db_session.py` handles: token acquisition (MSAL device code), token file caching (`.access_token.json` + `.msal_cache.json`), connection pooling, and auto-reconnect.
- On first run: user authenticates via device code (browser). Token is cached to disk. Subsequent runs (within ~1 hour) reuse the cached token with no prompts.

```python
import pyodbc, msal, json, os, time

_conn_cache = {}  # Module-level cache: {site_name: connection}

AUTHORITY = "https://login.microsoftonline.com/{tenant_id}"
CLIENT_ID = "1950a258-227b-4e31-a9cf-717495945fc2"  # Azure PowerShell well-known app
SCOPE = ["https://database.windows.net/.default"]

def _get_token():
    """Get Azure AD token via device code flow with file caching."""
    # Check cached token file first
    cache_path = os.path.join(os.path.dirname(__file__), ".access_token.json")
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        if cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]  # Still valid

    # MSAL device code flow
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
    flow = app.initiate_device_flow(scopes=SCOPE)
    print(flow["message"])  # User sees "go to https://... and enter code XXX"
    result = app.acquire_token_by_device_flow(flow)
    token = result["access_token"]

    # Cache to disk
    with open(cache_path, "w") as f:
        json.dump({"access_token": token, "expires_at": time.time() + 3600}, f)
    return token

def get_connection(site_config):
    """Get or reuse a cached database connection using MSAL token."""
    name = site_config["name"]
    if name in _conn_cache:
        try:
            _conn_cache[name].cursor().execute("SELECT 1")
            return _conn_cache[name]
        except Exception:
            pass  # Stale connection, reconnect

    token = _get_token()
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={site_config['server']};"
        f"DATABASE={site_config['database']};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=120",
        attrs_before={1256: token.encode()}  # SQL_COPT_SS_ACCESS_TOKEN
    )
    _conn_cache[name] = conn
    return conn
```

### Rule 7: Preserve Original Input Verbatim

The original SQL provided by the user **MUST be stored exactly as given** — including all:
- Original formatting and whitespace (even inconsistent indentation)
- Inline comments (`-- ...`, `/* ... */`)
- Commented-out debug lines (e.g., `-- select * from FINAL_Shipment`)
- Line breaks and spacing patterns

**Why:** The HTML report displays both Original and Remediated SQL **side-by-side**. Users need to verify the original matches their source exactly. Reformatting or removing comments would make the report untrustworthy — the user couldn't tell if we changed the logic or just the formatting.

**Implementation:** Store original SQL as a raw string literal. Never apply auto-formatting, comment stripping, or whitespace normalization to the original input.

---

## 3. Key Structural Changes: 2014 vs 2022

### 3.1 Areas → Zones (Biggest Change)

PrIME 2014 uses a flat **area-centric** model. PrIME 2022 restructures this into a multi-layer **zone** architecture:

| PrIME 2014 | PrIME 2022 | Purpose |
|------------|------------|---------|
| `aremst` (area master) | `aremst` + `sto_zone` + `mov_zone` + `pck_zone` | Separate zone layers for storage, movement, picking |
| `aremst.cntflg` (count flag) | **REMOVED** → all areas are countable | No need to filter by `cntflg=1` |
| `aremst.pckflg`, `pdflg`, `stoare_flg`, `shp_dck_flg` | **REMOVED from aremst** | These flags migrated to `locmst` |
| `locmst` flags | `locmst.PCKFLG` (pick flag), etc. | **Flags moved from aremst → locmst in 2022** |
| Area type via `arecod` lookup in `dscmst` | Same, but requires **COALESCE** fallback | Some sites use `arecod\|wh_id` key, others use plain `arecod` |
| `locmst.arecod` | `locmst.arecod` + `LOC_TYP_ID` | Location type added alongside area |
| Zone columns: N/A | `locmst.PCK_ZONE_ID`, `STO_ZONE_ID`, `MOV_ZONE_ID` | **New zone columns on locmst (with _ID suffix)** |

**Remediation Rule:** Remove `ar.cntflg = 1` filters. Add COALESCE for description lookups:
```sql
-- 2014 (simple)
LEFT JOIN dscmst e ON ar.arecod = e.colval AND e.colnam = 'arecod'

-- 2022 (COALESCE fallback)
LEFT JOIN dscmst e  ON CONCAT(ar.arecod,'|',ar.wh_id) = e.colval AND e.colnam = 'arecod|wh_id' AND e.locale_id = 'US_ENGLISH'
LEFT JOIN dscmst e2 ON ar.arecod = e2.colval AND e2.colnam = 'arecod' AND e2.locale_id = 'US_ENGLISH'
-- Then: COALESCE(e.short_dsc, e2.short_dsc, ar.arecod) AS aretyp
```

### 3.2 `untinp` →`untlay` (Footprint Rename)

| PrIME 2014 | PrIME 2022 | Notes |
|------------|------------|-------|
| `prtftp_view.untinp` (units per inner pack) | `prtftp_view.untlay` (units per layer) | Column renamed; same business meaning |
| `prtftp_dtl` has `untqty` + `uomcod` | Same | Use `uomcod IN ('PL','LY','CS')` for multi-level queries |

**Footprint Calculation Patterns (with division safety):**
```sql
-- Cases per Layer
CASE WHEN ISNULL(untcas, 0) = 0 THEN untlay ELSE untlay / untcas END AS CASLAY

-- Layers per Pallet
CASE WHEN ISNULL(untlay, 0) = 0 THEN untpal ELSE untpal / untlay END AS LAYPUL

-- Cases per Pallet
CASE WHEN ISNULL(untcas, 0) = 0 THEN untpal ELSE untpal / untcas END AS CASQTY
```

### 3.3 Inventory Model → View vs Base Tables

PrIME 2014 has `inventory_view` which flattens `invlod` + `invsub` + `invdtl`. PrIME 2022 sites may or may not have this view, but the base tables always work:

```sql
-- 2014: inventory_view (single table)
SELECT * FROM prodwms.inventory_view iv
JOIN prodwms.locmst c ON iv.stoloc = c.stoloc AND iv.wh_id = c.wh_id

-- 2022: base tables (always available)
SELECT * FROM dbo.invlod il
JOIN dbo.invsub ivs ON il.lodnum = ivs.lodnum
JOIN dbo.invdtl dtl ON ivs.subnum = dtl.subnum
JOIN dbo.locmst c ON il.stoloc = c.stoloc AND il.wh_id = c.wh_id
```

### 3.4 Schema Prefix Change

| Context | Schema Prefix |
|---------|---------------|
| PrIME 2014 (most sites) | `prodwms.` |
| PrIME 2022 (full upgrade) | `dbo.` |
| Hybrid sites (transitioning) | `prodwms.` but with 2022 behavior (no cntflg) |

### 3.5 Other Key Changes

| Feature | PrIME 2014 | PrIME 2022 |
|---------|------------|------------|
| `uc_custom_parameters` table | Active, used for site configs | **Deprecated** → use `poldat` instead |
| `HAVING` without aggregate | Common in legacy queries | Must move to `WHERE` clause |
| RTCIS `ITMCLS` values | `'F'` / `'P'` | `typcod`: `'FERT'` / `'ROH'` / `'HALB'` |
| `subsit` | RTCIS field | Maps to `wh_id` |
| `ZONCOD` | RTCIS field | Maps to `arecod` (PrIME 2014/2022) |
| Pick methods | Area-defined | `pck_mthd` table (2022) |
| Put-away / allocation | Area properties | Zone-level configuration |

### 3.6 Summary of "Safe Unchanged" Tables

These tables are structurally identical between 2014 and 2022 (only schema prefix changes):

| Table | Domain | Notes |
|-------|--------|-------|
| `locmst` | Location | Same; 2022 may add optional `loc_typ` column |
| `prtmst` | Item Master | Same PK: `prtnum + prt_client_id + wh_id_tmpl` |
| `dscmst` | Descriptions | Same; 2022 adds `arecod\|wh_id` key pattern |
| `cnthst` | Cycle Count History | Same; but `cntflg` filter removed from joins |
| `shipment` / `shipment_line` | Shipping | Same |
| `wkohdr` | Work Orders | Same |
| `poldat` | Policy Config | Same; `uc_custom_parameters` deprecated |
| `dlytrn` | Daily Transactions | Same base; activity codes may differ |

---

### 3.7 Worked Example: Loading Dock Shipment Progress Dashboard

This end-to-end example demonstrates all remediation rules applied to a **real complex query** with 5 CTEs, 8 tables, and site-specific custom objects.

**Business Context:** A shipping dock dashboard showing active loading doors with trailer status, arrival times, staging check, case-pick flag, and pallet loading progress.

#### 3.7.1 Original Query (PrIME 2014 — Crailsheim, DE29)

```sql
With Pronum as (
    select car_move_id as Shipment,
        case
            WHEN car_move.TRACK_NUM = 'ZUG' AND car_move.CTRY_TRACK_NUM = 'DE29' THEN 'DE29'
            WHEN car_move.TRACK_NUM = 'ZUG' THEN 'DE26'
            WHEN car_move.CTRY_TRACK_NUM IS NULL THEN car_move.TRACK_NUM
            ELSE car_move.TRACK_NUM
        end as Pronumtest
    from prodwms.car_move
),
Shipment_Details as (
    select distinct(car_move.Car_move_id)
        + case when left(ord.stcust,1) = 'P' then ' P&G' else '' END as Shipment,
        right(Yard_loc,3) DOOR,
        trlr.arrdte Ankunft,
        early_shpdte Avis,
        trlr_stat,
        trlr.mod_usr_id,
        ord.ordnum,
        case when trlr.live_load_flg = '1' then 'L' else 'D' end as 'LiveDrop'
    from prodwms.car_move
    left outer join prodwms.trlr on car_move.trlr_id = trlr.trlr_id
    left outer join prodwms.locmst on trlr.yard_loc = locmst.stoloc
    left outer join prodwms.ord on car_move.car_move_id = ord.vc_car_move_id
    left outer join prodwms.ord_line on ord.ordnum = ord_line.ordnum
    join Pronum on car_move.Car_move_id = Pronum.Shipment
    where (track_num = 'DE27' or Pronumtest = 'DE29')
        and locmst.arecod like 'RSD%'
        and trlr_stat in ('O', 'LDG')
        and right(left(Yard_loc,6),1) != 'V'
),
Shipment_User as (
    select Shipment_Details.*,
        case when trlr_stat = 'LDG' then mod_usr_id else '' end as User_ID
    from Shipment_Details
),
FINAL_Shipment as (
    select Shipment_User.Shipment, Shipment_User.DOOR, Shipment_User.Ankunft,
        Shipment_User.Avis, Shipment_User.[LiveDrop], Login_id,
        String_agg(case when shipment.shpsts = 'I' then 'NOT_STAGED' else 'OK' end,',') as StagedYesNo,
        case when Login_id is null then '' else Login_id end as Login_id_neu
    from Shipment_User
    left outer join prodwms.LES_USR_ATH on Shipment_User.User_ID = LES_USR_ATH.USR_ID
    left outer join prodwms.shipment on Shipment_User.ordnum = Shipment.SHIP_ID
    group by Shipment_User.Shipment, Shipment_User.DOOR, Shipment_User.Ankunft,
        Shipment_User.Avis, Shipment_User.[LiveDrop], Login_id
),
CP_CHECK as (
    Select VC_CAR_MOVE_ID,
        CASE WHEN SUM(((ORDQTY / UNTQTY) * UNTQTY - ORDQTY)) != 0 THEN 'CP' ELSE '' END AS CP
    from FINAL_Shipment
    left outer join Shipment_Details on left(FINAL_Shipment.Shipment,10) = left(Shipment_Details.Shipment,10)
    left outer join prodwms.ord_line on Shipment_Details.ordnum = ord_line.ordnum
    left outer join prodwms.prtftp on ord_line.prtnum = prtftp.prtnum
    left outer join prodwms.prtftp_dtl on prtftp.prtnum = PRTFTP_DTL.prtnum and prtftp.FTPCOD = PRTFTP_DTL.FTPCOD
    left outer join prodwms.ord on ord_line.ordnum = ord.ORDNUM
    where DEFFTP_FLG = '1' and PRTFTP_DTL.UOMCOD = 'PL'
    group by VC_CAR_MOVE_ID
)
Select FINAL_Shipment.Shipment, FINAL_Shipment.DOOR, FINAL_Shipment.Avis,
    FINAL_Shipment.Ankunft, FINAL_Shipment.[LiveDrop], FINAL_Shipment.Login_id_neu,
    CP_CHECK.CP,
    COALESCE(NoPallets_Geplant, 0) AS Gesamt,
    COALESCE(NoPallets_Loaded, 0) AS Loaded,
    Format(DATEADD(HOUR, 2, GETUTCDATE()),'HH:mm') as Refresh,
    case when StagedYesNo like '%NOT_STAGED%' then 'NOT_STAGED' else 'OK' end as StagedYesNo
from FINAL_Shipment
left outer join CP_CHECK on left(FINAL_Shipment.Shipment,10) = left(CP_CHECK.VC_CAR_MOVE_ID,10)
join [pbiadhoc].[LoadingProgress] on left(FINAL_Shipment.Shipment,10) = [pbiadhoc].[LoadingProgress].VC_CAR_MOVE_ID
```

#### 3.7.2 Remediated Query (PrIME 2022 — Athens, WMD1)

```sql
With Pronum as (
    select car_move_id as Shipment,
        COALESCE(car_move.TRACK_NUM, '') as Pronumtest
    from dbo.car_move
    WHERE car_move.wh_id = '{wh_id}'
),
Shipment_Details as (
    select distinct(car_move.Car_move_id)
        + case when left(ord.stcust,1) = 'P' then ' P&G' else '' END as Shipment,
        right(trlr.Yard_loc,3) as DOOR,
        trlr.arrdte as Ankunft,
        ord_line.EARLY_SHPDTE as Avis,
        trlr.trlr_stat,
        trlr.mod_usr_id,
        ord.ordnum,
        case when trlr.live_load_flg = '1' then 'L' else 'D' end as LiveDrop
    from dbo.car_move
    left outer join dbo.trlr on car_move.trlr_id = trlr.trlr_id
    left outer join dbo.locmst on trlr.yard_loc = locmst.stoloc AND car_move.wh_id = locmst.wh_id
    left outer join dbo.ord on car_move.car_move_id = ord.vc_car_move_id AND car_move.wh_id = ord.wh_id
    left outer join dbo.ord_line on ord.ordnum = ord_line.ordnum AND ord.wh_id = ord_line.wh_id
        AND ord.client_id = ord_line.client_id
    join Pronum on car_move.Car_move_id = Pronum.Shipment
    where car_move.wh_id = '{wh_id}'
        and locmst.arecod IN ('DOCK','SHIP')
        and trlr.trlr_stat in ('O','CI','EX','OR')  -- adaptive: all non-closed statuses at Athens (no LDG/R)
),
Shipment_User as (
    select Shipment_Details.*,
        case when trlr_stat = 'LDG' then mod_usr_id else '' end as User_ID  -- falls back to 'LDG' (no match → empty)
    from Shipment_Details
),
FINAL_Shipment as (
    select Shipment_User.Shipment, Shipment_User.DOOR, Shipment_User.Ankunft,
        Shipment_User.Avis, Shipment_User.LiveDrop,
        LES_USR_ATH.Login_id,
        String_agg(case when shp.shpsts = 'I' then 'NOT_STAGED' else 'OK' end,',') as StagedYesNo,
        case when LES_USR_ATH.Login_id is null then '' else LES_USR_ATH.Login_id end as Login_id_neu
    from Shipment_User
    left outer join dbo.LES_USR_ATH on Shipment_User.User_ID = LES_USR_ATH.USR_ID
    left outer join dbo.shipment shp on Shipment_User.ordnum = shp.SHIP_ID
    group by Shipment_User.Shipment, Shipment_User.DOOR, Shipment_User.Ankunft,
        Shipment_User.Avis, Shipment_User.LiveDrop, LES_USR_ATH.Login_id
),
CP_CHECK as (
    Select ord2.VC_CAR_MOVE_ID,
        CASE WHEN SUM(
            CASE WHEN ISNULL(fd.UNTQTY, 0) = 0 THEN 0
                 ELSE ((ol2.ORDQTY / fd.UNTQTY) * fd.UNTQTY - ol2.ORDQTY)
            END
        ) != 0 THEN 'CP' ELSE '' END AS CP
    from FINAL_Shipment
    left outer join Shipment_Details on left(FINAL_Shipment.Shipment,10) = left(Shipment_Details.Shipment,10)
    left outer join dbo.ord_line ol2 on Shipment_Details.ordnum = ol2.ordnum
    left outer join dbo.prtftp fp on ol2.prtnum = fp.prtnum AND ol2.prt_client_id = fp.prt_client_id
    left outer join dbo.prtftp_dtl fd on fp.prtnum = fd.prtnum AND fp.prt_client_id = fd.prt_client_id
        AND fp.FTPCOD = fd.FTPCOD
    left outer join dbo.ord ord2 on ol2.ordnum = ord2.ORDNUM AND ol2.wh_id = ord2.wh_id
    where fp.DEFFTP_FLG = '1' and fd.UOMCOD = 'PL'
    group by ord2.VC_CAR_MOVE_ID
),
PALLET_COUNTS as (
    -- Derived from pckwrk_view (pick-work records) — 78.3% accuracy vs LoadingProgress
    -- pckwrk_view exists at both Crailsheim (209 cols) and Athens (223 cols)
    Select o_p.VC_CAR_MOVE_ID,
        COUNT(*) as NoPallets_Geplant,
        SUM(CASE WHEN pw.pcksts IN ('C','P') THEN 1 ELSE 0 END) as NoPallets_Loaded
    from dbo.pckwrk_view pw
    JOIN dbo.ord o_p ON pw.ordnum = o_p.ordnum AND pw.wh_id = o_p.wh_id
    WHERE pw.wh_id = '{wh_id}'
    group by o_p.VC_CAR_MOVE_ID
)
Select FINAL_Shipment.Shipment, FINAL_Shipment.DOOR, FINAL_Shipment.Avis,
    FINAL_Shipment.Ankunft, FINAL_Shipment.LiveDrop,
    FINAL_Shipment.Login_id_neu,
    CP_CHECK.CP,
    COALESCE(PALLET_COUNTS.NoPallets_Geplant, 0) AS Gesamt,
    COALESCE(PALLET_COUNTS.NoPallets_Loaded, 0) AS Loaded,
    Format(DATEADD(HOUR, 2, GETUTCDATE()),'HH:mm') as Refresh,
    case when StagedYesNo like '%NOT_STAGED%' then 'NOT_STAGED' else 'OK' end as StagedYesNo
from FINAL_Shipment
left outer join CP_CHECK on left(FINAL_Shipment.Shipment,10) = left(CP_CHECK.VC_CAR_MOVE_ID,10)
left outer join PALLET_COUNTS on left(FINAL_Shipment.Shipment,10) = left(PALLET_COUNTS.VC_CAR_MOVE_ID,10)
```

#### 3.7.3 Remediation Changes (What Changed & Why)

| # | Change | 2014 Original | 2022 Remediation | Why |
|---|--------|---------------|------------------|-----|
| 1 | **Schema** | `prodwms.*` | `dbo.*` | PrIME 2022 uses dbo schema with synonyms |
| 2 | **Pronum CTE** | Filters `TRACK_NUM = 'ZUG'`, maps DE27/DE29/DE26 | `COALESCE(TRACK_NUM, '')` + `wh_id` filter | Track numbers are site-specific; scoping by wh_id is universal |
| 3 | **Area filter** | `arecod LIKE 'RSD%'` | `arecod IN ('DOCK','SHIP')` | Shipping dock area codes differ per site (discovered via probe) |
| 4 | **Trailer status** | `trlr_stat IN ('O','LDG')` | Adaptive: includes all non-closed statuses discovered by probe (e.g. `'O','CI','EX','OR'`) | Athens has no 'LDG' or 'R' status — code probes available statuses and includes all except closed (`C, D, SUSP`) |
| 5 | **Yard_loc filter** | `right(left(Yard_loc,6),1) != 'V'` | Removed | Site-specific to Crailsheim racking layout |
| 6 | **User_ID logic** | `trlr_stat = 'LDG'` | Adaptive: uses `'LDG'` if available, else `'R'`, else falls back to `'LDG'` (won't match → empty user, which is correct when no active loading status exists) | Only assigns user when trailer is actively loading |
| 7 | **trlr join** | `car_move.trlr_id = trlr.trlr_id` (no wh_id) | Same (NO `trlr.wh_id`) | Athens trlr synonym has no `wh_id` column |
| 8 | **locmst join** | No wh_id condition | `car_move.wh_id = locmst.wh_id` | Prevents cross-warehouse location matches |
| 9 | **ord join** | No wh_id condition | `car_move.wh_id = ord.wh_id` | Same warehouse scoping |
| 10 | **ord_line join** | `ordnum` only | `ordnum + wh_id + client_id` | 2022 composite key; prevents cross-client matches |
| 11 | **early_shpdte** | Unqualified `early_shpdte` | `ord_line.EARLY_SHPDTE` | Column exists on `ord_line` and `shipment`, not `car_move` — must qualify |
| 12 | **LiveDrop alias** | `'LiveDrop'` (quoted) | `LiveDrop` (unquoted) | SQL standard; quoted aliases break in some CTEs |
| 13 | **CP_CHECK** | `SUM(((ORDQTY/UNTQTY)*UNTQTY - ORDQTY))` | Added `ISNULL(UNTQTY,0)=0` guard | Prevents divide-by-zero on items without PL footprint |
| 14 | **prtftp joins** | `prtnum` only | `prtnum + prt_client_id` | 2022 composite key for footprint tables |
| 15 | **LoadingProgress** | `JOIN [pbiadhoc].[LoadingProgress]` | Derived `PALLET_COUNTS` CTE from `pckwrk_view` (pick-work records) joined to `ord` | `pbiadhoc.LoadingProgress` is a VIEW at Crailsheim (4 cols, 710 rows) — definition inaccessible. Does NOT exist at Athens. Investigation found `pckwrk_view` COUNT gives 78.3% accuracy vs LoadingProgress (far better than `ord_line + prtftp_dtl` approach at 7.7%). `pcksts IN ('C','P')` = loaded pallets. |
| 16 | **shipment alias** | `prodwms.shipment` (unaliased) | `shp` alias | Avoid ambiguity with `Shipment` column name |

#### 3.7.4 Output Column Mapping with NULL/Empty Classification

| # | Column | 2014 Source (Native) | 2022 Source (Native) | Data Type | NULL/Empty Classification |
|---|--------|---------------------|---------------------|-----------|--------------------------|
| 1 | `Shipment` | `car_move.car_move_id` + `ord.stcust` | Same tables, same logic | varchar | **ACTUAL DATA** — always populated for active car_moves |
| 2 | `DOOR` | `right(trlr.Yard_loc, 3)` | Same derivation | varchar | **ACTUAL DATA** — physical door number; empty if trailer has no yard_loc |
| 3 | `Avis` | `early_shpdte` (unqualified → resolves to `ord_line`) | `ord_line.EARLY_SHPDTE` (explicitly qualified) | datetime | **ACTUAL NULL** — NULL means no planned ship date is set for this order line |
| 4 | `Ankunft` | `trlr.arrdte` | Same | datetime | **ACTUAL NULL** — NULL means arrival time not recorded |
| 5 | `LiveDrop` | `trlr.live_load_flg` → 'L' or 'D' | Same logic | char(1) | **ACTUAL DATA** — always 'L' or 'D', never NULL (derived from flag) |
| 6 | `Login_id_neu` | `LES_USR_ATH.Login_id` (via `mod_usr_id` when `trlr_stat='LDG'`) | Same logic (via `USR_ID` when `trlr_stat='R'`) | varchar | **ACTUAL EMPTY** — empty string `''` when trailer not in loading status, or when user has no login mapping. Never NULL. |
| 7 | `CP` | `SUM(ORDQTY/UNTQTY*UNTQTY - ORDQTY) != 0 → 'CP'` | Same with div-by-zero guard | varchar | **ACTUAL EMPTY** — `''` means no case pick needed; `'CP'` means fractional pallet detected |
| 8 | `Gesamt` | `[pbiadhoc].[LoadingProgress].NoPallets_Geplant` | **Derived:** `COUNT(*)` from `pckwrk_view` joined to `ord` (all pick records for the car_move) | int | At 2014: **ACTUAL DATA** (from custom VIEW). At 2022: **DERIVED DATA** from `pckwrk_view` pick records — 78.3% accuracy vs LoadingProgress. `0` via `COALESCE` when no picks exist. |
| 9 | `Loaded` | `[pbiadhoc].[LoadingProgress].NoPallets_Loaded` | **Derived:** `SUM(CASE WHEN pcksts IN ('C','P') THEN 1 ELSE 0 END)` from `pckwrk_view` | int | At 2014: **ACTUAL DATA**. At 2022: **DERIVED DATA** — counts picks with completed/picked status. 80.4% accuracy vs LoadingProgress. `0` via `COALESCE` when no qualifying picks exist. |
| 10 | `Refresh` | `Format(DATEADD(HOUR,2,GETUTCDATE()),'HH:mm')` | Same | varchar | **ACTUAL DATA** — always populated (system time) |
| 11 | `StagedYesNo` | `shipment.shpsts = 'I' → 'NOT_STAGED'` | Same logic with `shp` alias | varchar | **ACTUAL DATA** — 'OK' or 'NOT_STAGED', never NULL |

#### 3.7.5 Site-Specific Differences Discovered by Probe

| Feature | Crailsheim (2014) | Athens (2022) | Impact |
|---------|-------------------|---------------|--------|
| Shipping dock areas | `RSDK01B1, RSDK03B1, RSDKAGVS1B, RSDKAGVS2B, SHIP, XDOCK-A, XDOCK-B` | `DOCK, SHIP` | Area filter must be site-specific |
| Trailer statuses | `C, CI, D, EX, LDG, O, OR, SUSP` | `CI, D, EX, O, OR` (no LDG, no R) | No direct LDG equivalent — code includes all non-closed statuses (`O, CI, EX, OR`) |
| `trlr.wh_id` column | Exists | **Does NOT exist** | Cannot use `trlr.wh_id` in joins; use `car_move.wh_id` instead |
| `pbiadhoc.LoadingProgress` | Exists (custom BI VIEW — 4 cols, 710 rows, definition inaccessible) | **Does NOT exist** | Must derive pallet counts from `pckwrk_view` instead |
| `pckwrk_view` | Exists (209 cols) — key cols: `ordnum, prtnum, pcksts, wh_id` | Exists (223 cols) — same key cols | Used for PALLET_COUNTS CTE derivation. `pcksts` values: P, H, C, W, R. Loaded = `pcksts IN ('C','P')` |
| `LES_USR_ATH` | Exists | Exists (42 columns) | Login_id mapping works at both sites |
| `shipment_line` | Exists | Exists | Enables loaded-pallet derivation |

---

## 4. Knowledge Base (KB)

The KB is the remediation engine's memory → all verified mappings, learnings, and unresolved questions accumulated across sites.

### 4.1 `verified-mappings.json` → Master Mapping Table

**Contents:** 52 tables, 64 columns, 9 join paths → all verified against live schema or expert review.

```
Structure:
├── tables:   { RTCIS_TABLE →{ prime_table, confidence, evidence, sources[] } }
├── columns:  { RTCIS_TABLE.COL →{ prime_table, prime_column, confidence, ... } }
└── joins:    { join_path_name →{ tables[], on_clauses[], verified } }
```

**Key Table Mappings:**
```
RTCIS          → PrIME           Notes
ORDDTL         → ord_line         Order detail
ORDHDR         → ord              Order header
TRUKIO         → trlr             Trailer (NOT trlract)
SYSTRN/SYSDTL  → dlytrn           Daily transaction (denormalized)
LOCATN         → locmst           Location master
ITEM_CONFIG    → prtmst           Item master
```

### 4.2 `remediation-learnings.json` → Accumulated Expertise

Captures discoveries from each remediation run. Each learning has:
- **Category:** `column_mapping`, `join_pattern`, `filter_logic`, `data_anomaly`
- **Implementation type:** `COLUMN_MAP` | `TABLE_MAP` | `apply_learnings` | `informational`
- **Status:** `active` | `superseded`

Example: *"SYSDTL.ITMCLS maps to prtmst.typcod, NOT prt_class_name (which is empty at Athens)"*

### 4.3 `prime-datamodel.json` → Complete Data Model
- **1,661 tables**, **22,867 fields** → full PrIME 2022 schema
- Used in Tier 2 lookup when KB has no mapping

### 4.4 `erd-index.json` →81 ER Diagrams
- Indexed by table, column, domain
- Used to discover join paths between tables

### 4.5 `open-questions.json` → Unresolved Issues
- Priority P1 (blocking) / P2 (non-blocking)
- Tracked until DBA/expert resolution

---

## 5. Agent Flow → 7-Phase Remediation Workflow

```
┌────────────────────────────────────────────────────────────────┐
│  Phase 0: Load KB + learnings + open questions                │
│  ↓                                                           │
│  Phase 1: Parse SQL → extract tables, columns, joins, filters│
│  ↓                                                           │
│  Phase 2: Smart 3-Tier Lookup (KB → Data Model → Schema)     │
│  ↓                                                           │
│  Phase 3: Confidence Gate (GO / WARN / BLOCK per mapping)     │
│  ↓                                                           │
│  Phase 4: Remediate SQL using verified mappings               │
│  ↓                                                           │
│  Phase 5: Live Validation on test instance                    │
│  ↓                                                           │
│  Phase 6: Generate HTML report (tabbed, per-query)            │
│  ↓                                                           │
│  Phase 7: Capture learnings → update KB for next run          │
└────────────────────────────────────────────────────────────────┘
```

### Phase 0 → Load KB
- Load `verified-mappings.json` (52 tables, 64 columns)
- Load `remediation-learnings.json` (accumulated discoveries)
- Check `open-questions.json` for P1-blocking issues

### Phase 1 → Parse SQL
- Extract RTCIS/PrIME 2014 table references from `FROM` / `JOIN` clauses
- Identify column usage with table qualifiers
- Handle query tool artifacts (e.g., Excel `[prodwms CNTHST.CNTDTE]`)
- Supports batch input: CSV, JSON, Excel, or direct SQL

### Phase 2 → Smart 3-Tier Lookup
*(See Section 5 for detail)*

### Phase 3 → Confidence Gate
Each mapping gets a confidence assessment:

| Gate | Criteria | Action |
|------|----------|--------|
| **GO** | All mappings HIGH confidence | Direct remediation, no flags |
| **WARN** | Some MED/LOW confidence | Remediate with ⚠️ flags for review |
| **BLOCK** | Critical structural issues (missing join, unknown table) | Alternative query provided; manual DBA resolution |

### Phase 4 → Remediate SQL
- Apply table/column mappings
- Rewrite schema prefix (`prodwms.` →`dbo.`)
- Remove 2014-specific filters (`cntflg = 1`)
- Add 2022 patterns (COALESCE descriptions, `untinp` →`untlay`)
- Rewrite multi-hop joins where needed

### Phase 5 → Live Validation
- Execute translated SQL on a **test instance** (e.g., Athens Replica, or site's `_REPLICA` database)
- Returns: row count, execution time, errors
- **Auto-fix loop:** If execution fails, analyze error → adjust → re-validate (up to 3 attempts)

### Phase 6 → Generate HTML Report
*(See Section 10 for output format)*

### Phase 7 → Learning Capture
- New mappings → append to `verified-mappings.json`
- Discoveries → append to `remediation-learnings.json`
- Unresolved → append to `open-questions.json`
- **Cross-site promotion:** When → sites confirm the same mapping, it's promoted to global baseline

---

## 6. 3-Tier Lookup & Iteration Method

### 6.1 Three-Tier Lookup Order

```
Tier 1: Knowledge Base (verified-mappings.json)
  ─ Highest confidence. Contains expert-verified, live-validated mappings.
  ─ If found here with HIGH confidence → use directly.
  ─ if not found ↓

Tier 2: Data Model (prime-datamodel.json — 1,661 tables, 22,867 fields)
  ─ Search by column name, predecessor name, or description match.
  ─ Tool: Lookup-DataModel.ps1 with -Predecessor flag.
  ─ if still uncertain ↓

Tier 3: Live Schema Verification (Verify-SchemaMapping.ps1)
  ─ Query INFORMATION_SCHEMA on target database.
  ─ Definitive: if column exists, it exists. Zero false negatives.
  ─ Also detects missing join keys, structural issues.
```

### 6.2 Source Weighting System

```
S1_SCHEMA        = 100   # Live DB column list — definitive
S2_ERD           =  95   # Official ER diagram — structural truth
S3_EXPERT        =  90   # DBA / expert confirmation
S4_DATAMODEL     =  80   # Data model documentation

V1_LIVE_QUERY    = 100   # Actually executed on DB
V2_ACCUMULATED   =  85   # Past learnings from verified KB
V3_EXPERT_REVIEW =  90   # Expert-reviewed prior output

UNKNOWN          =  20   # No known source
```

**Confidence = MAX(source weights for all evidence supporting the mapping)**

### 6.3 Iterative Refinement

The remediation process is iterative — each run improves the KB:

```
Run 1: Translate queries → 14/20 pass, 6 fail
  └─ Analyze failures → capture learnings → update KB

Run 2: Same queries with updated KB → 18/20 pass, 2 fail
  └─ DBA resolves open questions → update KB

Run 3: All 20 pass → promote to READY
  └─ New site inherits improved KB → fewer failures on Run 1
```

---

## 7. Site Configuration & Schema Discovery

### 7.1 Configurable Site Parameters

Each site is defined by 4 parameters:

```python
SITE_NAME = '{SITE}'                                     # e.g., 'CRAILSHEIM'
SERVER    = '<replica-host>'
DATABASE  = '{DATABASE}'                                  # e.g., 'CRAILSHEIM'
UID       = '<user>@<company>'                               # Azure AD user
```

### 7.2 Automatic Schema Probe

Before translating, the validation script **automatically discovers** each site's characteristics:

| Probe | What It Detects | Why It Matters |
|-------|-----------------|----------------|
| Schemas present | `prodwms` vs `dbo` | Determines schema prefix |
| `aremst.cntflg` | EXISTS vs NOT FOUND | 2014 has it; 2022 doesn't |
| Zone tables | `sto_zone`, `mov_zone`, `pck_zone`, `loc_typ`, `pck_mthd` | Present only in full 2022 |
| `inventory_view` | EXISTS vs NOT FOUND | 2014 uses view; 2022 uses base tables |
| Table case | UPPER vs lower | Some sites store tables as UPPERCASE in `INFORMATION_SCHEMA` |
| `wh_id` values | Site warehouse identifier | e.g., `DE29` for Crailsheim, `ES06` for Jijona |
| ASRS areas | `aremst` areas containing "ASRS" | Identifies automated storage |

### 7.3 Version Detection Logic

```
IF has_cntflg AND NOT has_zone_tables → PrIME 2014
IF NOT has_cntflg AND has_zone_tables → PrIME 2022
IF NOT has_cntflg AND NOT has_zone_tables → Hybrid (transitioning)
IF has_cntflg AND has_zone_tables →2014 with zone extensions
```

### 7.4 Hybrid Sites

Many sites are in a **hybrid** state →`prodwms` schema with 2014-era table structures, but `cntflg` already removed and `inventory_view` still present. Queries must adapt:
- Use `prodwms.` prefix (not `dbo.`)
- Remove `cntflg` filters
- Use `inventory_view` if available, fall back to base tables if not
- Use COALESCE for description lookups (handles both 2014 and 2022 key patterns)

---

## 8. Batch Remediation of Multiple Queries

### 8.1 Input Formats

The translator accepts queries from multiple sources:

| Format | Source | Example |
|--------|--------|---------|
| **Excel** (`.xlsx`) | Export from QuickView/NEMC | `allqueries.xlsx` (~99+ queries) |
| **CSV** | Comma-separated with `query_id` + `sql` columns | Manual extraction |
| **JSON** | Array of `{id, name, sql, category}` | Programmatic input |
| **SQL files** | One query per `.sql` file in a folder | Direct SQL |

### 8.2 Batch Configuration

To translate a batch of queries for any site, prepare a JSON config file:

```json
{
  "site": "{SITE_NAME}",
  "server": "<replica-host>",
  "database": "{DATABASE}",
  "source_version": "2014",
  "target_version": "2022",
  "source_schema": "prodwms",
  "target_schema": "dbo",
  "queries": [
    {
      "id": "Q01",
      "name": "Inventory by Area",
      "category": "Inventory",
      "sql": "SELECT ... FROM prodwms.inventory_view ..."
    },
    {
      "id": "Q02",
      "name": "IRA Cycle Count",
      "category": "Cycle Count",
      "sql": "SELECT ... FROM prodwms.cnthst ..."
    }
  ],
  "reference_site": {
    "name": "ATHENS",
    "server": "<replica-host>",
    "database": "ATHENS_REPLICA",
    "schema": "dbo",
    "version": "2022"
  }
}
```

### 8.3 Bulk Query Extraction from Excel

Use `_extract_all_queries.py` to extract all queries from site Excel workbooks:

```python
# Extracts SQL from allqueries.xlsx into JSON format
python _extract_all_queries.py --input "Sample Data RTCIS PRIME/PRIME 2014-2022/allqueries.xlsx" --output queries_batch.json
```

### 8.4 Remediation Rules Applied per Query

For each query in the batch, the translator applies these rules in order:

| # | Rule | Example |
|---|------|---------|
| 1 | Schema prefix replacement | `prodwms.cnthst` →`dbo.cnthst` |
| 2 | Remove `cntflg` filters | `AND ar.cntflg = 1` → removed |
| 3 | `untinp` →`untlay` | Column rename in prtftp_view |
| 4 | `inventory_view` → base tables | Single view →3-table JOIN |
| 5 | COALESCE descriptions | Area/zone description lookups |
| 6 | `uc_custom_parameters` →`poldat` | Config table replacement |
| 7 | `HAVING` without aggregate →`WHERE` | SQL standard compliance |
| 8 | Division safety wrappers | `CASE WHEN ISNULL(divisor,0)=0 ...` |
| 9 | ITMCLS value mapping | `'F'` →`'FERT'`, `'P'` →`'ROH'/'HALB'` |

---

## 9. Database Validation → Live Execution

### 9.1 Validation Strategy

Every translated query is validated by **live execution** on a test instance. The process:

```
1. Execute original 2014 query on source site → get row count + sample
2. Execute translated 2022 query on target site → get row count + sample
3. Compare: row count, column names, sample data
4. If error: analyze → auto-fix → retry (up to 3 times)
5. Record result: PASS / FAIL / WARN
```

### 9.2 Multi-Scenario Test Suite

The validation script (`_validate_site.py`) runs representative tests across **all WMS domains** to verify remediation patterns work on each site:

| Test ID | Domain | What It Validates |
|---------|--------|-------------------|
| INV-01 | Inventory | `inventory_view` → base table remediation |
| INV-02 | Inventory | Direct `invlod+invsub+invdtl` join |
| AREA-01 | Area/Zone | COALESCE description pattern |
| CC-01 | Cycle Count (IRA) | `cntflg` filter removal, IRA accuracy calculation |
| ITEM-01 | Item Master | `prtftp_view` join, `untinp→untlay` adaptation |
| SHIP-01 | Shipping | `shipment + shipment_line` (unchanged structure) |
| WO-01 | Production | `wkohdr` work orders (unchanged) |
| POL-01 | Policy | `poldat` configuration queries |
| LOC-01 | Location | `locmst` with area/useflg filters |
| DSC-01 | Descriptions | `dscmst` lookup patterns |
| PLANT-01 | Configuration | Plant code discovery from `poldat` |

### 9.3 IRA (Inventory Record Accuracy) → Full Validation

IRA is the highest-priority report. The validation includes a **full IRA run** with:
- Step 1: Build `#InvLookup` temp table from `invlod+invsub+invdtl+locmst+prtmst+poldat`
- Step 2: Join `cnthst` with lookup, apply filters, compute accuracy
- Output: Per-area type accuracy breakdown (FUPA, MIXE, PAPA, HOFF, etc.)

---

## 10. Two-Phase Comparison Approach (Go-Live Strategy)

For sites transitioning from 2014 →2022 (e.g., Crailsheim, next sites), validation happens in **two phases**:

### Phase 1: Pre-Go-Live → Compare with Reference 2022 Site

**When:** Before the site upgrades to 2022.

```
┌──────────────────────┐       ┌──────────────────────┐
│ {SITE} (2014)       │ vs    │ Reference Site      │
│ e.g., Crailsheim    │       │ e.g., Athens (2022) │
│ prodwms schema      │       │ dbo schema          │
│ Has cntflg (maybe)  │       │ No cntflg           │
│ Has inventory_view  │       │ Has zone tables     │
└──────────────────────┘       └──────────────────────┘
```

**Purpose:**
- Validate that remediated SQL **syntax** and **structure** are correct
- Confirm column mappings produce real data on a known-good 2022 instance
- Cannot compare **data equivalence** (different sites have different data)
- Focus: structural validation, confidence confidence, zero-error execution

**Configuration:**
```python
# _parallel_compare.py → SITES list
SITES = [
    # Phase 1: Run 2014 queries on Crailsheim, 2022 queries on Athens
    ('{SITE}',     '<replica-host>',     '{DATABASE}',       'prodwms', '2014', True),
    ('ATHENS',     '<replica-host>...',      'ATHENS_REPLICA',   'dbo',     '2022', False),
]
```

### Phase 2: Post-Go-Live → Compare Site's Own 2014 vs 2022

**When:** After the site upgrades to 2022. Run both old and new queries on the **same site**.

```
┌──────────────────────┐       ┌──────────────────────┐
│ {SITE} (2014 query) │ vs    │ {SITE} (2022 query) │
│ Original SQL        │       │ Translated SQL       │
│ prodwms schema      │       │ dbo schema (or same) │
│ With cntflg filter  │       │ Without cntflg       │
└──────────────────────┘       └──────────────────────┘
```

**Purpose:**
- Validate **data equivalence** → same row counts, same business meaning
- Catch remediation errors that produce different data on the same dataset
- Row count mismatches are expected for `cntflg`-filtered queries (2022 returns more rows because all areas are countable)

**⚠️ Go-Live Data Sparsity Warning:**
In the first few weeks after go-live, the upgraded site may have **limited historical data** in certain tables (e.g., `cnthst` cycle counts, `dlytrn` daily transactions). This is normal → transactional history accumulates over time. Expect:
- Cycle count (IRA) rows: sparse for first 1-2 weeks
- Daily transaction history: builds up over 30-90 days
- Configuration tables (`poldat`, `aremst`, `locmst`, `prtmst`): available immediately
- Inventory snapshots (`invlod/invsub/invdtl`): available immediately

**Recommendation:** Run Phase 2 comparison at **1 week**, **1 month**, and **3 months** post-go-live.

---

## 11. Output Format

### 11.1 HTML Report (Per Query Remediation)

Each remediation generates a **single-page HTML report** with 12 sections:

| # | Section | Content |
|---|---------|---------|
| 1 | **Business Context Analysis** | Query purpose, business workflow, what the dashboard shows |
| 2 | **Remediation Changes** | Plain-English list of every change (schema, filters, joins, statuses, custom objects) |
| 3 | **Original SQL (PrIME 2014)** | Formatted source SQL with **Copy to Clipboard** button |
| 4 | **Remediated SQL (PrIME 2022)** | Remediated SQL with inline comments + **Copy to Clipboard** button |
| 5 | **Execution Summary** | 2014 vs 2022 side-by-side: PASS/FAIL badge, row count, column count |
| 6 | **Column Comparison** | Native column names + data types, with row-by-row match/mapped/missing classification |
| 7 | **Output Column Detail** | 7-column table: column name, meaning, 2014 native source (`table.column`), 2022 native source, transformation applied, NULL/empty classification |
| 8 | **Site-Specific Differences** | Probe-discovered structural differences (shipping areas, trailer statuses, missing tables/columns, custom objects) |
| 9 | **Data Output — 2014 Site** | Actual rows from original query execution with data type annotations |
| 10 | **Data Output — 2022 Site** | Actual rows from remediated query execution |
| 11 | **Schema Probe Results** | Per-table EXISTS/MISSING with column counts for both sites |
| 12 | **Knowledge Captured** | Learnings from this remediation iteration |

**Confidence Badges:**
- `PASS` → Query executed successfully, returned data
- `FAIL` → Query failed or returned zero rows unexpectedly

**NULL/Empty Classifications (in Section 5):**
- `ACTUAL DATA` — Column always has a real value
- `ACTUAL NULL` — NULL is meaningful (e.g., "no planned date set")
- `ACTUAL EMPTY` — Empty string `''` is meaningful (e.g., "not in loading status")
- `DERIVED DATA` — Value computed from native tables (replacing a missing custom object)
- `PLACEHOLDER NULL` — NULL because source data is unavailable (known limitation)

### 11.2 HTML Report Template (Copy-Paste Reference)

Below is the full HTML template used by `_loading_dock_remediation.py` to generate the 12-section report. This serves as a reference for building new remediation report generators.

**Key design features:**
- Single-page self-contained HTML (no external CSS/JS dependencies)
- Copy-to-clipboard buttons on SQL sections (uses `navigator.clipboard`)
- Responsive grid layout for execution summary
- Color-coded column comparison (green=exact, yellow=mapped, red=missing)
- Confidence badges (`PASS`/`FAIL`) with semantic colors

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PrIME 2014 → 2022 Remediation: {QUERY_NAME}</title>
<style>
  body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 20px; background: #f5f5f5; color: #333; }
  h1 { color: #1a5276; border-bottom: 3px solid #2980b9; padding-bottom: 10px; }
  h2 { color: #2c3e50; margin-top: 30px; border-left: 4px solid #2980b9; padding-left: 10px; }
  h3 { color: #34495e; }
  .card { background: white; border-radius: 8px; padding: 20px; margin: 15px 0;
          box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
           font-size: 0.85em; font-weight: bold; }
  .badge-pass { background: #27ae60; color: white; }
  .badge-fail { background: #e74c3c; color: white; }
  .badge-warn { background: #f39c12; color: white; }
  .badge-info { background: #3498db; color: white; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; }
  th { background: #2c3e50; color: white; padding: 10px 8px; text-align: left; font-size: 0.9em; }
  td { padding: 8px; border-bottom: 1px solid #ddd; font-size: 0.85em; }
  tr:hover { background: #ecf0f1; }
  .data-table th { background: #34495e; }
  .compare-table .match td { background: #eafaf1; }
  .compare-table .mapped td { background: #fef9e7; }
  .compare-table .missing td { background: #fdedec; }
  .null { color: #95a5a6; font-style: italic; }
  .null-val { color: #95a5a6; font-style: italic; }
  .error { background: #fdedec; border-left: 4px solid #e74c3c; padding: 12px; margin: 10px 0; }
  .warn { background: #fef9e7; border-left: 4px solid #f39c12; padding: 12px; margin: 10px 0; }
  .info { background: #eaf2f8; border-left: 4px solid #3498db; padding: 12px; margin: 10px 0; }
  .success { background: #eafaf1; border-left: 4px solid #27ae60; padding: 12px; margin: 10px 0; }
  pre { background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px;
        overflow-x: auto; font-size: 0.85em; line-height: 1.5; white-space: pre-wrap;
        position: relative; }
  .row-count { color: #7f8c8d; font-size: 0.9em; }
  .dtype { color: #95a5a6; font-weight: normal; }
  .semantic-table td:first-child { font-weight: bold; white-space: nowrap; }
  .note { font-size: 0.9em; color: #666; margin: 5px 0; }
  .summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
  .sql-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
  .sql-grid .card { margin: 0; }
  .sql-grid pre { max-height: 600px; overflow-y: auto; font-size: 0.8em; }
  @media (max-width: 1200px) { .sql-grid { grid-template-columns: 1fr; } }
  @media (max-width: 900px) { .summary-grid { grid-template-columns: 1fr; } }
  .meta { color: #7f8c8d; font-size: 0.85em; }
  .changes-list { list-style: none; padding: 0; }
  .changes-list li { padding: 5px 0; border-bottom: 1px solid #eee; }
  .changes-list li:before { content: "→ "; color: #2980b9; font-weight: bold; }
  /* Copy-to-clipboard button */
  .sql-container { position: relative; }
  .copy-btn { position: absolute; top: 8px; right: 8px; background: #3498db; color: white;
    border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer;
    font-size: 0.8em; z-index: 10; transition: background 0.2s; }
  .copy-btn:hover { background: #2980b9; }
  .copy-btn.copied { background: #27ae60; }
</style>
<script>
function copySQL(btnId, preId) {
    var text = document.getElementById(preId).innerText;
    navigator.clipboard.writeText(text).then(function() {
        var btn = document.getElementById(btnId);
        btn.textContent = '✓ Copied!';
        btn.classList.add('copied');
        setTimeout(function() {
            btn.textContent = '📋 Copy SQL';
            btn.classList.remove('copied');
        }, 2000);
    });
}
</script>
</head>
<body>

<h1>PrIME 2014 → 2022 SQL Remediation Report</h1>
<p class="meta">Generated: {TIMESTAMP} | Query: {QUERY_NAME}</p>

<!-- Section 1: Business Context -->
<div class="card">
<h2>1. Business Context Analysis (Rule 1)</h2>
<p><strong>Query Purpose:</strong> {BUSINESS_DESCRIPTION}</p>
<p><strong>Business Workflow:</strong> {WORKFLOW_PATH}</p>
</div>

<!-- Section 2: Remediation Changes -->
<div class="card">
<h2>2. Remediation Changes (What Changed & Why)</h2>
<ul class="changes-list">
  <li>{CHANGE_1}</li>
  <li>{CHANGE_2}</li>
  <!-- ... one <li> per remediation note -->
</ul>
</div>

<!-- Sections 3-4: Side-by-side SQL comparison (Rule 7: original preserved verbatim) -->
<div class="sql-grid">
<div class="card">
<h2>3. Original SQL (PrIME 2014)</h2>
<div class="sql-container">
  <button class="copy-btn" id="copyBtn1" onclick="copySQL('copyBtn1','sql2014')">📋 Copy SQL</button>
  <pre id="sql2014">{ORIGINAL_SQL_ESCAPED}</pre>
</div>
</div>

<div class="card">
<h2>4. Remediated SQL (PrIME 2022)</h2>
<div class="sql-container">
  <button class="copy-btn" id="copyBtn2" onclick="copySQL('copyBtn2','sql2022')">📋 Copy SQL</button>
  <pre id="sql2022">{REMEDIATED_SQL_ESCAPED}</pre>
</div>
</div>
</div>

<!-- Section 5: Execution Summary (side-by-side grid) -->
<div class="card">
<h2>5. Execution Summary</h2>
<div class="summary-grid">
  <div>
    <h3>{SITE_2014_NAME} (PrIME 2014)</h3>
    <p>Status: <span class="badge badge-pass">PASS</span></p>
    <p>Rows: <strong>{ROW_COUNT_2014}</strong></p>
    <p>Columns: <strong>{COL_COUNT_2014}</strong></p>
  </div>
  <div>
    <h3>{SITE_2022_NAME} (PrIME 2022)</h3>
    <p>Status: <span class="badge badge-pass">PASS</span></p>
    <p>Rows: <strong>{ROW_COUNT_2022}</strong></p>
    <p>Columns: <strong>{COL_COUNT_2022}</strong></p>
  </div>
</div>
</div>

<!-- Section 6: Column Comparison -->
<div class="card">
<h2>6. Column Comparison (Native Columns & Data Types)</h2>
<table class="compare-table">
<thead><tr><th>#</th><th>2014 Column</th><th>2014 Type</th>
  <th>2022 Column</th><th>2022 Type</th><th>Semantic Match</th></tr></thead>
<tbody>
  <tr class="match"><td>1</td><td>Shipment</td><td>str</td>
    <td>Shipment</td><td>str</td><td>✓ Exact</td></tr>
  <!-- ... one row per column -->
</tbody>
</table>
</div>

<!-- Section 7: Output Column Detail (7-column table) -->
<div class="card">
<h2>7. Output Column Detail: Native Source, Transformation & NULL/Empty Classification</h2>
<table class="semantic-table">
<thead><tr><th>#</th><th>Column</th><th>Meaning</th><th>2014 Native Source</th>
  <th>2022 Native Source</th><th>Transformation</th><th>NULL/Empty Classification</th></tr></thead>
<tbody>
  <tr><td>1</td><td><strong>Shipment</strong></td><td>Carrier move ID</td>
    <td><code>car_move.car_move_id</code></td><td><code>car_move.car_move_id</code></td>
    <td>Schema prefix changed</td><td>ACTUAL DATA</td></tr>
  <!-- ... one row per output column -->
</tbody>
</table>
</div>

<!-- Section 8: Site Differences -->
<div class="card">
<h2>8. Site-Specific Differences (Discovered by Probe)</h2>
<table>
<thead><tr><th>Feature</th><th>{SITE_2014}</th><th>{SITE_2022}</th><th>Remediation Impact</th></tr></thead>
<tbody>
  <tr><td><strong>Shipping dock areas</strong></td><td>{AREAS_2014}</td>
    <td>{AREAS_2022}</td><td>Area filter must be site-specific</td></tr>
  <!-- ... one row per difference -->
</tbody>
</table>
</div>

<!-- Sections 9-10: Data Output tables (generated by make_data_table()) -->
<div class="card">
<h2>9. Data Output — {SITE_2014} (PrIME 2014, Original SQL)</h2>
<table class="data-table"><!-- header + data rows --></table>
<p class="row-count">Total rows: <strong>{N}</strong></p>
</div>

<div class="card">
<h2>10. Data Output — {SITE_2022} (PrIME 2022, Remediated SQL)</h2>
<table class="data-table"><!-- header + data rows --></table>
</div>

<!-- Section 11: Schema Probe Results -->
<div class="card">
<h2>11. Schema Probe Results</h2>
<h3>{SITE_2014} (2014)</h3>
<table>
<thead><tr><th>Table</th><th>Status</th><th>Columns</th></tr></thead>
<tbody>
  <tr><td>car_move</td><td><span class="badge badge-pass">✓ EXISTS</span></td><td>42</td></tr>
  <!-- ... one row per probed table -->
</tbody>
</table>
<h3>{SITE_2022} (2022)</h3>
<table><!-- same structure --></table>
</div>

<!-- Section 12: Knowledge Captured -->
<div class="card">
<h2>12. Knowledge Captured (Rule 3)</h2>
<div class="info">
<p>Learnings from this remediation iteration:</p>
<ul>
  <li>{LEARNING_1}</li>
  <li>{LEARNING_2}</li>
</ul>
</div>
</div>

</body>
</html>
```

**Placeholders** (replace in Python with `html.escape()` for all user-facing values):
- `{QUERY_NAME}` — e.g. "Loading Dock Shipment Progress Dashboard"
- `{TIMESTAMP}` — generation time
- `{ORIGINAL_SQL_ESCAPED}` / `{REMEDIATED_SQL_ESCAPED}` — HTML-escaped SQL
- `{SITE_2014}` / `{SITE_2022}` — site names (e.g. "Crailsheim", "Athens")
- `{ROW_COUNT_*}` / `{COL_COUNT_*}` — query result statistics
- `{CHANGE_N}` — remediation notes (one per `<li>`)

### 11.3 JSON Output (Machine-Readable)

Each validation run also outputs a JSON file for programmatic consumption:

```json
{
  "site": "CRAILSHEIM",
  "server": "<replica-host>",
  "database": "CRAILSHEIM",
  "info": {
    "version": "PrIME 2014→022 Hybrid",
    "working_schema": "prodwms",
    "has_cntflg": false,
    "has_zone_tables": false,
    "wh_ids": ["DE29"],
    "area_count": 176,
    "asrs_areas": [["ASRS1B1","DE29"], ...]
  },
  "test_summary": {
    "INV-01: Inventory by Area (view)": {"status": "PASS", "rows": 20, "time": 0.79},
    "CC-01: IRA Cycle Count Accuracy":  {"status": "PASS", "rows": 30, "time": 0.34}
  },
  "ira": {"status": "PASS", "rows": 2532}
}
```

---

## 12. Batch Validation Script

### 12.1 `_validate_site.py` → Multi-Site, Multi-Scenario Validator

This is the main validation script. It runs on any PrIME site by changing **3 lines** at the top:

```python
# ============================================================================
# SITE CONFIG → Change these for each site
# ============================================================================
SITE_NAME = 'CRAILSHEIM'                                           # <-- Change
SERVER    = '<replica-host>' # <-- Change
DATABASE  = 'CRAILSHEIM'                                            # <-- Change
UID       = '<user>@<company>'                                      # <-- Your AD user
```

**What it does (single connection, 3 phases):**

```
Phase 1: Schema Probe
  ─ Discovers schema, version, capabilities, table case, areas, ASRS, cycle count volume

Phase 2: Representative Query Tests (11 tests across all WMS domains)
  ─ Adapts queries to discovered schema/case automatically
  ─ Reports PASS/FAIL/row count/timing for each

Phase 3: Full IRA Run
  ─ 2-step temp-table approach (handles read-replica plan cache issues)
  ─ 7-day IRA summary by area type with percentage accuracy
  ─ Identifies ASRS areas in results
```

**Run:**
```bash
python _validate_site.py
# Output: console summary + JSON file at SQL_Translations/_{site}_validation.json
```

### 12.2 `_parallel_compare.py` → Multi-Site Parallel Comparison

For comparing multiple sites simultaneously (Phase 1 or Phase 2):

```python
# Configure sites in the SITES list:
SITES = [
    # (name, server, database, schema, version, has_cntflg)
    ('CRAILSHEIM', '<replica-host>...', 'CRAILSHEIM',     'prodwms', '2014', False),
    ('ATHENS',     '<replica-host>...',     'ATHENS_REPLICA',  'dbo',     '2022', False),
    # Add more sites as needed:
    # ('XIQING',   '<replica-host>...',     'XIQING',          'prodwms', '2014', True),
    # ('CAIRO',    '<replica-host>...',      'CAIRO',           'prodwms', '2014', True),
]
```

**What it does:**
- Runs IRA queries on all sites in **parallel** using `ThreadPoolExecutor`
- Each site gets both `inventory_view` query AND `base table` (2-step) query
- Generates an HTML comparison report with side-by-side results
- Supports both 2014 (`prodwms`, `cntflg=1`) and 2022 (`dbo`, no `cntflg`)

### 12.3 Running a Batch for a New Site

**Step-by-step for any new site:**

```bash
# 1. Probe and validate (edit SITE_NAME, SERVER, DATABASE in _validate_site.py)
python _validate_site.py

# 2. Check JSON output
cat SQL_Translations/_{site}_validation.json

# 3. For Phase 1 comparison (pre-go-live): add site + Athens to _parallel_compare.py SITES
python _parallel_compare.py

# 4. For Phase 2 comparison (post-go-live): run same site with 2014 and 2022 queries
# Modify SITES list to have the same site twice with different version configs
```

---

## 13. Validation Results (Reference)

### 13.1 Crailsheim (DE29) → Validated May 11, 2026

| Property | Value |
|----------|-------|
| Version | PrIME 2014→022 Hybrid (no cntflg, no zone tables) |
| Schema | `prodwms` (lowercase tables) |
| wh_id | `DE29` |
| Areas | 176 total, **10 ASRS** areas |
| Cycle counts (7 day) | 2,532 |
| Tests | **11/11 PASS** |
| IRA rows | 2,532 |

**IRA Accuracy Breakdown:**
| Area Type | Correct / Total | Accuracy |
|-----------|-----------------|----------|
| FUPA | 2,359 / 2,361 | 99.9% |
| HOFF | 4 / 6 | 66.7% |
| MIXE | 74 / 76 | 97.4% |
| PAPA | 89 / 89 | 100.0% |

### 13.2 Jijona (ES06) → Validated May 11, 2026

| Property | Value |
|----------|-------|
| Version | PrIME 2014→022 Hybrid (no cntflg, no zone tables) |
| Schema | `prodwms` (UPPERCASE tables in INFORMATION_SCHEMA) |
| wh_id | `ES06` |
| Areas | With ASRS areas (ASRS01B1, ZZASRS) →**zero cycle count data** |
| Cycle counts (7 day) | 297 |
| Tests | 9/15 PASS (6 failed due to UPPERCASE case sensitivity) |
| IRA rows | 297 (all PSTO area type, 100% accuracy) |

### 13.3 Crailsheim — allqueries.xlsx Sample Validation (May 11, 2026)

10 representative queries extracted from `allqueries.xlsx` (~765 unique production queries), tested on Crailsheim with both original 2014 SQL and remediated 2022 SQL:

| ID | Name | Category | Original | Remediated | Comparison |
|----|------|----------|----------|------------|------------|
| AQ-01 | Shipment List | Shipping | FAIL | FAIL | `TRKNUM` column not on shipment at this site |
| AQ-02 | CAR_MOVE (Carrier Moves) | Carrier/AGV | PASS (50 rows) | PASS (50 rows) | MATCH — identical |
| AQ-03 | Inventory by Area | Inventory | FAIL | FAIL | `STOLOC` not on aremst (site-specific schema) |
| AQ-04 | Cycle Count with cntflg | Cycle Count / IRA | PASS (100 rows) | PASS (100 rows) | Both return 100 (cntflg already absent) |
| AQ-05 | Area Descriptions (COALESCE) | Area/Zone | PASS (50 rows) | PASS (50 rows) | Data equivalence OK |
| AQ-06 | Item Footprint | Item Master | PASS (50 rows) | PASS (50 rows) | MATCH — identical |
| AQ-07 | Work Order Status | Production | FAIL | FAIL | `ordqty`/`cmpqty` not on wkohdr at this site |
| AQ-08 | Location Master | Location | PASS (50 rows) | PASS (50 rows) | MATCH — identical |
| AQ-09 | Policy Config (VC-PRIME) | Configuration | PASS (50 rows) | PASS (50 rows) | MATCH — identical |
| AQ-10 | Daily Transactions | Transactions | FAIL | FAIL | `stoloc` not on dlytrn at this site |

**Result: 6/10 PASS on both original and remediated.** The 4 failures are **site-specific column variations** — the same columns fail on both 2014 and 2022 versions, confirming these are site schema differences (not remediation errors). This demonstrates the value of the probe-first approach: the remediation engine must discover per-site column availability before applying transformations.

**Script:** `_validate_allqueries_sample.py` — configurable for any site (change 3 lines).

### 13.4 Athens (ATHENS_REPLICA) — Reference 2022 Site (Deep Probe May 11, 2026)

| Property | Value |
|----------|-------|
| Version | **Full PrIME 2022** |
| Server | `<replica-host>` |
| Database | `ATHENS_REPLICA` |
| Schema | `dbo` (all core tables are **synonyms** pointing to linked objects) |
| wh_id | `WMD1` |
| Architecture | **Synonym-based** — `locmst`, `trlr`, `aremst`, `invlod`, `shipment`, `car_move` are all SYNONYMS |
| INFORMATION_SCHEMA | Returns empty for synonym-based tables — must use `SELECT TOP 0 *` to discover columns |
| Views | 14 pre-built views: `inventory_view`, `pckwrk_view`, `prtftp_view`, `prtmst_view`, `ship_struct_view`, etc. |
| `aremst` | **Minimal** — only `ARECOD, WH_ID, BLDG_ID, LOST_LOC, LOGIC_FLG, BU_ID` — NO pckflg/pdflg/stoare_flg/shp_dck_flg |
| `locmst` | **Extended** — has `PCKFLG`, `STOFLG`, `REPFLG`, `PCK_ZONE_ID`, `STO_ZONE_ID`, `MOV_ZONE_ID`, `LOC_TYP_ID` |
| Zone columns | On `locmst`: `PCK_ZONE_ID`, `STO_ZONE_ID`, `MOV_ZONE_ID` (with `_ID` suffix, NOT `pck_zone`) |
| `dscmst` | ✓ Exists as synonym |
| `prtdsc` | ✓ Exists as synonym |
| `trlr_note` | ✓ Exists as synonym |
| `rplcfg` | ✓ Exists as synonym (has `ARECOD` column, no `STOARE_FLG`) |
| `dbo.getdate2()` | ✓ Works |
| `untinp` in prtftp_dtl | ✗ NOT found — use `untlay` via `prtftp_view` |
| Areas with inventory | LIQUID(7716), EXPR(5503), PAPER(3575), BEAUTY(2073), POWDER(1293), etc. |

#### Critical Athens 2022 Discovery: Flag Migration

| Flag | PrIME 2014 Location | PrIME 2022 Location | Remediation |
|------|---------------------|---------------------|-------------|
| `pckflg` (pick flag) | `aremst.pckflg` | `locmst.PCKFLG` | Change JOIN target |
| `pdflg` (putaway done) | `aremst.pdflg` | **REMOVED** | Use `locmst.PCKFLG` or area naming |
| `stoare_flg` (storage) | `aremst.stoare_flg` | `locmst.STOFLG` | Change JOIN target |
| `shp_dck_flg` (shipping dock) | `aremst.shp_dck_flg` | **Check locmst** | Adapt per site |
| `cntflg` (count) | `aremst.cntflg` | **REMOVED** | Remove filter entirely |

### 13.5 Context-Aware Validation (May 11, 2026)

5 diverse queries validated with **context-aware remediation** approach:
- Original 2014 → Crailsheim (still 2014) 
- Remediated 2022 → Athens (reference 2022)

| ID | Name | Domain | 2014/Crailsheim | 2022/Athens | Verdict | Key Remediation |
|----|------|--------|-----------------|-------------|---------|------------------|
| Q1 | Pickface Multiple Lots | Inventory/Quality | 0 rows | 849 rows | **PASS** | `aremst.pckflg=1` → `locmst.PCKFLG=1` |
| Q2 | Out of Service Trailers | Yard Mgmt | 1 row | 0 rows | **PASS** | Schema only (`prodwms` → `dbo`) |
| Q3 | Shipment ID Listing | Shipping | 993 rows | 812 rows | **PASS** | Schema only |
| Q4 | ALPS Pick Area Inventory | Replenishment | 0 rows | 23,192 rows | **PASS** | `aremst.pdflg=1` → `locmst.PCKFLG=1`, remove ALPS filter |
| Q5 | CAR_MOVE Check | Transportation | 10 rows | 10 rows | **PASS** | Schema only |

**Result: 5/5 PASS.** Key insight: Q1 and Q4 initially failed (3/5) because the naive 1:1 approach used `aremst.pckflg` and `aremst.pdflg` which don't exist in Athens 2022. Only after understanding the business intent and discovering that flags migrated to `locmst` could the correct remediation be produced.

**Script:** `_context_aware_validation.py` — validates original on 2014 site + remediated on 2022 reference site.

---

## 14. Quick-Start Checklist

For remediating queries at a new site:

- [ ] **Identify site connection:** Server URL, database name, AD credentials
- [ ] **Run schema probe:** Execute `_validate_site.py` with site config → get JSON output
- [ ] **Review probe results:** Check version (2014/2022/hybrid), schema, cntflg, zone tables, table case
- [ ] **Collect source queries:** Extract from QuickView Excel exports using `_extract_all_queries.py`
- [ ] **Phase 1 comparison:** Add site + Athens to `_parallel_compare.py` → run → verify structure matches
- [ ] **Apply remediation rules:** Schema prefix, cntflg removal, untinp→untlay, COALESCE descriptions, inventory_view→base tables
- [ ] **Validate each query:** Live execution on test instance, compare row counts
- [ ] **Generate HTML report:** Per-query confidence + live validation + what-changed
- [ ] **Track KB updates:** New mappings →`verified-mappings.json`, discoveries →`remediation-learnings.json`
- [ ] **Phase 2 comparison (post-go-live):** Compare site's own 2014 vs 2022 output at 1 week, 1 month, 3 months
- [ ] **Handle data sparsity:** Expect sparse transactional data in first weeks post-go-live; config/inventory tables are immediate

---

## Appendix A: Azure SQL Connection Pattern

All PrIME sites follow the same connection pattern:

```
Server:   <replica-host>
Database: {SITE_NAME}
Auth:     MSAL Device Code Flow (Azure AD token → pyodbc attrs_before)
Driver:   ODBC Driver 18 for SQL Server
Encrypt:  yes
Tenant:   <guid>
Client:   1950a258-227b-4e31-a9cf-717495945fc2 (Azure PowerShell well-known app)
Scope:    https://database.windows.net/.default
```

**Why MSAL device code (not `ActiveDirectoryInteractive`)?**
- `ActiveDirectoryInteractive` opens a browser popup **per connection per process** — breaks batch/multi-site scripts.
- MSAL device code flow authenticates once, caches the token to disk (`.access_token.json` + `.msal_cache.json`), and all subsequent connections reuse the cached token for ~1 hour with zero prompts.

Python connection (using cached MSAL token):
```python
import pyodbc, struct

token = _get_token()  # From _db_session.py — see Rule 6
# Pack token as SQL_COPT_SS_ACCESS_TOKEN (attribute 1256)
token_bytes = token.encode("UTF-16-LE")
token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER=<replica-host>"
    f"DATABASE={database};"
    f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=120",
    attrs_before={1256: token_struct}
)
```

**Note:** The full implementation with caching, reconnect, and multi-site support is in `SQL_Translations/_db_session.py`.

## Appendix B: Key Table Reference (PrIME 2014 →2022)

| Domain | Table | 2014 Schema | 2022 Schema | Key Changes |
|--------|-------|-------------|-------------|-------------|
| Inventory | `invlod`, `invsub`, `invdtl` | `prodwms.` | `dbo.` | Same structure |
| Inventory | `inventory_view` | `prodwms.` | May not exist | View over invlod+invsub+invdtl |
| Location | `locmst` | `prodwms.` | `dbo.` | 2022 adds `loc_typ` |
| Area | `aremst` | `prodwms.` (has `cntflg`, `pckflg`, `pdflg`, `stoare_flg`) | `dbo.` (minimal: no flags) | **All flags removed from aremst in 2022** |
| Location | `locmst` | `prodwms.` | `dbo.` | 2022 adds `LOC_TYP_ID`, `PCK_ZONE_ID`, `STO_ZONE_ID`, `MOV_ZONE_ID`, `PCKFLG`, `STOFLG` |
| Cycle Count | `cnthst` | `prodwms.` | `dbo.` | Same; remove cntflg JOIN filter |
| Item | `prtmst` | `prodwms.` | `dbo.` | Same PK |
| Item Footprint | `prtftp_view` | `prodwms.` (`untinp`) | `dbo.` (`untlay`) | Column renamed |
| Descriptions | `dscmst` | `prodwms.` | `dbo.` | 2022 adds `arecod\|wh_id` key |
| Shipping | `shipment`, `shipment_line` | `prodwms.` | `dbo.` | Same |
| Work Order | `wkohdr` | `prodwms.` | `dbo.` | Same |
| Policy | `poldat` | `prodwms.` | `dbo.` | Same; `uc_custom_parameters` deprecated |
| Transaction | `dlytrn` | `prodwms.` | `dbo.` | Activity codes may differ |
| Trailer | `trlr` | `prodwms.` | `dbo.` | Same |
| Zones | N/A | N/A | `PCK_ZONE_ID`, `STO_ZONE_ID`, `MOV_ZONE_ID` on `locmst` | **New in 2022** (with `_ID` suffix) |

## Appendix C: File Inventory

| File | Location | Purpose |
|------|----------|---------|
| **Core Infrastructure** | | |
| `_db_session.py` | `SQL_Translations/` | **Shared database session manager** — MSAL device code auth, file-based token cache, connection pooling, `get_connection()`, `discover_wh_ids()`, `discover_shipping_areas()`, `discover_trlr_stats()` |
| `_loading_dock_remediation.py` | `SQL_Translations/` | **End-to-end remediation engine** — probe, build_2022_query (adaptive), HTML report (12 sections with native sources + NULL/empty classification) |
| `_run_loading_dock.py` | `SQL_Translations/` | Combined diagnostic + full test runner (single-process, reuses cached token) |
| **Validation Scripts** | | |
| `_validate_site.py` | `SQL_Translations/` | Single-site probe + 11-test validation + full IRA |
| `_parallel_compare.py` | `SQL_Translations/` | Multi-site parallel IRA comparison |
| `_context_aware_validation.py` | `SQL_Translations/` | **Context-aware validation: 2014→ Crailsheim + 2022→ Athens** |
| `_validate_allqueries_sample.py` | `SQL_Translations/` | allqueries.xlsx sample validation (10 queries, 2014 vs 2022) |
| **Utility Scripts** | | |
| `_extract_all_queries.py` | `SQL_Translations/` | Bulk query extraction from Excel |
| `_translate_universal.py` | `SQL_Translations/` | Universal 7-phase Python remediator |
| `_show_data_output.py` | `SQL_Translations/` | Data output comparison with NULL/empty analysis |
| `_diag_wh_id.py` | `SQL_Translations/` | Diagnostic for wh_id column testing per table |
| `_probe_athens4.py` | `SQL_Translations/` | Athens 2022 deep schema probe (synonym discovery) |
| **Knowledge Base** | | |
| `verified-mappings.json` | `.github/tools/` | KB →52 tables, 64 columns |
| `remediation-learnings.json` | `.github/tools/` | Accumulated remediation discoveries |
| `prime-datamodel.json` | `.github/tools/` | Full PrIME 2022 data model (1,661 tables) |
| `erd-index.json` | `.github/tools/` | 81 ER diagram index |
| **Documentation** | | |
| `RTCIS-TO-PRIME-ARCHITECTURE.md` | Root | Full system architecture documentation |
| `PRIME-2014-TO-2022-REMEDIATION-GUIDE.md` | Root | **This file** — comprehensive methodology guide |
| **Data Sources** | | |
| `allqueries.xlsx` | `Sample Data RTCIS PRIME/PRIME 2014-2022/` | ~99+ production QuickView reports |
| `2014_2022-DatabaseComparison.xlsx` | `Sample Data RTCIS PRIME/PRIME 2014-2022/` | Field-by-field table comparison |
| **Generated Outputs** | | |
| `_loading_dock_remediation_report.html` | `SQL_Translations/` | Latest HTML report — Loading Dock Dashboard remediation (12 sections) |
| `.access_token.json` | `SQL_Translations/` | Cached MSAL access token (~1 hour validity) |
| `.msal_cache.json` | `SQL_Translations/` | MSAL token cache (refresh tokens) |
