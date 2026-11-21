"""
config_governance.py — load the PrIME Configuration GOVERNANCE layer into Neo4j so
the knowledge graph accurately answers the two operating questions:

  OBJ-1  running Config Drift  -> what is a deviation? (types, severities, scoring)
  OBJ-2  a new site config     -> does it meet the standard? what is the impact?
                                  (governance gates, deployment, migration)

Grounded in the SharePoint "Configuration" tab (Configuration-Drift.aspx, CAR, CHR,
Design-Review, Standard-Configuration-Deployment-Process[-2022], Configuration-with-
Code, Migration-Readiness-2014-to-2022). Same facts as window.WHS.configModel in
UIUX/assets/data.js.

All nodes carry :ConfigGov (so this layer can be wiped independently). The layer
BRIDGES into the existing graph:
  (DriftTool)-[:AUDITS]->(:Version 2014 & 2022)
  (Gate 'CFG-RFC')-[:RESOLVES_VIA]->(:Process {id:'crfc'})
  (DeploymentPath)-[:DEPLOYS]->(:Version)

USAGE
    python config_governance.py --build            # write config_governance.json
    python config_governance.py --build --neo4j    # + load into Neo4j
"""
from __future__ import annotations

import argparse
import datetime
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_catalogue_graph_full")
SRC = "https://<sharepoint-host>/sites/WMSPrIMEService/SitePages/Configuration.aspx"


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


DEVIATION_TYPES = [
    ("dt_missing", "Missing record", "Record is absent in the audited instance."),
    ("dt_unexpected", "Unexpected record", "Record present but not allowed (may be allowed for other sites)."),
    ("dt_mismatch", "Mismatching value", "Record present but has an unsupported setting (A Value vs R Value)."),
]

SEVERITIES = [
    ("sev_high", "High", "Significant WMS impact — must be addressed.", "sc_config"),
    ("sev_medium", "Medium", "Should be reviewed; risk if not addressed.", "sc_config"),
    ("sev_low", "Low", "Information only — cosmetic / new base config.", "sc_config"),
    ("sev_accepted", "Accepted", "CoE-approved exception / temporary variance; carries a Rationale.", None),
    ("sev_2022", "2022", "Only affects the 2014→2022 migration — must be fixed before migrating.", None),
    ("sev_health", "health_high/medium/low", "Checks only (June 2026).", "sc_health"),
]

SCORES = [
    ("sc_config", "Config Score", "Adherence to configuration standards."),
    ("sc_health", "Health Score", "Configuration and Health Checks (split out in v3.0)."),
]

GATES = [
    ("gate_dr", "Design Review (DR)",
     "Project gate — GBS PM raises 2 weeks prior; global experts review Work Process + PrIME Configuration vs standards; needs CoE signoff. Gaps route to CFG-RFC or CoE Features.", None),
    ("gate_car", "CAR — Configuration Audit Report",
     "Shows not-allowed configurations vs the global standard; now built from the Config Drift report. Fix to standard or raise a CFG-RFC.", "based_drift"),
    ("gate_chr", "CHR — Configuration & Health Report",
     "Site config choices + health checks; NOK must be fixed for CoE signoff, NOK-CC approve the CC in SCDT, CHECK review, INFO informative. Merged into Drift Mar 2026.", "merged_drift"),
    ("gate_cfgrfc", "CFG-RFC",
     "The change request that turns a new/changed config into an approved standard, allowed deviation, or exception.", "resolves_crfc"),
    ("gate_coe_feat", "CoE Features (config with code)",
     "Config-with-code must be productized via a P-RFC in iCM; deployed via SCDT (2014) or Roll-out (2022). Un-productized code is overwritten by the DxC RO.", None),
]

MIGRATION_CATS = [
    ("mig_cleanup", "Action Required - PrIME 2014 Cleanup", "MUST be fixed prior to migration."),
    ("mig_aware", "Action Required - Site Awareness", "Resolved or migrated; site must know post-migration behavior; may raise a CFG-RFC."),
    ("mig_none", "No Action for Migration", "No impact for the site; no review required."),
    ("mig_undef", "Undefined - CoE to Review", "Temporary category for new deviations CoE will triage."),
    ("mig_notpossible", "Not Possible as Per Drift Rules", "Internal tracking — should not occur in 2022."),
]

DEPLOY_PATHS = [
    ("dep_2014", "PrIME v2014 deployment (SCDR)",
     "SCD Portfolio (TMPLCHG packages), tracked in QuickBase/SCDT. Sequence: Rollout → SCDR package → Hard Bounce → Security Refresh.",
     ["version:2014"]),
    ("dep_2022", "PrIME v2022 deployment (DxC RO)",
     "Push model — no SCDR; the Roll-out carries most config + CoE-Feature code (disabled). SSCD packages for special cases; features enabled via Role Base Policy Maintenance.",
     ["version:2022"]),
]

BUCKETS = [
    ("bucket_central", "Central configuration", "Owned by Product Team; shared by all sites; preloaded; must NOT be modified."),
    ("bucket_site", "Site configuration", "Owned by SE / site KU / BPO; business work-process + site preferences."),
]


