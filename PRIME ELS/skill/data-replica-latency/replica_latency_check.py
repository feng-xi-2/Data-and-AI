"""
replica_latency_check.py — Data Replica latency for ANY site, ANY engine
(PrIME 2022 / PrIME 2014 / RTCIS). Read-only, self-discovering, fact-grounded.

WHAT IT MEASURES (two independent latency numbers per site)
  1. HVR CAPTURE LATENCY  = SYSUTCDATETIME() - trailer_cap_begin
       trailer_cap_begin is the HVR capture watermark (UTC) read from the
       integrate-state table hvr_is* in the <SITE>_RTDS database, hvr schema.
       This says "how far behind the SOURCE the replication capture is".
  2. DATA LATENCY         = site_local_now - MAX(<txn>.<trndte>)
       Newest business transaction actually landed in the replica.
       - 2022 : dbo.dlytrn.trndte
       - 2014 : prodwms.dlytrn.trndte
       - RTCIS: live3.SYSTRN.SYSDAT  (SYSDAT = real system-txn time; NOT APTDAT/
                LRDATE which are FUTURE appointment dates) — auto-detected
       dlytrn.trndte / SYSTRN.SYSDAT are SITE-LOCAL, so we compare to local now.
  3. integ_blocked flag from hvr_ic* (0 = flowing, !=0 = HVR ALERT).

ENGINE DETECTION (per replica db)
  - 2022 : dlytrn resolves in schema 'dbo' (synonym over base tables)
  - 2014 : dlytrn resolves in schema 'prodwms'
  - RTCIS: no dlytrn; SYSTRN / AS_RTCIS_* present (live3-style)

CRAILSHEIM DB TRAP (baked in): <replica-server> hosts a STALE 2014 facade db
'CRAILSHEIM' (frozen). The live 2022 feed is 'CRAILSHEIM_REPLICA'. The resolver
below auto-picks the freshest WMS db when the caller passes a site alias.

USAGE
  python replica_latency_check.py                 # default demo set (one of each engine)
  python replica_latency_check.py ATHENS CRAILSHEIM POMEZIA
  python replica_latency_check.py --server <replica-server> --db XIQING --offset 8

Auth reuses the SQL_Translations/_mm_audit/_prfc3957_db.py AAD helper (MSAL device
code, token cached in ~/.sql_session). Heartbeat every 5s; per-step try/except;
statement timeout; NOTHING suppressed.
"""
from __future__ import annotations
import argparse, os, sys, csv, datetime as dt, threading, traceback

# locate the AAD helper (_prfc3957_db) — works from either the OneDrive or the
# Local Desktop workspace copy. The helper lives in SQL_Translations/_mm_audit.
_HERE = os.path.dirname(os.path.abspath(__file__))
_USER = os.path.expanduser("~")
_FOUND = False
for _cand in (
    os.path.join(_HERE, "_mm_audit"),
    os.path.join(_USER, "Desktop", "M&M", "SQL_Translations", "_mm_audit"),
    os.path.join(_USER, "OneDrive - <company>", "Desktop", "M&M", "SQL_Translations", "_mm_audit"),
    os.path.abspath(os.path.join(_HERE, "..", "..", "..", "SQL_Translations", "_mm_audit")),
):
    if os.path.isdir(_cand):
        sys.path.insert(0, _cand)
        _FOUND = True
        break
if not _FOUND:
    sys.stderr.write("could not locate _mm_audit/_prfc3957_db.py — set SQLT_MM_AUDIT env var\n")
    _env = os.environ.get("SQLT_MM_AUDIT")
    if _env and os.path.isdir(_env):
        sys.path.insert(0, _env)
import pyodbc
import _prfc3957_db as _db

SUFFIX = _db.SUFFIX
DRIVER = _db.DRIVER

