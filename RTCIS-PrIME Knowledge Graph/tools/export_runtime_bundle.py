"""Write the runtime bundle an application ships instead of the full graph files and the wiki (see kg_runtime.py).

    python tools/export_runtime_bundle.py <out dir>     e.g. ...\\<app>\\sql_remediation_agent\\bundle

Contents: index.json (table index with descriptions + theme / concept entries + query templates), catalog.json (live
catalog columns per engine), templates.json (validated SQL templates), cosmos_load_rtcis_prime.json (load record: counts
per partition and edge type, exact-checked when the graph was loaded)."""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
import kg_runtime  # noqa: E402
import kg_services  # noqa: E402


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    out = os.path.abspath(sys.argv[1])
    os.environ.pop("KG_BUNDLE_DIR", None)          # build from the graph files, never from an older bundle
    index, cat, templates = kg_services.load_index_and_templates()
    import json
    record = json.load(open(os.path.join(kg_services.KIT, "benchmark", "cosmos_load_rtcis_prime.json"), encoding="utf-8"))
    if os.path.isdir(out):
        shutil.rmtree(out)
    kg_runtime.write_bundle(out, index, cat, templates, record)
    sizes = {f: os.path.getsize(os.path.join(out, f)) // 1024 for f in sorted(os.listdir(out))}
    print(f"{len(index)} index entries, {sum(len(t) for t in cat.values())} catalog tables, {len(templates)} templates -> {out} (KB: {sizes})")


if __name__ == "__main__":
    main()
