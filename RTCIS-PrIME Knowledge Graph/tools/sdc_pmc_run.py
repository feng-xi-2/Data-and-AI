"""Run the SDC / PMC layer against the REAL sources and databases, then write the PASS-only layer for build_graph.
    python tools/sdc_pmc_run.py
V1 live catalog (benchmark/catalog.json) -> V3 data presence: TOP 1 on the replica (RTCIS Euskirchen + London for RTCIS
tables, PrIME 2022 DE08 + Athens for PrIME tables; a table counts as populated if any site has a row).
Output: benchmark/sdc_pmc_validation.json (every check, incl. rejects) and relationships/sdc_pmc_layer.json."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import dbconn  # noqa: E402
import graphio  # noqa: E402
import sdc_pmc  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.environ.get("RTCIS_PRIME_TOKEN_DIR", "")
CAT = json.load(open(os.path.join(KIT, "benchmark", "catalog.json"), encoding="utf-8"))
PRESENCE_SITES = {"RTCIS": ["RTCIS_EUS", "RTCIS_LON"], "PrIME2022": ["PRIME22_DE08", "PRIME22_WMD1"]}


def presence(engine, table):
    out = {}
    for site in PRESENCE_SITES[engine]:
        loc = CAT["sites"][site]["tables"].get(table)
        if not loc:
            out[site] = "absent"
            continue
        db, schema = loc
        try:
            cur = dbconn.connect(site, database=db, timeout=60).cursor()
            cur.execute(f"SELECT TOP 1 1 FROM [{db}].[{schema}].[{table}]")
            out[site] = "rows" if cur.fetchone() else "empty"
        except Exception as e:
            out[site] = "error: " + str(e)[:120]
    return out


def main():
    script = open(os.path.join(SRC, "_build_sdc_prime_hierarchy.py"), encoding="utf-8").read()
    standards = json.load(open(os.path.join(SRC, "_mm_audit", "_sdc_pmc_standards.json"), encoding="utf-8"))
    layer = sdc_pmc.parse_sources(script, standards)
    catalog = {e: set(t) for e, t in CAT["engines"].items()}
    maps = {(e["src"].split(":", 2)[2], e["dst"].split(":", 2)[2]) for e in graphio.load("edges")
            if e["label"] == "MAPS_TO" and e["src"].startswith("Table:rtcis:") and e["dst"].startswith("Table:prime:")}
    checks = sdc_pmc.validate(layer, catalog, maps)

    t0 = time.time()
    cache_f = os.path.join(KIT, "benchmark", "sdc_pmc_presence.json")
    cache = {tuple(k.split("|")): v for k, v in json.load(open(cache_f, encoding="utf-8")).items()} if os.path.exists(cache_f) else {}
    for c in checks:
        if c["verdict"] != "PASS" or c["kind"] == "transformation":
            continue
        key = (c["engine"], c["object"])
        if key not in cache:
            cache[key] = presence(*key)
        c["presence"] = cache[key]
        c["populated"] = any(v == "rows" for v in cache[key].values())
    json.dump({"|".join(k): v for k, v in cache.items()}, open(cache_f, "w", encoding="utf-8"), indent=0)
    print(f"presence checked on {len(cache)} tables in {time.time() - t0:.0f}s", flush=True)

    nodes, edges = sdc_pmc.to_graph(layer, checks)
    sdc_pmc.annotate_presence(edges, checks)
    from collections import Counter
    summary = {"checks": dict(Counter((c["kind"], c["verdict"]) for c in checks).items()),
               "rejected": [c for c in checks if c["verdict"] != "PASS"],
               "pass_unpopulated": sorted({f"{c['engine']}.{c['object']}" for c in checks if c.get("populated") is False}),
               "presence_errors": {f"{k[0]}.{k[1]}": v for k, v in cache.items() if any(str(x).startswith("error") for x in v.values())},
               "transform_agreement": dict(Counter(c["detail"] for c in checks if c["kind"] == "transformation")),
               "pmc_without_standard_doc": sorted(p for p, v in layer["pmc"].items() if not v["source_file"]),
               "graph": {"nodes": dict(Counter(n["label"] for n in nodes)), "edges": dict(Counter(e["label"] for e in edges))}}
    summary["checks"] = {f"{k[0]} {k[1]}": v for k, v in summary["checks"].items()}
    json.dump({"summary": summary, "checks": checks}, open(os.path.join(KIT, "benchmark", "sdc_pmc_validation.json"), "w", encoding="utf-8"), indent=1)
    json.dump({"nodes": nodes, "edges": edges}, open(os.path.join(KIT, "relationships", "sdc_pmc_layer.json"), "w", encoding="utf-8"), indent=0)
    print(json.dumps({k: v for k, v in summary.items() if k != "rejected"}, indent=1))
    print("REJECTED:", [(c["subject"], c["object"], c["detail"]) for c in summary["rejected"]])


if __name__ == "__main__":
    main()
