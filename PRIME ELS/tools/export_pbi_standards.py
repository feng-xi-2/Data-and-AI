"""Standard Power BI kit for the public repo: query templates per WMS engine + the skills to build a warehouse report.

    py tools/export_pbi_standards.py "<repo>/PBI Standard Kit"

Writes
  queries/PrIME_2014/<query>.sql, queries/PrIME_2022/<query>.sql
      every replica query of the kit (sql/new, sql/reference, the SQL inside sql/extracted/*.m) with the ENGINE tokens filled from
      config/engine_profiles.csv (schema, zone column, zone join, footprint view, location-type rules). SITE tokens stay as {TOKEN}
      placeholders - listed in the file header and explained in queries/TOKENS.md.
  skills/<skill>/...     hypercare-site-setup, wh-hypercare-kpi, data-replica-latency, pbi-build-standards
  README.md
Every file goes through tools/export_public.py sanitize() (servers, tenants, mail, paths, ids) and the secret check; the run stops
when a secret pattern is found.
"""
import csv
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from export_public import SECRET, local_ids, sanitize  # noqa: E402

TOKEN = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
SQL_IN_M = re.compile(r'SqlQuery\s*=\s*"((?:[^"]|"")*)"', re.S)
SKILLS = {
    "hypercare-site-setup": ROOT.parent / ".github" / "skills" / "hypercare-site-setup",
    "data-replica-latency": ROOT.parent / ".github" / "skills" / "data-replica-latency",
    "wh-hypercare-kpi": ROOT / "skill" / "wh-hypercare-kpi",
    "pbi-build-standards": ROOT / "skill" / "pbi-build-standards",
}
SKIP = re.compile(r"(^_|\.(log|txt|csv|json|xlsx|pbix|png|zip)$|__pycache__)", re.I)


def skill_dir(name, path):
    if path.is_dir():
        return path
    for p in Path.home().glob(f"OneDrive*/Desktop/M&M/.github/skills/{name}"):
        if p.is_dir():
            return p
    return None


def templates():
    """(name, sql template, source file) of every replica query of the kit."""
    for d in ("new", "reference"):
        for f in sorted((ROOT / "sql" / d).glob("*.sql")):
            yield f.stem, f.read_text(encoding="utf-8"), f"sql/{d}/{f.name}"
    for f in sorted((ROOT / "sql" / "extracted").glob("*.m")):
        m = SQL_IN_M.search(f.read_text(encoding="utf-8"))
        if m:
            yield f.stem.replace("%2F", "-"), m.group(1).replace('""', '"'), f"sql/extracted/{f.name}"


def render(sql, eng):
    for _ in range(3):                                 # engine tokens may contain tokens ({S} inside STO_ZONE_JOIN)
        sql = TOKEN.sub(lambda m: eng[m.group(1)] if m.group(1) in eng else m.group(0), sql)
    return sql


def main(argv):
    if not argv:
        sys.exit(__doc__)
    out = Path(argv[0])
    if out.exists():
        shutil.rmtree(out)
    ids = local_ids()
    engines = {r["WMS_Version"]: {k: v for k, v in r.items() if k not in ("WMS_Version", "Notes")}
               for r in csv.DictReader(open(ROOT / "config" / "engine_profiles.csv", encoding="utf-8-sig"))}
    notes = {r["WMS_Version"]: r["Notes"] for r in csv.DictReader(open(ROOT / "config" / "engine_profiles.csv", encoding="utf-8-sig"))}
    site_cols = next(csv.reader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig")))
    written, used_tokens, n_rules = [], {}, 0

    def put(rel, text):
        nonlocal n_rules
        text, k = sanitize(text, ids)
        n_rules += k
        if SECRET.search(text):
            sys.exit(f"STOP: secret-like text in {rel} - not exported")
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        written.append(rel)

    for name, sql, src in templates():
        for ver, eng in engines.items():
            body = render(sql, eng).strip("\n")
            toks = sorted(set(TOKEN.findall(body)))
            for t in toks:
                used_tokens.setdefault(t, set()).add(name)
            head = (f"-- {name} - {ver} replica (schema {eng['S']})\n"
                    f"-- Source: PRIME ELS Hypercare KPI kit, {src} (validated on the replicas with tools/validate_sql.py)\n"
                    f"-- Replace the site tokens before running: {', '.join('{' + t + '}' for t in toks) or 'none'} - see ../TOKENS.md\n"
                    f"-- Engine notes: {notes[ver]}\n\n")
            put(f"queries/{ver.replace(' ', '_')}/{name}.sql", head + body + "\n")
    rows = ["# Site tokens used by the query templates", "",
            "Engine tokens (schema, zone column, ...) are already filled per folder. Site tokens come from the site's row in the",
            "Sites tab / `config/site_config.csv` of the kit and are measured from the replica by `tools/profile_site.py` (see",
            "`skills/hypercare-site-setup/references/settings.md`).", "",
            "| Token | In site_config | Used by |", "|---|---|---|"]
    for t in sorted(used_tokens):
        rows.append(f"| `{{{t}}}` | {'yes' if t in site_cols else 'derived / default (Cfg_Engine, build)'} | {', '.join(sorted(used_tokens[t]))[:300]} |")
    put("queries/TOKENS.md", "\n".join(rows) + "\n")
    for name, path in SKILLS.items():
        src = skill_dir(name, path)
        if src is None:
            print(f"  !! skill {name} not found - left out")
            continue
        for f in src.rglob("*"):
            if f.is_file() and not SKIP.search(f.name) and "__pycache__" not in f.parts:
                put(f"skills/{name}/{f.relative_to(src).as_posix()}", f.read_text(encoding="utf-8", errors="replace"))
    readme = (ROOT / "skill" / "pbi-build-standards" / "KIT_README.md")
    put("README.md", readme.read_text(encoding="utf-8") if readme.exists() else "# PBI Standard Kit\n")
    n_sql = sum(1 for w in written if w.endswith(".sql"))
    print(f"{len(written)} files ({n_sql} query templates for {len(engines)} engines, {len(used_tokens)} site tokens), "
          f"{n_rules} sanitised values -> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
