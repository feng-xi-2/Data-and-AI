"""Publish the Config Drift Governance CODE (not its data) into the public repository, sanitised, then run the publish check.

    python export_config_drift_public.py <config-drift-governance dir> <repo folder>   e.g. ...\\Data-and-AI\\"Config Drift Governance"

Kept: backend *.py (no _diag_/_probe_ scratch), build.py, README, requirements, .env.example, docs, skills (SKILL.md), UI pages,
UI code assets (shell.js, bot.js, design-system.css, logo, the RTCIS <-> PrIME tab + its graph views exported from Cosmos).
Dropped: every AUTO-GENERATED data asset (site deviations, exception ledger, discovered config, change capture ...), the
Config report folder, caches, decision logs (*.jsonl), slide decks. Pages fall back to their offline state without them."""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from export_public import clear, put  # noqa: E402  (same masks: hosts, e-mails, user paths, GUIDs, Cosmos names)

KEEP_ASSETS = {"shell.js", "bot.js", "design-system.css", "logo.png", "rtcis-prime-tab.js", "rtcis-prime-views.js", "rtcis-prime-graph.js",
               "sql-remediation-dialog.js"}
SCRATCH = re.compile(r"^_(diag|probe|accuracy|verify|config_pages)", re.I)


def wanted(rel):
    p = rel.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    if any(s in p for s in ("__pycache__", "/.cache/", "Config report/")) or p.startswith((".cache/", "Config report/")):
        return False
    if name.endswith((".jsonl", ".pptx", ".xlsx", ".csv", ".pyc")) or name == ".env":
        return False
    if p.startswith("backend/"):
        return (name.endswith(".py") and not SCRATCH.match(name)) or name in (".env.example", "requirements.txt")
    if p.startswith(".github/skills/") or p.startswith("UIUX/skills/"):
        return name.endswith(".md")
    if p.startswith("UIUX/assets/"):
        return name in KEEP_ASSETS
    if p.startswith("UIUX/"):
        return name.endswith((".html", ".md"))
    if p.startswith("docs/"):
        return name.endswith((".md", ".html"))
    return "/" not in p and name in ("README.md", "build.py", "requirements.txt", ".env.example")


def main():
    src, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    if os.path.isdir(out):
        clear(out)
    kept = dropped = 0
    for dp, dirs, fs in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".cache")]
        for f in fs:
            rel = os.path.relpath(os.path.join(dp, f), src)
            if wanted(rel):
                put(os.path.join(dp, f), os.path.join(out, rel))
                kept += 1
            else:
                dropped += 1
    open(os.path.join(out, ".gitignore"), "w").write(".env\n.cache/\nConfig report/\n__pycache__/\n*.jsonl\n")
    note = ("\n\n## Published copy\n\nThis public copy holds the **code only**. Data assets under `UIUX/assets/` (site deviations, "
            "exception ledger, discovered configuration, change capture, graph snapshot) and the `Config report/` inputs are generated "
            "locally by `python build.py` from your own Config report and are not published. The **RTCIS \u2194 PrIME 2014 \u2194 2022** tab "
            "of `UIUX/knowledge-graph.html` works offline from `assets/rtcis-prime-views.js` (views exported from the Cosmos graph) and "
            "live with `tools/kg_api.py` of the `RTCIS-PrIME Knowledge Graph` folder. Internal host names are masked "
            "(`<sharepoint-host>`, `<replica-host>`): set your own in `backend/sharepoint_reader.py` (`SP_HOST`) and `backend/.env`.\n")
    readme = os.path.join(out, "README.md")
    open(readme, "a", encoding="utf-8", newline="\n").write(note)
    print(f"kept {kept} files, dropped {dropped}")
    chk = os.path.join(os.path.dirname(__file__), "check_publish.py")
    import shutil
    os.makedirs(os.path.join(out, "tools"), exist_ok=True)
    shutil.copy2(chk, os.path.join(out, "tools", "check_publish.py"))   # verbatim: masking would rewrite its own allow-list
    r = subprocess.run([sys.executable, chk, out], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-1000:])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
