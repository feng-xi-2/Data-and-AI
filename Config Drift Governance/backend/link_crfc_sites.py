"""
link_crfc_sites.py -- Bridge the CFG-RFC register to the audited drift layer.

Problem: the register (:CrfcReg) knows each CFG-RFC's declared plant + replica
code, but those only connect to register-side (:Site)/(:ReplicaSite) nodes.
Only the 196 CRFCs cited in a site's accepted-deviation rationale reach the
audited (:PcdSite) layer (via CFG<-GOVERNED_BY<-DevIdentity<-HAS_DEVIATION).

This script links EVERY register CRFC that names a replica code to its matching
audited PcdSite(s) with:
    (:CrfcReg)-[:EXCEPTION_AT {decisionClass, requestStatus, viaReplica, reflected}]->(:PcdSite)
`reflected` = does that PcdSite actually ACCEPT a deviation governed by the CFG?

Then it reports the CRFCs that are NOT registered as an exception against the
site -- i.e. exception-class CRFCs that either (a) have no audited site to attach
to, or (b) attach to an audited site that does NOT reflect the exception in drift.
"""
import csv
import os
import re
from collections import defaultdict
from datetime import datetime
from neo4j import GraphDatabase

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
os.makedirs(OUT_DIR, exist_ok=True)

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ["NEO4J_USER"]
PWD = os.environ["NEO4J_PASSWORD"]

EXCEPTION_CLASSES = {"SITE_EXCEPTION", "TEMP_EXCEPTION", "ALLOWED_DEVIATION"}

# Deterministic replica-code -> audited-PcdSite prefix map.  A PcdSite whose
# normalised name (lowercased, spaces/hyphens removed) STARTS WITH any prefix
# is a match.  Variants (- SIT/- SITH/- UAT/2022) are picked up automatically.
REPLICA_TO_PCD_PREFIX = {
    "NEMC": ["nem"],
    "WCMC": ["wcmc"],
    "DALLAS": ["dallas"],
    "DAYTON": ["daytondymc", "dayton"],
    "GCFC": ["greaterchicagogcfc", "gcfc"],
    "SEFC": ["sefcboombox", "sefc"],
    "ALBANY": ["albany"],
    "ANDOVER": ["andover"],
    "BRANTFORD": ["brantford"],
    "TABLER": ["tabler"],
    "LIMA": ["lima"],
    "BOXELDER": ["boxelder"],
    "PHOENIX": ["phoenix"],
    "GREENSBORO": ["greensboro"],
    "CRAILSHEIM": ["crailsheim"],
    "ATHENS": ["athens"],
    "AMIENS_BB": ["amiensbb"],
    "AMIENS": ["amienskh"],
    "XIQING": ["xiqing"],
    "HUANGPU": ["huangpu"],
    "LUOGANG": ["luogang"],
    "TAICANG": ["taicang"],
    "MANDIDEEP": ["mandideep"],
    "JIJONA": ["arborajijona", "jijona"],
    "CABUYAO": ["cabuyao"],
    "LOUVEIRA": ["louveira"],
    "POMEZIA": ["pomezia"],
    "URLATI": ["urlati"],
    "MEHOOPANY": ["mehoopany"],
    "STLOUIS": ["stlouis"],
    "CAPEGIRARDEAU": ["capegirardeau"],
}


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def resolve_pcd(replica_codes, pcd_names):
    """Return the set of audited PcdSite names matched by any replica code."""
    hits = set()
    for code in replica_codes:
        prefixes = REPLICA_TO_PCD_PREFIX.get(code.strip().upper())
        if not prefixes:
            continue
        for name in pcd_names:
            nn = norm(name)
            if any(nn.startswith(p) for p in prefixes):
                hits.add(name)
    return hits


# ---------------------------------------------------------------------------
# Reusable graph operations (imported by build_graph.py so the whole linking
# stage lives in one place and the pipeline stays sustainable).
# ---------------------------------------------------------------------------
def bridge_registered_as(session):
    """(:CFG {code})-[:REGISTERED_AS]->(:CrfcReg {label}). Idempotent MERGE.

    Connects the deviation-layer CFG nodes to their governance register row so a
    single traversal spans register -> CFG -> DevIdentity -> PcdSite.
    Returns the number of REGISTERED_AS edges.
    """
    res = session.run(
        """
        MATCH (c:CFG)
        MATCH (r:CrfcReg {label: c.code})
        MERGE (c)-[rel:REGISTERED_AS]->(r)
        RETURN count(rel) AS n
        """
    ).single()
    return res["n"]