def build_graph() -> dict:
    nodes, edges = [], []

    def add(nid, ntype, **a):
        nodes.append({"id": nid, "type": ntype, **a})

    add("pcd", "DriftTool", label="PrIME Config Drift (PCD)", version="v3.0 (June 2026)",
        source=SRC,
        description="Audits PrIME configurations twice weekly on the Decision Automation "
                    "Platform vs the MNTWMS standard; publishes to Power BI. 132 instances "
                    "(Jan 2026). Rules refreshed weekly via approved CFG-RFCs.")

    for nid, label, desc in DEVIATION_TYPES:
        add(nid, "DeviationType", label=label, description=desc)
        edges.append({"src": "pcd", "dst": nid, "rel": "DETECTS"})

    for nid, label, desc in SCORES:
        add(nid, "Score", label=label, description=desc)
        edges.append({"src": "pcd", "dst": nid, "rel": "PRODUCES_SCORE"})

    for nid, label, impact, score in SEVERITIES:
        add(nid, "Severity", label=label, impact=impact)
        edges.append({"src": "pcd", "dst": nid, "rel": "RANKS_BY"})
        if score:
            edges.append({"src": nid, "dst": score, "rel": "AFFECTS"})

    for nid, label, desc, link in GATES:
        add(nid, "Gate", label=label, description=desc)
        edges.append({"src": nid, "dst": "pcd", "rel": "USES"} if link in ("based_drift", "merged_drift")
                     else {"src": "pcd", "dst": nid, "rel": "FEEDS"})
        if link == "resolves_crfc":
            edges.append({"src": nid, "dst": "crfc", "rel": "RESOLVES_VIA"})

    for nid, label, desc in MIGRATION_CATS:
        add(nid, "MigrationCategory", label=label, description=desc)
        edges.append({"src": "pcd", "dst": nid, "rel": "HAS_MIGRATION_CATEGORY"})

    for nid, label, desc, versions in DEPLOY_PATHS:
        add(nid, "DeploymentPath", label=label, description=desc)
        for v in versions:
            edges.append({"src": nid, "dst": v, "rel": "DEPLOYS"})

    for nid, label, desc in BUCKETS:
        add(nid, "ConfigBucket", label=label, description=desc)

    # --- bridges into the existing graph ---
    edges.append({"src": "pcd", "dst": "version:2014", "rel": "AUDITS"})
    edges.append({"src": "pcd", "dst": "version:2022", "rel": "AUDITS"})

    graph = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": SRC,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": nodes, "edges": edges,
    }
    log(f"config-governance graph: {len(nodes)} nodes, {len(edges)} edges")
    return graph


def load_neo4j(graph: dict):
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
            log("Neo4j: clearing previous ConfigGov nodes")
            s.run("MATCH (n:ConfigGov) DETACH DELETE n")
            for label in ("DriftTool", "DeviationType", "Severity", "Score", "Gate",
                          "MigrationCategory", "DeploymentPath", "ConfigBucket"):
                s.run(f"CREATE CONSTRAINT cg_{label.lower()} IF NOT EXISTS "
                      f"FOR (n:{label}) REQUIRE n.id IS UNIQUE")

            by_type: dict[str, list] = {}
            for n in graph["nodes"]:
                by_type.setdefault(n["type"], []).append(n)
            for ntype, rows in by_type.items():
                clean = [{k: v for k, v in r.items() if k != "type"} for r in rows]
                s.run(f"UNWIND $rows AS row MERGE (n:{ntype}:ConfigGov {{id: row.id}}) SET n += row",
                      rows=clean)
                log(f"  loaded {len(clean)} :{ntype}")

            by_rel: dict[str, list] = {}
            for e in graph["edges"]:
                by_rel.setdefault(e["rel"], []).append({"src": e["src"], "dst": e["dst"]})
            for rel, rows in by_rel.items():
                s.run(f"UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
                      f"MERGE (a)-[:{rel}]->(b)", rows=rows)
                log(f"  loaded {len(rows)} [:{rel}]")

            log("Neo4j: ConfigGov labels ===")
            for r in s.run("MATCH (n:ConfigGov) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"):
                print(f"    {r['l']}: {r['c']}")
            b = s.run("MATCH (:DriftTool)-[r:AUDITS]->(:Version) RETURN count(r) AS c").single()["c"]
            x = s.run("MATCH (:Gate)-[r:RESOLVES_VIA]->(:Process) RETURN count(r) AS c").single()["c"]
            log(f"Neo4j: {b} AUDITS→Version bridges, {x} Gate→CRFC bridges")
    finally:
        driver.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Build config-governance layer into the graph")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--neo4j", action="store_true")
    args = ap.parse_args()
    if not args.build:
        ap.print_help()
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    graph = build_graph()
    with open(os.path.join(OUT_DIR, "config_governance.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    log(f"wrote {os.path.join(OUT_DIR, 'config_governance.json')}")
    if args.neo4j:
        load_neo4j(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