# ── Known-site registry: alias -> (server_host_short, preferred_wms_db, utc_offset_h, engine_hint)
# offset = site-local minus UTC (summer values as of 2026-09). engine_hint is advisory only;
# the script re-detects engine live. If a site is not here, pass --server/--db/--offset.
SITES = {
    # PrIME 2022 (dbo synonyms)
    "ATHENS":     ("<replica-server>",     "ATHENS_REPLICA",     3, "2022"),
    "BINHDUONG":  ("<replica-server>.database.windows.net", "BINHDUONG_REPLICA", 7, "2022"),   # PRIME ELS hypercare sites
    "MINHANG":    ("<replica-server>.database.windows.net",   "MINHANG_REPLICA",   8, "2022"),   # (other domain than SUFFIX)
    "JAKARTA":    ("<replica-server>",    "JAKARTA",            7, "2014"),
    "AKASHI":     ("<replica-server>",     "AKASHI_REPLICA",     9, "2022"),
    "CRAILSHEIM": ("<replica-server>", "CRAILSHEIM_REPLICA", 2, "2022"),   # NOT the stale 'CRAILSHEIM' facade
    "XIQING":     ("<replica-server>",     "XIQING",             8, "2014"),
    # RTCIS (live3 / AS_RTCIS_*)
    "POMEZIA":    ("<replica-server>",    "POMEZIA",            2, "RTCIS"),
    # PrIME 2014 (prodwms) — LA + others
    "SMO":        ("<replica-server>",        "SMO",               -6, "2014"),
    "VALLEJO":    ("<replica-server>",    "VALLEJO",           -6, "2014"),
    "CABUYAO":    ("<replica-server>",    "CABUYAO",            8, "2014"),
}

DEFAULT_SET = ["ATHENS", "SMO", "POMEZIA"]  # one 2022, one 2014, one RTCIS

OUT_TXT = os.path.join(_HERE, "_replica_latency.txt")
OUT_CSV = os.path.join(_HERE, "_replica_latency.csv")
_log = open(OUT_TXT, "w", encoding="utf-8", buffering=1)
_lock = threading.Lock(); _stop = threading.Event(); _fails: list[str] = []


def emit(m=""):
    with _lock:
        print(m, flush=True); print(m, file=_log, flush=True)


def heartbeat():
    n = 0
    while not _stop.wait(5):
        n += 1
        emit(f"[HEARTBEAT {n:03d}] alive utc={dt.datetime.now(dt.timezone.utc):%H:%M:%S} fails={len(_fails)}")


