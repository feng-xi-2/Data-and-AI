"""Load a property graph (nodes.json + edges.json) into Azure Cosmos DB for Apache Gremlin - one graph per theme.

    python load_cosmos.py --graph rtcis_prime                       # relationships/nodes.json + edges.json
    python load_cosmos.py --graph config_drift --dir relationships/config_drift   # another theme, same database
    python load_cosmos.py --graph rtcis_prime --check               # exact presence check against the local files
    python load_cosmos.py --graph rtcis_prime --sync ../benchmark/last_loaded   # incremental: only the changes
    python load_cosmos.py --drop-database rtcis_prime_kg            # remove an old test database (asks no questions)

Layout (see docs/ARCHITECTURE.md): database KG_DB (default whs_kg) with SHARED autoscale throughput (max 1000 RU/s,
bills 100-1000), one graph container per theme, partition key /pk:
  Table / Column  -> pk = "<label>:<platform>"   (schema spread over the three engines)
  everything else -> pk = label
Account / resource group / subscription: env KG_COSMOS_ACCOUNT, KG_COSMOS_RG, KG_COSMOS_SUB_NAME (tools/azauth.py).
The account key is read through ARM listKeys at run time (signed-in user) and kept in memory only.
"""
import argparse
import asyncio
import json
import os
import sys
import threading
import time
import warnings
from concurrent.futures import wait, FIRST_COMPLETED

warnings.filterwarnings("ignore", category=DeprecationWarning)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from gremlin_python.driver import client, serializer  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
import azauth  # noqa: E402
import graphio  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB = os.environ.get("KG_DB", "whs_kg")
INFLIGHT = int(os.environ.get("KG_INFLIGHT", "24"))
RETRY = ("429", "RequestRateTooLarge", "408", "Timeout", "ServiceUnavailable", "1009", "Connection", "449")


def pk_of(n):
    return f"{n['label']}:{n.get('platform', '')}" if n["label"] in ("Table", "Column") else n["label"]


def wait_get(path, want=200, tries=90):
    for _ in range(tries):
        if azauth.arm("GET", path)[0] == want:
            return True
        time.sleep(4)
    return False


def ensure(graph, reset=False):
    p = azauth.account_path()
    dbp = f"{p}/gremlinDatabases/{DB}"
    if azauth.arm("GET", dbp)[0] != 200:
        st, out, _ = azauth.arm("PUT", dbp, {"properties": {"resource": {"id": DB}, "options": {"autoscaleSettings": {"maxThroughput": 1000}}}})
        print("create database", DB, st, flush=True)
        if not wait_get(dbp):
            raise SystemExit(f"database not created: {out}")
    gp = f"{dbp}/graphs/{graph}"
    if reset and azauth.arm("GET", gp)[0] == 200:
        print("reset: deleting graph", graph, azauth.arm("DELETE", gp)[0], flush=True)
        wait_get(gp, want=404)
    if azauth.arm("GET", gp)[0] != 200:
        st, out, _ = azauth.arm("PUT", gp, {"properties": {"resource": {"id": graph, "partitionKey": {"paths": ["/pk"], "kind": "Hash"}}}})
        print("create graph", graph, st, flush=True)
        if not wait_get(gp):
            raise SystemExit(f"graph not created: {out}")
        time.sleep(10)
    st, keys, _ = azauth.arm("POST", f"{p}/listKeys")
    if st != 200:
        raise SystemExit(f"listKeys {st}")
    return keys["primaryMasterKey"]


def connect(key, graph):
    return client.Client(f"wss://{azauth.ACCOUNT}.gremlin.cosmos.azure.com:443/", "g", username=f"/dbs/{DB}/colls/{graph}",
                         password=key, message_serializer=serializer.GraphSONSerializersV2d0(), pool_size=INFLIGHT, max_workers=INFLIGHT)


def run(c, q, b=None, tries=10):
    for i in range(tries):
        try:
            return c.submit(q, b or {}).all().result()
        except Exception as e:
            if i == tries - 1 or not any(x in str(e) for x in RETRY):
                raise
            time.sleep(min(15, 0.5 * 2 ** i))


