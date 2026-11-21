"""
graph_api.py — LOCAL bridge server that makes the static UIUX pages "really connect"
to the live Neo4j knowledge graph and to the cached SharePoint content, and answers
NATURAL-LANGUAGE questions by translating them to grounded, read-only Cypher.

A browser page opened from disk (file://) or from any origin CANNOT open a bolt://
socket or authenticate to SharePoint directly. This tiny stdlib HTTP server is the
honest bridge: the page fetches http://127.0.0.1:8737/... and this process talks to
Neo4j (python driver) + reads the SharePoint pull cache.

No third-party web framework needed (uses http.server). Requires: neo4j driver.

ENDPOINTS (all CORS-enabled)
  GET  /health                      -> {ok, neo4j, sharepoint}
  GET  /schema                      -> live labels + relationship types + counts
  POST /query   {cypher, params}    -> read-only Cypher (writes are rejected)
  POST /nl      {q}                 -> {question, cypher, explain, rows, graph}
  GET  /graph/sample?label=Stage&limit=40 -> nodes+edges for a mini graph
  GET  /sharepoint/pages[?q=term]   -> cached SitePages (from sharepoint_pages.json)
  GET  /examples                    -> suggested natural-language questions

RUN
  set NEO4J_USER / NEO4J_PASSWORD, then:
    python graph_api.py                # serves on http://127.0.0.1:8737
    python graph_api.py --port 8800
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import skill_platform as sp
import expert_feedback as ef
import change_watch as cw

BASE = os.path.dirname(os.path.abspath(__file__))
SP_PAGES = os.path.join(BASE, "_sharepoint", "sharepoint_pages.json")

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|"
                    r"CALL\s+\{[^}]*\b(CREATE|MERGE|DELETE|SET)\b|FOREACH|"
                    r"CREATE\s+CONSTRAINT|CREATE\s+INDEX)\b", re.IGNORECASE)


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


# ------------------------------------------------------------------ Neo4j ---
class Graph:
    def __init__(self):
        from neo4j import GraphDatabase
        if not NEO4J_PASSWORD:
            raise RuntimeError("set NEO4J_PASSWORD (and NEO4J_USER) before starting")
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), connection_timeout=10)
        self.driver.verify_connectivity()
        log(f"Neo4j connected: {NEO4J_URI} as {NEO4J_USER}")

    def close(self):
        self.driver.close()

    def read(self, cypher: str, params: dict | None = None, limit_records: int = 500):
        if _WRITE.search(cypher):
            raise ValueError("write operations are not allowed on this read-only endpoint")
        with self.driver.session(default_access_mode="READ") as s:
            res = s.run(cypher, params or {})
            rows, graph_nodes, graph_edges = [], {}, []
            for i, rec in enumerate(res):
                if i >= limit_records:
                    break
                rows.append({k: _val(v, graph_nodes, graph_edges) for k, v in rec.items()})
            return {"rows": rows,
                    "graph": {"nodes": list(graph_nodes.values()), "edges": graph_edges}}

    def schema(self):
        with self.driver.session(default_access_mode="READ") as s:
            labels = [{"label": r["label"], "count": r["c"]} for r in s.run(
                "MATCH (n) UNWIND labels(n) AS label "
                "RETURN label, count(*) AS c ORDER BY c DESC")]
            rels = [{"type": r["t"], "count": r["c"]} for r in s.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC")]
            total = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            totrel = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        return {"labels": labels, "relationships": rels,
                "totals": {"nodes": total, "relationships": totrel}}


def _val(v, gn, ge):
    """Serialize a Neo4j value; collect Node/Relationship into the mini-graph."""
    try:
        from neo4j.graph import Node, Relationship, Path
    except Exception:  # pragma: no cover
        Node = Relationship = Path = ()
    if isinstance(v, Node):
        nid = v.element_id
        if nid not in gn:
            gn[nid] = {"id": v.get("id", nid), "eid": nid,
                       "labels": list(v.labels), "props": dict(v)}
        return {"_node": v.get("id", nid), "labels": list(v.labels), **dict(v)}
    if isinstance(v, Relationship):
        ge.append({"src": v.start_node.get("id", v.start_node.element_id),
                   "dst": v.end_node.get("id", v.end_node.element_id),
                   "type": v.type})
        return {"_rel": v.type}
    if isinstance(v, Path):
        return [_val(x, gn, ge) for x in v]
    if isinstance(v, (list, tuple)):
        return [_val(x, gn, ge) for x in v]
    if isinstance(v, dict):
        return {k: _val(x, gn, ge) for k, x in v.items()}
    return v


# ---------------------------------------------------- NL -> Cypher (grounded) ---
# Curated, schema-grounded intents. Each rule: (regex, cypher, explanation).
# Everything is READ-ONLY and limited. Grounded in the real labels present:
#   Config: Section, Column, Field, Exception, Change, Version (+FullConfig)
#   Ontology/WHS: RTCISTable, PrIMETable, RTCISColumn, PrIMEColumn, RTCISValue,
#                 PrIMEValue, ViewObject, Learning, KBRule, QueryDomain
#   CRFC: Process, Stage, Role, Trigger, Decision, Deployment, Output, Tool
NL_RULES = [
    # ---- Cross-site exception inconsistencies (accepted here, penalised there) ----
    # "deviations one site registered/accepted but other sites with the same config leave open"
    (r"\b(cross[- ]?site|other sites?|another site|one site|some sites?)\b.*\b(exception|deviation|accept\w*|register\w*|inconsist\w*|open|penali\w*|cover\w*)\b|"
     r"\b(exception|deviation|accept\w*|register\w*)\b.*\b(cross[- ]?site|other sites?|another site|not cover\w*|same config\w*|inconsist\w*)\b|"
     r"\baccepted (here|somewhere).*(penali|open|elsewhere)\w*|"
     r"\binconsisten\w* (exception|deviation)\w*\b|"
     r"\bregistered by one site\b",
     "MATCH (d:DevIdentity) "
     "OPTIONAL MATCH (sa)-[ra:HAS_DEVIATION]->(d) WHERE ra.severity='accepted' "
     "WITH d, count(DISTINCT sa) AS nAcc, [x IN collect(DISTINCT ra.cfg) WHERE x<>''] AS cfg "
     "OPTIONAL MATCH (so)-[ro:HAS_DEVIATION]->(d) WHERE ro.severity IN ['medium','low','high'] "
     "WITH d, nAcc, cfg, count(DISTINCT so) AS nOpen, "
     "     collect(DISTINCT ro.severity) AS openSevs, sum(ro.count) AS openRows "
     "WHERE nAcc>0 AND nOpen>0 "
     "RETURN d.section AS section, d.element AS element, d.attr AS attribute, "
     "       d.a AS a_value, d.r AS r_value, d.type AS deviation_type, "
     "       nAcc AS accepted_sites, nOpen AS open_sites, openRows AS open_rows, "
     "       openSevs AS open_severities, cfg AS cfg_precedent "
     "ORDER BY open_sites DESC, open_rows DESC",
     "Deviations accepted/registered as an exception by at least one site but left OPEN "
     "(penalised) by other sites sharing the same configuration identity "
     "(same section/element/attribute/A/R/type). CFG-backed rows carry an approved precedent."),

    # ---- CRFC process ----
    (r"\b(crfc|cfg-?rfc|change process|life ?cycle|lifecycle|stages?)\b.*\b(order|flow|steps?|sequence)\b|"
     r"\b(order|flow|steps?|sequence)\b.*\b(crfc|stages?|lifecycle)\b|"
     r"\bcrfc (process|lifecycle|stages?)\b",
     "MATCH (p:Process)-[:HAS_STAGE]->(s:Stage) "
     "OPTIONAL MATCH (s)-[:NEXT]->(n:Stage) "
     "RETURN s.label AS stage, s.terminal AS terminal, n.label AS next_stage, s.description AS detail "
     "ORDER BY terminal, stage",
     "CFG-RFC lifecycle stages and their ordering (Process-[:HAS_STAGE]->Stage-[:NEXT]->Stage)."),

    (r"\bwho\b.*\b(approv|authori|sign)\w*|"
     r"\b(roles?|actors?|who does)\b.*\b(crfc|change|process|approv)\w*|"
     r"\b(opl|tpl|coe)\b",
     "MATCH (s:Stage)-[:PERFORMED_BY]->(r:Role) "
     "RETURN s.label AS stage, collect(r.label) AS roles ORDER BY stage",
     "Roles that act at each CFG-RFC stage (Stage-[:PERFORMED_BY]->Role)."),

    (r"\b(decision outcomes?|decision|approved as (new )?standard)\b",
     "MATCH (:Process)-[:HAS_DECISION]->(d:Decision) "
     "RETURN d.label AS decision, d.description AS detail",
     "The possible CFG-RFC decision outcomes (Process-[:HAS_DECISION]->Decision)."),

    (r"\bdeployment methods?\b|\b(crfc|cfg-?rfc)\b.*\bdeploy|\b(security refresh|template refresh)\b",
     "MATCH (:Process)-[:DEPLOYED_VIA]->(d:Deployment) "
     "RETURN d.label AS method, d.description AS detail",
     "Deployment methods used to deliver a CFG-RFC (Process-[:DEPLOYED_VIA]->Deployment)."),

    (r"\b(trigger|start|initiat|raise|source of)\w*\b.*\b(crfc|change)\b|"
     r"\bwhat (triggers?|starts?)\b",
     "MATCH (:Process)-[:TRIGGERED_BY]->(t:Trigger)-[:RAISED_BY]->(r:Role) "
     "RETURN t.label AS trigger, r.label AS raised_by, t.description AS detail",
     "What triggers a CFG-RFC and who raises it (Process-[:TRIGGERED_BY]->Trigger-[:RAISED_BY]->Role)."),

    (r"\b(output|produce|deliverable|config\w* library|audit tool)\b",
     "MATCH (:Process)-[:PRODUCES]->(o:Output) "
     "OPTIONAL MATCH (o)-[b:UPDATES|AUDITS|DEPLOYS_TO]->(v:Version) "
     "RETURN o.label AS output, o.description AS detail, "
     "collect(type(b)+' '+coalesce(v.label,'')) AS bridges",
     "CFG-RFC outputs and how they bridge to the config standard versions (Output-[:UPDATES/AUDITS]->Version)."),

    (r"\b(bridge|connect\w*|link\w*)\b.*\b(config|version|standard|2014|2022)\b|"
     r"\bhow.*crfc.*(config|catalog)\w*\b",
     "MATCH (o:Output)-[r:UPDATES|AUDITS|DEPLOYS_TO]->(v:Version) "
     "RETURN o.label AS output, type(r) AS relationship, v.label AS version",
     "How the CFG-RFC process connects to the configuration catalogue (Output->Version)."),

    # ---- Config governance / drift (the two operating objectives) ----
    # OBJ-1: running Config Drift -> what is a deviation?
    (r"\b(deviation|drift)\b.*\b(type|kind|what)\w*|"
     r"\bwhat (is|are)\b.*\bdeviation|"
     r"\btypes? of deviation",
     "MATCH (:DriftTool)-[:DETECTS]->(dt:DeviationType) "
     "RETURN dt.label AS deviation_type, dt.description AS meaning",
     "The deviation types Config Drift reports (DriftTool-[:DETECTS]->DeviationType)."),

    (r"\b(severit|scoring|score|penalty|penalt)\w*",
     "MATCH (:DriftTool)-[:RANKS_BY]->(s:Severity) "
     "OPTIONAL MATCH (s)-[:AFFECTS]->(sc:Score) "
     "RETURN s.label AS severity, s.impact AS impact, coalesce(sc.label,'no score impact') AS affects",
     "Deviation severities and how they affect Config vs Health Score (Severity-[:AFFECTS]->Score)."),

    (r"\bconfig(uration)? drift\b|\bwhat.*(pcd|config drift)\b|\bdrift tool\b",
     "MATCH (t:DriftTool) OPTIONAL MATCH (t)-[:AUDITS]->(v:Version) "
     "RETURN t.label AS tool, t.version AS version, t.description AS detail, collect(v.label) AS audits_versions",
     "The PrIME Config Drift (PCD) tool and what it audits."),

    # OBJ-2: a new site config -> does it meet the standard? what impact?
    (r"\b(gate|governance|meet\w* (the )?(standard|requirement)|new config\w*|"
     r"design review|\bcar\b|\bchr\b|approv\w* (new )?config|impact)\b",
     "MATCH (g:Gate) OPTIONAL MATCH (g)-[r:RESOLVES_VIA|USES]->(x) "
     "RETURN g.label AS gate, g.description AS how, "
     "collect(type(r)+' '+coalesce(x.label,x.id)) AS links",
     "Governance gates that check whether a new site config meets the standard (Gate nodes)."),

    (r"\bmigration\b.*\b(categor|action|readiness)\w*|"
     r"\b(categor|action)\w*.*\bmigration\b|\b2014.*2022.*migrat\w*",
     "MATCH (:DriftTool)-[:HAS_MIGRATION_CATEGORY]->(m:MigrationCategory) "
     "RETURN m.label AS migration_category, m.description AS meaning",
     "Migration Readiness 2014->2022 categories that guide required actions."),

    (r"\b(deploy\w*|scdr|roll ?out|\bro\b|sscd)\b.*\b(2014|2022|path|config)\b|"
     r"\b(2014|2022)\b.*\bdeploy\w*|how.*deploy\w*.*config",
     "MATCH (d:DeploymentPath)-[:DEPLOYS]->(v:Version) "
     "RETURN d.label AS path, d.description AS how, v.label AS version",
     "How approved configuration is deployed in 2014 (SCDR) vs 2022 (DxC RO)."),

    (r"\b(central|site) config\w*|config\w* buckets?\b",
     "MATCH (b:ConfigBucket) RETURN b.label AS bucket, b.description AS rule",
     "The two configuration buckets: Central (Product Team) vs Site (SE/BPO)."),

    # ---- Config catalogue ----
    (r"\b(what|which|show|list).*\bchang\w*\b|\bchang\w*\b.*\b(2014|2022|between|renam)\w*|\brenam\w*\b",
     "MATCH (c:Change) "
     "OPTIONAL MATCH (c)-[:CHANGE_FROM]->(a) OPTIONAL MATCH (c)-[:CHANGE_TO]->(b) "
     "RETURN c.kind AS kind, a.label AS from_2014, b.label AS to_2022 "
     "ORDER BY kind LIMIT 100",
     "Captured changes between the 2014 and 2022 configuration standards (Change nodes)."),

    (r"\bsections?\b.*\b2022\b|\b2022\b.*\bsections?\b",
     "MATCH (s:Section {version:'2022'}) RETURN s.label AS section ORDER BY section",
     "Configuration sections in the 2022 standard."),
    (r"\bsections?\b.*\b2014\b|\b2014\b.*\bsections?\b",
     "MATCH (s:Section {version:'2014'}) RETURN s.label AS section ORDER BY section",
     "Configuration sections in the 2014 standard."),
    (r"\b(added|new)\b.*\b2022\b|\b2022\b.*\b(added|new)\b",
     "MATCH (s:Section)-[:ADDED_IN_2022]->(:Version) RETURN s.label AS added_section ORDER BY added_section",
     "Sections added in the 2022 standard."),
    (r"\b(removed|dropped|deleted)\b.*\b2022\b",
     "MATCH (s:Section)-[:REMOVED_IN_2022]->(:Version) RETURN s.label AS removed_section ORDER BY removed_section",
     "Sections removed in the 2022 standard."),

    (r"\bexceptions?\b",
     "MATCH (e:Exception) RETURN e.label AS exception, e.section AS section "
     "ORDER BY section, exception LIMIT 100",
     "Configuration exception rows."),

    # ---- RTCIS <-> PrIME ontology ----
    (r"\b(rtcis).*\b(prime|map)\w*|\bmap\w*\b.*\b(rtcis|prime)\b|\bontology\b",
     "MATCH (a:RTCISTable)-[r:MAPS_TO|RENAMED_TO|EVOLVES_TO]->(b:PrIMETable) "
     "RETURN a.label AS rtcis, type(r) AS relationship, b.label AS prime "
     "ORDER BY rtcis LIMIT 100",
     "RTCIS -> PrIME table mapping (ontology)."),

    (r"\btables?\b",
     "MATCH (t) WHERE t:RTCISTable OR t:PrIMETable "
     "RETURN labels(t)[0] AS kind, t.label AS name ORDER BY kind, name LIMIT 100",
     "RTCIS and PrIME tables in the ontology."),
]

# label synonyms for generic count/list fallback
LABEL_SYNONYMS = {
    "section": "Section", "sections": "Section",
    "column": "Column", "columns": "Column",
    "field": "Field", "fields": "Field",
    "exception": "Exception", "exceptions": "Exception",
    "change": "Change", "changes": "Change",
    "version": "Version", "versions": "Version",
    "stage": "Stage", "stages": "Stage", "status": "Stage", "statuses": "Stage",
    "role": "Role", "roles": "Role",
    "trigger": "Trigger", "triggers": "Trigger",
    "decision": "Decision", "decisions": "Decision",
    "deployment": "Deployment", "output": "Output", "outputs": "Output",
    "tool": "Tool", "tools": "Tool", "process": "Process",
    "table": "RTCISTable", "learning": "Learning", "learnings": "Learning",
    "rule": "KBRule", "rules": "KBRule",    "gate": "Gate", "gates": "Gate",
    "severity": "Severity", "severities": "Severity",
    "deviationtype": "DeviationType",
    "migrationcategory": "MigrationCategory",
    "deploymentpath": "DeploymentPath",
    "bucket": "ConfigBucket", "buckets": "ConfigBucket",}


def nl_to_cypher(q: str) -> tuple[str, str]:
    ql = q.strip().lower()
    # count intent takes priority ("how many exceptions", "number of changes")
    m = re.search(r"\b(how many|count|number of|total)\b\s+([a-z]+)", ql)
    if m:
        lbl = LABEL_SYNONYMS.get(m.group(2))
        if lbl:
            return (f"MATCH (n:{lbl}) RETURN count(n) AS `{lbl} count`",
                    f"Count of :{lbl} nodes.")
    for rx, cypher, why in NL_RULES:
        if re.search(rx, ql):
            return cypher, why
    # generic: "show/list X"
    m = re.search(r"\b(show|list|display|what are|give me)\b.*?\b([a-z]+)\b", ql)
    if m:
        lbl = LABEL_SYNONYMS.get(m.group(2))
        if lbl:
            return (f"MATCH (n:{lbl}) RETURN coalesce(n.label,n.id) AS name "
                    f"ORDER BY name LIMIT 100", f"List of :{lbl} nodes.")
    # bare label mention
    for word, lbl in LABEL_SYNONYMS.items():
        if re.search(rf"\b{word}\b", ql):
            return (f"MATCH (n:{lbl}) RETURN coalesce(n.label,n.id) AS name "
                    f"ORDER BY name LIMIT 100", f"List of :{lbl} nodes (matched '{word}').")
    raise ValueError("could not translate that question — try mentioning a label "
                     "(sections, changes, stages, roles, tables, exceptions) or ask "
                     "'how many X', 'the crfc lifecycle', 'who approves', 'rtcis to prime mapping'.")


EXAMPLES = [
    "What is a deviation in Config Drift?",
    "Which deviations are accepted by one site but open at other sites with the same config?",
    "Show deviation severities and scoring",
    "What governance gates check a new site config?",
    "Show the migration 2014 to 2022 categories",
    "How is config deployed in 2014 vs 2022?",
    "Show the CRFC lifecycle in order",
    "Who approves a change?",
    "How does CRFC connect to the config catalogue?",
    "What changed between 2014 and 2022?",
    "Show RTCIS to PrIME mapping",
    "How many exceptions?",
    "How many sections?",
]


# ----------------------------------------------------------- SharePoint cache ---
def sharepoint_pages(term: str | None):
    if not os.path.exists(SP_PAGES):
        return {"available": False, "pages": [],
                "note": "run sharepoint_reader.py --pages-only first"}
    with open(SP_PAGES, encoding="utf-8") as f:
        data = json.load(f)
    pages = data.get("pages", data if isinstance(data, list) else [])
    out = []
    for p in pages:
        title = (p.get("title") or "")
        fname = (p.get("file") or p.get("name") or "")
        url = p.get("url") or p.get("ServerRelativeUrl") or ""
        if term:
            hay = f"{title} {fname} {url} {p.get('text') or ''}".lower()
            if term.lower() not in hay:
                continue
        out.append({"title": title, "file": fname, "url": url,
                    "modified": p.get("modified"),
                    "chars": p.get("textLen") or p.get("chars")})
    out.sort(key=lambda x: (x["title"] or x["file"]).lower())
    return {"available": True, "count": len(out), "pages": out[:400]}


# ------------------------------------------------------- Config Drift compare ---
# Config Drift now reads deviations computed from the LIVE replica databases
# (replica_drift.py -> _replica_drift/deviations.json), indexed by
# site -> section -> {severity, deviation type}, and snapshots the live graph's
# :Section labels as the "standard". The Power BI export (data.xlsx / the PBI model)
# is used ONLY as an accuracy benchmark (replica_drift.py --compare-pbi), never as the
# source of the dashboard figures.
DRIFT_JSON = os.environ.get(
    "DRIFT_JSON",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "_replica_drift", "deviations.json"))
# Benchmark-only Power BI export path (kept for /health + accuracy comparison, not the source).
DRIFT_EXCEL_PATH = os.environ.get(
    "DRIFT_EXCEL_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "Config report", "data.xlsx"))

_DRIFT = {"loaded": False, "error": None, "sites": {}, "std": {}, "meta": {}}

# --------------------------------------------------- CRFC register graph (UI) ---
# crfc_register.py exports the change/exception register as a graph
# (crfc:CFGxxxx -[RAISED_AS]-> gate, -[FOR_SITE]-> Site, -[AT_REPLICA_SITE]-> ReplicaSite).
# The full graph (~1.6k nodes) is too dense for the mini-graph, so /crfc/graph
# returns a compact hub->ReplicaSite summary for rendering, and
# /crfc/graph/export returns the full normalized graph for JSON download.
CRFC_GRAPH_JSON = os.environ.get(
    "CRFC_GRAPH_JSON",
    os.path.join(BASE, "_replica_drift", "crfc_graph.json"))

_CRFC_G = {"loaded": False, "error": None, "raw": None, "mtime": 0.0}


def _crfc_graph_raw():
    """Load + cache crfc_graph.json, reloading if the file changed on disk."""
    try:
        if not os.path.exists(CRFC_GRAPH_JSON):
            _CRFC_G.update(loaded=False, error="crfc_graph.json not found — run crfc_register.py", raw=None)
            return None
        mt = os.path.getmtime(CRFC_GRAPH_JSON)
        if _CRFC_G["raw"] is None or mt != _CRFC_G["mtime"]:
            with open(CRFC_GRAPH_JSON, encoding="utf-8") as fh:
                _CRFC_G["raw"] = json.load(fh)
            _CRFC_G.update(loaded=True, error=None, mtime=mt)
            log(f"crfc_graph.json loaded ({_CRFC_G['raw'].get('counts')})")
        return _CRFC_G["raw"]
    except Exception as e:
        _CRFC_G.update(loaded=False, error=f"{type(e).__name__}: {e}", raw=None)
        log(f"ERROR loading crfc_graph.json: {type(e).__name__}: {e}")
        return None


def crfc_graph_summary():
    """Compact hub -> ReplicaSite graph for renderMiniGraph (few dozen nodes)."""
    g = _crfc_graph_raw()
    if g is None:
        return {"available": False, "error": _CRFC_G["error"]}
    nodes_by_id = {n["id"]: n for n in g.get("nodes", [])}
    # count CRFC per replica site via AT_REPLICA_SITE edges
    per_replica = {}
    for e in g.get("edges", []):
        if e.get("rel") == "AT_REPLICA_SITE":
            per_replica[e["dst"]] = per_replica.get(e["dst"], 0) + 1
    counts = g.get("counts", {})
    hub_id = "hub:cfgrfc"
    out_nodes = [{"id": hub_id, "props": {
        "label": "CFG-RFC Register", "type": "Register",
        "count": counts.get("nodes", 0)}}]
    out_edges = []
    # rank replica sites by CRFC count, keep all 31 (small)
    ranked = sorted(per_replica.items(), key=lambda kv: -kv[1])
    for rid, cnt in ranked:
        nd = nodes_by_id.get(rid, {})
        code = nd.get("label") or rid.split(":")[-1]
        out_nodes.append({"id": rid, "props": {
            "label": f"{code} ({cnt})", "type": "ReplicaSite",
            "code": code, "count": cnt}})
        out_edges.append({"src": hub_id, "dst": rid, "type": "AT_REPLICA_SITE"})
    crfc_n = sum(1 for n in g.get("nodes", []) if n.get("type") == "CRFC")
    return {"available": True,
            "counts": {"crfc": crfc_n, "sites": counts.get("sites", 0),
                       "replicaSites": counts.get("replicaSites", len(ranked)),
                       "edges": counts.get("edges", 0)},
            "generated": g.get("generated"),
            "graph": {"nodes": out_nodes, "edges": out_edges}}


def crfc_graph_full():
    """Full normalized graph (nodes: id+props, edges: src/dst/type) for download."""
    g = _crfc_graph_raw()
    if g is None:
        return {"available": False, "error": _CRFC_G["error"]}
    out_nodes = []
    for n in g.get("nodes", []):
        props = {k: v for k, v in n.items() if k not in ("id",)}
        props.setdefault("label", n.get("label") or n.get("id"))
        out_nodes.append({"id": n["id"], "props": props})
    out_edges = [{"src": e["src"], "dst": e["dst"], "type": e.get("rel", "REL")}
                 for e in g.get("edges", [])]
    return {"available": True, "generated": g.get("generated"),
            "counts": g.get("counts", {}),
            "graph": {"nodes": out_nodes, "edges": out_edges}}


# --------------------------------------------- Expert training loop (explainer) ---
def expert_examples_list():
    """Return the expert-verified examples + stats for the UI training panel."""
    try:
        ex = ef.load_examples()
        st = ef.stats()
        # trim verdict text for the list view
        rows = []
        for r in ex[-50:][::-1]:
            m = r.get("match", {})
            v = r.get("verdict", {})
            rows.append({
                "id": r.get("id"), "created": r.get("created"),
                "author": r.get("author"),
                "section": m.get("section"), "deviation_type": m.get("deviation_type"),
                "element": m.get("element"), "exception_code": m.get("exception_code"),
                "site": m.get("site"),
                "ai_class": v.get("ai_class"), "ai_criticality": v.get("ai_criticality"),
                "ai_explanation": v.get("ai_explanation"),
                "note": r.get("note")})
        return {"available": True, "stats": st, "examples": rows}
    except Exception as e:
        log(f"ERROR expert_examples_list: {type(e).__name__}: {e}")
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def expert_teach(body):
    """Persist one expert-verified example submitted from the UI."""
    rec = ef.add_example(
        section=body.get("section", ""),
        deviation_type=body.get("deviation_type", ""),
        element=body.get("element", ""),
        exception_code=body.get("exception_code", ""),
        site=body.get("site", ""),
        ai_class=body.get("ai_class", ""),
        ai_criticality=body.get("ai_criticality", "MEDIUM"),
        ai_explanation=body.get("ai_explanation", ""),
        ai_suggested_action=body.get("ai_suggested_action", ""),
        ai_citations=body.get("ai_citations", ""),
        note=body.get("note", ""),
        author=body.get("author", "expert"))
    return {"ok": True, "id": rec["id"], "stats": ef.stats()}


# --------------------------------------------- Expert standing rules (Layer-1) ---
def expert_rules_list():
    """Return the expert standing rules + stats for the UI training panel."""
    try:
        rl = ef.load_rules()
        rows = []
        for r in rl[-50:][::-1]:
            m = r.get("match", {})
            a = r.get("action", {})
            rows.append({
                "id": r.get("id"), "created": r.get("created"), "author": r.get("author"),
                "exception_code": m.get("exception_code"), "element": m.get("element"),
                "section": m.get("section"), "deviation_type": m.get("deviation_type"),
                "change_kind": m.get("change_kind"), "site": m.get("site"),
                "classify_as": a.get("classify_as"), "criticality": a.get("criticality"),
                "resolve": a.get("resolve"), "explanation": a.get("explanation")})
        return {"available": True, "stats": ef.rules_stats(), "rules": rows}
    except Exception as e:
        log(f"ERROR expert_rules_list: {type(e).__name__}: {e}")
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def expert_add_rule(body):
    """Persist one standing exception rule submitted from the UI."""
    rec = ef.add_rule(
        exception_code=body.get("exception_code", ""),
        element=body.get("element", ""),
        section=body.get("section", ""),
        deviation_type=body.get("deviation_type", ""),
        change_kind=body.get("change_kind", ""),
        site=body.get("site", ""),
        classify_as=body.get("classify_as", ""),
        criticality=body.get("criticality", "MEDIUM"),
        resolve=bool(body.get("resolve", True)),
        explanation=body.get("explanation", ""),
        suggested_action=body.get("suggested_action", ""),
        note=body.get("note", ""),
        author=body.get("author", "expert"))
    return {"ok": True, "id": rec["id"], "stats": ef.rules_stats()}


# --------------------------------------------- Change watch (inputs -> graph) ---
def change_status():
    """Report what changed in the watched inputs (register / SharePoint / drift CSVs)."""
    try:
        r = cw.scan()
        # trim the heavy 'current' fingerprint before returning to the UI
        r = {k: v for k, v in r.items() if k != "current"}
        return {"available": True, **r}
    except Exception as e:
        log(f"ERROR change_status: {type(e).__name__}: {e}")
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def change_apply(body):
    """Scan + rebuild the CFG-RFC graph if the register changed + refresh the baseline."""
    try:
        r = cw.apply_changes(auto_update=bool(body.get("update", True)))
        r = {k: v for k, v in r.items() if k != "current"}
        return {"available": True, **r}
    except Exception as e:
        log(f"ERROR change_apply: {type(e).__name__}: {e}")
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def _norm_sev(v):
    s = str(v or "").strip().lower()
    return s if s in ("high", "medium", "low", "accepted") else (s or "unknown")


def _sev_get(d):
    return {"high": d.get("high", 0), "medium": d.get("medium", 0),
            "low": d.get("low", 0), "accepted": d.get("accepted", 0)}


def _load_drift(graph):
    """Load + index the PBI export and snapshot the graph's standard sections."""
    if _DRIFT["loaded"]:
        return _DRIFT
    # 1) the "standard": Section labels present in the live graph (2014 / 2022)
    std = {}
    try:
        with graph.driver.session(default_access_mode="READ") as s:
            for r in s.run("MATCH (n:Section) RETURN n.label AS label, n.version AS version"):
                key = str(r["label"] or "").strip().lower()
                if key:
                    std.setdefault(key, set()).add(str(r["version"] or "").strip())
        _DRIFT["std"] = {k: sorted(x for x in v if x) for k, v in std.items()}
    except Exception as e:
        log(f"drift: could not read graph sections: {type(e).__name__}: {e}")
        _DRIFT["std"] = {}
    # 2) the PBI export
    # 2) the LIVE-REPLICA deviations (replica_drift.py output). PBI is benchmark-only.
    if not os.path.exists(DRIFT_JSON):
        _DRIFT.update(loaded=True,
                      error=f"live-replica deviations not found: {DRIFT_JSON} "
                            f"— run: python replica_drift.py --site <SITE> --mode migration")
        log(f"drift: {_DRIFT['error']}")
        return _DRIFT
    try:
        with open(DRIFT_JSON, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", []) if isinstance(data, dict) else (data or [])
        sites, total_rows = {}, 0
        for row in rows:
            site = str(row.get("Audited Site") or row.get("Audited Instance") or "").strip()
            if not site:
                continue
            total_rows += 1
            sec = str(row.get("Configuration Section") or "").strip() or "(unspecified)"
            sev = _norm_sev(row.get("Deviation Severity"))
            typ = str(row.get("Deviation Type") or "").strip() or "(unspecified)"
            S = sites.setdefault(site, {"total": 0, "sev": {}, "sections": {}})
            S["total"] += 1
            S["sev"][sev] = S["sev"].get(sev, 0) + 1
            e = S["sections"].setdefault(sec, {"total": 0, "sev": {}, "type": {}})
            e["total"] += 1
            e["sev"][sev] = e["sev"].get(sev, 0) + 1
            e["type"][typ] = e["type"].get(typ, 0) + 1
        _DRIFT.update(loaded=True, sites=sites,
                      meta={"rows": total_rows, "sites": len(sites),
                            "standardSections": len(_DRIFT["std"]),
                            "source": (data.get("source") if isinstance(data, dict) else "live-replica"),
                            "mode": (data.get("mode") if isinstance(data, dict) else None),
                            "generated": (data.get("generated") if isinstance(data, dict) else None),
                            "path": DRIFT_JSON})
        log(f"drift: indexed {total_rows} live-replica deviations · {len(sites)} sites · "
            f"{len(_DRIFT['std'])} standard sections")
    except Exception as e:
        _DRIFT.update(loaded=True, error=f"{type(e).__name__}: {e}")
        log(f"drift: load failed: {type(e).__name__}: {e}")
    return _DRIFT


def drift_sites():
    d = _DRIFT
    if d.get("error"):
        return {"available": False, "error": d["error"], "sites": []}
    out = []
    for site, S in d["sites"].items():
        sev = _sev_get(S["sev"])
        out.append({"site": site, "total": S["total"], **sev,
                    "actionable": sev["high"] + sev["medium"] + sev["low"]})
    out.sort(key=lambda x: (-x["actionable"], -x["total"], x["site"].lower()))
    return {"available": True, "count": len(out), "meta": d.get("meta", {}),
            "sites": out}


def drift_site(name):
    d = _DRIFT
    if d.get("error"):
        return {"available": False, "error": d["error"]}
    name = (name or "").strip()
    S = d["sites"].get(name)
    if S is None:  # tolerant match (collapse whitespace, case-insensitive)
        key = re.sub(r"\s+", " ", name).lower()
        for k, v in d["sites"].items():
            if re.sub(r"\s+", " ", k).lower() == key:
                S, name = v, k
                break
    if S is None:
        return {"available": False, "error": f"site not found: {name}"}
    std = d.get("std", {})
    sections, in_std = [], 0
    for sec, e in S["sections"].items():
        versions = std.get(sec.strip().lower(), [])
        if versions:
            in_std += 1
        sev = _sev_get(e["sev"])
        sections.append({"section": sec, "inStandard": bool(versions),
                         "versions": versions, "total": e["total"], **sev,
                         "actionable": sev["high"] + sev["medium"] + sev["low"],
                         "byType": e["type"]})
    sections.sort(key=lambda x: (-x["actionable"], -x["total"], x["section"].lower()))
    tot = _sev_get(S["sev"])
    return {"available": True, "site": name,
            "totals": {"total": S["total"], **tot,
                       "actionable": tot["high"] + tot["medium"] + tot["low"],
                       "sections": len(S["sections"]),
                       "sectionsInStandard": in_std},
            "sections": sections}


# ---------------------------------------------------------------- HTTP layer ---
class Handler(BaseHTTPRequestHandler):
    graph: Graph = None  # set on the class before serving

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code, html):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def log_message(self, fmt, *args):  # quieter access log
        log(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        try:
            path, _, qs = self.path.partition("?")
            params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
            params = {k: urllib.parse.unquote(v) for k, v in params.items()}
            if path == "/health":
                sp_cache = os.path.exists(SP_PAGES)
                return self._send(200, {"ok": True, "neo4j": True, "sharepoint_cache": sp_cache,
                                        "drift_source": "live-replica",
                                        "drift_replica": os.path.exists(DRIFT_JSON),
                                        "drift_benchmark_export": os.path.exists(DRIFT_EXCEL_PATH),
                                        "skillPlatform": sp.summary(),
                                        "time": datetime.datetime.now().isoformat()})
            if path == "/schema":
                return self._send(200, self.graph.schema())
            if path == "/examples":
                return self._send(200, {"examples": EXAMPLES})
            if path == "/graph/sample":
                lbl = params.get("label", "Stage")
                if not re.fullmatch(r"[A-Za-z_]+", lbl):
                    return self._send(400, {"error": "bad label"})
                lim = min(int(params.get("limit", 40)), 200)
                res = self.graph.read(
                    f"MATCH (n:{lbl})-[r]-(m) RETURN n,r,m LIMIT {lim}")
                return self._send(200, res)
            if path == "/sharepoint/pages":
                return self._send(200, sharepoint_pages(params.get("q")))
            if path == "/drift/sites":
                _load_drift(self.graph)
                return self._send(200, drift_sites())
            if path == "/drift/site":
                _load_drift(self.graph)
                return self._send(200, drift_site(params.get("name", "")))
            # ---- CRFC register graph (UI) ----
            if path == "/crfc/graph":
                return self._send(200, crfc_graph_summary())
            if path == "/crfc/graph/export":
                return self._send(200, crfc_graph_full())
            # ---- Expert training loop (Config Drift explainer) ----
            if path == "/explain/examples":
                return self._send(200, expert_examples_list())
            if path == "/explain/rules":
                return self._send(200, expert_rules_list())
            # ---- Change watch (register / SharePoint / drift CSV -> graph) ----
            if path == "/change/status":
                return self._send(200, change_status())
            # ---- Skill Platform modules ----
            if path == "/sp/summary":
                return self._send(200, sp.summary())
            if path == "/sp/skills":
                return self._send(200, sp.skills_list())
            if path == "/sp/skill":
                return self._send(200, sp.skill_detail(params.get("id", "")))
            if path == "/sp/apps":
                return self._send(200, sp.apps_list())
            if path == "/sp/app":
                return self._send(200, sp.app_get(params.get("id", "")))
            if path == "/sp/app/csv":
                return self._send(200, sp.app_csv_rows(params.get("id", "")))
            if path == "/sp/experts":
                return self._send(200, sp.experts_list())
            if path == "/sp/projects":
                return self._send(200, sp.projects_list())
            if path.startswith("/p/"):
                aid = path[3:].strip("/")
                html = sp.published_html(aid)
                if html is None:
                    return self._send(404, {"error": "not published", "id": aid})
                return self._send_html(200, html)
            return self._send(404, {"error": "not found", "path": path})
        except Exception as e:
            log(f"ERROR GET {self.path}: {type(e).__name__}: {e}")
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        try:
            body = self._body()
            if self.path == "/query":
                cypher = (body.get("cypher") or "").strip()
                if not cypher:
                    return self._send(400, {"error": "missing 'cypher'"})
                res = self.graph.read(cypher, body.get("params"))
                return self._send(200, {"cypher": cypher, **res})
            if self.path == "/nl":
                q = (body.get("q") or "").strip()
                if not q:
                    return self._send(400, {"error": "missing 'q'"})
                cypher, why = nl_to_cypher(q)
                res = self.graph.read(cypher)
                return self._send(200, {"question": q, "cypher": cypher,
                                        "explain": why, **res})
            # ---- Expert training loop (Config Drift explainer) ----
            if self.path == "/explain/teach":
                return self._send(200, expert_teach(body))
            if self.path == "/explain/rule":
                return self._send(200, expert_add_rule(body))
            # ---- Change watch: apply detected changes (rebuild graph on register change) ----
            if self.path == "/change/apply":
                return self._send(200, change_apply(body))
            # ---- Skill Platform modules (writes to local _skill_platform state) ----
            if self.path == "/sp/skills/install":
                return self._send(200, sp.skill_set_state(body.get("id", ""), installed=True))
            if self.path == "/sp/skills/uninstall":
                return self._send(200, sp.skill_set_state(body.get("id", ""), installed=False))
            if self.path == "/sp/skills/toggle":
                return self._send(200, sp.skill_set_state(body.get("id", ""),
                                                          enabled=bool(body.get("enabled"))))
            if self.path == "/sp/skills/create":
                return self._send(200, sp.skill_create(body.get("name", ""),
                                                       body.get("description", ""),
                                                       body.get("instructions", "")))
            if self.path == "/sp/app/save":
                return self._send(200, sp.app_save(body.get("id"), body.get("name"),
                                                   body.get("html"), body.get("csv"),
                                                   body.get("kind")))
            if self.path == "/sp/app/csv":
                return self._send(200, sp.app_csv_write(body.get("id", ""),
                                                        body.get("header", []),
                                                        body.get("rows", [])))
            if self.path == "/sp/app/publish":
                return self._send(200, sp.app_publish(body.get("id", ""),
                                                      bool(body.get("publish", True))))
            if self.path == "/sp/app/delete":
                return self._send(200, sp.app_delete(body.get("id", "")))
            if self.path == "/sp/expert/save":
                return self._send(200, sp.expert_save(body.get("expert", body)))
            if self.path == "/sp/expert/delete":
                return self._send(200, sp.expert_delete(body.get("id", "")))
            if self.path == "/sp/experts/seed":
                return self._send(200, sp.experts_seed(body.get("seed", [])))
            if self.path == "/sp/project/save":
                return self._send(200, sp.project_save(body.get("project", body)))
            if self.path == "/sp/project/delete":
                return self._send(200, sp.project_delete(body.get("id", "")))
            return self._send(404, {"error": "not found", "path": self.path})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            log(f"ERROR POST {self.path}: {type(e).__name__}: {e}")
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main() -> int:
    ap = argparse.ArgumentParser(description="Local Neo4j + SharePoint + NL bridge")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8737)
    args = ap.parse_args()

    Handler.graph = Graph()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"bridge listening on http://{args.host}:{args.port}")
    log("  GET  /health /schema /examples /graph/sample?label=Stage /sharepoint/pages?q=term")
    log("  GET  /drift/sites  /drift/site?name=NEM")
    log("  GET  /crfc/graph  /crfc/graph/export   (CRFC register graph + JSON export)")
    log("  GET  /explain/examples  /explain/rules   POST /explain/teach  /explain/rule")
    log("  GET  /change/status   POST /change/apply   (register/SharePoint/CSV change -> graph)")
    log("  GET  /sp/summary /sp/skills /sp/skill?id= /sp/apps /sp/app?id= /sp/experts /sp/projects")
    log("  GET  /p/{appId}   (published light-app)")
    log("  POST /sp/skills/{install,uninstall,toggle,create}  /sp/app/{save,csv,publish,delete}")
    log("  POST /sp/expert/save /sp/experts/seed /sp/project/save")
    log("  POST /query {cypher}   /nl {q}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("shutting down")
    finally:
        Handler.graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