def link_exception_at(session):
    """Create (:CrfcReg)-[:EXCEPTION_AT {decisionClass, requestStatus, viaReplica,
    reflected}]->(:PcdSite) for every register CRFC that names a replica code
    resolving to an audited site.  `reflected` = the site actually ACCEPTS a
    deviation governed by that CFG.  Idempotent (deletes prior EXCEPTION_AT first).

    Returns (link_rows, crfcs) where link_rows is the list of edge dicts written
    and crfcs is every register CRFC with its decision metadata.
    """
    # audited sites (drop the junk "Applied filters" artefact row)
    pcd_names = [r["n"] for r in session.run("MATCH (p:PcdSite) RETURN p.name AS n")
                 if not (r["n"] or "").startswith("Applied filters")]
    log(f"audited PcdSite nodes: {len(pcd_names)}")

    crfcs = [dict(r) for r in session.run(
        """
        MATCH (r:CrfcReg:CRFC)
        RETURN r.label AS code, r.site AS site, r.replicaSites AS replicaSites,
               r.decisionClass AS decisionClass, r.requestStatus AS requestStatus,
               r.decisionStatus AS decisionStatus, r.owner AS owner, r.title AS title
        """
    )]
    log(f"register CRFCs: {len(crfcs)}")

    # PcdSite name -> set of CFG codes it ACCEPTS (via the deviation layer)
    accepts = defaultdict(set)
    for r in session.run(
        """
        MATCH (p:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(:DevIdentity)-[:GOVERNED_BY]->(c:CFG)
        RETURN p.name AS site, c.code AS code
        """
    ):
        accepts[r["site"]].add(r["code"])

    link_rows, linked_codes = [], set()
    for c in crfcs:
        codes = [x for x in (c.get("replicaSites") or "").split(",") if x.strip()]
        if not codes:
            continue
        for site in resolve_pcd(codes, pcd_names):
            link_rows.append({
                "code": c["code"], "site": site,
                "decisionClass": c.get("decisionClass") or "UNSPECIFIED",
                "requestStatus": c.get("requestStatus") or "",
                "viaReplica": ",".join(codes),
                "reflected": c["code"] in accepts.get(site, set()),
            })
            linked_codes.add(c["code"])
    log(f"EXCEPTION_AT links to write: {len(link_rows)} covering {len(linked_codes)} CRFCs")

    session.run("MATCH (:CrfcReg)-[e:EXCEPTION_AT]->(:PcdSite) DELETE e")
    session.run(
        """
        UNWIND $rows AS row
        MATCH (r:CrfcReg:CRFC {label: row.code})
        MATCH (p:PcdSite {name: row.site})
        MERGE (r)-[e:EXCEPTION_AT]->(p)
        SET e.decisionClass = row.decisionClass,
            e.requestStatus = row.requestStatus,
            e.viaReplica    = row.viaReplica,
            e.reflected     = row.reflected
        """,
        rows=link_rows,
    )
    made = session.run(
        "MATCH (:CrfcReg)-[e:EXCEPTION_AT]->(:PcdSite) RETURN count(e) AS c"
    ).single()["c"]
    log(f"EXCEPTION_AT edges now in graph: {made}")
    return link_rows, crfcs


def gap_analysis(link_rows, crfcs, write_csv=True):
    """Classify exception-class CRFCs into reflected / linked-but-not-reflected /
    unlinkable, and (optionally) export the gap CSV.  Returns a metrics dict."""
    by_code = defaultdict(list)
    for lr in link_rows:
        by_code[lr["code"]].append(lr)

    exc = [c for c in crfcs if (c.get("decisionClass") or "") in EXCEPTION_CLASSES]
    no_site = [c for c in exc if c["code"] not in by_code]
    not_reflected = [c for c in exc
                     if c["code"] in by_code
                     and not any(lr["reflected"] for lr in by_code[c["code"]])]
    reflected_ok = len(exc) - len(no_site) - len(not_reflected)

    log("=" * 66)
    log(f"exception-class CRFCs total:                 {len(exc)}")
    log(f"  (a) not linkable to any audited site:      {len(no_site)}")
    log(f"  (b) linked to a site but NOT reflected:    {len(not_reflected)}")
    log(f"  (c) reflected as accepted at its site:     {reflected_ok}")

    if write_csv:
        out = os.path.join(OUT_DIR, "crfc_not_registered_as_exception.csv")
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["code", "gap", "decisionClass", "requestStatus",
                        "declaredSite", "replicaSites", "linkedAuditedSites",
                        "owner", "title"])
            for c in sorted(no_site, key=lambda x: x["code"]):
                w.writerow([c["code"], "NO_AUDITED_SITE", c.get("decisionClass"),
                            c.get("requestStatus"), c.get("site"),
                            c.get("replicaSites"), "", c.get("owner"),
                            (c.get("title") or "")[:180]])
            for c in sorted(not_reflected, key=lambda x: x["code"]):
                sites = "; ".join(sorted({lr["site"] for lr in by_code[c["code"]]}))
                w.writerow([c["code"], "SITE_NOT_REFLECTED", c.get("decisionClass"),
                            c.get("requestStatus"), c.get("site"),
                            c.get("replicaSites"), sites, c.get("owner"),
                            (c.get("title") or "")[:180]])
        log(f"wrote {out}  ({len(no_site) + len(not_reflected)} gap CRFCs)")

    return {
        "exceptionCrfcs": len(exc),
        "reflected": reflected_ok,
        "linkedNotReflected": len(not_reflected),
        "unlinkable": len(no_site),
        "gapTotal": len(no_site) + len(not_reflected),
    }


def main():
    drv = GraphDatabase.driver(URI, auth=(USER, PWD), connection_timeout=15)
    drv.verify_connectivity()
    with drv.session() as s:
        n = bridge_registered_as(s)
        log(f"REGISTERED_AS edges (CFG->CrfcReg): {n}")
        link_rows, crfcs = link_exception_at(s)
    drv.close()
    gap_analysis(link_rows, crfcs, write_csv=True)


if __name__ == "__main__":
    main()
