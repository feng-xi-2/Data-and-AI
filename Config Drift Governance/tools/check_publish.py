"""Publish check for the PUBLIC copy of the PRIME ELS kit: fails (exit 1) when any file could expose a secret, a token, user access
information or an internal host. Runs locally inside tools/export_public.py and in the repository's GitHub Action on every pull request.

    python tools/check_publish.py <folder>        # e.g. "PRIME ELS"

Checks (patterns are generic - this file names no internal value):
  SECRET      password / client secret / API key / connection-string keys / SAS signatures with a value
  TOKEN       JWT access tokens, GitHub / Slack / AWS / Databricks personal tokens, private keys
  HOST        Azure SQL Managed Instance DNS zones, SharePoint / OneDrive URLs, Databricks workspace hosts
  IDENTITY    e-mail addresses (other than placeholders), local user profile paths
  GUID        ids that are not in ALLOWED_GUIDS (public Microsoft app ids / a uuid namespace) - workspace, tenant, model ids stay out
  BINARY      .pbix / .abf / .xlsx / .zip / .pfx / .pem files (data or keys), files over 2 MB
"""
import re
import sys
from pathlib import Path

ALLOWED_GUIDS = {
    "1950a258-227b-4e31-a9cf-717495945fc2",   # Microsoft Azure PowerShell - public client id (MSAL device code)
    "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d",   # Azure Databricks - Microsoft first-party resource id (token scope)
    "6d1b7a1e-0c55-4a8e-9b1e-5a1c0de0f001",   # uuid5 namespace of the kit (lineage tags / logical ids)
}
RULES = [
    ("SECRET", re.compile(r"(client_secret|password|passwd|pwd|api[_-]?key|AccountKey|SharedAccessKey|SharedAccessSignature|sig)\s*[:=]\s*['\"]?"
                          r"(?!<|\{|\$|os\.environ|None|null|\"\"|''|getenv)[A-Za-z0-9/+_\-=]{12,}", re.I)),
    ("TOKEN", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}"
                         r"|AKIA[0-9A-Z]{16}|dapi[0-9a-f]{32}|-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("HOST", re.compile(r"\.[0-9a-f]{12}\.database\.windows\.net|(?<![\w.])\.(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12}\b"
                        r"|[a-z0-9-]+(-my)?\.sharepoint\.com|adb-\d{6,}\.\d+\.azuredatabricks\.net", re.I)),
    ("IDENTITY", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!<|example\.|users\.noreply\.github\.com)[A-Za-z0-9-]+\.[A-Za-z]{2,}\b|[A-Za-z]:[\\/]Users[\\/](?!<)[^\\/\s\"']+", re.I)),
]
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
BINARY = re.compile(r"\.(pbix|abf|xlsx|xlsm|zip|pfx|pem|p12|key|bak)$", re.I)
TEXT = {".py", ".ps1", ".csv", ".md", ".sql", ".m", ".json", ".tmdl", ".yml", ".yaml", ".html", ".txt", ".dax", ".gitignore", ""}
EXAMPLE = re.compile(r"(?i)\b(user|name|someone|you)@")      # e.g. user@company placeholders in docs


def scan(root):
    hits = []
    for f in sorted(Path(root).rglob("*")):
        if not f.is_file() or ".git" in f.parts:
            continue
        rel = f.relative_to(root)
        if BINARY.search(f.name):
            hits.append((rel, 0, "BINARY", f.suffix))
            continue
        if f.stat().st_size > 2_000_000:
            hits.append((rel, 0, "BINARY", f"{f.stat().st_size / 1e6:.1f} MB"))
            continue
        if f.suffix.lower() not in TEXT:
            continue
        if f.name == Path(__file__).name:       # this file holds the patterns themselves
            continue
        for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for kind, rx in RULES:
                for m in rx.finditer(ln):
                    if kind == "IDENTITY" and EXAMPLE.search(m.group(0)):
                        continue
                    hits.append((rel, i, kind, m.group(0)[:60]))
            for g in GUID.findall(ln):
                if g.lower() not in ALLOWED_GUIDS:
                    hits.append((rel, i, "GUID", g))
    return hits


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    hits = scan(argv[0])
    for rel, i, kind, what in hits[:200]:
        print(f"  !! {kind:8s} {rel}:{i}  {what}")
    print(f"publish check: {len(hits)} finding(s) in {argv[0]}" + ("" if hits else " - clean (no secret, token, user access info or internal host)"))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
