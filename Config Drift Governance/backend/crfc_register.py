"""crfc_register — load the P&G Configuration RFC (CFG-RFC) register and make it usable by
(a) the knowledge graph (Neo4j) and (b) the deviation enricher's exception matching.

WHY
---
Every "accepted" Config-Drift deviation carries a CFGxxxx code. That code is a CFG-RFC — the
approved change/exception that justifies the deviation. Today the exceptions list is
hand-maintained; this module makes the CFG-RFC register itself the single source of truth:

  * as a GRAPH layer  : one :CRFC node per CFG code, linked to the CFG-RFC gate + its Site,
                        classified by Decision Status (new standard / allowed deviation /
                        temporary exception / site exception). Wipeable via :CrfcReg label.
  * as an EXCEPTIONS   : load_register() returns {CFGcode -> record} so enrich_deviations.py
                        can validate each accepted deviation against the authoritative
                        register (found? approved? withdrawn? -> exception_valid).

INPUT  : Configuration_RFC.csv (cp1252). Key = CFGxxxx parsed from the Title.
USAGE
  python crfc_register.py --csv "<Configuration_RFC.csv>" --build           # write JSON
  python crfc_register.py --csv "<...>" --build --neo4j                      # + load graph

Rules: timestamped logs; no silent failure (log type+message then raise); Neo4j has a
connection timeout; the :CrfcReg layer is cleared before reload so it stays idempotent.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import html
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
DEFAULT_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(BASE))),  # up to Desktop\M&M (OneDrive not guaranteed)
    "Config report", "Configuration_RFC.csv")

_CFG = re.compile(r"CFG\d+", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_NAMEID = re.compile(r"\s*<[^>]*>\s*$")  # trailing "<62326286.btmx>" on owner names

# Decision Status -> canonical exception class used by the enricher / graph
DECISION_CLASS = {
    "approved as a new standard": "NEW_STANDARD",
    "approved as an allowed deviation": "ALLOWED_DEVIATION",
    "approved as a new allowed deviation": "ALLOWED_DEVIATION",
    "exception temporarily approved as workaround": "TEMP_EXCEPTION",
    "exception approved for a site /region": "SITE_EXCEPTION",
    "exception approved for a site / region": "SITE_EXCEPTION",
    "pending": "PENDING",
    "": "UNSPECIFIED",
}

# Request Status values that mean the CFG-RFC is NO LONGER a valid justification
INVALID_STATUS = {"withdrawn", "superseded", "rejected", "disused"}

# --- CFG-RFC plant name  ->  replica / drift site code -----------------------
# The register's Site column carries full plant names (e.g. "NORTH EAST MIX
# CENTER"); the drift results, replica DB and PBI use short site codes (NEMC).
# This is NOT a 1:1 rename — a single register row can list several plants,
# semicolon-separated, so a CFG-RFC can map to MANY replica sites. We match by
# the most specific keyword first. Codes match SITE_TO_PBI in drift_accuracy.py
# and SITE_TO_REPLICA in validate_against_replica.py.
PLANT_TO_SITE = [
    # (keyword tested against the UPPER-cased plant string, replica site code)
    ("NORTH EAST MIX CENTER", "NEMC"),
    ("WEST COAST MIX CENTER", "WCMC"),
    ("WCMC", "WCMC"),
    ("DALLAS MIX CENTER", "DALLAS"),
    ("DAYTON MIX CENTER", "DAYTON"),
    ("GREATER CHICAGO FULFILLMENT CENTER", "GCFC"),
    ("GCFC", "GCFC"),
    ("SOUTH EAST FULFILMENT CENTER", "SEFC"),
    ("SEFC", "SEFC"),
    ("ALBANY PLANT", "ALBANY"),
    ("ANDOVER", "ANDOVER"),
    ("BRANTFORD", "BRANTFORD"),
    ("TABLER STATION PLANT", "TABLER"),
    ("LIMA PLANT", "LIMA"),
    ("BOX ELDER", "BOXELDER"),
    ("PHOENIX PLANT", "PHOENIX"),
    ("PHOENIX", "PHOENIX"),
    ("GREENSBORO", "GREENSBORO"),
    ("CRAILSHEIM", "CRAILSHEIM"),
    ("ATHENS", "ATHENS"),
    ("AMIENS BIG BOX", "AMIENS_BB"),
    ("AMIENS", "AMIENS"),
    ("XIQING", "XIQING"),
    ("HUANGPU", "HUANGPU"),
    ("LUOGANG", "LUOGANG"),
    ("TAICANG", "TAICANG"),
    ("MANDIDEEP", "MANDIDEEP"),
    ("JIJONA", "JIJONA"),
    ("CABUYAO", "CABUYAO"),
    ("LOUVEIRA", "LOUVEIRA"),
    ("POMEZIA", "POMEZIA"),
    ("URLATI", "URLATI"),
    ("MEHOOPANY", "MEHOOPANY"),
    ("ST LOUIS", "STLOUIS"),
    ("CAPE GIRARDEAU", "CAPEGIRARDEAU"),
]


def _replica_sites(plant: str) -> list[str]:
    """Map a register Site cell (may list several plants, ';'-separated) to the
    set of replica/drift site codes it covers. Returns [] when none match."""
    if not plant:
        return []
    out: list[str] = []
    for part in re.split(r"[;/]", plant):
        up = part.strip().upper()
        if not up:
            continue
        for kw, code in PLANT_TO_SITE:
            if kw in up:
                if code not in out:
                    out.append(code)
                break
    return out


def log(m: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def _clean(v) -> str:
    s = "" if v is None else str(v)
    s = _TAG.sub(" ", s)          # strip HTML tags from rich-text fields
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _decision_class(decision: str) -> str:
    return DECISION_CLASS.get(decision.strip().lower(), "OTHER")


def _better(a: dict, b: dict) -> dict:
    """When a CFG code appears twice, prefer the record that is a valid, decided one."""
    def score(r):
        s = 0
        if r["requestStatus"].lower() not in INVALID_STATUS:
            s += 2
        if r["decisionClass"] not in ("UNSPECIFIED", "OTHER", "PENDING"):
            s += 1
        if r["appliedTo"].lower() in ("prod", "test"):
            s += 1
        return s
    return a if score(a) >= score(b) else b


def load_register(path: str) -> dict:
    """Return {CFGcode: record}. Records are cleaned + classified. Deduped by preference."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"CFG-RFC register not found: {path}")
    log(f"reading CFG-RFC register: {path}")
    try:
        with open(path, encoding="cp1252", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log(f"ERROR reading register {type(e).__name__}: {e}")
        raise

    reg: dict[str, dict] = {}
    no_code = 0
    for r in rows:
        title = _clean(r.get("Title"))
        m = _CFG.search(title)
        if not m:
            no_code += 1
            continue
        code = m.group(0).upper()
        decision = _clean(r.get("Decision Status"))
        rec = {
            "code": code,
            "title": title,
            "site": _clean(r.get("Site")),
            "requestStatus": _clean(r.get("Request Status")),
            "decisionStatus": decision,
            "decisionClass": _decision_class(decision),
            "codeType": _clean(r.get("Code")),
            "urgency": _clean(r.get("Urgency")),
            "appliedTo": _clean(r.get("Already applied")),
            "relatedStdChangeId": _clean(r.get("Related Standard Configuration Change ID")),
            "owner": _NAMEID.sub("", _clean(r.get("DXC COE Owner"))),
            "closedDate": _clean(r.get("Closed Date")),
            "rfcDoc": _clean(r.get("RFC Document")),
        }
        rec["valid"] = rec["requestStatus"].lower() not in INVALID_STATUS
        rec["replicaSites"] = _replica_sites(rec["site"])
        if code in reg:
            reg[code] = _better(reg[code], rec)
        else:
            reg[code] = rec
    log(f"register: {len(reg)} unique CFG codes ({no_code} rows had no code)")
    return reg


# ---- graph -----------------------------------------------------------------
def _site_id(site: str) -> str:
    return "site:" + re.sub(r"[^a-z0-9]+", "-", site.lower()).strip("-")


def build_nodes(reg: dict) -> dict:
    nodes, edges = [], []
    sites: dict[str, int] = {}
    replica_hits: dict[str, int] = {}
    for code, r in reg.items():
        nid = f"crfc:{code}"
        nodes.append({"id": nid, "type": "CRFC", "label": code,
                      "title": r["title"], "site": r["site"],
                      "requestStatus": r["requestStatus"], "decisionStatus": r["decisionStatus"],
                      "decisionClass": r["decisionClass"], "codeType": r["codeType"],
                      "appliedTo": r["appliedTo"], "owner": r["owner"],
                      "valid": r["valid"], "relatedStdChangeId": r["relatedStdChangeId"],
                      "replicaSites": ",".join(r.get("replicaSites") or [])})
        # each CFG-RFC is raised through the CFG-RFC gate (base graph node id: gate_cfgrfc)
        edges.append({"src": nid, "dst": "gate_cfgrfc", "rel": "RAISED_AS"})
        # link to the site that requested it (skip blank / GLOBAL HOSTING handled as a site too)
        if r["site"]:
            sid = _site_id(r["site"])
            sites[sid] = sites.get(sid, 0) + 1
            edges.append({"src": nid, "dst": sid, "rel": "FOR_SITE"})
        # link directly to the resolved replica/drift site code(s) so the CFG-RFC
        # register cross-links to the live drift results (NEMC, DALLAS, ...)
        for rc in (r.get("replicaSites") or []):
            rid = f"replica:{rc}"
            replica_hits[rc] = replica_hits.get(rc, 0) + 1
            edges.append({"src": nid, "dst": rid, "rel": "AT_REPLICA_SITE"})
    # deduped Site nodes derived from the register
    seen = set()
    for code, r in reg.items():
        if not r["site"]:
            continue
        sid = _site_id(r["site"])
        if sid in seen:
            continue
        seen.add(sid)
        nodes.append({"id": sid, "type": "Site", "label": r["site"],
                      "isGlobal": r["site"].strip().upper() == "GLOBAL HOSTING",
                      "replicaSites": ",".join(r.get("replicaSites") or []),
                      "crfcCount": sites.get(sid, 0)})
    # deduped ReplicaSite nodes (the short drift/replica codes the CFG-RFCs map to)
    for rc, n in sorted(replica_hits.items()):
        nodes.append({"id": f"replica:{rc}", "type": "ReplicaSite", "label": rc,
                      "code": rc, "crfcCount": n})
    graph = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
             "counts": {"nodes": len(nodes), "edges": len(edges),
                        "sites": len(seen), "replicaSites": len(replica_hits)},
             "nodes": nodes, "edges": edges}
    log(f"CRFC graph: {len(nodes)} nodes ({len(seen)} sites, "
        f"{len(replica_hits)} replica-mapped), {len(edges)} edges")
    return graph


