"""Export the Config Drift governance graph from Neo4j into the kit's node/edge JSON, ready for its own Cosmos graph.

    set NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD   (Neo4j Desktop DBMS holding the config-drift graph must be running)
    python export_config_drift.py                 -> relationships/config_drift/nodes.json, edges.json
    python load_cosmos.py --graph config_drift --dir relationships/config_drift

Only the config-drift labels are exported; the older RTCIS->PrIME labels that share that Neo4j database (RTCISTable, PrIMETable,
RTCISColumn, PrIMEColumn, RTCISValue, PrIMEValue, Learning, KBRule ...) are skipped - that knowledge now lives, catalog-validated,
in the rtcis_prime graph. Cross-graph links are kept as shared keys only (Site code, PrIME table/column name), never as edges.

Validation gate (same rule as rtcis_prime): a node is exported only if it carries `validated` / `replica_checked` = true OR it
is governance metadata (CFG, CRFC, Section, Field, Site ...).
STATUS 2026-11-21: config-drift-governance/backend/validate_against_replica.py checks only the Policy Maintenance section
(against POLDAT_VIEW) and writes a report; it does not yet set that property on the graph. Until it does, deviation nodes
(DevIdentity, Exception, FullConfig) are held back by this gate - extend the validator to tag the nodes it confirmed first.
"""
import json
import os
import re
import sys

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(KIT, "relationships", "config_drift")
SKIP = {"RTCISTable", "PrIMETable", "RTCISColumn", "PrIMEColumn", "RTCISValue", "PrIMEValue", "Learning", "KBRule", "Column"}
GOVERNANCE = {"CFG", "CRFC", "CrfcReg", "Section", "Field", "Site", "PcdSite", "ReplicaSite", "Snapshot", "Change", "Role", "Stage",
              "Severity", "Trigger", "Gate", "Decision", "ConfigGov", "QueryDomain", "MigrationCategory", "Deployment", "Output", "Tool"}


def key_of(label, props, eid):
    for k in ("key", "id", "name", "code", "cfg_id", "crfc_id", "site"):
        if props.get(k) not in (None, ""):
            return re.sub(r"[/\\?#\s]+", "_", f"cd:{label}:{props[k]}")[:250]
    return f"cd:{label}:{eid}"


def main():
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise SystemExit("pip install neo4j")
    drv = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                               auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]))
    nodes, ids, skipped = [], {}, 0
    with drv.session() as s:
        for rec in s.run("MATCH (n) RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS p"):
            label = next((x for x in rec["labels"] if x not in SKIP), None)
            p = dict(rec["p"])
            if not label or (label not in GOVERNANCE and not (p.get("validated") or p.get("replica_checked"))):
                skipped += 1
                continue
            vid = key_of(label, p, rec["eid"])
            ids[rec["eid"]] = vid
            nodes.append({"id": vid, "label": label, **{k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in p.items()}})
        edges = []
        for rec in s.run("MATCH (a)-[r]->(b) RETURN elementId(a) AS a, type(r) AS t, elementId(b) AS b, properties(r) AS p"):
            if rec["a"] in ids and rec["b"] in ids:
                edges.append({"id": f"cd:{len(edges)}", "label": rec["t"], "src": ids[rec["a"]], "dst": ids[rec["b"]],
                              **{k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in dict(rec["p"]).items()}})
    drv.close()
    os.makedirs(OUT, exist_ok=True)
    json.dump(nodes, open(os.path.join(OUT, "nodes.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(edges, open(os.path.join(OUT, "edges.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"exported {len(nodes)} nodes, {len(edges)} edges; skipped {skipped} (other graph's labels or not replica-validated)")


if __name__ == "__main__":
    sys.exit(main())


