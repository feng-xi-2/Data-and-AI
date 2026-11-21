"""Copy the kit into the PUBLIC repository folder, sanitised, and run the publish check (exit 1 on any finding).

    python export_public.py <repo folder>      e.g. ...\\Data-and-AI\\"RTCIS-PrIME Knowledge Graph"

What is copied: tools (no sites.local.json / env.local.ps1 / token caches), templates, docs, ui, relationships (sharded),
benchmark (schema metadata, gold, predictions, validation, results - no data rows), knowledge (wiki pages + the two
reference guides + verified mappings) from WIKI_ROOT.
What is masked: replica / server host names, e-mail addresses, local user paths, the Cosmos account / resource group /
subscription names (they come from environment variables at run time).
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import graphio  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WIKI = os.environ.get("WIKI_ROOT", "")
TEXT = (".py", ".md", ".json", ".html", ".sql", ".yml", ".txt", ".ps1", ".js", ".gitignore")
MASKS = [
    (re.compile(r"\b[\w-]+\.[0-9a-f]{12}\.database\.windows\.net\b", re.I), "<replica-host>"),
    (re.compile(r"\bsql[a-z]{3}[a-z0-9]*?(?:prod|nonprod\d*)\b", re.I), "<replica-host>"),
    (re.compile(r"\bsql[a-z]{3}\{[a-z_]+\}[^'\"\s]*", re.I), "<replica-host>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com)(pg\.com|[a-z0-9-]+\.(com|net|org))\b", re.I), "<user>@<company>"),
    (re.compile(r"\{[A-Za-z_]+\}@pg\.com\b", re.I), "<user>@<company>"),
    (re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>]+", re.I), "<home>"),
    (re.compile(r"\b[\w-]+\.scm\.azurewebsites\.net\b", re.I), "<app-host>"),
    (re.compile(r"\bipa-nonprod-\d+\.pg\.com\b", re.I), "<platform-host>"),
    (re.compile(r"\b[\w-]+\.sharepoint\.com\b", re.I), "<sharepoint-host>"),
]
for env in ("KG_COSMOS_ACCOUNT", "KG_COSMOS_RG", "KG_COSMOS_SUB_NAME"):
    if os.environ.get(env):
        MASKS.append((re.compile(re.escape(os.environ[env]), re.I), f"<{env.lower()}>"))
SKIP = {"sites.local.json", "env.local.ps1", ".access_token.json", ".msal_cache.json"}


ALLOWED_GUIDS = {"1950a258-227b-4e31-a9cf-717495945fc2", "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"}   # public Microsoft app/resource ids
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def clean_text(t):
    for rx, rep in MASKS:
        t = rx.sub(rep, t)
    return GUID.sub(lambda m: m.group(0) if m.group(0).lower() in ALLOWED_GUIDS else "<guid>", t)


def put(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if src.endswith(TEXT) and os.path.basename(src) != "check_publish.py":   # the checker keeps its own allow-list verbatim
        open(dst, "w", encoding="utf-8", newline="\n").write(clean_text(open(src, encoding="utf-8", errors="replace").read()))
    else:
        shutil.copy2(src, dst)


def tree(src, dst, keep=lambda p: True):
    for dp, dirs, fs in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "parts")]
        for f in fs:
            p = os.path.join(dp, f)
            if f in SKIP or not keep(p):
                continue
            put(p, os.path.join(dst, os.path.relpath(p, src)))


def clear(out):
    """Remove every old file; a directory held open by a file watcher stays (empty) instead of aborting the export."""
    for dp, dirs, fs in os.walk(out, topdown=False):
        for f in fs:
            os.remove(os.path.join(dp, f))
        try:
            os.rmdir(dp)
        except OSError:
            pass


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    out = os.path.abspath(sys.argv[1])
    if os.path.isdir(out):
        clear(out)
    for d in ("tools", "templates", "docs", "ui", "tests", "agent"):
        tree(os.path.join(KIT, d), os.path.join(out, d))
    put(os.path.join(KIT, "README.md"), os.path.join(out, "README.md"))
    if os.path.exists(os.path.join(KIT, "tracker", "PRD.md")):   # delivery status per requirement (docs/PRD.md links it)
        put(os.path.join(KIT, "tracker", "PRD.md"), os.path.join(out, "tracker", "PRD.md"))
    rel = os.path.join(out, "relationships")
    put(os.path.join(KIT, "relationships", "ontology.json"), os.path.join(rel, "ontology.json"))
    for f in ("sdc_pmc_layer.json", "semantic_layer.json"):
        put(os.path.join(KIT, "relationships", f), os.path.join(rel, f))
    for kind in ("nodes", "edges"):
        items = json.loads(clean_text(json.dumps(graphio.load(kind), ensure_ascii=False)))
        print(kind, len(items), "->", graphio.shard(items, os.path.join(rel, "parts"), kind), "shards")
    b = os.path.join(out, "benchmark")
    for f in ("catalog.json", "gold.json", "predicted.json", "graph_validation.json", "results.json", "RESULTS.md",
              "cosmos_load_rtcis_prime.json", "sdc_pmc_validation.json", "cloud_batch_results.json", "cloud_batch_results_round1.json", "cloud_batch_results_round2.json",
                            "cloud_batch_results_deep_agent.json", "sdc_pmc_presence.json", "CLOUD_RESULTS.md",
              "cloud_batch_results_theme_before.json", "cloud_batch_results_theme_after.json", "cloud_batch_results_theme_after2.json",
              "cloud_batch_results_theme_stability.json", "cloud_batch_results_theme_v3_changed.json", "cloud_batch_results_theme_v3_zone.json"):
        if os.path.exists(os.path.join(KIT, "benchmark", f)):
            put(os.path.join(KIT, "benchmark", f), os.path.join(b, f))
    mv = json.load(open(os.path.join(KIT, "benchmark", "mapping_validation.json"), encoding="utf-8"))
    json.dump(mv["summary"], open(os.path.join(b, "mapping_validation_summary.json"), "w", encoding="utf-8"), indent=1)
    print("mappings", len(mv["mappings"]), "->", graphio.shard(json.loads(clean_text(json.dumps(mv["mappings"]))), os.path.join(b, "parts"), "mappings"), "shards")
    if WIKI:
        k = os.path.join(out, "knowledge")
        tree(os.path.join(WIKI, "wiki"), os.path.join(k, "wiki"), keep=lambda p: p.endswith(".md"))
        for f in ("AGENTS.md", "index.md", "log.md"):
            put(os.path.join(WIKI, f), os.path.join(k, f))
        for f in (("raw", "reference", "RTCIS-TO-PRIME-COMPLETE-REFERENCE.md"), ("raw", "kb", "PRIME-2014-TO-2022-REMEDIATION-GUIDE.md"),
                  ("raw", "schema", "verified-mappings.json"), ("queries", "field_notes.json")):
            put(os.path.join(WIKI, *f), os.path.join(k, "sources", f[-1]))
        for side in ("rtcis_tsql", "prime"):
            tree(os.path.join(WIKI, "queries", side), os.path.join(k, "queries", side))
    open(os.path.join(out, "tools", ".gitignore"), "w").write("sites.local.json\nenv.local.ps1\n.access_token.json\n.msal_cache.json\n__pycache__/\n")
    chk = os.path.join(out, "tools", "check_publish.py")
    r = subprocess.run([sys.executable, chk, out], capture_output=True, text=True)
    print(r.stdout[-3000:])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