def load_neo4j(graph: dict) -> None:
    from neo4j import GraphDatabase
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user, pw = os.environ.get("NEO4J_USER"), os.environ.get("NEO4J_PASSWORD")
    if not user or not pw:
        raise RuntimeError("set NEO4J_USER / NEO4J_PASSWORD to load Neo4j")
    log(f"Neo4j: connecting {uri} as {user}")
    driver = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=10)
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            log("Neo4j: clearing previous CrfcReg nodes")
            s.run("MATCH (n:CrfcReg) DETACH DELETE n")
            s.run("CREATE CONSTRAINT crfc_id IF NOT EXISTS FOR (n:CRFC) REQUIRE n.id IS UNIQUE")
            s.run("CREATE CONSTRAINT site_id IF NOT EXISTS FOR (n:Site) REQUIRE n.id IS UNIQUE")
            s.run("CREATE CONSTRAINT replica_id IF NOT EXISTS FOR (n:ReplicaSite) REQUIRE n.id IS UNIQUE")
            crfc_rows = [{k: v for k, v in n.items() if k != "type"}
                         for n in graph["nodes"] if n["type"] == "CRFC"]
            site_rows = [{k: v for k, v in n.items() if k != "type"}
                         for n in graph["nodes"] if n["type"] == "Site"]
            replica_rows = [{k: v for k, v in n.items() if k != "type"}
                            for n in graph["nodes"] if n["type"] == "ReplicaSite"]
            s.run("UNWIND $rows AS row MERGE (n:CRFC:CrfcReg {id: row.id}) SET n += row", rows=crfc_rows)
            log(f"  loaded {len(crfc_rows)} :CRFC")
            s.run("UNWIND $rows AS row MERGE (n:Site:CrfcReg {id: row.id}) SET n += row", rows=site_rows)
            log(f"  loaded {len(site_rows)} :Site")
            s.run("UNWIND $rows AS row MERGE (n:ReplicaSite:CrfcReg {id: row.id}) SET n += row",
                  rows=replica_rows)
            log(f"  loaded {len(replica_rows)} :ReplicaSite")
            # link to the existing CFG-RFC gate if it is present
            gate_edges = [e for e in graph["edges"] if e["rel"] == "RAISED_AS"]
            res = s.run(
                "UNWIND $rows AS row MATCH (c:CRFC {id: row.src}) "
                "MATCH (g {id: 'gate_cfgrfc'}) MERGE (c)-[:RAISED_AS]->(g) RETURN count(*) AS c",
                rows=gate_edges).single()
            log(f"  linked {res['c']} CRFC-[:RAISED_AS]->gate_cfgrfc")
            site_edges = [e for e in graph["edges"] if e["rel"] == "FOR_SITE"]
            res = s.run(
                "UNWIND $rows AS row MATCH (c:CRFC {id: row.src}) MATCH (t:Site {id: row.dst}) "
                "MERGE (c)-[:FOR_SITE]->(t) RETURN count(*) AS c", rows=site_edges).single()
            log(f"  linked {res['c']} CRFC-[:FOR_SITE]->Site")
            replica_edges = [e for e in graph["edges"] if e["rel"] == "AT_REPLICA_SITE"]
            res = s.run(
                "UNWIND $rows AS row MATCH (c:CRFC {id: row.src}) MATCH (t:ReplicaSite {id: row.dst}) "
                "MERGE (c)-[:AT_REPLICA_SITE]->(t) RETURN count(*) AS c", rows=replica_edges).single()
            log(f"  linked {res['c']} CRFC-[:AT_REPLICA_SITE]->ReplicaSite")
            log("Neo4j: CRFC by decisionClass ===")
            for r in s.run("MATCH (n:CRFC) RETURN n.decisionClass AS d, count(*) AS c ORDER BY c DESC"):
                print(f"    {r['d']}: {r['c']}")
    finally:
        driver.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Load the CFG-RFC register into graph + exceptions")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="path to Configuration_RFC.csv")
    ap.add_argument("--build", action="store_true", help="write register + graph JSON")
    ap.add_argument("--neo4j", action="store_true", help="load CRFC nodes into Neo4j")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    reg = load_register(args.csv)

    # persist the register (used by enrich_deviations.py --crfc)
    reg_path = os.path.join(OUT_DIR, "crfc_register.json")
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    log(f"wrote {reg_path}")

    if args.build or args.neo4j:
        graph = build_nodes(reg)
        gpath = os.path.join(OUT_DIR, "crfc_graph.json")
        with open(gpath, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2, ensure_ascii=False)
        log(f"wrote {gpath}")
        if args.neo4j:
            load_neo4j(graph)

    # quick classification summary
    from collections import Counter
    log("register decisionClass distribution:")
    for k, v in Counter(r["decisionClass"] for r in reg.values()).most_common():
        log(f"   {k:20s} {v}")
    invalid = sum(1 for r in reg.values() if not r["valid"])
    log(f"valid (still justifying)   : {len(reg) - invalid}")
    log(f"invalid (withdrawn/superseded/rejected/disused): {invalid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
