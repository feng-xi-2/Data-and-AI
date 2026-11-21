"""Copy the SQL Remediation service (kit modules, agent instructions, runtime bundle) into an application's backend,
with a checksum manifest so the app can verify its copy was not edited by hand.

    python tools/export_aiapp.py <app backend package dir>
    e.g. ...\\_idecide_integ\\src\\base\\backend\\app\\sql_remediation_agent

Layout written:  kit/*.py (unchanged copies) · agent/ (AGENTS.md + skills) · bundle/ (export_runtime_bundle) ·
MANIFEST.json (sha256 per file) · VENDORED.md. Change the code here, in _kg_cosmos, never in the copy."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODULES = ["kg_core.py", "kg_assistant.py", "kg_deep_agent.py", "kg_services.py", "kg_runtime.py", "kg_api.py"]


def sha(path):
    """sha256 of the content with LF line endings: identical on a Windows (CRLF) and a Linux (LF) checkout."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    out = os.path.abspath(sys.argv[1])
    for d in ("kit", "agent", "bundle"):
        if os.path.isdir(os.path.join(out, d)):
            shutil.rmtree(os.path.join(out, d))
    os.makedirs(os.path.join(out, "kit"), exist_ok=True)
    for m in MODULES:
        shutil.copy2(os.path.join(KIT, "tools", m), os.path.join(out, "kit", m))
    shutil.copytree(os.path.join(KIT, "agent"), os.path.join(out, "agent"), ignore=shutil.ignore_patterns("__pycache__"))
    r = subprocess.run([sys.executable, os.path.join(KIT, "tools", "export_runtime_bundle.py"), os.path.join(out, "bundle")],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    print(r.stdout.strip())
    files = {}
    for d in ("kit", "agent", "bundle"):
        for dp, _, fs in os.walk(os.path.join(out, d)):
            for f in sorted(fs):
                p = os.path.join(dp, f)
                files[os.path.relpath(p, out).replace("\\", "/")] = sha(p)
    with open(os.path.join(out, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(sorted(files.items())), f, indent=1)
        f.write("\n")
    with open(os.path.join(out, "VENDORED.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Vendored: SQL Remediation service (RTCIS / PrIME 2014 / PrIME 2022 knowledge graph + LangGraph Deep Agent)\n\n"
                "Source of truth: the `RTCIS-PrIME Knowledge Graph` kit (`tools/`, `agent/`), published in "
                "feng-xi-2/Data-and-AI. Do not edit these files here: change the kit, run `tools/export_aiapp.py <this folder>`, "
                "and commit the result. `MANIFEST.json` holds a sha256 per file; `tests/unit/integrations/"
                "test_sql_remediation_inprocess.py` fails if a copy was edited.\n\n"
                "- `kit/` - kg_core (guard, routing, retrieval), kg_assistant, kg_deep_agent (deepagents.create_deep_agent), "
                "kg_services (Cosmos graph, replica endpoint, GenAI), kg_runtime (service-principal token, bundle), kg_api (HTTP API)\n"
                "- `agent/` - AGENTS.md (always loaded) + skills (loaded on demand)\n"
                "- `bundle/` - table index with theme / concept entries, live catalog columns, validated SQL templates, "
                "Cosmos load record\n")
    print(f"{len(files)} files + MANIFEST.json -> {out}")


if __name__ == "__main__":
    main()
