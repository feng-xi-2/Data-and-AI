"""replica_drift — compute PrIME Config Drift from the LIVE replica databases (2014 + 2022).

WHY THIS EXISTS
---------------
The Config Drift results used to be read from a Power BI Excel export
("Config report/data.xlsx"). This module instead computes the SAME deviations directly
from each site's live Azure SQL replica, so the knowledge graph / dashboard shows genuine
current data. Power BI is now used ONLY as an accuracy benchmark (see --compare-pbi).

DRIFT MODEL (grounded in PrIME Config Drift: an AUDITED instance vs a REFERENCE instance)
----------------------------------------------------------------------------------------
  * migration mode  : reference = the site's 2014 archive (archwms.POLDAT, raw, SRC03 filter)
                      audited   = the site's 2022 target  (prodwms.POLDAT_VIEW)
                      -> the real 2014->2022 pair (e.g. Crailsheim). "What drifted in/after
                      the migration."
  * standard  mode  : reference = a golden reference SITE's prodwms.POLDAT_VIEW
                      audited   = the target site's       prodwms.POLDAT_VIEW
                      -> "does this site meet the standard set by the reference site."

Deviation semantics (A = Audited, R = Reference), matching the Power BI model:
  * key in R but not in A          -> "Missing record"                (R value set, A value "")
  * key in A but not in R          -> "Unexpected record"             (A value set, R value "")
  * key in both, valuedata differs -> "Unexpected mismatching value"  (both values)

SECTION COVERAGE
----------------
Today = "Policy Maintenance" — the ONE section the replicas expose as data (POLDAT_VIEW /
POLDAT). Area / Job / other sections are not exposed by the replica schema, so they cannot be
drift-checked from live data yet. The SECTIONS registry below is the single extension point:
add a section by giving it a fetch(conn) -> triples(tablename, keys, valuedata) function.

OUTPUT — the FULL Power BI field schema per deviation
-----------------------------------------------------
  Audited Instance, Reference Instance, A value, R value, Category, Comparison Type,
  Configuration Element, Configuration Element Attribute ID, Configuration Element Attribute
  Name (GUI), Configuration Level, Configuration Section, Deviation Comments, Deviation Notes,
  Deviation Severity, Deviation Status, Deviation Type, First seen on, Last seen on,
  Rationale, Migration Notes   (+ convenience aliases the graph bridge consumes:
  "Audited Site", "Configuration Section", "Deviation Severity", "Deviation Type").

Severity + Rationale are enriched from the Standard Configuration Catalogue graph
(_catalogue_graph_full/graph_full.json): per-section severity_new / severity_missing, and
accepted Exceptions -> Deviation Severity "accepted" + Rationale.

Writes:
  _replica_drift/deviations.json           combined (consumed by graph_api.py drift endpoints)
  _replica_drift/deviations_<SITE>.json    per-site snapshot

USAGE
  python replica_drift.py --site CRAILSHEIM --mode migration
  python replica_drift.py --site NEMC --reference WCMC --mode standard
  python replica_drift.py --self-test                 # offline logic check, no DB/auth
  python replica_drift.py --site CRAILSHEIM --mode migration --compare-pbi   # accuracy vs PBI

Follows the workspace rules: timestamped heartbeat logging, no silent failures (errors are
logged with type+message then re-raised), timeouts + bounded retries on every remote call.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
CATALOGUE_JSON = os.path.join(BASE, "_catalogue_graph_full", "graph_full.json")

# The diamond package (db / sources / queries / poldat) lives in the Desktop copy of
# SQL_Translations. Add its parent to sys.path so `import diamond.*` resolves.
DIAMOND_PARENT = os.path.join(BASE, "..", "Diamond_Translation")
DIAMOND_PARENT = os.path.abspath(DIAMOND_PARENT)
if DIAMOND_PARENT not in sys.path:
    sys.path.insert(0, DIAMOND_PARENT)

# Remote-call resilience (per workspace rules).
DB_TIMEOUT = 60          # seconds per replica connect / query
FETCH_RETRIES = 3        # attempts before giving up on a replica read
BACKOFF_BASE = 2         # seconds; exponential 1,2,4...


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 1. Standard catalogue enrichment (severity + accepted exceptions)
# ---------------------------------------------------------------------------
def load_catalogue_standard(section: str = "Policy Maintenance") -> dict:
    """Read the Standard Configuration Catalogue graph for per-section severity + exceptions.

    Returns {version: {severity_new, severity_missing}} and a set of accepted-exception keys
    for the given section. Degrades to sane defaults (never a silent failure) if the catalogue
    file is missing.
    """
    std = {"severity": {}, "exceptions": {}, "loaded": False, "note": ""}
    if not os.path.exists(CATALOGUE_JSON):
        std["note"] = f"catalogue not found: {CATALOGUE_JSON} (using default severities)"
        log("standard: " + std["note"])
        return std
    try:
        with open(CATALOGUE_JSON, encoding="utf-8") as f:
            g = json.load(f)
        for n in g.get("nodes", []):
            if n.get("type") == "Section" and str(n.get("label", "")).strip().lower() == section.lower():
                ver = str(n.get("version", "")).strip()
                std["severity"][ver] = {
                    "new": str(n.get("severity_new") or "medium").strip().lower() or "medium",
                    "missing": str(n.get("severity_missing") or "medium").strip().lower() or "medium",
                    "new_records_allowed": str(n.get("new_records_allowed") or "").strip(),
                }
            if n.get("type") == "Exception" and str(n.get("screen", "")).strip().lower() == section.lower():
                entry = str(n.get("entry", "")).strip()
                if entry:
                    std["exceptions"][entry] = {
                        "deviation_type": str(n.get("deviation_type") or "").strip(),
                        "where_allowed": str(n.get("where_allowed") or "").strip(),
                        "rationale": str(n.get("rationale") or "CoE-approved exception").strip(),
                    }
        std["loaded"] = True
        log(f"standard: '{section}' severities={std['severity']} "
            f"accepted-exceptions={len(std['exceptions'])}")
    except Exception as e:
        std["note"] = f"catalogue parse failed: {type(e).__name__}: {e} (using defaults)"
        log("standard: " + std["note"])
    return std


def _severity_for(dev_type: str, version: str, std: dict) -> str:
    sev = std.get("severity", {}).get(version) or {}
    if dev_type == "Missing record":
        return sev.get("missing", "medium")
    return sev.get("new", "medium")  # Unexpected record / mismatching value


# ---------------------------------------------------------------------------
# 2. Section registry — how each config section is pulled as triples
# ---------------------------------------------------------------------------
def _fetch_poldat_triples(conn, *, schema: str, obj: str, read_mode: str, source_kind: str):
    """Pull Policy-Maintenance rows from a replica as (tablename, keys, valuedata) triples."""
    import diamond.sources as sources  # imported lazily so --self-test needs no pyodbc
    return sources.fetch_poldat_from_replica(
        conn, schema=schema, view=obj, table_label="poldat",
        source_kind=source_kind, log=log, read_mode=read_mode)


# section label -> how to read audited (2022) and reference (2014) sides.
SECTIONS = {
    "Policy Maintenance": {
        "audited": dict(schema="prodwms", obj="POLDAT_VIEW", read_mode="view", source_kind="target"),
        "reference_2014": dict(schema="archwms", obj="POLDAT", read_mode="raw", source_kind="source2014"),
        "reference_std": dict(schema="prodwms", obj="POLDAT_VIEW", read_mode="view", source_kind="target"),
        "fetch": _fetch_poldat_triples,
        "attribute_from_key": lambda key: (key.split("#", 1)[0] if key else ""),
    },
}


def _with_retry(what: str, fn):
    """Run a remote read with bounded exponential backoff. No silent failure."""
    import time
    last = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — log + retry, re-raise at the end
            last = e
            wait = BACKOFF_BASE ** (attempt - 1)
            log(f"{what}: attempt {attempt}/{FETCH_RETRIES} failed "
                f"({type(e).__name__}: {e}) — retrying in {wait}s")
            time.sleep(wait)
    log(f"{what}: all {FETCH_RETRIES} attempts failed — giving up")
    raise last


# ---------------------------------------------------------------------------
# 3. Core drift computation (pure — unit-testable offline)
# ---------------------------------------------------------------------------
def compute_deviations(audited_rows, reference_rows, *, section, audited_name,
                       reference_name, mode, audited_version, std):
    """Compare two triple lists and emit full-PBI-schema deviation dicts.

    audited_rows / reference_rows: iterables of (keys, valuedata) tuples (tablename dropped).
    """
    a = {}
    for key, val in audited_rows:
        a[key] = val
    r = {}
    for key, val in reference_rows:
        r[key] = val

    now = datetime.datetime.now().isoformat(timespec="seconds")
    attr_of = SECTIONS[section]["attribute_from_key"]
    exceptions = std.get("exceptions", {})
    devs = []

    def emit(key, dev_type, a_val, r_val):
        attr = attr_of(key)
        sev = _severity_for(dev_type, audited_version, std)
        rationale, notes, status = "", "", "ACTIVE"
        exc = exceptions.get(key) or exceptions.get(attr)
        if exc:
            sev, status = "accepted", "ACCEPTED"
            rationale = exc.get("rationale", "CoE-approved exception")
            notes = f"accepted where: {exc.get('where_allowed', '')}".strip()
        devs.append({
            "Audited Instance": audited_name,
            "Reference Instance": reference_name,
            "A value": a_val,
            "R value": r_val,
            "Category": "Configuration",
            "Comparison Type": mode,
            "Configuration Element": key,
            "Configuration Element Attribute ID": attr,
            "Configuration Element Attribute Name (GUI)": attr,
            "Configuration Level": "Warehouse" if "#" in key else "Global",
            "Configuration Section": section,
            "Deviation Comments": "",
            "Deviation Notes": notes,
            "Deviation Severity": sev,
            "Deviation Status": status,
            "Deviation Type": dev_type,
            "First seen on": now,
            "Last seen on": now,
            "Rationale": rationale,
            "Migration Notes": "2014->2022 migration drift" if mode == "migration" else "",
            # convenience aliases consumed by the graph bridge (graph_api._load_drift):
            "Audited Site": audited_name,
        })

    for key, r_val in r.items():
        if key not in a:
            emit(key, "Missing record", "", r_val)
    for key, a_val in a.items():
        if key not in r:
            emit(key, "Unexpected record", a_val, "")
        elif a_val != r[key]:
            emit(key, "Unexpected mismatching value", a_val, r[key])

    return devs


# ---------------------------------------------------------------------------
# 4. Live-replica orchestration
# ---------------------------------------------------------------------------
def _triples_iter(df):
    """Yield (keys, valuedata) from a diamond triple DataFrame."""
    for _, row in df.iterrows():
        yield str(row["keys"]), str(row["valuedata"])


def run_site(site: str, mode: str, reference: str | None, section: str, std: dict) -> dict:
    import diamond.db as db

    spec = SECTIONS[section]
    audited_version = "2022"
    log(f"=== drift: site={site} mode={mode} section='{section}' ===")

    # --- audited (2022) side ---
    a_cfg = spec["audited"]
    log(f"audited: connecting {site} ({a_cfg['schema']}.{a_cfg['obj']})")
    conn_a = _with_retry(f"connect {site}", lambda: db.connect(site, timeout=DB_TIMEOUT))
    audited_df = _with_retry(
        f"fetch audited {site}",
        lambda: spec["fetch"](conn_a, schema=a_cfg["schema"], obj=a_cfg["obj"],
                              read_mode=a_cfg["read_mode"], source_kind=a_cfg["source_kind"]))
    log(f"audited: {len(audited_df):,} rows")

    # --- reference side ---
    if mode == "migration":
        r_cfg = spec["reference_2014"]
        reference_name = f"{site} · 2014"
        # 2014 archive lives on the SAME replica server, under the archive schema.
        log(f"reference(2014): reading {r_cfg['schema']}.{r_cfg['obj']} on {site}")
        reference_df = _with_retry(
            f"fetch reference2014 {site}",
            lambda: spec["fetch"](conn_a, schema=r_cfg["schema"], obj=r_cfg["obj"],
                                  read_mode=r_cfg["read_mode"], source_kind=r_cfg["source_kind"]))
    elif mode == "standard":
        if not reference:
            raise ValueError("standard mode needs --reference <SITE>")
        r_cfg = spec["reference_std"]
        reference_name = reference
        log(f"reference(std): connecting {reference} ({r_cfg['schema']}.{r_cfg['obj']})")
        conn_r = _with_retry(f"connect {reference}", lambda: db.connect(reference, timeout=DB_TIMEOUT))
        reference_df = _with_retry(
            f"fetch reference {reference}",
            lambda: spec["fetch"](conn_r, schema=r_cfg["schema"], obj=r_cfg["obj"],
                                  read_mode=r_cfg["read_mode"], source_kind=r_cfg["source_kind"]))
    else:
        raise ValueError(f"unknown mode: {mode}")
    log(f"reference: {len(reference_df):,} rows")

    devs = compute_deviations(
        _triples_iter(audited_df), _triples_iter(reference_df),
        section=section, audited_name=site, reference_name=reference_name,
        mode=mode, audited_version=audited_version, std=std)
    log(f"drift: {len(devs):,} deviations "
        f"(missing={sum(d['Deviation Type']=='Missing record' for d in devs)}, "
        f"unexpected={sum(d['Deviation Type']=='Unexpected record' for d in devs)}, "
        f"mismatch={sum(d['Deviation Type']=='Unexpected mismatching value' for d in devs)}, "
        f"accepted={sum(d['Deviation Severity']=='accepted' for d in devs)})")
    return {"site": site, "mode": mode, "reference": reference_name,
            "section": section, "deviations": devs}


def write_output(results: list[dict], mode: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    all_rows = []
    for res in results:
        all_rows.extend(res["deviations"])
        per = os.path.join(OUT_DIR, f"deviations_{res['site']}.json")
        with open(per, "w", encoding="utf-8") as f:
            json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                       "source": "live-replica", "mode": res["mode"],
                       "site": res["site"], "reference": res["reference"],
                       "rows": res["deviations"]}, f, indent=2, ensure_ascii=False)
        log(f"wrote {per} ({len(res['deviations']):,} rows)")
    combined = os.path.join(OUT_DIR, "deviations.json")
    with open(combined, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "source": "live-replica", "mode": mode,
                   "sites": [r["site"] for r in results],
                   "meta": {"rows": len(all_rows), "sites": len(results),
                            "sections": sorted({r["section"] for r in results})},
                   "rows": all_rows}, f, indent=2, ensure_ascii=False)
    log(f"wrote {combined} (combined {len(all_rows):,} rows across {len(results)} site(s))")
    return combined


# ---------------------------------------------------------------------------
# 5. Accuracy benchmark vs the live Power BI model
# ---------------------------------------------------------------------------
def compare_pbi(results: list[dict]) -> None:
    """Compare replica-derived deviations against the live Power BI model (accuracy check).

    PBI is the benchmark only. Reports precision/recall of the replica result vs PBI per site,
    keyed on (Configuration Section, Configuration Element, Deviation Type).
    """
    try:
        import pbi_drift_alert as pbi
    except Exception as e:
        log(f"compare-pbi: cannot import pbi_drift_alert ({type(e).__name__}: {e})")
        raise
    for res in results:
        site = res["site"]
        log(f"compare-pbi: querying Power BI for audited instance ~ {site}")
        try:
            pbi_rows = pbi.query_pbi_for_site(site)  # returns list of dicts (see pbi_drift_alert)
        except Exception as e:
            log(f"compare-pbi: PBI query failed for {site}: {type(e).__name__}: {e}")
            raise
        def keyset(rows):
            return {(str(r.get("Configuration Section", "")).strip().lower(),
                     str(r.get("Configuration Element", "")).strip(),
                     str(r.get("Deviation Type", "")).strip().lower()) for r in rows}
        rep, ref = keyset(res["deviations"]), keyset(pbi_rows)
        inter = rep & ref
        precision = len(inter) / len(rep) if rep else 0.0
        recall = len(inter) / len(ref) if ref else 0.0
        log(f"compare-pbi[{site}]: replica={len(rep)} pbi={len(ref)} match={len(inter)} "
            f"precision={precision:.1%} recall={recall:.1%}")


# ---------------------------------------------------------------------------
# 6. Offline self-test (no DB, no auth) — verifies the drift LOGIC
# ---------------------------------------------------------------------------
def self_test() -> int:
    log("self-test: running offline drift-logic check")
    std = {"severity": {"2022": {"new": "high", "missing": "medium"}},
           "exceptions": {"POL-ACCEPTED#X#Y": {"rationale": "CoE variance", "where_allowed": "site A"}}}
    audited = [("POL-A#1#ON", "v=1"),          # same in both -> Match (no dev)
               ("POL-B#2#OFF", "v=9"),         # value differs -> mismatching value
               ("POL-EXTRA#3#ON", "v=3"),      # only in audited -> Unexpected record
               ("POL-ACCEPTED#X#Y", "v=7")]    # only in audited but accepted -> accepted
    reference = [("POL-A#1#ON", "v=1"),
                 ("POL-B#2#OFF", "v=5"),
                 ("POL-MISSING#4#ON", "v=4")]  # only in reference -> Missing record
    devs = compute_deviations(iter(audited), iter(reference), section="Policy Maintenance",
                              audited_name="TEST", reference_name="REF", mode="standard",
                              audited_version="2022", std=std)
    by = {}
    for d in devs:
        by[d["Deviation Type"]] = by.get(d["Deviation Type"], 0) + 1
    log(f"self-test: deviations by type = {by}")
    ok = True
    checks = [
        ("Missing record", 1), ("Unexpected record", 2), ("Unexpected mismatching value", 1),
    ]
    for t, n in checks:
        got = by.get(t, 0)
        status = "OK" if got == n else "FAIL"
        if got != n:
            ok = False
        log(f"  [{status}] {t}: expected {n}, got {got}")
    accepted = sum(d["Deviation Severity"] == "accepted" for d in devs)
    log(f"  [{'OK' if accepted == 1 else 'FAIL'}] accepted severity: expected 1, got {accepted}")
    if accepted != 1:
        ok = False
    mismatch = [d for d in devs if d["Deviation Type"] == "Unexpected mismatching value"][0]
    fields_ok = mismatch["A value"] == "v=9" and mismatch["R value"] == "v=5"
    log(f"  [{'OK' if fields_ok else 'FAIL'}] mismatch A/R values: A={mismatch['A value']} R={mismatch['R value']}")
    if not fields_ok:
        ok = False
    # verify the full PBI field set is present on every deviation
    required = ["Audited Instance", "Reference Instance", "A value", "R value", "Category",
                "Comparison Type", "Configuration Element", "Configuration Element Attribute ID",
                "Configuration Element Attribute Name (GUI)", "Configuration Level",
                "Configuration Section", "Deviation Comments", "Deviation Notes",
                "Deviation Severity", "Deviation Status", "Deviation Type", "First seen on",
                "Last seen on", "Rationale", "Migration Notes"]
    missing_fields = [f for f in required if any(f not in d for d in devs)]
    log(f"  [{'OK' if not missing_fields else 'FAIL'}] full PBI field schema present "
        f"({len(required)} fields){'' if not missing_fields else ' missing=' + str(missing_fields)}")
    if missing_fields:
        ok = False
    # write a demo output so the graph bridge can be exercised offline
    write_output([{"site": "SELFTEST", "mode": "standard", "reference": "REF",
                   "section": "Policy Maintenance", "deviations": devs}], "standard")
    log(f"self-test: {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", help="audited site code (see diamond.db.SITES)")
    ap.add_argument("--reference", help="reference site code (standard mode)")
    ap.add_argument("--mode", choices=["migration", "standard"], default="migration")
    ap.add_argument("--section", default="Policy Maintenance",
                    help=f"config section (available: {list(SECTIONS)})")
    ap.add_argument("--compare-pbi", action="store_true",
                    help="benchmark the replica result against the live Power BI model")
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline drift-logic self-test (no DB / no auth)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.site:
        ap.error("--site is required (or use --self-test)")
    if args.section not in SECTIONS:
        ap.error(f"unknown section '{args.section}'; available: {list(SECTIONS)}")

    std = load_catalogue_standard(args.section)
    try:
        results = [run_site(args.site, args.mode, args.reference, args.section, std)]
        write_output(results, args.mode)
        if args.compare_pbi:
            compare_pbi(results)
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        try:
            import diamond.db as db
            db.close_all()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
