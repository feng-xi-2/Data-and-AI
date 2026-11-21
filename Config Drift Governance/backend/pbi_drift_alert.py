"""pbi_drift_alert — rebuild of the "PrIME Config Drift Overview" Power BI report as a
runnable script + auto-alert (Teams + Email).

WHAT THIS REPLACES
------------------
The shared "PrIME Config Drift Overview.xlsx" is NOT a standalone report — it is an Excel
PivotTable live-connected to a published Power BI semantic model. Extracted from the file's
xl/connections.xml + pivotCache:

  * Provider     : MSOLAP (Power BI XMLA / Analysis Services)
  * Data Source  : pbiazure://api.powerbi.com
  * Dataset (Initial Catalog) : <guid>
  * Model name   : "DAP SP PROD Data Combined"
  * Main table   : 'DAP SP PROD Data Combined' with columns:
        Audited Instance (A), Reference Instance (R), A value, R value, Category,
        Comparison Type, Configuration Element, Configuration Element Attribute ID,
        Configuration Element Attribute Name (GUI), Configuration Level,
        Configuration Section, Deviation Comments, Deviation Notes, Deviation Severity,
        Deviation Status, Deviation Type, First seen on, Last seen on, Rationale,
        Migration Notes, Index

Rather than download the .pbix, this script queries that same model directly using the
Power BI REST `executeQueries` endpoint (pure Python — no .NET / ADOMD needed) and raises
an alert when drift matching your rule is present.

HOW IT AUTHENTICATES
--------------------
MSAL device-code flow (same 3-layer token-reuse pattern as diamond/db.py), but with the
Power BI scope. Token cache lives in a FIXED folder (~/.pbi_session) so you are not asked
to log in every run.

USAGE
-----
    # 1) one-time: install deps
    pip install -r requirements.txt

    # 2) discover the REAL severity / status / instance values so you can calibrate the rule
    python pbi_drift_alert.py --discover

    # 3) dry-run the alert (queries + evaluates, prints, but does NOT send)
    python pbi_drift_alert.py --dry-run

    # 4) real run (queries + evaluates + sends Teams/Email if breached)
    python pbi_drift_alert.py

Alerting is CONFIG-DRIVEN (see the CONFIG block). Adjust ALERT_SEVERITIES /
ALERT_OPEN_STATUSES / ONLY_NEW_TODAY to match the exact Power BI data-alert rule you want
to reproduce.

Follows the workspace rules: timestamped heartbeat logging, no silent failures (errors are
logged with type+message then re-raised), timeouts + bounded retries on every remote call.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import traceback

import msal
import requests

# ============================================================================
# CONFIG
# ============================================================================
# --- Where to read the drift data from --------------------------------------
#   "replica" : (DEFAULT) read deviations computed from the LIVE replica databases
#               (replica_drift.py -> _replica_drift/deviations.json). This is the source
#               of truth for the dashboard/graph.
#   "excel"   : read a refreshed export (Config report/data.xlsx) — benchmark/offline only.
#   "pbi"     : query the live Power BI semantic model via REST executeQueries — used only
#               to BENCHMARK the replica result for accuracy (see query_pbi_for_site /
#               replica_drift.py --compare-pbi). Power BI is no longer the source of figures.
SOURCE = os.environ.get("DRIFT_SOURCE", "replica").lower()
REPLICA_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_replica_drift", "deviations.json")
EXCEL_PATH = os.environ.get(
    "DRIFT_EXCEL_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "Config report", "data.xlsx"),
)
# --- Power BI dataset (taken straight from the .xlsx connection) ------------
DATASET_ID = os.environ.get("PBI_DATASET_ID", "<guid>")
# Optional: if the dataset lives in a specific workspace (group), set its GUID. Not required
# for executeQueries when you have Build permission via "My workspace"/shared access.
GROUP_ID = os.environ.get("PBI_GROUP_ID", "").strip()

TABLE = "DAP SP PROD Data Combined"  # the model's main fact table

# --- Auth (reuses the Azure PowerShell public client, Power BI scope) -------
TENANT_ID = os.environ.get("PBI_TENANT_ID", "<guid>")
CLIENT_ID = os.environ.get("PBI_CLIENT_ID", "1950a258-227b-4e31-a9cf-717495945fc2")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]

CACHE_DIR = os.path.expanduser("~/.pbi_session")          # FIXED path (not cwd)
TOKEN_PATH = os.path.join(CACHE_DIR, "pbi_token.json")
MSAL_CACHE_PATH = os.path.join(CACHE_DIR, "pbi_msal_cache.json")

# --- Alert rule (values VERIFIED from the real export, not guessed) ----------
# Real Deviation Severity values in the data : high, medium, low, accepted
# Real Deviation Type values                 : Missing record, Unexpected record,
#                                              Unexpected mismatching value
#
# PrIME Config Drift v3.0 (June 2026) severity model — per PrIME CoE docs:
#   Config severities (impact the CONFIG Score):   high, medium, low
#   'accepted'  = CoE-approved exception/variance; does NOT impact score (see Rationale col).
#   Health severities (impact only the HEALTH Score, added June 2026, Checks only):
#                                                  health_high, health_medium, health_low
#   These belong to Configuration Section "Configuration and Health Checks", which was
#   SPLIT OUT of Config scoring in v3.0. The data.xlsx export used here is pre-filtered with
#   "Configuration Section is not Configuration and Health Checks", so it contains ONLY the
#   config severities (that is why --discover shows no health_* values). To alert on health
#   checks, use an export WITHOUT that section filter, then add the health_* severities below.
#
# The published "Total Deviations" report filter is:
#     Deviation Status is ACTIVE
#   AND Audited Site is not blank
#   AND Scheduled Standard Comparison is not N / N-A
#   AND signal to PROD is not N
# In the Excel export the status/signal columns are not present, so the Excel path
# approximates the rule with severity (+ optional first-seen-today). The live PBI path
# can apply the full status filter.
#
# A deviation is alert-worthy when its Deviation Severity is in ALERT_SEVERITIES.
# 'accepted' is intentionally excluded (CoE-approved, no score impact).
# Set ALERT_SEVERITIES = None to alert on ANY deviation.
CONFIG_SEVERITIES = {"high", "medium", "low"}     # impact Config Score
HEALTH_SEVERITIES = {"health_high", "health_medium", "health_low"}  # impact Health Score only
ALERT_SEVERITIES = {"high"}                       # default: config high only
ALERT_OPEN_STATUSES = {"ACTIVE"}                  # live-PBI only (status col not in export)
ONLY_NEW_TODAY = False                            # alert only on drift first-seen today
MAX_DETAIL_ROWS = 50                              # cap rows included in the alert body

# --- Notification channels (secrets come from env, never hard-coded) --------
TEAMS_WEBHOOK = os.environ.get("TEAMS_WEBHOOK", "").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))
SMTP_SENDER = os.environ.get("SMTP_SENDER", "").strip()
SMTP_TO = [a.strip() for a in os.environ.get("SMTP_TO", "").split(",") if a.strip()]

# --- Remote-call resilience -------------------------------------------------
HTTP_TIMEOUT = 90       # seconds per Power BI query call
HTTP_RETRIES = 3        # attempts before giving up
BACKOFF_BASE = 2        # seconds; exponential: 1,2,4...

PBI_API = "https://api.powerbi.com/v1.0/myorg"


# ============================================================================
# logging (timestamped heartbeat — never let anything look frozen)
# ============================================================================
def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ============================================================================
# auth — MSAL device code, 3-layer token reuse, fixed cache
# ============================================================================
def _load_msal_app():
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = msal.SerializableTokenCache()
    if os.path.exists(MSAL_CACHE_PATH):
        cache.deserialize(open(MSAL_CACHE_PATH).read())
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    return app, cache


def _save_cache(cache) -> None:
    if cache.has_state_changed:
        with open(MSAL_CACHE_PATH, "w") as f:
            f.write(cache.serialize())


def get_access_token() -> str:
    # Layer 1: raw token file.
    if os.path.exists(TOKEN_PATH):
        try:
            d = json.load(open(TOKEN_PATH))
            if d.get("expires_at", 0) > time.time() + 300:
                log("token: reused cached raw token")
                return d["access_token"]
        except Exception as e:
            log(f"token: raw cache unusable ({type(e).__name__}: {e}) — re-authenticating")
    # Layer 2: MSAL silent.
    app, cache = _load_msal_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPE, account=accounts[0])
        if result and "access_token" in result:
            log("token: silent MSAL renewal")
    # Layer 3: device code.
    if not result or "access_token" not in result:
        flow = app.initiate_device_flow(scopes=SCOPE)
        if "user_code" not in flow:
            raise RuntimeError(f"device flow failed: {flow}")
        log("=" * 60)
        log("ACTION REQUIRED — sign in to Power BI:")
        log(flow["message"])
        log("=" * 60)
        result = app.acquire_token_by_device_flow(flow)  # blocks until done
    if "access_token" not in result:
        raise RuntimeError(f"auth failed: {result.get('error_description', result)}")
    _save_cache(cache)
    expires_at = time.time() + int(result.get("expires_in", 3600))
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump({"access_token": result["access_token"], "expires_at": expires_at}, f)
    return result["access_token"]


# ============================================================================
# Power BI DAX query via REST executeQueries (timeout + bounded retry)
# ============================================================================
def _execute_queries_url() -> str:
    if GROUP_ID:
        return f"{PBI_API}/groups/{GROUP_ID}/datasets/{DATASET_ID}/executeQueries"
    return f"{PBI_API}/datasets/{DATASET_ID}/executeQueries"


def run_dax(dax: str) -> list[dict]:
    """Run a DAX query against the Power BI model; return the first table's rows as dicts."""
    token = get_access_token()
    url = _execute_queries_url()
    body = {
        "queries": [{"query": dax}],
        "serializerSettings": {"includeNulls": True},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            log(f"query: POST executeQueries (attempt {attempt}/{HTTP_RETRIES})")
            r = requests.post(url, headers=headers, json=body, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                rows = data["results"][0]["tables"][0].get("rows", [])
                log(f"query: OK — {len(rows)} row(s)")
                return rows
            # 401/403 -> token/permission; 429/5xx -> transient. Log body then decide.
            snippet = r.text[:500].replace("\n", " ")
            log(f"query: HTTP {r.status_code} — {snippet}")
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {r.status_code}")
            else:
                # 400/401/403 won't fix themselves on retry — fail fast, loudly.
                raise RuntimeError(f"executeQueries failed HTTP {r.status_code}: {snippet}")
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            log(f"query: network error ({type(e).__name__}: {e})")
        if attempt < HTTP_RETRIES:
            wait = BACKOFF_BASE ** (attempt - 1)
            log(f"query: retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"executeQueries failed after {HTTP_RETRIES} attempts: {last_err}")


def _col(name: str) -> str:
    """DAX column reference for the main table."""
    return f"'{TABLE}'[{name}]"


# ============================================================================
# Excel source — read a refreshed export (Config report/data.xlsx), no creds
# ============================================================================
# Map the export's column names -> the canonical keys the alert/notifiers use.
EXCEL_COLMAP = {
    "Audited Site": "Audited",
    "Reference Value": "R_value",
    "Audited Value": "A_value",
    "Configuration Section": "Section",
    "Configuration Element": "Element",
    "Deviation Severity": "Severity",
    "Deviation Type": "Type",
    "Deviation Details": "Details",
    "First seen on": "FirstSeen",
    "Last seen on": "LastSeen",
}


def read_excel_rows() -> list[dict]:
    """Read data.xlsx and return normalised deviation rows (canonical keys)."""
    import openpyxl

    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel export not found: {EXCEL_PATH}")
    log(f"excel: opening {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb["Export"] if "Export" in wb.sheetnames else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it))
    n = len(hdr)
    idx = {h: i for i, h in enumerate(hdr)}
    missing = [c for c in EXCEL_COLMAP if c not in idx]
    if missing:
        log(f"excel: WARNING missing expected columns: {missing}")
    out: list[dict] = []
    total = 0
    for raw in it:
        total += 1
        raw = list(raw) + [None] * (n - len(raw))
        rec = {canon: (raw[idx[src]] if src in idx else None)
               for src, canon in EXCEL_COLMAP.items()}
        rec.setdefault("Reference", None)   # export has no explicit reference-instance col
        out.append(rec)
    log(f"excel: read {total} row(s)")
    return out


def _sev_norm(v) -> str:
    return str(v).strip().lower() if v is not None else ""


def _is_today(v) -> bool:
    if v is None:
        return False
    if isinstance(v, datetime.datetime):
        return v.date() == datetime.date.today()
    if isinstance(v, datetime.date):
        return v == datetime.date.today()
    try:
        return str(v).startswith(datetime.date.today().isoformat())
    except Exception:
        return False


def evaluate_excel() -> list[dict]:
    rows = read_excel_rows()
    sev_set = {s.lower() for s in ALERT_SEVERITIES} if ALERT_SEVERITIES else None
    hits = []
    for r in rows:
        if sev_set is not None and _sev_norm(r.get("Severity")) not in sev_set:
            continue
        if ONLY_NEW_TODAY and not _is_today(r.get("FirstSeen")):
            continue
        hits.append(r)
    log(f"excel: {len(hits)} row(s) match the alert rule "
        f"(severities={sorted(sev_set) if sev_set else 'ANY'}, today_only={ONLY_NEW_TODAY})")
    return hits


def discover_excel() -> None:
    from collections import Counter
    rows = read_excel_rows()
    for col in ("Severity", "Type", "Status"):
        c = Counter(_sev_norm(r.get(col)) if col == "Severity" else r.get(col) for r in rows)
        if any(k not in (None, "") for k in c):
            log(f"DISCOVER excel: distinct {col}")
            for k, v in c.most_common():
                print("   ", repr(k), v)


# ============================================================================
# discover — pull the REAL distinct values so the alert rule can be calibrated
# ============================================================================
def discover() -> None:
    log("DISCOVER: distinct Deviation Severity")
    for r in run_dax(f"EVALUATE VALUES({_col('Deviation Severity')})"):
        print("   severity:", list(r.values())[0])

    log("DISCOVER: distinct Deviation Status")
    for r in run_dax(f"EVALUATE VALUES({_col('Deviation Status')})"):
        print("   status:", list(r.values())[0])

    log("DISCOVER: distinct Deviation Type")
    for r in run_dax(f"EVALUATE VALUES({_col('Deviation Type')})"):
        print("   type:", list(r.values())[0])

    log("DISCOVER: row count by severity")
    dax = (
        "EVALUATE\n"
        "SUMMARIZECOLUMNS(\n"
        f"    {_col('Deviation Severity')},\n"
        f"    {_col('Deviation Status')},\n"
        '    "Count", COUNTROWS(\'' + TABLE + "')\n"
        ")"
    )
    for r in run_dax(dax):
        print("   ", r)


# ============================================================================
# alert query + evaluation
# ============================================================================
def _quote_set(values: set[str]) -> str:
    return "{" + ", ".join('"' + v.replace('"', '""') + '"' for v in sorted(values)) + "}"


def build_alert_dax() -> str:
    conditions = []
    if ALERT_SEVERITIES:
        conditions.append(f"{_col('Deviation Severity')} IN {_quote_set(ALERT_SEVERITIES)}")
    if ALERT_OPEN_STATUSES:
        conditions.append(f"{_col('Deviation Status')} IN {_quote_set(ALERT_OPEN_STATUSES)}")
    if ONLY_NEW_TODAY:
        conditions.append(f"{_col('First seen on')} = TODAY()")
    filt = " && ".join(conditions) if conditions else "TRUE()"

    return (
        "EVALUATE\n"
        "SELECTCOLUMNS(\n"
        f"    FILTER('{TABLE}', {filt}),\n"
        f'    "Audited",   {_col("Audited Instance (A)")},\n'
        f'    "Reference", {_col("Reference Instance (R)")},\n'
        f'    "Section",   {_col("Configuration Section")},\n'
        f'    "Element",   {_col("Configuration Element")},\n'
        f'    "Severity",  {_col("Deviation Severity")},\n'
        f'    "Status",    {_col("Deviation Status")},\n'
        f'    "A_value",   {_col("A value")},\n'
        f'    "R_value",   {_col("R value")},\n'
        f'    "FirstSeen", {_col("First seen on")}\n'
        ")\n"
        f"ORDER BY [Severity], [Audited]"
    )


def _clean(row: dict) -> dict:
    """Strip the DAX '[Col]' bracket wrapper from result keys."""
    out = {}
    for k, v in row.items():
        key = k
        if key.startswith("[") and key.endswith("]"):
            key = key[1:-1]
        out[key] = v
    return out


def evaluate() -> list[dict]:
    dax = build_alert_dax()
    log("ALERT query DAX:\n" + dax)
    rows = [_clean(r) for r in run_dax(dax)]
    return rows


# ============================================================================
# replica source (DEFAULT) — read deviations computed from the live replicas
# ============================================================================
def read_replica_rows() -> list[dict]:
    """Read replica_drift.py output and normalise to the canonical alert keys."""
    if not os.path.exists(REPLICA_JSON):
        raise FileNotFoundError(
            f"live-replica deviations not found: {REPLICA_JSON} — run "
            f"'python replica_drift.py --site <SITE> --mode migration' first")
    log(f"replica: opening {REPLICA_JSON}")
    with open(REPLICA_JSON, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("rows", []) if isinstance(data, dict) else (data or [])
    out = []
    for r in rows:
        out.append({
            "Audited": r.get("Audited Instance") or r.get("Audited Site"),
            "Reference": r.get("Reference Instance"),
            "Section": r.get("Configuration Section"),
            "Element": r.get("Configuration Element"),
            "Severity": r.get("Deviation Severity"),
            "Status": r.get("Deviation Status"),
            "Type": r.get("Deviation Type"),
            "A_value": r.get("A value"),
            "R_value": r.get("R value"),
            "FirstSeen": r.get("First seen on"),
            "LastSeen": r.get("Last seen on"),
        })
    log(f"replica: read {len(out)} deviation(s) from {data.get('source', 'live-replica')} "
        f"(mode={data.get('mode') if isinstance(data, dict) else '?'})")
    return out


def evaluate_replica() -> list[dict]:
    rows = read_replica_rows()
    sev_set = {s.lower() for s in ALERT_SEVERITIES} if ALERT_SEVERITIES else None
    hits = []
    for r in rows:
        if sev_set is not None and _sev_norm(r.get("Severity")) not in sev_set:
            continue
        if ONLY_NEW_TODAY and not _is_today(r.get("FirstSeen")):
            continue
        hits.append(r)
    log(f"replica: {len(hits)} of {len(rows)} deviation(s) match the alert rule "
        f"(severities={sorted(sev_set) if sev_set else 'ANY'})")
    return hits


# ============================================================================
# Power BI BENCHMARK — only used to score the replica result for accuracy
# ============================================================================
def query_pbi_for_site(site: str) -> list[dict]:
    """Benchmark provider: pull the live Power BI deviations for an audited instance.

    Used by replica_drift.py --compare-pbi to score replica-computed drift against the Power
    BI model. Returns rows keyed with the Power BI field names (Configuration Section /
    Configuration Element / Deviation Type / Deviation Severity / A value / R value ...).
    Power BI is the BENCHMARK here, never the dashboard source.
    """
    safe = str(site).replace('"', '""')
    dax = (
        "EVALUATE\n"
        "SELECTCOLUMNS(\n"
        f'    FILTER(\'{TABLE}\', SEARCH("{safe}", {_col("Audited Instance (A)")}, 1, 0) > 0),\n'
        f'    "Configuration Section", {_col("Configuration Section")},\n'
        f'    "Configuration Element", {_col("Configuration Element")},\n'
        f'    "Deviation Type",        {_col("Deviation Type")},\n'
        f'    "Deviation Severity",    {_col("Deviation Severity")},\n'
        f'    "A value",               {_col("A value")},\n'
        f'    "R value",               {_col("R value")},\n'
        f'    "Audited Instance",      {_col("Audited Instance (A)")},\n'
        f'    "Reference Instance",    {_col("Reference Instance (R)")}\n'
        ")"
    )
    log(f"pbi-benchmark: querying deviations for audited instance ~ '{site}'")
    return [_clean(r) for r in run_dax(dax)]


# ============================================================================
# notifiers — Teams + Email, each with bounded retry, never silent
# ============================================================================
def _summary_text(rows: list[dict]) -> str:
    n = len(rows)
    by_site: dict[str, int] = {}
    for r in rows:
        by_site[r.get("Audited", "?")] = by_site.get(r.get("Audited", "?"), 0) + 1
    top = ", ".join(f"{k} ({v})" for k, v in sorted(by_site.items(), key=lambda x: -x[1])[:8])
    return f"{n} config-drift deviation(s) match the alert rule. Sites: {top}"


def notify_teams(rows: list[dict]) -> None:
    if not TEAMS_WEBHOOK:
        log("teams: TEAMS_WEBHOOK not set — skipping Teams alert")
        return
    lines = []
    for r in rows[:MAX_DETAIL_ROWS]:
        lines.append(
            f"- **{r.get('Audited')}** vs {r.get('Reference')} | "
            f"{r.get('Section')} / {r.get('Element')} | "
            f"{r.get('Severity')} / {r.get('Status')} | "
            f"A=`{r.get('A_value')}` R=`{r.get('R_value')}`"
        )
    if len(rows) > MAX_DETAIL_ROWS:
        lines.append(f"- …and {len(rows) - MAX_DETAIL_ROWS} more")
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "D93F0B",
        "summary": "PrIME Config Drift alert",
        "title": "⚠️ PrIME Config Drift Overview — alert",
        "text": _summary_text(rows) + "\n\n" + "\n".join(lines),
    }
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.post(TEAMS_WEBHOOK, json=card, timeout=30)
            resp.raise_for_status()
            log("teams: alert sent")
            return
        except Exception as e:
            log(f"teams: send failed ({attempt}/{HTTP_RETRIES}) {type(e).__name__}: {e}")
            if attempt < HTTP_RETRIES:
                time.sleep(BACKOFF_BASE ** (attempt - 1))
    raise RuntimeError("teams alert failed after retries")


def notify_email(rows: list[dict]) -> None:
    if not (SMTP_HOST and SMTP_SENDER and SMTP_TO):
        log("email: SMTP_HOST/SMTP_SENDER/SMTP_TO not fully set — skipping Email alert")
        return
    import smtplib
    from email.mime.text import MIMEText

    body_lines = [_summary_text(rows), ""]
    for r in rows[:MAX_DETAIL_ROWS]:
        body_lines.append(
            f"{r.get('Audited')} vs {r.get('Reference')} | {r.get('Section')} / "
            f"{r.get('Element')} | {r.get('Severity')} / {r.get('Status')} | "
            f"A={r.get('A_value')} | R={r.get('R_value')} | first_seen={r.get('FirstSeen')}"
        )
    if len(rows) > MAX_DETAIL_ROWS:
        body_lines.append(f"...and {len(rows) - MAX_DETAIL_ROWS} more")
    body_lines += ["", f"Generated: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
                   f"Dataset: {DATASET_ID}"]

    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = f"[ALERT] PrIME Config Drift — {len(rows)} deviation(s)"
    msg["From"] = SMTP_SENDER
    msg["To"] = ", ".join(SMTP_TO)

    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.sendmail(SMTP_SENDER, SMTP_TO, msg.as_string())
            log("email: alert sent")
            return
        except Exception as e:
            log(f"email: send failed ({attempt}/{HTTP_RETRIES}) {type(e).__name__}: {e}")
            if attempt < HTTP_RETRIES:
                time.sleep(BACKOFF_BASE ** (attempt - 1))
    raise RuntimeError("email alert failed after retries")


# ============================================================================
# main
# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="PrIME Config Drift — script + auto-alert")
    ap.add_argument("--discover", action="store_true",
                    help="print distinct severity/status/type + counts, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="query + evaluate + print, but do NOT send any alert")
    args = ap.parse_args()

    log("=== PrIME Config Drift alert START ===")
    log(f"source={SOURCE}")
    try:
        if args.discover:
            if SOURCE == "excel":
                discover_excel()
            elif SOURCE == "replica":
                log("discover: replica source — inspect _replica_drift/deviations.json "
                    "(run replica_drift.py to (re)compute)")
            else:
                log(f"dataset={DATASET_ID} group={GROUP_ID or '(shared/my)'}")
                discover()
            log("=== DISCOVER DONE ===")
            return 0

        if SOURCE == "excel":
            rows = evaluate_excel()
        elif SOURCE == "replica":
            rows = evaluate_replica()
        else:
            log(f"dataset={DATASET_ID} group={GROUP_ID or '(shared/my)'}")
            rows = evaluate()
        log(f"result: {len(rows)} deviation(s) match the alert rule")

        if not rows:
            log("OK — no drift matches the rule. No alert.")
            log("=== DONE ===")
            return 0

        # show a preview always
        for r in rows[:10]:
            log("  " + json.dumps(r, default=str))

        if args.dry_run:
            log("DRY-RUN — breach detected but not sending (would alert Teams/Email).")
            log("=== DONE (dry-run) ===")
            return 2

        log("BREACH — sending alerts")
        notify_teams(rows)
        notify_email(rows)
        log("=== DONE (alerted) ===")
        return 2

    except Exception as e:
        # never fail silently
        log(f"FATAL: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        raise


if __name__ == "__main__":
    sys.exit(main())
