"""load_deviation_graph — load the PCD deviations into Neo4j as a REAL, queryable graph.

Turns the flat all-sites deviation CSV into graph structure so the cross-site
"accepted here / open there" question is answered by an actual Cypher traversal, not a
Python CSV scan. Model:

    (:PcdSite {name})
    (:DevIdentity {id, section, element, attrId, attr, a, r, type})     -- site-independent
    (:CFG {code})                                                       -- reuse existing CFG nodes

    (:PcdSite)-[:HAS_DEVIATION {severity, bucket, count}]->(:DevIdentity)
        bucket = 'accepted' | 'open' | 'health' | 'other'
    (:DevIdentity)-[:GOVERNED_BY]->(:CFG)   -- when an accepted row cites a CFG code

The cross-site inconsistency is then:

    MATCH (acc:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d:DevIdentity)
    MATCH (opn:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d)
    WITH d, count(DISTINCT acc) AS nAcc, count(DISTINCT opn) AS nOpen
    WHERE nAcc >= 1 AND nOpen >= 1
    RETURN count(d)

Env: NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD.
Follows workspace rules: timestamped logs; no silent failure (log type+message then raise).
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import os
import re
import sys
from collections import defaultdict

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
DEFAULT_IN = os.path.join(ONEDRIVE, "Config report", "all_sites_deviations.csv")

OPEN_SEV = {"high", "medium", "low"}
_cfg_re = re.compile(r"\bCFG\d+\b", re.IGNORECASE)


def log(m: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def bucket_of(sev: str) -> str:
    s = (sev or "").strip().lower()
    if s == "accepted":
        return "accepted"
    if s in OPEN_SEV:
        return "open"
    if s.startswith("health"):
        return "health"
    return "other"


def identity_id(key: tuple) -> str:
    return "DEV_" + hashlib.md5("||".join(key).encode("utf-8")).hexdigest()[:16]


def main() -> int:
    inp = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN
    if not os.path.exists(inp):
        log(f"ERROR input not found: {inp}")
        raise SystemExit(2)

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user, pw = os.environ.get("NEO4J_USER"), os.environ.get("NEO4J_PASSWORD")
    if not user or not pw:
        log("ERROR set NEO4J_USER / NEO4J_PASSWORD")
        raise SystemExit(2)

    log(f"reading {inp}")
    identities: dict[str, dict] = {}
    # (site, id, bucket) -> {severity, count, cfg}
    edges: dict[tuple, dict] = {}
    sites: set[str] = set()
    n = 0
    try:
        with open(inp, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                site = (r.get("Audited Instance (A)") or "").strip()
                if not site:
                    continue
                sev = (r.get("Deviation Severity") or "").strip()
                key = (
                    (r.get("Configuration Section") or "").strip(),
                    (r.get("Configuration Element") or "").strip(),
                    (r.get("Configuration Element Attribute ID") or "").strip(),
                    (r.get("A value") or "").strip(),
                    (r.get("R value") or "").strip(),
                    (r.get("Deviation Type") or "").strip(),
                )
                did = identity_id(key)
                if did not in identities:
                    identities[did] = {
                        "id": did, "section": key[0], "element": key[1],
                        "attrId": key[2], "attr": (r.get("Configuration Element Attribute Name (GUI)") or "").strip(),
                        "a": key[3], "r": key[4], "type": key[5],
                    }
                bkt = bucket_of(sev)
                ek = (site, did, bkt)
                rec = edges.get(ek)
                if rec is None:
                    rec = edges[ek] = {"severity": sev.lower(), "count": 0, "cfg": ""}
                rec["count"] += 1
                if bkt == "accepted" and not rec["cfg"]:
                    m = _cfg_re.search(r.get("Rationale") or "")
                    if m:
                        rec["cfg"] = m.group(0).upper()
                sites.add(site)
                n += 1
                if n % 20000 == 0:
                    log(f"  parsed {n} rows…")
    except Exception as e:
        log(f"ERROR reading input: {type(e).__name__}: {e}")
        raise
    log(f"parsed {n} rows · {len(identities)} identities · {len(sites)} sites · {len(edges)} site-edges")

    from neo4j import GraphDatabase
    log(f"Neo4j: connecting {uri} as {user}")
    driver = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=10)
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            log("Neo4j: clearing previous PCD deviation layer")
            s.run("MATCH (n:DevIdentity) DETACH DELETE n")
            s.run("MATCH (n:PcdSite) DETACH DELETE n")
            s.run("CREATE CONSTRAINT devid IF NOT EXISTS FOR (n:DevIdentity) REQUIRE n.id IS UNIQUE")
            s.run("CREATE CONSTRAINT pcdsite IF NOT EXISTS FOR (n:PcdSite) REQUIRE n.name IS UNIQUE")

            # sites
            s.run("UNWIND $rows AS name MERGE (:PcdSite {name: name})",
                  rows=sorted(sites))
            log(f"  loaded {len(sites)} :PcdSite")

            # identities (batched)
            idrows = list(identities.values())
            for i in range(0, len(idrows), 2000):
                s.run("UNWIND $rows AS row MERGE (d:DevIdentity {id: row.id}) SET d += row",
                      rows=idrows[i:i + 2000])
            log(f"  loaded {len(idrows)} :DevIdentity")

            # edges (batched)
            erows = [{"site": k[0], "id": k[1], "bucket": k[2],
                      "severity": v["severity"], "count": v["count"], "cfg": v["cfg"]}
                     for k, v in edges.items()]
            for i in range(0, len(erows), 5000):
                s.run(
                    "UNWIND $rows AS row "
                    "MATCH (p:PcdSite {name: row.site}) "
                    "MATCH (d:DevIdentity {id: row.id}) "
                    "MERGE (p)-[h:HAS_DEVIATION {bucket: row.bucket}]->(d) "
                    "SET h.severity = row.severity, h.count = row.count, h.cfg = row.cfg",
                    rows=erows[i:i + 5000])
            log(f"  loaded {len(erows)} [:HAS_DEVIATION]")

            # link accepted identities to existing CFG nodes (create if missing)
            cfg_pairs = sorted({(k[1], v["cfg"]) for k, v in edges.items()
                                if k[2] == "accepted" and v["cfg"]})
            for i in range(0, len(cfg_pairs), 3000):
                s.run(
                    "UNWIND $rows AS row "
                    "MATCH (d:DevIdentity {id: row[0]}) "
                    "MERGE (c:CFG {code: row[1]}) "
                    "MERGE (d)-[:GOVERNED_BY]->(c)",
                    rows=[list(x) for x in cfg_pairs[i:i + 3000]])
            log(f"  linked {len(cfg_pairs)} [:GOVERNED_BY]->(:CFG)")

            # ---- verify: cross-site inconsistency via Cypher ----
            q = (
                "MATCH (acc:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d:DevIdentity) "
                "MATCH (opn:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d) "
                "WITH d, count(DISTINCT acc) AS nAcc, count(DISTINCT opn) AS nOpen "
                "WHERE nAcc >= 1 AND nOpen >= 1 "
                "RETURN count(d) AS identities, sum(nOpen) AS penalised"
            )
            rec = s.run(q).single()
            log("Neo4j: === cross-site inconsistency (via Cypher) ===")
            log(f"  inconsistent identities = {rec['identities']}")
            log(f"  penalised open findings = {rec['penalised']}")

            # CFG-backed subset
            q2 = (
                "MATCH (acc:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d:DevIdentity)-[:GOVERNED_BY]->(:CFG) "
                "MATCH (opn:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d) "
                "WITH d, count(DISTINCT acc) AS nAcc, count(DISTINCT opn) AS nOpen "
                "WHERE nAcc >= 1 AND nOpen >= 1 "
                "RETURN count(DISTINCT d) AS cfgBacked"
            )
            log(f"  CFG-backed inconsistent identities = {s.run(q2).single()['cfgBacked']}")

            # the MIXE / CFG1531 example, straight from the graph
            q3 = (
                "MATCH (d:DevIdentity {element:'MIXE', attrId:'lpncnt_area_lodlvl'}) "
                "WHERE d.a='N' "
                "OPTIONAL MATCH (acc:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d) "
                "OPTIONAL MATCH (opn:PcdSite)-[:HAS_DEVIATION {bucket:'open'}]->(d) "
                "OPTIONAL MATCH (d)-[:GOVERNED_BY]->(c:CFG) "
                "RETURN d.section AS section, d.attr AS attr, d.a AS a, d.r AS r, "
                "count(DISTINCT acc) AS nAcc, count(DISTINCT opn) AS nOpen, "
                "collect(DISTINCT c.code) AS cfg"
            )
            r3 = s.run(q3).single()
            if r3:
                log("Neo4j: === MIXE / LPN Count Area Level example (via Cypher) ===")
                log(f"  {r3['section']} · {r3['attr']} · A='{r3['a']}' R='{r3['r']}' "
                    f"| accepted@{r3['nAcc']} open@{r3['nOpen']} | CFG={r3['cfg']}")
    except Exception as e:
        log(f"ERROR Neo4j load: {type(e).__name__}: {e}")
        raise
    finally:
        driver.close()
    log("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
