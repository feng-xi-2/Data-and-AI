"""Ontology conformance of the graph files: every vertex label is declared, every edge label is declared, both endpoints
exist and their labels are in the edge's domain / range (relationships/ontology.json). Exit 1 on any violation.

    python check_ontology.py [relationships folder]
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
import graphio  # noqa: E402


def main(folder):
    ont = json.load(open(os.path.join(folder, "ontology.json"), encoding="utf-8"))
    nodes, edges = graphio.load("nodes", folder), graphio.load("edges", folder)
    lab = {n["id"]: n["label"] for n in nodes}
    bad_v = Counter(n["label"] for n in nodes if n["label"] not in ont["vertices"])
    bad_e = Counter()
    for e in edges:
        dom, rng = ont["edges"].get(e["label"], (None, None))
        if dom is None:
            bad_e[f"undeclared edge {e['label']}"] += 1
        elif e["src"] not in lab or e["dst"] not in lab:
            bad_e[f"{e['label']} dangling endpoint"] += 1
        elif lab[e["src"]] not in dom or lab[e["dst"]] not in rng:
            bad_e[f"{e['label']} {lab[e['src']]}->{lab[e['dst']]}"] += 1
    print(f"{len(nodes)} nodes, {len(edges)} edges; vertex violations {dict(bad_v)}; edge violations {dict(bad_e)}")
    return 1 if bad_v or bad_e else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "relationships")))
