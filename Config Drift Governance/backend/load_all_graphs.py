"""
Load BOTH knowledge graphs into the running Neo4j Desktop DBMS:

  1. WHS / RTCIS -> PrIME graph  (from neo4j_rtcis_prime_loader.py)
       labels: RTCISTable, PrIMETable, RTCISColumn, PrIMEColumn, RTCISValue,
               PrIMEValue, Learning, KBRule, Query, ...
  2. Config catalogue 2022 graph (from _catalogue_graph/graph.json)
       labels: Version, Section, Column, Exception

The two graphs use disjoint labels, so they coexist in one database.

Connection: bolt://localhost:7687   user/pass from env NEO4J_USER / NEO4J_PASSWORD
Usage:
    set NEO4J_USER / NEO4J_PASSWORD, then:
    python load_all_graphs.py            # wipe once, load WHS, load config
    python load_all_graphs.py --config-only
    python load_all_graphs.py --whs-only
    python load_all_graphs.py --no-wipe  # keep existing nodes, MERGE both

Follows the no-silent-failure rule: timestamped heartbeat logs, explicit
errors, connection timeout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

from neo4j import GraphDatabase

# --- paths -------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_GRAPH_JSON = os.path.join(HERE, "_catalogue_graph", "graph.json")

# The WHS loader lives in the OneDrive copy of SQL_Translations. Add it to path
# so we can reuse its verified table/column/value/learning definitions.
WHS_LOADER_DIR = os.environ.get(
    "WHS_LOADER_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SQL_Translations"),
)
if WHS_LOADER_DIR not in sys.path:
    sys.path.insert(0, WHS_LOADER_DIR)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --- config catalogue graph loader ------------------------------------------
def load_config_graph(session) -> None:
    if not os.path.exists(CONFIG_GRAPH_JSON):
        raise FileNotFoundError(f"Config graph.json not found: {CONFIG_GRAPH_JSON}")

    log(f"Reading config graph: {CONFIG_GRAPH_JSON}")
    with open(CONFIG_GRAPH_JSON, "r", encoding="utf-8") as fh:
        g = json.load(fh)

    nodes = g["nodes"]
    edges = g["edges"]
    log(f"Config graph: {len(nodes)} nodes, {len(edges)} edges")

    # constraints (id uniqueness per label)
    for label in ("Version", "Section", "Column", "Exception"):
        session.run(
            f"CREATE CONSTRAINT cfg_{label.lower()}_id IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
        )

    # group nodes by type so each batch is a single label
    by_type: dict[str, list[dict]] = {}
    for n in nodes:
        by_type.setdefault(n["type"], []).append(n)

    for ntype, rows in by_type.items():
        # flatten non-scalar props (dict/list) to JSON strings so Neo4j accepts them
        clean = []
        for r in rows:
            props = {}
            for k, v in r.items():
                if k == "type":
                    continue
                if isinstance(v, (dict, list)):
                    props[k] = json.dumps(v, ensure_ascii=False)
                else:
                    props[k] = v
            clean.append(props)
        session.run(
            f"UNWIND $rows AS row MERGE (n:{ntype} {{id: row.id}}) SET n += row",
            rows=clean,
        )
        log(f"  loaded {len(clean)} :{ntype} nodes")

    # relationships grouped by rel type (labels come from id-based match)
    by_rel: dict[str, list[dict]] = {}
    for e in edges:
        by_rel.setdefault(e["rel"], []).append({"src": e["src"], "dst": e["dst"]})

    for rel, rows in by_rel.items():
        session.run(
            f"UNWIND $rows AS row "
            f"MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
            f"MERGE (a)-[:{rel}]->(b)",
            rows=rows,
        )
        log(f"  loaded {len(rows)} [:{rel}] edges")


# --- WHS graph loader (reuse existing functions) ----------------------------
def load_whs_graph(session) -> None:
    import neo4j_rtcis_prime_loader as whs

    log("Loading WHS/RTCIS->PrIME graph (reusing neo4j_rtcis_prime_loader)")
    steps = [
        ("constraints", whs.create_constraints),
        ("table mappings", whs.load_tables),
        ("column mappings", whs.load_columns),
        ("value remappings", whs.load_value_remappings),
        ("queries", whs.load_queries),
        ("KB rules", whs.load_kb_rules),
        ("learnings", whs.load_learnings),
        ("site-schema evidence", whs.load_site_schema_evidence),
        ("view lineage", whs.load_view_lineage),
        ("query corpus", whs.load_query_corpus),
    ]
    for name, fn in steps:
        session.execute_write(fn)
        log(f"  WHS: {name} done")


def summary(session) -> None:
    log("=== Node labels ===")
    for r in session.run(
        "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"
    ):
        print(f"    {r['l']}: {r['c']}")
    log("=== Relationship types ===")
    for r in session.run(
        "MATCH ()-[x]->() RETURN type(x) AS t, count(x) AS c ORDER BY c DESC"
    ):
        print(f"    {r['t']}: {r['c']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Load WHS + config graphs into Neo4j")
    ap.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    ap.add_argument("--config-only", action="store_true")
    ap.add_argument("--whs-only", action="store_true")
    ap.add_argument("--no-wipe", action="store_true", help="do not DETACH DELETE first")
    args = ap.parse_args()

    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not user or not password:
        log("ERROR: set NEO4J_USER and NEO4J_PASSWORD environment variables")
        return 2

    t0 = time.time()
    log(f"Connecting to {args.uri} as {user} ...")
    driver = GraphDatabase.driver(args.uri, auth=(user, password), connection_timeout=10)
    try:
        driver.verify_connectivity()
        log("Connected.")
        with driver.session() as session:
            if not args.no_wipe:
                log("Wiping existing graph (MATCH (n) DETACH DELETE n) ...")
                session.run("MATCH (n) DETACH DELETE n")

            if not args.config_only:
                load_whs_graph(session)
            if not args.whs_only:
                load_config_graph(session)

            summary(session)
    except Exception as exc:  # no silent failure
        log(f"FATAL {type(exc).__name__}: {exc}")
        raise
    finally:
        driver.close()

    log(f"Done in {time.time() - t0:.1f}s")
    log("Neo4j Browser: http://localhost:7474")
    log("Try: MATCH (s:Section)-[:HAS_KEY]->(c:Column) RETURN s,c LIMIT 50")
    log("Try: MATCH (r:RTCISTable)-[:MAPS_TO]->(p:PrIMETable) RETURN r,p")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