_tok = None
def connect(server, database, timeout=45):
    global _tok
    if _tok is None:
        _tok = _db.get_access_token()
    cs = (f"Driver={{{DRIVER}}};Server=tcp:{server},1433;Database={database};"
          f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout={timeout};")
    cn = pyodbc.connect(cs, attrs_before={_db.SQL_COPT_SS_ACCESS_TOKEN: _db._token_struct(_tok)}, timeout=timeout)
    cn.timeout = 120
    return cn


def q(cn, sql):
    c = cn.cursor(); c.execute(sql)
    cols = [d[0] for d in c.description] if c.description else []
    return cols, c.fetchall()


def fmt(seconds):
    if seconds is None:
        return "n/a"
    sign = "-" if seconds < 0 else ""
    s = abs(int(seconds)); h, r = divmod(s, 3600); m, s = divmod(r, 60)
    return f"{sign}{h}h {m}m {s}s"


def list_databases(server):
    cn = connect(server, "master")
    _, rows = q(cn, "SELECT name FROM sys.databases ORDER BY name;")
    cn.close()
    return [r[0] for r in rows]


def resolve_wms_db(server, preferred, dbs):
    """Pick the live WMS db. Honour 'preferred' if present; else prefer *_REPLICA,
    then a bare site db, avoiding *_RTDS/_simp/_ARCH facades."""
    if preferred in dbs:
        return preferred
    repl = [d for d in dbs if d.upper().endswith("_REPLICA")]
    if repl:
        return repl[0]
    bad = ("_RTDS", "_SIMP", "_ARCH", "ARCHIVE", "_CREATEDBYSIMP")
    cand = [d for d in dbs if d.upper() not in ("MASTER", "MODEL", "MSDB", "TEMPDB",
            "MAINTENANCE", "MONITORING") and not any(b in d.upper() for b in bad)]
    return cand[0] if cand else preferred


def find_hvr(server, dbs):
    """Locate the HVR integrate-state / control tables across engines.
    They live in different places depending on engine:
      - 2022 : <SITE>_RTDS.hvr.hvr_is* / hvr_ic*
      - 2014 : <SITE>_simp.dbo.hvr_is<site> / hvr_ic<site>
      - RTCIS : <SITE>_simp.simp_repl_live.hvr_is<site> / hvr_ic<site>
    We match hvr_is*/hvr_ic* by NAME pattern regardless of schema, scanning the
    RTDS db first, then any *_simp db, then the rest.
    Returns (hvr_db, schema, is_tbl, ic_tbl, total_hvr_tables)."""
    ordered = ([d for d in dbs if d.upper().endswith("_RTDS")] +
               [d for d in dbs if d.upper().endswith("_SIMP")] +
               [d for d in dbs if not d.upper().endswith(("_RTDS", "_SIMP"))
                and d.upper() not in ("MASTER", "MODEL", "MSDB", "TEMPDB",
                                      "MAINTENANCE", "MONITORING")])
    for cand in ordered:
        try:
            cn = connect(server, cand)
            _, rr = q(cn, "SELECT s.name AS sch, o.name AS tbl "
                          "FROM sys.objects o JOIN sys.schemas s ON o.schema_id=s.schema_id "
                          "WHERE (o.name LIKE 'hvr[_]is%' OR o.name LIKE 'hvr[_]ic%') "
                          "AND o.type IN ('U','V','SN') ORDER BY o.name;")
            cn.close()
            iss = [(s, t) for s, t in rr if t.lower().startswith("hvr_is")]
            ics = [(s, t) for s, t in rr if t.lower().startswith("hvr_ic")]
            if iss:
                sch, is_tbl = iss[0]
                ic_tbl = ics[0][1] if ics else None
                return cand, sch, is_tbl, ic_tbl, len(rr)
        except Exception as e:
            emit(f"    [warn] scan {cand}: {type(e).__name__}: {str(e)[:120]}")
    return None, None, None, None, 0


# transaction-source candidates in priority order: (schema, table)
TXN_CANDIDATES = [
    ("dbo", "dlytrn"),        # 2022
    ("prodwms", "dlytrn"),    # 2014
    ("live3", "dlytrn"),      # RTCIS (if exposed)
    ("dbo", "SYSTRN"),        # RTCIS system-transaction
    ("live3", "SYSTRN"),
]
# preferred date-column names (upper), BEST-FIRST by business meaning.
# SYSDAT = RTCIS SYSTRN system-transaction timestamp (real event time). It MUST
# rank ABOVE APTDAT/LRDATE, which are future *appointment* dates and would
# otherwise overstate freshness (they sit hours in the future).
DATE_COL_PREF = ("TRNDTE", "SYSDAT", "TRN_DATE", "TRNDATE", "GENDAT",
                 "ADDDTE", "ADD_DTE", "MOD_DTE", "MODDTE", "INS_DT",
                 "LAST_UPD_DT", "SYSTIME", "TRN_TIME")


def _resolve_date_col(cn, sch, tbl):
    """Return the business-correct date column for sch.tbl. dlytrn/SYSTRN are
    SYNONYMS, so sys.columns is empty — probe candidate names with MAX() and
    return the FIRST one in DATE_COL_PREF that exists and has data. First-match
    (not newest-value) respects intent: e.g. RTCIS SYSDAT beats future APTDAT."""
    # dlytrn's PrIME daily-transaction date is always 'trndte'
    if tbl.lower() == "dlytrn":
        try:
            q(cn, f"SELECT MAX(trndte) FROM {sch}.{tbl};")
            return "trndte"
        except Exception:
            pass
    for c in DATE_COL_PREF:
        try:
            _, rr = q(cn, f"SELECT MAX([{c}]) FROM {sch}.{tbl};")
            if rr and rr[0][0] is not None:
                return c  # first preferred column that exists with data
        except Exception:
            continue  # column doesn't exist on this table
    return None


def detect_txn(cn):
    """Find which transaction source exists and its best date column.
    Returns (schema, table, date_col, engine). Synonym-safe."""
    _, objs = q(cn, "SELECT s.name, o.name FROM sys.objects o "
                    "JOIN sys.schemas s ON o.schema_id=s.schema_id "
                    "WHERE o.name IN ('dlytrn','SYSTRN') AND o.type IN ('U','V','SN');")
    have = {(s.lower(), o.lower()): (s, o) for s, o in objs}
    for sch, tbl in TXN_CANDIDATES:
        key = (sch.lower(), tbl.lower())
        if key not in have:
            continue
        rsch, rtbl = have[key]
        col = _resolve_date_col(cn, rsch, rtbl)
        if not col:
            continue  # no usable date column (e.g. empty synonym) — try next
        engine = ("2022" if (rsch == "dbo" and rtbl.lower() == "dlytrn")
                  else "2014" if (rsch == "prodwms" and rtbl.lower() == "dlytrn")
                  else "RTCIS")
        return rsch, rtbl, col, engine
    return None, None, None, "UNKNOWN"


def probe(alias, server_host, preferred_db, offset_h, engine_hint):
    # a full host name (with its own domain, e.g. BINHDUONG / MINHANG on .<mi-dns-zone>) is used as given; a short name gets SUFFIX
    server = server_host if "." in server_host else server_host + SUFFIX
    emit("\n" + "=" * 100)
    emit(f"SITE: {alias}   server={server}   hint={engine_hint}   offset=UTC{offset_h:+d}")
    emit("=" * 100)
    r = {"site": alias, "server": server, "engine": engine_hint,
         "wms_db": None, "hvr_db": None, "cap_lag_s": None, "data_lag_s": None,
         "integ_blocked": None, "cap_watermark": None, "max_trndte": None, "status": "OK"}
    try:
        dbs = list_databases(server)
        emit(f"databases: {dbs}")
    except Exception as e:
        emit(f"[FAIL] db-list: {type(e).__name__}: {str(e)[:160]}"); _fails.append(alias)
        r["status"] = "CONN_FAIL"; return r

    wms_db = resolve_wms_db(server, preferred_db, dbs)
    r["wms_db"] = wms_db
    emit(f"resolved WMS db: {wms_db}")

    # HVR watermark
    hvr_db, hvr_sch, is_tbl, ic_tbl, ntab = find_hvr(server, dbs)
    r["hvr_db"] = hvr_db
    if hvr_db and is_tbl:
        emit(f"HVR control db = {hvr_db}.{hvr_sch}: is={is_tbl} ic={ic_tbl} (hvr tables={ntab})")
        try:
            cn = connect(server, hvr_db)
            _, rr = q(cn, f"""SELECT trailer_cap_begin, last_integ_end, SYSUTCDATETIME() now_utc,
                                     DATEDIFF(second, trailer_cap_begin, SYSUTCDATETIME()) cap_lag_s
                              FROM {hvr_sch}.{is_tbl};""")
            if rr:
                tcb, lie, now_utc, cap_lag = rr[0]
                emit(f"  capture watermark (UTC) trailer_cap_begin = {tcb}")
                emit(f"  last_integ_end (UTC)                       = {lie}")
                emit(f"  now (UTC)                                  = {now_utc}")
                emit(f"  >>> HVR CAPTURE LATENCY = {cap_lag}s  ({fmt(cap_lag)})")
                r["cap_lag_s"] = cap_lag; r["cap_watermark"] = str(tcb)
            cn.close()
            if ic_tbl:
                cn = connect(server, hvr_db)
                _, rr = q(cn, f"SELECT integ_blocked, hvr_tx_countdown FROM {hvr_sch}.{ic_tbl};")
                if rr:
                    ib = rr[0][0]
                    r["integ_blocked"] = ib
                    emit(f"  integ_blocked={ib} hvr_tx_countdown={rr[0][1]}"
                         + ("   <-- ALERT: HVR BLOCKED" if ib else ""))
                cn.close()
        except Exception as e:
            emit(f"[FAIL] HVR read: {type(e).__name__}: {str(e)[:160]}"); _fails.append(alias + ":hvr")
    else:
        emit("  [WARN] no HVR integrate-state table found (hvr_is* in *_RTDS/_simp)")

    # Latest transaction
    try:
        cn = connect(server, wms_db)
        sch, tbl, col, engine = detect_txn(cn)
        if engine != "UNKNOWN":
            r["engine"] = engine
        if sch:
            emit(f"  txn source: {sch}.{tbl}.{col}  (engine={engine})")
            _, rr = q(cn, f"""SELECT MAX({col}) mx,
                                     DATEADD(hour,{offset_h},SYSUTCDATETIME()) now_local,
                                     DATEDIFF(second, MAX({col}), DATEADD(hour,{offset_h},SYSUTCDATETIME())) data_lag_s
                              FROM {sch}.{tbl};""")
            mx, now_local, dlag = rr[0]
            emit(f"  MAX({col}) (site-local) = {mx}")
            emit(f"  now (site-local)        = {now_local}")
            emit(f"  >>> DATA LATENCY = {dlag}s  ({fmt(dlag)})")
            r["data_lag_s"] = dlag; r["max_trndte"] = str(mx)
        else:
            emit("  [WARN] no dlytrn/SYSTRN transaction source found")
        cn.close()
    except Exception as e:
        emit(f"[FAIL] txn read: {type(e).__name__}: {str(e)[:160]}"); _fails.append(alias + ":txn")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="*", help="site aliases (see SITES) or empty for default set")
    ap.add_argument("--server", help="explicit server host short (e.g. <replica-server>)")
    ap.add_argument("--db", help="explicit WMS database")
    ap.add_argument("--offset", type=int, help="site-local UTC offset hours")
    args = ap.parse_args()

    hb = threading.Thread(target=heartbeat, daemon=True); hb.start()
    emit(f"DATA REPLICA LATENCY — run_utc={dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}")
    _db.get_access_token()

    targets = []
    if args.server and args.db:
        targets.append(("CUSTOM", args.server, args.db, args.offset or 0, "auto"))
    for s in (args.sites or ([] if targets else DEFAULT_SET)):
        key = s.upper()
        if key in SITES:
            host, db, off, hint = SITES[key]
            targets.append((key, host, db, off, hint))
        else:
            emit(f"[WARN] unknown site '{s}' — pass --server/--db/--offset for ad-hoc sites")

    results = []
    for alias, host, db, off, hint in targets:
        try:
            results.append(probe(alias, host, db, off, hint))
        except Exception as e:
            emit(f"[FAIL] {alias}: {type(e).__name__}: {str(e)[:180]}")
            emit(traceback.format_exc()); _fails.append(alias)
    _stop.set()

    # CSV
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site", "engine", "server", "wms_db", "hvr_db",
                                          "cap_lag_s", "data_lag_s", "integ_blocked",
                                          "cap_watermark", "max_trndte", "status"])
        w.writeheader(); w.writerows(results)

    emit("\n" + "#" * 100)
    emit("SUMMARY — HVR capture latency vs data latency")
    emit("#" * 100)
    emit(f"{'SITE':<12}{'ENGINE':<8}{'HVR cap lat':>14}{'data latency':>16}{'blocked':>9}")
    for r in results:
        emit(f"{r['site']:<12}{str(r['engine']):<8}{fmt(r['cap_lag_s']):>14}"
             f"{fmt(r['data_lag_s']):>16}{str(r.get('integ_blocked','?')):>9}")
    emit(f"\nfails: {_fails if _fails else 'none'}")
    emit(f"txt: {OUT_TXT}\ncsv: {OUT_CSV}")


if __name__ == "__main__":
    main()
