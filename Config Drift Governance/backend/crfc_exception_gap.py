"""
crfc_exception_gap.py  --  Find CRFCs in the register that are NOT linked to an
accepted site exception in the deviation layer, and export the gap for review.

Layers in Neo4j:
  Register :  (:CrfcReg {label:'CFGxxxx', decisionClass, requestStatus, site, replicaSites, ...})
  Bridge   :  (:CFG {code})-[:REGISTERED_AS]->(:CrfcReg)
  Deviation:  (:PcdSite)-[:HAS_DEVIATION {bucket}]->(:DevIdentity)-[:GOVERNED_BY]->(:CFG)

A CRFC is "exercised as an exception" when at least one site ACCEPTS a deviation
governed by its CFG.  This script finds the CRFCs that are registered but have
NO accepted linkage (the missing exceptionals), plus a breakdown of the fleet.
"""
import csv
import os
import sys
from datetime import datetime
from neo4j import GraphDatabase

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
os.makedirs(OUT_DIR, exist_ok=True)

uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
user = os.environ["NEO4J_USER"]
pwd = os.environ["NEO4J_PASSWORD"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


EXCEPTION_CLASSES = ("SITE_EXCEPTION", "TEMP_EXCEPTION", "ALLOWED_DEVIATION")


def main():
    drv = GraphDatabase.driver(uri, auth=(user, pwd))
    with drv.session() as s:
        # 0) sanity counts
        tot = s.run("MATCH (r:CrfcReg) RETURN count(r) AS n").single()["n"]
        linked_cfg = s.run(
            "MATCH (:CFG)-[:REGISTERED_AS]->(r:CrfcReg) RETURN count(DISTINCT r) AS n"
        ).single()["n"]
        log(f"register CRFCs: {tot}   with a bridged CFG node: {linked_cfg}")

        # 1) per-CRFC accepted / open site counts via full traversal
        q = """
        MATCH (r:CrfcReg)
        OPTIONAL MATCH (r)<-[:REGISTERED_AS]-(c:CFG)<-[:GOVERNED_BY]-(d:DevIdentity)
        OPTIONAL MATCH (sa:PcdSite)-[:HAS_DEVIATION {bucket:'accepted'}]->(d)
        OPTIONAL MATCH (so:PcdSite)-[ho:HAS_DEVIATION]->(d) WHERE ho.bucket <> 'accepted'
        RETURN r.label AS code,
               r.title AS title,
               r.decisionClass AS decisionClass,
               r.decisionStatus AS decisionStatus,
               r.requestStatus AS requestStatus,
               r.site AS site,
               r.replicaSites AS replicaSites,
               r.owner AS owner,
               count(DISTINCT c)  AS cfgNodes,
               count(DISTINCT d)  AS identities,
               count(DISTINCT sa) AS nAccepted,
               count(DISTINCT so) AS nOpen,
               collect(DISTINCT sa.name)[..12] AS acceptedSites
        ORDER BY code
        """
        rows = [dict(r) for r in s.run(q)]

    drv.close()

    for r in rows:
        r["hasCfgNode"] = r["cfgNodes"] > 0
        r["exercised"] = r["nAccepted"] > 0            # some site accepts it
        r["isExceptionClass"] = (r.get("decisionClass") or "") in EXCEPTION_CLASSES

    # ---- Buckets --------------------------------------------------------------
    # A) registered exception, but NO site accepts it  -> "missing exceptional"
    missing = [r for r in rows if r["isExceptionClass"] and not r["exercised"]]
    # B) registered exception with no bridge CFG node at all (identity never loaded)
    no_bridge = [r for r in rows if r["isExceptionClass"] and not r["hasCfgNode"]]
    # C) exercised but the accepting site is NOT in the register's declared scope
    scope_mismatch = []
    for r in rows:
        if not r["exercised"]:
            continue
        declared = {x.strip().upper() for x in (r.get("replicaSites") or "").split(",") if x.strip()}
        accepting = {(x or "").upper() for x in r["acceptedSites"]}
        # strip -SITH/-UAT suffixes for scope comparison
        acc_base = {a.split("-")[0] for a in accepting}
        if declared and not (declared & acc_base):
            scope_mismatch.append(r)

    log(f"missing exceptionals (exception class, 0 accepting site): {len(missing)}")
    log(f"  of which have NO bridge CFG node at all:                {len(no_bridge)}")
    log(f"exercised-but-out-of-declared-scope:                      {len(scope_mismatch)}")

    # class breakdown
    from collections import Counter
    by_class = Counter((r.get("decisionClass") or "UNSPECIFIED") for r in rows)
    exercised_by_class = Counter((r.get("decisionClass") or "UNSPECIFIED") for r in rows if r["exercised"])
    log("--- by decisionClass (total / exercised) ---")
    for k in sorted(by_class):
        log(f"  {k:20s} {by_class[k]:4d} / {exercised_by_class.get(k,0)}")

    # ---- Write the gap CSV ----------------------------------------------------
    out = os.path.join(OUT_DIR, "crfc_exception_gap.csv")
    cols = ["code", "decisionClass", "decisionStatus", "requestStatus", "site",
            "replicaSites", "owner", "hasCfgNode", "identities",
            "nAccepted", "nOpen", "acceptedSites", "title"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([
                r["code"], r.get("decisionClass"), r.get("decisionStatus"),
                r.get("requestStatus"), r.get("site"), r.get("replicaSites"),
                r.get("owner"), r["hasCfgNode"], r["identities"],
                r["nAccepted"], r["nOpen"], "; ".join(r["acceptedSites"]),
                (r.get("title") or "")[:180],
            ])
    log(f"wrote {out}  ({len(rows)} CRFC rows)")

    # ---- Print the missing exceptionals list ----------------------------------
    print("\n=== CRFCs registered as an exception but NOT accepted at any site ===")
    for r in sorted(missing, key=lambda x: x["code"]):
        print(f"  {r['code']:9s} [{r.get('decisionClass'):15s}] "
              f"site={r.get('site')!r:24s} bridged={r['hasCfgNode']} "
              f"open@{r['nOpen']}  :: {(r.get('title') or '')[:70]}")


if __name__ == "__main__":
    main()
