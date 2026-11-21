"""
build_graph.py -- ONE sustainable command to (re)build the Config-Drift knowledge
graph, capture change over time, surface the deviations-not-captured-as-exception
gap, and verify every headline number against a real Cypher path.

WHY
---
The graph is assembled from several sources (deviation audit CSV, CFG-RFC register,
config catalogue).  Run ad hoc, they drift out of sync and there is no record of
what changed between runs.  This orchestrator makes the build:

  * REPEATABLE  - one entrypoint, fixed stage order, idempotent loads
  * GROUNDED    - each run records provenance (source file, sha1, rows, mtime)
                  as a (:Snapshot) node; every metric is traced to a Cypher path
  * CHANGE-AWARE- diffs this run's snapshot against the previous (:Snapshot) so you
                  see new/removed sites, deviation deltas, and gap movement
  * SUSTAINABLE - adding a site = drop its rows in the CSV and re-run; the snapshot
                  timeline and gap report update automatically

STAGES
------
  1. register    -> crfc_register.py    (:CRFC/:CrfcReg/:Site/:ReplicaSite)
  2. deviations  -> load_deviation_graph.py (:PcdSite/:DevIdentity/:CFG + HAS_DEVIATION/GOVERNED_BY)
  3. link        -> REGISTERED_AS (CFG->CrfcReg) + EXCEPTION_AT (CrfcReg->PcdSite, reflected flag)
  4. snapshot    -> compute metrics via Cypher, write (:Snapshot) node + JSON, link PREV_SNAPSHOT
  5. diff        -> compare to previous snapshot, print + persist change log
  6. verify      -> assert grounded graph paths resolve (fail loudly otherwise)

USAGE
  set NEO4J_USER / NEO4J_PASSWORD, then:
    python build_graph.py                 # full rebuild + snapshot + diff + verify
    python build_graph.py --refresh-csv   # first regenerate all_sites_deviations.csv from data.xlsx
    python build_graph.py --skip-loads    # only re-link + snapshot (graph already loaded)
    python build_graph.py --no-verify     # skip the assertion stage

Rules: timestamped heartbeat logs; no silent failure (log type+message, then raise);
Neo4j connection timeout; snapshots use a FIXED on-disk folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from neo4j import GraphDatabase

HERE = os.path.dirname(os.path.abspath(__file__))
from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
PY = sys.executable
SNAP_DIR = os.path.join(HERE, "_snapshots")
DEV_CSV = os.path.join(ONEDRIVE, "Config report", "all_sites_deviations.csv")
CRFC_CSV = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
XLSX = os.path.join(ONEDRIVE, "Config report", "data.xlsx")

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER")
PWD = os.environ.get("NEO4J_PASSWORD")


def log(m: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def sha1_of(path: str) -> dict:
    """Provenance fingerprint for a source file (grounding)."""
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    st = os.stat(path)
    return {
        "path": path, "exists": True, "sha1": h.hexdigest(),
        "bytes": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


def run_script(script: str, *script_args: str) -> None:
    """Run a pipeline script with the venv python; raise loudly on failure."""
    cmd = [PY, os.path.join(HERE, script), *script_args]
    log(f"STAGE -> {script} {' '.join(script_args)}")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    for line in (proc.stdout or "").splitlines():
        print("   " + line, flush=True)
    if proc.returncode != 0:
        log(f"FATAL {script} exited {proc.returncode}")
        for line in (proc.stderr or "").splitlines()[-30:]:
            print("   ! " + line, flush=True)
        raise RuntimeError(f"{script} failed with exit code {proc.returncode}")
    log(f"   {script} ok in {time.time() - t0:.1f}s")


# --------------------------------------------------------------------------
# Metrics: every number below is produced by a real Cypher path (grounding).
# --------------------------------------------------------------------------
METRIC_QUERIES = {
    "pcdSites":
        "MATCH (p:PcdSite) WHERE NOT p.name STARTS WITH 'Applied filters' RETURN count(p) AS v",
    "devIdentities":
        "MATCH (d:DevIdentity) RETURN count(d) AS v",
    "hasDeviation":
        "MATCH (:PcdSite)-[h:HAS_DEVIATION]->(:DevIdentity) RETURN count(h) AS v",
    "acceptedEdges":
        "MATCH (:PcdSite)-[h:HAS_DEVIATION {bucket:'accepted'}]->(:DevIdentity) RETURN count(h) AS v",
    "openEdges":
        "MATCH (:PcdSite)-[h:HAS_DEVIATION {bucket:'open'}]->(:DevIdentity) RETURN count(h) AS v",
    "crfcs":
        "MATCH (r:CrfcReg:CRFC) RETURN count(r) AS v",
    "registeredAs":
        "MATCH (:CFG)-[e:REGISTERED_AS]->(:CrfcReg) RETURN count(e) AS v",
    "exceptionAt":
        "MATCH (:CrfcReg)-[e:EXCEPTION_AT]->(:PcdSite) RETURN count(e) AS v",
    "exceptionAtReflected":
        "MATCH (:CrfcReg)-[e:EXCEPTION_AT {reflected:true}]->(:PcdSite) RETURN count(e) AS v",
    "governedBy":
        "MATCH (:DevIdentity)-[e:GOVERNED_BY]->(:CFG) RETURN count(e) AS v",
    # exception CRFCs linked to a site but NOT reflected as an accepted deviation
    "gapNotReflected":
        "MATCH (r:CrfcReg)-[e:EXCEPTION_AT]->(:PcdSite) "
        "WHERE r.decisionClass IN ['SITE_EXCEPTION','TEMP_EXCEPTION','ALLOWED_DEVIATION'] "
        "WITH r, max(CASE WHEN e.reflected THEN 1 ELSE 0 END) AS anyRef "
        "WITH sum(1 - anyRef) AS notReflected RETURN notReflected AS v",
    # cross-site inconsistency: same identity accepted somewhere, open elsewhere
    "crossSiteIdentities":
        "MATCH (:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d:DevIdentity) "
        "MATCH (:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d) "
        "WITH DISTINCT d RETURN count(d) AS v",
    # open deviations at a site that have NO governing CFG at all (ungoverned drift)
    "ungovernedOpenIdentities":
        "MATCH (:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d:DevIdentity) "
        "WHERE NOT (d)-[:GOVERNED_BY]->(:CFG) "
        "WITH DISTINCT d RETURN count(d) AS v",
}


def compute_metrics(session) -> dict:
    out = {}
    for name, q in METRIC_QUERIES.items():
        out[name] = session.run(q).single()["v"]
    return out


def load_prev_snapshot() -> dict | None:
    latest = os.path.join(SNAP_DIR, "latest.json")
    if os.path.exists(latest):
        with open(latest, encoding="utf-8") as f:
            return json.load(f)
    return None


def write_snapshot(session, snap: dict) -> None:
    os.makedirs(SNAP_DIR, exist_ok=True)
    stamp = snap["runId"]
    with open(os.path.join(SNAP_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    with open(os.path.join(SNAP_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)

    # persist a (:Snapshot) node + PREV_SNAPSHOT timeline edge (grounded change history)
    props = {"runId": snap["runId"], "at": snap["at"], **snap["metrics"]}
    props["sources"] = json.dumps(snap["sources"], ensure_ascii=False)
    session.run(
        "MERGE (s:Snapshot {runId: $runId}) SET s += $props",
        runId=snap["runId"], props=props,
    )
    if snap.get("prevRunId"):
        session.run(
            "MATCH (s:Snapshot {runId:$cur}) MATCH (p:Snapshot {runId:$prev}) "
            "MERGE (s)-[:PREV_SNAPSHOT]->(p)",
            cur=snap["runId"], prev=snap["prevRunId"],
        )


def diff_metrics(prev: dict | None, cur: dict) -> dict:
    if not prev:
        return {k: {"prev": None, "now": v, "delta": None} for k, v in cur.items()}
    pm = prev.get("metrics", {})
    return {
        k: {"prev": pm.get(k), "now": v,
            "delta": (v - pm[k]) if isinstance(pm.get(k), int) else None}
        for k, v in cur.items()
    }


def diff_sites(session, prev: dict | None) -> dict:
    """New / removed audited sites vs the previous run (grounded from the graph)."""
    now = {r["n"] for r in session.run(
        "MATCH (p:PcdSite) WHERE NOT p.name STARTS WITH 'Applied filters' RETURN p.name AS n")}
    before = set((prev or {}).get("sites", []))
    return {
        "count": len(now),
        "added": sorted(now - before),
        "removed": sorted(before - now),
        "all": sorted(now),
    }


# grounded verification: each headline must resolve through the intended path
VERIFY = [
    ("REGISTERED_AS reaches the register",
     "MATCH (:CFG)-[:REGISTERED_AS]->(:CrfcReg) RETURN count(*) > 0 AS ok"),
    ("EXCEPTION_AT reaches an audited site",
     "MATCH (:CrfcReg)-[:EXCEPTION_AT]->(:PcdSite) RETURN count(*) > 0 AS ok"),
    ("CFG1531 full path register->CFG->DevIdentity->accepting site",
     "MATCH (r:CrfcReg {label:'CFG1531'})<-[:REGISTERED_AS]-(:CFG)<-[:GOVERNED_BY]-"
     "(d:DevIdentity)<-[:HAS_DEVIATION {bucket:'accepted'}]-(:PcdSite) "
     "RETURN count(d) > 0 AS ok"),
    ("cross-site inconsistency path resolves",
     "MATCH (:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d:DevIdentity) "
     "MATCH (:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d) RETURN count(d) > 0 AS ok"),
]


def verify(session) -> bool:
    log("STAGE -> verify grounded graph paths")
    ok_all = True
    for name, q in VERIFY:
        ok = session.run(q).single()["ok"]
        log(f"   [{'PASS' if ok else 'FAIL'}] {name}")
        ok_all = ok_all and ok
    if not ok_all:
        raise RuntimeError("grounded-path verification FAILED — graph is not trustworthy")
    return ok_all


def main() -> int:
    ap = argparse.ArgumentParser(description="Sustainable Config-Drift graph build + change capture")
    ap.add_argument("--refresh-csv", action="store_true",
                    help="regenerate all_sites_deviations.csv from data.xlsx first")
    ap.add_argument("--skip-loads", action="store_true",
                    help="skip register/deviation loads; only re-link + snapshot")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    if not USER or not PWD:
        log("ERROR: set NEO4J_USER and NEO4J_PASSWORD")
        return 2

    t0 = time.time()
    runId = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log(f"=== build_graph run {runId} ===")

    # provenance up front (grounding)
    sources = {
        "deviations": sha1_of(DEV_CSV),
        "register": sha1_of(CRFC_CSV),
        "xlsx": sha1_of(XLSX),
    }
    for k, v in sources.items():
        log(f"source[{k}] exists={v['exists']} "
            f"sha1={v.get('sha1', '-')[:12]} rows/bytes={v.get('bytes', 0)}")

    # 0. optional refresh of the deviation CSV from the master xlsx
    if args.refresh_csv:
        run_script("xlsx_to_deviations_csv.py")
        sources["deviations"] = sha1_of(DEV_CSV)

    # 1 + 2. heavy loads (idempotent, each clears its own layer)
    if not args.skip_loads:
        run_script("crfc_register.py", "--csv", CRFC_CSV, "--build", "--neo4j")
        run_script("load_deviation_graph.py", DEV_CSV)

    # 3-6. link + snapshot + diff + verify — one session
    log(f"Neo4j: connecting {URI} as {USER}")
    drv = GraphDatabase.driver(URI, auth=(USER, PWD), connection_timeout=15)
    try:
        drv.verify_connectivity()
        import link_crfc_sites as lk
        with drv.session() as s:
            # 3. link
            log("STAGE -> link REGISTERED_AS + EXCEPTION_AT")
            n_reg = lk.bridge_registered_as(s)
            log(f"   REGISTERED_AS edges: {n_reg}")
            link_rows, crfcs = lk.link_exception_at(s)
            gap = lk.gap_analysis(link_rows, crfcs, write_csv=True)

            # 4. snapshot (metrics via grounded Cypher)
            log("STAGE -> snapshot")
            metrics = compute_metrics(s)
            metrics.update({f"gap_{k}": v for k, v in gap.items()})
            prev = load_prev_snapshot()
            site_info = diff_sites(s, prev)
            snap = {
                "runId": runId,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "prevRunId": (prev or {}).get("runId"),
                "sources": sources,
                "metrics": metrics,
                "sites": site_info["all"],
            }
            write_snapshot(s, snap)
            log(f"   snapshot {runId} written ({len(metrics)} metrics)")

            # 5. diff / change capture
            log("STAGE -> diff vs previous snapshot")
            md = diff_metrics(prev, metrics)
            print("   metric                       prev      now     delta", flush=True)
            for k in sorted(md):
                d = md[k]
                delta = "" if d["delta"] in (None, 0) else f"{d['delta']:+d}"
                prevv = "-" if d["prev"] is None else str(d["prev"])
                print(f"   {k:26s} {prevv:>8} {str(d['now']):>8}   {delta}", flush=True)
            if prev is None:
                log("   (baseline run — no previous snapshot to compare)")
            else:
                if site_info["added"]:
                    log(f"   + sites added: {', '.join(site_info['added'])}")
                if site_info["removed"]:
                    log(f"   - sites removed: {', '.join(site_info['removed'])}")
                if not site_info["added"] and not site_info["removed"]:
                    log("   site set unchanged")
            # persist change log next to snapshots
            with open(os.path.join(SNAP_DIR, f"{runId}_diff.json"), "w", encoding="utf-8") as f:
                json.dump({"runId": runId, "prevRunId": snap["prevRunId"],
                           "metricDiff": md, "sites": site_info}, f, indent=2, ensure_ascii=False)

            # 6. verify grounded paths
            if not args.no_verify:
                verify(s)
    except Exception as exc:
        log(f"FATAL {type(exc).__name__}: {exc}")
        raise
    finally:
        drv.close()

    log(f"=== done in {time.time() - t0:.1f}s ===")
    log("Snapshots: _snapshots/  |  Gap CSV: _replica_drift/crfc_not_registered_as_exception.csv")
    log("Timeline in graph: MATCH (s:Snapshot)-[:PREV_SNAPSHOT*0..]->(p) RETURN s,p")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
