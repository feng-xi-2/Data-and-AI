"""
crfc_semantic.py — add the CRFC (Configuration Change Process, "CFG-RFC") into the
semantic model / knowledge graph, GROUNDED in the real SharePoint SitePage:
  https://<sharepoint-host>/sites/WMSPrIMEService/SitePages/Configuration-Change-Process.aspx
  (title "Change Process (CFG-RFC)", pulled live via sharepoint_reader.py --pages-only;
   raw text saved at _sharepoint/_crfc_text.txt)

The model below is TRANSCRIBED from that page (statuses, roles, decisions, outputs,
deployment methods, triggers). It is not invented — every node maps to text on the page.

Graph shape (all nodes carry :CRFC so we can wipe just this sub-graph):
  (:Process {id:'crfc'})
  (:Stage)      lifecycle statuses, ordered by NEXT
  (:Role)       actors (Requestor, CoE, OPL, TPL, ...)
  (:Decision)   approval outcomes
  (:Deployment) deployment methods
  (:Trigger)    what starts a CFG-RFC
  (:Output)     what a CFG-RFC updates/produces
  (:Tool)       supporting systems (QuickBase, SCDT, SCD Portfolio, Panaya)

Relationships:
  (Process)-[:HAS_STAGE]->(Stage)     (Stage)-[:NEXT]->(Stage)
  (Stage)-[:PERFORMED_BY]->(Role)
  (Process)-[:TRIGGERED_BY]->(Trigger)   (Trigger)-[:RAISED_BY]->(Role)
  (Process)-[:HAS_DECISION]->(Decision)
  (Process)-[:PRODUCES]->(Output)
  (Process)-[:DEPLOYED_VIA]->(Deployment)
  (Process)-[:TRACKED_IN]->(Tool)
  (Output {id:'out_config_library'})-[:UPDATES]->(:Version 2014 & 2022)   <-- bridges to config graph
  (Output {id:'out_audit_tool'})-[:AUDITS]->(:Version 2022)

USAGE
    python crfc_semantic.py --build            # write crfc_graph.json
    python crfc_semantic.py --build --neo4j    # + load into Neo4j (bolt://localhost:7687)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_catalogue_graph_full")
SOURCE_URL = ("https://<sharepoint-host>/sites/WMSPrIMEService/SitePages/"
              "Configuration-Change-Process.aspx")


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


# --- the grounded CRFC model (transcribed from the page) --------------------
# lifecycle statuses, in order (the "step by step, status by status" section)
STAGES = [
    ("submitted", "Submitted",
     "Core CoE team pre-screens new CFG-RFCs weekly; complete ones set to Ready for CoE meeting."),
    ("ready_coe", "Ready for CoE meeting",
     "CoE prepares proposed deliverables (technical content, business impact, when/when-not to apply)."),
    ("waiting_requestor", "Waiting for requestor action",
     "Drives actions needed to make a CFG ready for decision; owner brings it back when ready."),
    ("waiting_opl_tpl", "Waiting for OPL/TPL approval",
     "TPL and OPL are the formal decision authority; they type 'I approve'."),
    ("integration", "Integration in progress",
     "Deliverables executed: deployment packages produced, template updated, audit tool + library updated."),
    ("waiting_accept", "Waiting for requestor to accept integration",
     "Re-validation (EOF) when final code differs from submitted code; site tests & documents."),
    ("delivered", "Delivered",
     "All deliverables done; deployment method is set (Security Refresh / Rollout / Template Refresh / Combo / N-A)."),
]
# terminal / off-ramp statuses
TERMINAL_STAGES = [
    ("rejected", "Rejected", "Risk higher than benefit, or code-injection -> follow CoE Features process."),
    ("withdrawn", "Withdrawn", "No longer needed or another solution selected."),
    ("disused", "Disused", "Temporary approved config reached end of use / end of life."),
]

ROLES = [
    ("role_requestor", "Requestor", "Submits the CFG-RFC (Solution Expert / Site BPO / Regional BPX / Product Team)."),
    ("role_solution_expert", "Solution Expert (SE)", "From PrIME Implementation Projects; submits when change is tested."),
    ("role_site_bpo", "Site BPO", "PrIME live site; submits ad-hoc needs."),
    ("role_regional_bpx", "Regional BPX", "PrIME Wave deployment; business-case decision authority."),
    ("role_product_team", "Product Team (BY/PT)", "PrIME Product Development; new configuration entry points."),
    ("role_core_coe", "Core CoE Team", "Pre-screens, prepares deliverables, documents decisions."),
    ("role_coe_meeting", "Weekly CoE Meeting", "Decision-making body about the change & deliverables."),
    ("role_opl", "OPL", "Operational formal approver ('I approve')."),
    ("role_tpl", "TPL", "Technical formal approver ('I approve')."),
    ("role_pt", "PT", "Signs off code applied to the master template."),
    ("role_librarian", "CoE Librarian", "Grants QuickBase access (Johann Tan / ITS Warehousing Product Team)."),
]

TRIGGERS = [
    ("trg_impl", "Implementation project gap", "Business process requirement can't be met by existing standards.",
     "role_solution_expert"),
    ("trg_wave", "Wave deployment review", "Outcome of pre-NNIT configuration review with CoE.",
     "role_regional_bpx"),
    ("trg_prfc", "New P-RFC configuration", "New BY/PT P-RFC introduces new config entry points.",
     "role_product_team"),
    ("trg_live_site", "Live-site change", "Live site introduces change not configurable in current standards.",
     "role_site_bpo"),
    ("trg_bug", "Bug workaround", "Temporary configuration workaround for a PrIME bug, shared across sites.",
     "role_site_bpo"),
]

DECISIONS = [
    ("dec_new_standard", "Approved as new standard", "May be a standard for specific scenarios only."),
    ("dec_allowed_dev", "Approved as allowed deviation", "For config that had limited allowed values."),
    ("dec_exception_temp", "Exception temporary approved", "Workaround for a bug / temporary gap; needs line of sight to P-RFC or PR-Bug ('Till' field)."),
    ("dec_exception_site", "Exception approved for site/region", "Not allowed to deploy to other sites/regions."),
]

DEPLOYMENTS = [
    ("dep_security_refresh", "Security Refresh", "Deployment via security refresh."),
    ("dep_rollout", "Rollout (RO)", "v2022 deployment via Rollout (RO); v2014 via SCDR."),
    ("dep_template_refresh", "Template Refresh", "Global PrIME template refresh."),
    ("dep_combo", "Combo", "Combination of methods."),
    ("dep_na", "N/A — Documentation only", "No deployment; documentation-only change."),
]

OUTPUTS = [
    ("out_config_library", "Configuration Library", "Config standards documentation (SharePoint pages & standards files)."),
    ("out_audit_tool", "Configuration Audit Tool", "Design Review + Configuration Drift Monitoring (CAR / Drift)."),
    ("out_deploy_pkg", "Configuration Deployment Package", "Packages to deploy config records (TMPL / EXCP)."),
    ("out_global_template", "Global Configuration Template", "Basis for new implementation projects."),
    ("out_solution_guides", "Solution Guides", "Updated guidance."),
]

TOOLS = [
    ("tool_quickbase", "QuickBase (CFG-RFC app)", "Where CFG-RFC requests are raised and tracked."),
    ("tool_scdt", "SCDT", "Standard Configuration Deployment Tracker / Template Tracker."),
    ("tool_scd_portfolio", "SCD Portfolio", "Where approved change documentation is published for Design Reviews & Wave RO."),
    ("tool_panaya", "Panaya", "PUMA project fixes to CoE Features (Testing Execution)."),
    ("tool_icm", "iCM (P-RFC)", "Where configuration-with-code (CoE Features) is submitted as P-RFC."),
]


def build_graph() -> dict:
    nodes, edges = [], []

    def add(nid, ntype, **attrs):
        nodes.append({"id": nid, "type": ntype, **attrs})

    add("crfc", "Process", label="CFG-RFC — Configuration Change Process",
        source=SOURCE_URL,
        description="Change management process for the PrIME Configuration standards. "
                    "Input: a request for change (CFG-RFC). Outputs: updated Configuration "
                    "Library, audit tool, deployment packages, and global template.")

    # stages + NEXT chain
    prev = None
    for sid, label, desc in STAGES:
        add(f"stage:{sid}", "Stage", label=label, description=desc, terminal=False)
        edges.append({"src": "crfc", "dst": f"stage:{sid}", "rel": "HAS_STAGE"})
        if prev:
            edges.append({"src": f"stage:{prev}", "dst": f"stage:{sid}", "rel": "NEXT"})
        prev = sid
    for sid, label, desc in TERMINAL_STAGES:
        add(f"stage:{sid}", "Stage", label=label, description=desc, terminal=True)
        edges.append({"src": "crfc", "dst": f"stage:{sid}", "rel": "HAS_STAGE"})

    # roles
    for rid, label, desc in ROLES:
        add(rid, "Role", label=label, description=desc)

    # stage -> role (who acts at each stage)
    stage_role = {
        "submitted": ["role_core_coe"],
        "ready_coe": ["role_core_coe", "role_coe_meeting"],
        "waiting_requestor": ["role_requestor", "role_solution_expert"],
        "waiting_opl_tpl": ["role_opl", "role_tpl"],
        "integration": ["role_core_coe", "role_pt"],
        "waiting_accept": ["role_requestor", "role_site_bpo"],
        "delivered": ["role_core_coe"],
    }
    for sid, roles in stage_role.items():
        for r in roles:
            edges.append({"src": f"stage:{sid}", "dst": r, "rel": "PERFORMED_BY"})

    # triggers
    for tid, label, desc, role in TRIGGERS:
        add(tid, "Trigger", label=label, description=desc)
        edges.append({"src": "crfc", "dst": tid, "rel": "TRIGGERED_BY"})
        edges.append({"src": tid, "dst": role, "rel": "RAISED_BY"})

    # decisions
    for did, label, desc in DECISIONS:
        add(did, "Decision", label=label, description=desc)
        edges.append({"src": "crfc", "dst": did, "rel": "HAS_DECISION"})
        edges.append({"src": "stage:ready_coe", "dst": did, "rel": "DECIDES"})

    # deployments
    for dpid, label, desc in DEPLOYMENTS:
        add(dpid, "Deployment", label=label, description=desc)
        edges.append({"src": "crfc", "dst": dpid, "rel": "DEPLOYED_VIA"})
        edges.append({"src": "stage:delivered", "dst": dpid, "rel": "USES_METHOD"})

    # outputs
    for oid, label, desc in OUTPUTS:
        add(oid, "Output", label=label, description=desc)
        edges.append({"src": "crfc", "dst": oid, "rel": "PRODUCES"})
        edges.append({"src": "stage:integration", "dst": oid, "rel": "UPDATES_OUTPUT"})

    # tools
    for tid, label, desc in TOOLS:
        add(tid, "Tool", label=label, description=desc)
        edges.append({"src": "crfc", "dst": tid, "rel": "TRACKED_IN"})

    # --- BRIDGE to the config catalogue graph (Version nodes already loaded) ---
    # The Configuration Library output updates BOTH standards versions; the audit
    # tool audits the 2022 standard. These edges connect CRFC -> config graph.
    edges.append({"src": "out_config_library", "dst": "version:2014", "rel": "UPDATES"})
    edges.append({"src": "out_config_library", "dst": "version:2022", "rel": "UPDATES"})
    edges.append({"src": "out_audit_tool", "dst": "version:2022", "rel": "AUDITS"})
    edges.append({"src": "out_deploy_pkg", "dst": "version:2022", "rel": "DEPLOYS_TO"})
    edges.append({"src": "out_deploy_pkg", "dst": "version:2014", "rel": "DEPLOYS_TO"})

    graph = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": SOURCE_URL,
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": nodes,
        "edges": edges,
    }
    log(f"CRFC graph: {len(nodes)} nodes, {len(edges)} edges")
    return graph


def load_neo4j(graph: dict):
    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER")
    pw = os.environ.get("NEO4J_PASSWORD")
    if not user or not pw:
        raise RuntimeError("set NEO4J_USER / NEO4J_PASSWORD to load Neo4j")

    log(f"Neo4j: connecting {uri} as {user}")
    driver = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=10)
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            log("Neo4j: clearing previous CRFC nodes")
            s.run("MATCH (n:CRFC) DETACH DELETE n")
            for label in ("Process", "Stage", "Role", "Trigger", "Decision",
                          "Deployment", "Output", "Tool"):
                s.run(f"CREATE CONSTRAINT crfc_{label.lower()} IF NOT EXISTS "
                      f"FOR (n:{label}) REQUIRE n.id IS UNIQUE")

            by_type: dict[str, list] = {}
            for n in graph["nodes"]:
                by_type.setdefault(n["type"], []).append(n)
            for ntype, rows in by_type.items():
                clean = [{k: v for k, v in r.items() if k != "type"} for r in rows]
                s.run(f"UNWIND $rows AS row MERGE (n:{ntype}:CRFC {{id: row.id}}) SET n += row",
                      rows=clean)
                log(f"  loaded {len(clean)} :{ntype}")

            by_rel: dict[str, list] = {}
            for e in graph["edges"]:
                by_rel.setdefault(e["rel"], []).append({"src": e["src"], "dst": e["dst"]})
            for rel, rows in by_rel.items():
                # MERGE by id; dst may be a config Version node (no :CRFC label) — that's fine
                s.run(f"UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
                      f"MERGE (a)-[:{rel}]->(b)", rows=rows)
                log(f"  loaded {len(rows)} [:{rel}]")

            log("Neo4j: CRFC labels ===")
            for r in s.run("MATCH (n:CRFC) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"):
                print(f"    {r['l']}: {r['c']}")
            # confirm the bridge
            b = s.run("MATCH (:Output)-[r:UPDATES|AUDITS|DEPLOYS_TO]->(v:Version) "
                      "RETURN count(r) AS c").single()["c"]
            log(f"Neo4j: {b} CRFC->config bridge edges to Version nodes")
    finally:
        driver.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Build CRFC semantic model into the graph")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--neo4j", action="store_true")
    args = ap.parse_args()
    if not args.build:
        ap.print_help()
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    graph = build_graph()
    with open(os.path.join(OUT_DIR, "crfc_graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    log(f"wrote {os.path.join(OUT_DIR, 'crfc_graph.json')}")
    if args.neo4j:
        load_neo4j(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