def props(d):
    out = {}
    for k, v in d.items():
        if k in ("id", "label", "src", "dst") or v is None:
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        out[k] = v[:1500] if isinstance(v, str) else v
    return out


def bulk(c, jobs, what):
    """Run (query, bindings) jobs with INFLIGHT concurrent requests, retrying throttled ones."""
    pending, futs, done_n, failed, t0 = list(jobs), {}, 0, [], time.time()
    tries = {}
    lock = threading.Lock()
    while pending or futs:
        while pending and len(futs) < INFLIGHT:
            q, b = pending.pop()
            futs[c.submit_async(q, b)] = (q, b)
        finished, _ = wait(list(futs), return_when=FIRST_COMPLETED, timeout=120)
        for f in finished:
            q, b = futs.pop(f)
            try:
                f.result().all().result()
                done_n += 1
            except Exception as e:
                k = b.get("vid") or b.get("eid")
                with lock:
                    tries[k] = tries.get(k, 0) + 1
                if any(x in str(e) for x in RETRY) and tries[k] < 12:
                    time.sleep(min(5, 0.2 * tries[k]))
                    pending.append((q, b))
                else:
                    failed.append((k, str(e)[:200]))
        if done_n and done_n % 2000 < INFLIGHT:
            print(f"  {what} {done_n}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    print(f"  {what} done {done_n}/{len(jobs)} in {time.time() - t0:.0f}s, failed {len(failed)}", flush=True)
    return failed


def load(c, nodes, edges, pk=None):
    pk = {**(pk or {}), **{n["id"]: pk_of(n) for n in nodes}}
    vjobs = []
    for n in nodes:
        p = props(n)
        q = "g.addV(lbl).property('id', vid).property('pk', pk)" + "".join(f".property('{k}', p{j})" for j, k in enumerate(p))
        vjobs.append((q, {"lbl": n["label"], "vid": n["id"], "pk": pk[n["id"]], **{f"p{j}": v for j, v in enumerate(p.values())}}))
    failed = bulk(c, vjobs, "vertices")
    ejobs = []
    for e in edges:
        if e["src"] not in pk or e["dst"] not in pk:
            continue
        p = props(e)
        q = ("g.V(s).has('pk', sp).addE(lbl).property('id', eid).to(g.V(d).has('pk', dp))"
             + "".join(f".property('{k}', p{j})" for j, k in enumerate(p)))
        ejobs.append((q, {"s": e["src"], "sp": pk[e["src"]], "d": e["dst"], "dp": pk[e["dst"]], "lbl": e["label"], "eid": e["id"],
                          **{f"p{j}": v for j, v in enumerate(p.values())}}))
    failed += bulk(c, ejobs, "edges")
    return failed


def sync(c, prev_dir, cur_dir):
    """Incremental update: apply only the difference between the last loaded state and the new build (adds, property
    changes, removals) - minutes instead of a full reload, and the graph stays online."""
    pn = {n["id"]: n for n in graphio.load("nodes", prev_dir)}
    pe = {e["id"]: e for e in graphio.load("edges", prev_dir)}
    nodes, edges = graphio.load("nodes", cur_dir), graphio.load("edges", cur_dir)
    cn, ce = {n["id"]: n for n in nodes}, {e["id"]: e for e in edges}
    pk = {**{k: pk_of(v) for k, v in pn.items()}, **{k: pk_of(v) for k, v in cn.items()}}
    jobs = []
    for eid in pe.keys() - ce.keys() | {k for k in pe.keys() & ce.keys() if pe[k] != ce[k]}:
        e = pe[eid]
        jobs.append(("g.V().has('pk', sp).has('id', s).outE().has('id', eid).drop()", {"sp": pk[e["src"]], "s": e["src"], "eid": eid}))
    for vid in pn.keys() - cn.keys():
        jobs.append(("g.V().has('pk', p).has('id', vid).drop()", {"p": pk[vid], "vid": vid}))
    failed = bulk(c, jobs, "removals") if jobs else []
    add_v = [cn[k] for k in cn.keys() - pn.keys()]
    upd_v = [cn[k] for k in cn.keys() & pn.keys() if cn[k] != pn[k]]
    add_e = [ce[k] for k in ce.keys() - pe.keys() | {k for k in pe.keys() & ce.keys() if pe[k] != ce[k]}]
    vj = []
    for n in upd_v:
        p = props(n)
        vj.append(("g.V().has('pk', pk).has('id', vid)" + "".join(f".property('{k}', p{j})" for j, k in enumerate(p)),
                   {"pk": pk[n["id"]], "vid": n["id"], **{f"p{j}": v for j, v in enumerate(p.values())}}))
    failed += (bulk(c, vj, "vertex updates") if vj else []) + (load(c, add_v, add_e, pk) if add_v or add_e else [])
    print(f"sync: -{len(pe.keys() - ce.keys())} edges, -{len(pn.keys() - cn.keys())} vertices, +{len(add_v)} vertices, "
          f"~{len(upd_v)} vertices updated, +{len(add_e)} edges (incl. changed)", flush=True)
    return failed


def counts(c, nodes=None):
    """Exact presence check in chunks of 200 ids per partition: cheap requests the shared RU budget never throttles for long
    (a single count over a 12k-vertex partition costs more RU than the 1,000 RU/s ceiling)."""
    nodes = nodes or graphio.load("nodes")
    by_pk = {}
    for n in nodes:
        by_pk.setdefault(pk_of(n), []).append(n["id"])
    v, e = {}, {}
    for pk, ids in sorted(by_pk.items()):
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            v[pk] = v.get(pk, 0) + run(c, "g.V().has('pk', pk).has('id', within(ids)).count()", {"ids": chunk, "pk": pk})[0]
            e[pk] = e.get(pk, 0) + run(c, "g.V().has('pk', pk).has('id', within(ids)).outE().count()", {"ids": chunk, "pk": pk})[0]
    return v, {k: n for k, n in e.items() if n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="rtcis_prime")
    ap.add_argument("--dir", default=os.path.join(KIT, "relationships"), help="folder with nodes.json/edges.json or parts/")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sync", metavar="PREV_DIR", help="incremental: apply only the difference to the state loaded from PREV_DIR")
    ap.add_argument("--drop-database")
    a = ap.parse_args()
    if a.drop_database:
        path = f"{azauth.account_path()}/gremlinDatabases/{a.drop_database}"
        print("delete database", a.drop_database, azauth.arm("DELETE", path)[0])
        print("gone" if wait_get(path, want=404) else "still deleting")
        return
    key = ensure(a.graph, reset=not (a.check or a.sync))
    c = connect(key, a.graph)
    try:
        failed = []
        if a.sync:
            failed = sync(c, a.sync, a.dir)
        elif not a.check:
            failed = load(c, graphio.load("nodes", a.dir), graphio.load("edges", a.dir))
        if not a.check and not failed:   # remember what is now in Cosmos, for the next incremental sync
            last = os.path.join(KIT, "benchmark", "last_loaded")
            os.makedirs(last, exist_ok=True)
            for kind in ("nodes", "edges"):
                json.dump(graphio.load(kind, a.dir), open(os.path.join(last, f"{kind}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        v, e = counts(c, graphio.load("nodes", a.dir))
        print("cosmos", a.graph, "vertices", sum(v.values()), v, flush=True)
        print("cosmos", a.graph, "edges", sum(e.values()), e, flush=True)
        json.dump({"db": DB, "graph": a.graph, "loaded_at": time.strftime("%Y-%m-%d %H:%M"), "vertices": v, "edges": e,
                   "failed": failed[:50]}, open(os.path.join(KIT, "benchmark", f"cosmos_load_{a.graph}.json"), "w"), indent=1)
    finally:
        c.close()


if __name__ == "__main__":
    main()
