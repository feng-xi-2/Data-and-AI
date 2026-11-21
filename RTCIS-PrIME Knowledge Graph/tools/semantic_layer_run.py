"""Semantic layer (Timbr concept / mapping SQL of the semantic-layer repo) -> relationships/semantic_layer.json for build_graph.
    KG_SEMANTIC_LAYER_DIR=<osst-whs-semantic-layer checkout> python tools/semantic_layer_run.py
Mapped tables are linked only when the live replica catalog has them (benchmark/catalog.json); the rest are ExternalSource."""
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import semantic_layer as SL  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    root = os.environ.get("KG_SEMANTIC_LAYER_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not root:
        raise SystemExit("set KG_SEMANTIC_LAYER_DIR")
    files = [f for f in glob.glob(os.path.join(root, "**", "*.sql"), recursive=True)
             if "backup" not in f.lower() and "validation" not in f.lower()]
    concepts, mappings = [], []
    for f in sorted(files):
        text = open(f, encoding="utf-8", errors="replace").read()
        name = os.path.basename(f)
        if name.endswith("_Concept.sql") or name.endswith("_Concepts.sql"):
            concepts += SL.parse_concepts(text)
        if name.endswith("_Mapping_DDL.sql") or name.endswith("_Mappings_DDL.sql"):
            mappings += SL.parse_mappings(text)
    catalog = {e: set(t) for e, t in json.load(open(os.path.join(KIT, "benchmark", "catalog.json"), encoding="utf-8"))["engines"].items()}
    nodes, edges = SL.to_graph(concepts, mappings, catalog)
    for n in nodes:
        n["theme"] = "Europe NPI" if any(k in n.get("name", "") for k in ("npi", "disposal", "non_performing")) else "Flow Radar / warehouse"
    json.dump({"nodes": nodes, "edges": edges}, open(os.path.join(KIT, "relationships", "semantic_layer.json"), "w", encoding="utf-8"), indent=0)
    linked = Counter(e["dst"].split(":")[1] for e in edges if e["label"] == "MAPPED_FROM" and e["dst"].startswith("Table:"))
    print(f"{len(concepts)} concepts, {len(mappings)} mappings -> {Counter(n['label'] for n in nodes)}, {Counter(e['label'] for e in edges)}")
    print("MAPPED_FROM catalog tables by engine:", dict(linked), "| external:", sum(1 for n in nodes if n["label"] == "ExternalSource"))


if __name__ == "__main__":
    main()
