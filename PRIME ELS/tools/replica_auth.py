"""
_prfc3957_db.py — Azure SQL (Data Replica MI) connection helper for NA PrIME sites.
Mirrors the SSMS _db_session.py pattern documented in memory:
  - MSAL device-code flow, client 1950a258-227b-4e31-a9cf-717495945fc2 (Azure PowerShell)
  - scope https://database.windows.net/.default
  - token injected via attrs_before {1256: SQL_COPT_SS_ACCESS_TOKEN}
  - 3-layer token reuse: raw token json -> MSAL silent -> device code
Token cache fixed folder: ~/.sql_session/  (survives across processes, like databricks one).

Usage:
    from _prfc3957_db import connect, SITES
    cn = connect("LIMA")            # returns live pyodbc connection
    cur = cn.cursor(); cur.execute("select 1"); print(cur.fetchone())
"""
import os, json, time, struct, datetime, sys

import msal
import pyodbc

TENANT_ID = "<tenant-id>"
CLIENT_ID = "1950a258-227b-4e31-a9cf-717495945fc2"   # Azure PowerShell public client
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://database.windows.net/.default"]
DRIVER = "ODBC Driver 18 for SQL Server"
SUFFIX = ".<mi-dns-zone>.database.windows.net"
SQL_COPT_SS_ACCESS_TOKEN = 1256

CACHE_DIR = os.path.expanduser("~/.sql_session")
TOKEN_PATH = os.path.join(CACHE_DIR, "sql_token.json")
MSAL_CACHE_PATH = os.path.join(CACHE_DIR, "sql_msal_cache.json")

# PrIME replica sites: name -> (server_host_short, database)
# NA sites plus EU sites that sit on the SAME server suffix (see
# kb/WH_Data_Replica_Servers.md).
SITES = {
    "ALBANY":     ("<replica-server>", "ALBANY"),
    "ANDOVER":    ("<replica-server>", "ANDOVER"),
    "BOXELDER":   ("<replica-server>", "BOXELDER"),
    "BRANTFORD":  ("<replica-server>", "BRANTFORD"),
    "DALLAS":     ("<replica-server>", "DLMC"),
    "DAYTON":     ("<replica-server>", "DYMC"),
    "EDMC":       ("<replica-server>", "EDMC"),
    "GCFC":       ("<replica-server>", "GCFC"),
    "GREENSBORO": ("<replica-server>", "GREENSBORO"),
    "LIMA":       ("<replica-server>", "LIMA"),
    "MEHOOPANY":  ("<replica-server>", "MEHOOPANY"),
    "NEMC":       ("<replica-server>", "NEMC"),
    "SEFC":       ("<replica-server>", "SEFC"),
    "SEMC":       ("<replica-server>", "SEMC"),
    "TABLER":     ("<replica-server>", "TABLER"),
    "WCMC":       ("<replica-server>", "WCMC"),
    "PHOENIX":    ("<replica-server>", "PHOENIX"),
    # EUROPE
    "MECHELEN":   ("<replica-server>", "MECHELEN"),
    # fleet-validation sites (kb/WH_Data_Replica_Servers.md)
    "JAKARTA":    ("<replica-server>",  "JAKARTA"),
    "BLOIS":      ("<replica-server>",    "BLOIS"),
    "MEDELLIN":   ("<replica-server>", "MEDELLIN"),
    "NAUCALPAN":  ("<replica-server>","NAUCALPAN"),
}


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _load_msal_app():
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = msal.SerializableTokenCache()
    if os.path.exists(MSAL_CACHE_PATH):
        cache.deserialize(open(MSAL_CACHE_PATH).read())
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    return app, cache


def _save_cache(cache):
    if cache.has_state_changed:
        with open(MSAL_CACHE_PATH, "w") as f:
            f.write(cache.serialize())


def get_access_token():
    # Layer 1: raw token file
    if os.path.exists(TOKEN_PATH):
        try:
            d = json.load(open(TOKEN_PATH))
            if d.get("expires_at", 0) > time.time() + 300:
                log("token: reused cached raw token")
                return d["access_token"]
        except Exception:
            pass
    # Layer 2: MSAL silent
    app, cache = _load_msal_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPE, account=accounts[0])
        if result and "access_token" in result:
            log("token: silent MSAL renewal")
    # Layer 3: device code
    if not result or "access_token" not in result:
        flow = app.initiate_device_flow(scopes=SCOPE)
        if "user_code" not in flow:
            raise RuntimeError(f"device flow failed: {flow}")
        log("=" * 60)
        log("ACTION REQUIRED — sign in to Azure SQL:")
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


def _token_struct(access_token):
    tok = access_token.encode("utf-16-le")
    return struct.pack(f"<I{len(tok)}s", len(tok), tok)


def connect(site, timeout=30):
    if site not in SITES:
        raise KeyError(f"{site} not a known PrIME replica site: {list(SITES)}")
    host_short, db = SITES[site]
    server = host_short + SUFFIX
    token = get_access_token()
    conn_str = (
        f"Driver={{{DRIVER}}};Server=tcp:{server},1433;Database={db};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout={timeout};"
    )
    log(f"connecting {site} -> {server} / {db}")
    cn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _token_struct(token)},
                        timeout=timeout)
    log(f"connected {site}")
    return cn


if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "LIMA"
    cn = connect(site)
    cur = cn.cursor()
    cur.execute("SELECT DB_NAME(), SUSER_SNAME(), SYSUTCDATETIME()")
    print("probe:", cur.fetchone())
    cn.close()
    log("done")
