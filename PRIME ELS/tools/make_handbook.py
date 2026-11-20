"""One package: PBI skills + queries for PrIME 2014 and 2022 + how to update + how to build - as a single offline HTML handbook and a zip.

    py tools/make_handbook.py [--examples JAKARTA,BINHDUONG]

Output (dist/_share):
  PRIME_ELS_Hypercare_Handbook.html   one self-contained file (no internet needed): every section, every query with a copy button
  PRIME_ELS_Hypercare_Handbook.zip    the HTML + skills/ + queries/ (PrIME_2014, PrIME_2022 templates, examples/<SITE>) + guides/ +
                                      config/ (engine profiles, production models, token reference) + inputs template
Everything is generated from the kit sources (config, sql, tools, docs, skill) - re-run after any change.
"""
import csv
import datetime
import html
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import markdown

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import validate_sql as V  # noqa: E402

OUT = ROOT / "dist" / "_share"
PKG = OUT / "PRIME_ELS_Hypercare_Handbook"
CFG = ROOT / "config"
args = sys.argv[1:]
EXAMPLES = (args[args.index("--examples") + 1].split(",") if "--examples" in args else None)


def hb(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def rows(name):
    with open(CFG / name, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def engine_tokens(engine):
    """Engine values resolved, every site setting left as {TOKEN} (the template for any site of that engine)."""
    site_cols = list(rows("site_config.csv")[0].keys())
    eng = next(r for r in rows("engine_profiles.csv") if r["WMS_Version"] == engine)
    tok = {c: "{" + c + "}" for c in site_cols}
    tok.update({k: "{" + k + "}" for k in ("START_DT", "START_YYYYMMDD", "LTA_MAP_VALUES")})
    tok.update(V.INC_DEFAULTS)
    tok.update({k: (v or "") for k, v in eng.items() if k not in ("WMS_Version", "Notes")})      # empty engine value = construct not used
    return tok


def sql_of(kind, body, tok):
    return V.render(V.sql_from_m(body, tok) if kind == "orig" else body, tok).strip() + "\n"


def tokens_left(sql):
    return sorted(set(re.findall(r"\{([A-Za-z_0-9]+)\}", sql)))


def md(path):
    return markdown.markdown(Path(path).read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])


def skill_md(path):
    t = Path(path).read_text(encoding="utf-8")
    t = re.sub(r"^---\n.*?\n---\n", "", t, flags=re.S)          # YAML front matter
    return markdown.markdown(t, extensions=["tables", "fenced_code"])


def main():
    hb("collecting queries")
    Q = V.queries()
    basis = {r["Table"]: r for r in rows("table_basis.csv")}
    engines = ["PrIME 2014", "PrIME 2022"]
    sites = rows("site_config.csv")
    examples = EXAMPLES or [next(s["SiteCode"] for s in sites if s["WMS_Version"] == e and s["Config_Status"].startswith(("VALIDATED", "AUTO")))
                            for e in engines]
    if PKG.exists():
        shutil.rmtree(PKG)
    (PKG / "queries").mkdir(parents=True)
    # ---- queries: engine templates + examples
    qsec = {}
    for e in engines:
        tok = engine_tokens(e)
        folder = PKG / "queries" / e.replace(" ", "_")
        folder.mkdir()
        items = []
        for name, (kind, body) in sorted(Q.items()):
            try:
                sql = sql_of(kind, body, tok)
            except Exception as ex:                       # report, never hide
                hb(f"  !! {e} {name}: {ex!r}"[:200])
                sql = f"-- could not render: {ex!r}\n"
            (folder / f"{name.replace('%2F', '-').replace('/', '-')}.sql").write_text(sql, encoding="utf-8")
            items.append((name, kind, sql))
        qsec[e] = items
        hb(f"  {e}: {len(items)} query templates")
    for code in examples:
        site, tok = V.tokens(code)
        folder = PKG / "queries" / "examples" / f"{code} ({site['WMS_Version']})"
        folder.mkdir(parents=True)
        for name, (kind, body) in sorted(Q.items()):
            (folder / f"{name.replace('%2F', '-').replace('/', '-')}.sql").write_text(sql_of(kind, body, tok), encoding="utf-8")
        hb(f"  example {code}: {len(Q)} rendered queries")
    # ---- token reference: every site setting, its meaning (skill reference) and the value per engine example
    ref = {}
    sref = ROOT / "skill" / "hypercare-site-setup" / "references" / "settings.md"
    for line in sref.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([A-Za-z_0-9*,/ ]+?)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", line)
        if m and not m.group(1).startswith(("Setting", "---")):
            for k in re.split(r"[,/+]\s*", m.group(1)):
                ref[k.strip()] = (m.group(2).strip(), m.group(3).strip())
    (PKG / "config").mkdir()
    with open(PKG / "config" / "TOKEN_REFERENCE.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Token", "Source", "Meaning"] + [f"Example {c}" for c in examples])
        ex_rows = {c: next(s for s in sites if s["SiteCode"] == c) for c in examples}
        for col in sites[0].keys():
            src, mean = ref.get(col, ("", ""))
            w.writerow([col, src, mean] + [ex_rows[c].get(col, "") for c in examples])
    for n in ("engine_profiles.csv", "production_models.csv", "page_guide.csv", "refresh_policy.csv", "shift_columns.csv"):
        shutil.copy(CFG / n, PKG / "config" / n)
    # ---- skills, guides, inputs template
    for sk in ("wh-hypercare-kpi", "hypercare-site-setup"):
        shutil.copytree(ROOT / "skill" / sk, PKG / "skills" / sk)
    (PKG / "guides").mkdir()
    for n in ("HOW_TO_USE.md", "HOW_TO_UPDATE.md", "HOW_TO_BUILD.md", "VALIDATION.md"):
        shutil.copy(ROOT / "docs" / n, PKG / "guides" / n)
    shutil.copy(ROOT / "README.md", PKG / "guides" / "README_kit.md")
    tpl = ROOT / "inputs" / "Hypercare_KPI_Inputs_TEMPLATE.xlsx"
    if tpl.exists():
        (PKG / "inputs").mkdir()
        shutil.copy(tpl, PKG / "inputs" / tpl.name)
    # ---- the HTML handbook
    hb("writing the HTML handbook")
    guide = rows("page_guide.csv")
    sec_rows = "".join(f"<tr><td>{html.escape(r['Section'].split(' ', 1)[-1])}</td><td><b>{html.escape(r['Page'])}</b></td>"
                       f"<td>{html.escape(r.get('Purpose', ''))}</td><td>{html.escape(r.get('How_Calculated', '')[:400])}</td></tr>" for r in guide)
    tok_rows = ""
    for col in sites[0].keys():
        src, mean = ref.get(col, ("", ""))
        tok_rows += (f"<tr><td><code>{{{html.escape(col)}}}</code></td><td>{html.escape(src)}</td><td>{html.escape(mean)}</td>"
                     + "".join(f"<td><code>{html.escape(next(s for s in sites if s['SiteCode'] == c).get(col, '')[:60])}</code></td>" for c in examples) + "</tr>")
    eng_rows = ""
    for r in rows("engine_profiles.csv"):
        for k, v in r.items():
            if k not in ("WMS_Version", "Notes") and v:
                eng_rows += f"<tr><td>{html.escape(r['WMS_Version'])}</td><td><code>{{{html.escape(k)}}}</code></td><td><code>{html.escape(v)}</code></td></tr>"
    qhtml = ""
    for e in engines:
        qhtml += f"<h3 id='q-{e[-4:]}'>{e} - {len(qsec[e])} queries</h3>"
        for name, kind, sql in qsec[e]:
            b = basis.get(name.replace("%2F", "/"), {})
            gate = V.GATE.get(name)
            left = tokens_left(sql)
            meta = (f"{'BD original feed (sql/extracted)' if kind == 'orig' else 'new feed (sql/new)'}"
                    f"{' | feature flag ' + gate if gate else ''}{' | ' + b.get('Basis', '') if b else ''}")
            qhtml += (f"<details><summary><b>{html.escape(name.replace('%2F', '/'))}</b> <span class='m'>{html.escape(meta)}</span></summary>"
                      f"<p class='m'>{html.escape(b.get('Meaning', ''))}</p>"
                      f"<p class='m'>Site settings used: {', '.join('<code>{' + html.escape(t) + '}</code>' for t in left) or 'none'}</p>"
                      f"<button onclick='cp(this)'>Copy SQL</button><pre>{html.escape(sql)}</pre></details>")
    skills_html = ""
    for sk, files in (("wh-hypercare-kpi", ["SKILL.md"]), ("hypercare-site-setup", ["SKILL.md", "references/settings.md"])):
        for fn in files:
            skills_html += f"<h3>{sk} / {fn}</h3><div class='box'>{skill_md(ROOT / 'skill' / sk / fn)}</div>"
    now = datetime.datetime.now()
    nav = [("overview", "1 Overview"), ("use", "How to use the report"), ("pages", "2 Pages"), ("update", "3 How to update"), ("build", "4 How to build"),
           ("skills", "5 Skills"), ("queries", "6 Queries 2014 / 2022"), ("tokens", "7 Token reference"), ("package", "8 Package contents")]
    css = """body{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#252423;overflow-x:hidden}nav{position:fixed;top:0;left:0;width:220px;height:100%;
background:#0B2A4A;color:#fff;padding:18px 12px;box-sizing:border-box;overflow:auto}nav a{display:block;color:#DCE6F2;text-decoration:none;
padding:7px 8px;border-radius:4px;font-size:14px}nav a:hover{background:#1F5FA8;color:#fff}nav h1{font-size:16px;margin:0 0 14px}
main{margin-left:220px;padding:24px 32px;box-sizing:border-box;width:calc(100% - 220px);max-width:1250px;min-width:0;overflow-wrap:anywhere}.box h1{font-size:20px;color:#0B2A4A}main h1{font-size:22px}td code,th code{white-space:normal}td:first-child{white-space:nowrap}h2{color:#0B2A4A;border-bottom:3px solid #1F5FA8;padding-bottom:4px;margin-top:40px}
h3{color:#1F5FA8}table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0;table-layout:auto}th,td{border:1px solid #D9DFE8;padding:5px 7px;
vertical-align:top;text-align:left}th{background:#0B2A4A;color:#fff}tr:nth-child(even) td{background:#F3F6FA}code{background:#EEF2F7;padding:1px 4px;
border-radius:3px;font-size:12px}pre{background:#0F1E2E;color:#E6EDF6;padding:12px;border-radius:6px;overflow:auto;font-size:12px;max-height:520px;max-width:100%;white-space:pre}pre code{background:transparent;color:inherit;padding:0;border-radius:0;font-size:inherit}
details{border:1px solid #D9DFE8;border-radius:6px;padding:6px 10px;margin:6px 0}summary{cursor:pointer}.m{color:#605E5C;font-size:12px}
button{background:#1F5FA8;color:#fff;border:0;border-radius:4px;padding:4px 10px;cursor:pointer;margin:6px 0}.box{border-left:4px solid #1F5FA8;
padding:4px 16px;background:#FAFBFD}.kpi{display:inline-block;background:#E6EDF6;border-radius:6px;padding:8px 14px;margin:4px;font-size:13px}"""
    js = """function cp(b){navigator.clipboard.writeText(b.nextElementSibling.innerText).then(()=>{b.innerText='Copied';setTimeout(()=>b.innerText='Copy SQL',1500)})}"""
    files = sorted(str(p.relative_to(PKG)).replace("\\", "/") for p in PKG.rglob("*") if p.is_file())
    body = f"""
<h2 id='overview'>1 Overview</h2>
<p><b>PRIME ELS Hypercare KPI</b> - one Power BI report for every PrIME 2014 / 2022 site in hypercare: throughput, trucks (TTAT, dock, staging),
production, storage, orders, people, alerts with targets, process mining and data health. The report is <b>generated</b> from configuration,
SQL and DAX sources (tools/build_pbip.py) - never edited by hand - so a fix in one place works for every site.</p>
<p><span class='kpi'>{len(sites)} sites configured</span><span class='kpi'>{len(Q)} replica queries</span>
<span class='kpi'>{len(guide)} pages in 7 process sections</span><span class='kpi'>2 engines: PrIME 2014 + 2022</span>
<span class='kpi'>generated {now:%d-%b-%Y %H:%M}</span></p>
<div class='box'>{md(ROOT / 'docs' / 'HOW_TO_BUILD.md').split('<h2')[0]}</div>
<h2 id='use'>How to use the report</h2>{md(ROOT / 'docs' / 'HOW_TO_USE.md')}
<h2 id='pages'>2 Pages (tab order = site process)</h2>
<p>Every page: navy title strip (Home button, site, section + page, refresh info) and the filter bar <b>Site | Day | Shift</b> (synced on every page;
Day blank = today's shift day, Shift blank = whole day). Desktop: <b>Ctrl + click</b> a button; Service: click.</p>
<table><tr><th>Section</th><th>Page</th><th>Answers</th><th>How it is calculated</th></tr>{sec_rows}</table>
<h2 id='update'>3 How to update</h2>{md(ROOT / 'docs' / 'HOW_TO_UPDATE.md')}
<h2 id='build'>4 How to build</h2>{md(ROOT / 'docs' / 'HOW_TO_BUILD.md')}
<h2 id='skills'>5 Skills (VS Code / Copilot)</h2>
<p>Copy the folders of <code>skills/</code> to <code>.github/skills/</code> of your workspace. <b>wh-hypercare-kpi</b>: build, validate and publish
the report; <b>hypercare-site-setup</b>: explore a replica, configure, add or remove a site.</p>{skills_html}
<h2 id='queries'>6 Queries for PrIME 2014 and PrIME 2022</h2>
<p>Engine differences are resolved (schema, zones, location types, inbound truck link); the remaining <code>{{TOKENS}}</code> are site
settings (section 7). Fully rendered examples for {', '.join(examples)}: <code>queries/examples/</code> in the zip.
Render for any configured site: <code>py tools/validate_sql.py &lt;SITE&gt;</code> (runs them) or <code>py tools/make_handbook.py --examples &lt;SITE&gt;</code>.</p>
<h3>Engine values</h3><table><tr><th>Engine</th><th>Token</th><th>Value</th></tr>{eng_rows}</table>
{qhtml}
<h2 id='tokens'>7 Token reference (site settings - config/site_config.csv)</h2>
<table><tr><th>Token</th><th>Source</th><th>Meaning</th>{''.join(f'<th>{c}</th>' for c in examples)}</tr>{tok_rows}</table>
<h2 id='package'>8 Package contents</h2><pre>{html.escape(chr(10).join(files + ['PRIME_ELS_Hypercare_Handbook.html']))}</pre>
"""
    page = (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>PRIME ELS Hypercare KPI - Handbook</title><style>{css}</style></head>"
            f"<body><nav><h1>PRIME ELS Hypercare KPI<br><span style='font-weight:normal;font-size:12px'>Handbook {now:%d-%b-%Y}</span></h1>"
            + "".join(f"<a href='#{i}'>{t}</a>" for i, t in nav)
            + "".join(f"<a href='#q-{e[-4:]}' style='padding-left:22px'>{e}</a>" for e in engines)
            + f"</nav><main>{body}</main><script>{js}</script></body></html>")
    (PKG / "PRIME_ELS_Hypercare_Handbook.html").write_text(page, encoding="utf-8")
    shutil.copy(PKG / "PRIME_ELS_Hypercare_Handbook.html", OUT / "PRIME_ELS_Hypercare_Handbook.html")
    z = OUT / "PRIME_ELS_Hypercare_Handbook.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in PKG.rglob("*"):
            if p.is_file():
                zf.write(p, Path(PKG.name) / p.relative_to(PKG))
    hb(f"DONE {OUT / 'PRIME_ELS_Hypercare_Handbook.html'} ({(OUT / 'PRIME_ELS_Hypercare_Handbook.html').stat().st_size // 1024} KB), "
       f"{z.name} ({z.stat().st_size // 1024} KB, {len(files) + 1} files)")


if __name__ == "__main__":
    main()
