"""Bundle for colleagues (GitHub Copilot in VS Code): how to use the report, the scripts, and the skills to update the PBI - one zip,
uploaded to the PRIME ELS SharePoint folder (never the PRISM 2 folders).

    py tools/make_copilot_bundle.py            # build dist/_share/PRIME_ELS_Hypercare_KPI_Copilot_Bundle.zip
    py tools/make_copilot_bundle.py --upload   # ... and upload it to the builders subfolder of the PRIME ELS folder (BUILDER_FOLDER)

Zip layout:
  START_HERE.md                       what is inside, 3 ways to use it
  1_HOW_TO_USE_THE_REPORT.md          report users (docs/HOW_TO_USE.md)
  2_HOW_TO_UPDATE.md / 3_HOW_TO_BUILD.md
  PRIME_ELS_Hypercare_Handbook.html   everything in one offline page (queries for PrIME 2014 / 2022 with copy buttons)
  report/                             ready-to-open site files (dist/_share/WH Hypercare KPI - <SITE>.zip)
  kit/                                the generator = the VS Code workspace for Copilot:
        .github/copilot-instructions.md   rules Copilot follows in this workspace
        .github/skills/<skill>/SKILL.md    hypercare-site-setup, wh-hypercare-kpi (Copilot loads them on demand)
        config/ sql/ tools/ docs/ theme/ skill/ _src_oct/(model + report source, no data) inputs/ README.md
Never packed: caches, logs, test output, personal tokens (the MSAL cache lives in %LOCALAPPDATA%, outside the kit), the BD .pbix with data.
"""
import datetime
import shutil
import sys
import time
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
OUT = ROOT / "dist" / "_share"
NAME = "PRIME_ELS_Hypercare_KPI_Copilot_Bundle"
KIT_DIRS = ["config", "sql", "tools", "docs", "theme", "skill", "inputs"]
SRC_KEEP = ["_src_oct/tmdl_original", "_src_oct/pbix/Report"]
SKIP_PARTS = {"__pycache__", ".pbi", "_sync_build"}
SKIP_FILES = {"_auto_refresh.log"}
# SharePoint layout (PRIME ELS / Hypercare KPI): users see the report .pbix + START HERE page; builder material sits one level down
BUILDER_FOLDER = "For report builders (optional)"


def hb(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def keep(p: Path):
    if SKIP_PARTS & set(p.parts) or p.name in SKIP_FILES:
        return False
    if p.name.startswith("_validate_") or p.suffix in (".log", ".pyc", ".lock"):
        return False
    return True


COPILOT_INSTRUCTIONS = """# Copilot instructions - PRIME ELS Hypercare KPI kit

This workspace GENERATES a Power BI report (PBIP: TMDL model + PBIR report) for PrIME 2014 / 2022 warehouse sites.
Use the skills in `.github/skills/`: **hypercare-site-setup** (explore a replica, add / remove / configure a site, thresholds) and
**wh-hypercare-kpi** (build, validate, publish, measures, pages, refresh).

Rules - always:
- Never edit `dist/` by hand: change config / sql / tools, then `py tools/build_pbip.py`. Fix generically for every site, never one visual.
- No site values or thresholds in code: site settings in `config/site_config.csv` (tokens such as `{WH_ID}`), engine differences in
  `config/engine_profiles.csv`, targets in the inputs file / `config/kpi_thresholds.csv` (measures use `thr("KEY")`).
- Users see numbers and plain words, never config names; every field has a unit; an empty field or visual needs a reason in
  `config/field_expectations.csv` / `config/visual_expectations.csv`.
- Validate before publishing: `py tools/validate_sql.py <SITE>` -> build (gates must pass) -> refresh -> `tools/run_full_tests.ps1`.
- Database queries: read-only, bounded windows (TOP / date filters), timeout <= 120 s; long work prints a heartbeat; never fail silently.
- PRIME ELS is not PRISM 2 ELS: the inputs live in SharePoint `Data Projects/PRIME ELS/Hypercare KPI` - never use PRISM 2 folders.
- Python: `py`. Power BI engine scripts (AMO / ADOMD) run under Windows PowerShell (`powershell.exe`).
"""

START_HERE = """# PRIME ELS Hypercare KPI - start here

Bundle built {date}. Three ways to use it:

## 1. I only want to USE the report
Read **START HERE - how to open the Hypercare report.pdf** in the SharePoint folder: open **`WH Hypercare KPI - ALL_SITES.pbix`**
(one file, data inside, no refresh - click it in SharePoint or download it). The zips in **report/** are per-site project files
for people who change the report.

## 2. I want to UPDATE the report with GitHub Copilot (VS Code)
1. Unzip, then in VS Code: **File → Open Folder → `kit`** (this folder is the workspace; Copilot reads `kit/.github/`).
2. Install once: Python 3.11+, `pip install pyodbc msal openpyxl pillow markdown requests truststore`, ODBC Driver 18 for SQL Server,
   Power BI Desktop.
3. Ask Copilot Chat in **Agent** mode, for example:
   * "Add the site <CODE> to the hypercare report" → uses the skill **hypercare-site-setup**
   * "Change the outbound TTAT target for <SITE> to 90 minutes" → inputs file + rebuild (targets are built into the file)
   * "Why does Trucks & TTAT show no staging lanes for <SITE>?" → profiles the replica with evidence
   * "Rebuild, test and publish the report" → uses the skill **wh-hypercare-kpi**
   Type `/` in the chat to see the skills; Copilot also loads them by itself when the question matches.
4. The rules Copilot follows are in `kit/.github/copilot-instructions.md` (generic fixes, no hard-coded values, validate before publish).

## 3. I want to understand / copy the queries
Open **PRIME_ELS_Hypercare_Handbook.html** (works offline): every query for **PrIME 2014** and **PrIME 2022** with a *Copy SQL* button,
the token reference (site settings), how to update and how to build.

## Where things live
| What | Where |
|---|---|
| Inputs file (sites + alert targets) | SharePoint *OSS warehousing data and GenAI* → Data Projects → **PRIME ELS** → Hypercare KPI → Hypercare_KPI_Inputs.xlsx |
| This bundle | same folder |
| Scripts | `kit/tools/` (`build_pbip.py`, `add_site.py`, `profile_site.py`, `validate_sql.py`, `run_full_tests.ps1`, `publish.py` ...) |
| Skills | `kit/.github/skills/` (also `kit/skill/`) |
"""


def main():
    stage = OUT / NAME
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "kit" / ".github" / "skills").mkdir(parents=True)
    hb("staging the kit")
    n = 0
    for d in KIT_DIRS + SRC_KEEP:
        for f in (ROOT / d).rglob("*"):
            rel = f.relative_to(ROOT)
            if f.is_file() and keep(rel):
                dst = stage / "kit" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
                n += 1
    shutil.copy2(ROOT / "README.md", stage / "kit" / "README.md")
    for sk in (ROOT / "skill").iterdir():
        if sk.is_dir():
            shutil.copytree(sk, stage / "kit" / ".github" / "skills" / sk.name)
    (stage / "kit" / ".github" / "copilot-instructions.md").write_text(COPILOT_INSTRUCTIONS, encoding="utf-8")
    hb(f"  kit: {n} files + .github (2 skills, copilot-instructions)")
    for src, dst in (("docs/HOW_TO_USE.md", "1_HOW_TO_USE_THE_REPORT.md"), ("docs/HOW_TO_UPDATE.md", "2_HOW_TO_UPDATE.md"),
                     ("docs/HOW_TO_BUILD.md", "3_HOW_TO_BUILD.md")):
        shutil.copy2(ROOT / src, stage / dst)
    hand = OUT / "PRIME_ELS_Hypercare_Handbook.html"
    if not hand.exists():
        raise SystemExit("handbook missing - run py tools/make_handbook.py first")
    shutil.copy2(hand, stage / hand.name)
    (stage / "report").mkdir()
    sites = sorted(OUT.glob("WH Hypercare KPI - *.zip"))
    if not sites:
        raise SystemExit("no site files in dist/_share - run py tools/make_packages.py first")
    for z in sites:
        shutil.copy2(z, stage / "report" / z.name)
    (stage / "START_HERE.md").write_text(START_HERE.format(date=f"{datetime.date.today():%d-%b-%Y}"), encoding="utf-8")
    zp = OUT / f"{NAME}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in stage.rglob("*"):
            if f.is_file():
                zf.write(f, Path(NAME) / f.relative_to(stage))
    files = sum(1 for f in stage.rglob("*") if f.is_file())
    hb(f"DONE {zp.name}: {files} files, {zp.stat().st_size / 1e6:.1f} MB")
    if "--upload" in sys.argv:
        upload(zp, BUILDER_FOLDER)
        # the rest of the builder material sits next to it (users only see the report .pbix + START HERE in the main folder)
        for f in [OUT / "PRIME_ELS_Hypercare_Handbook.html"] + sorted(OUT.glob("WH Hypercare KPI - *.zip")):
            upload(f, BUILDER_FOLDER)


def upload(zp: Path, subfolder: str = None):
    """Upload next to the inputs file (folder of config/inputs_source.csv SharePoint_Url), or into a subfolder of it, through Microsoft
    Graph (upload session; the subfolder is created by the path)."""
    import requests
    from urllib.parse import unquote, urlparse
    sys.path.insert(0, str(TOOLS))
    import inputs_file
    import replica_auth as A
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    url = inputs_file.source()["SharePoint_Url"]              # refuses PRISM 2 locations
    u = urlparse(url)
    parts = unquote(u.path).split("/")                        # /sites/<site>/Shared Documents/<folder...>/<file>
    site_path, folder = "/".join(parts[:3]), "/".join(parts[4:-1])
    if subfolder:
        folder = f"{folder}/{subfolder}"
    app, cache = A._load_msal_app()
    tok = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=app.get_accounts()[0])
    if not tok or "access_token" not in tok:
        raise SystemExit("no Microsoft Graph token - run any replica tool once to sign in, then retry")
    h = {"Authorization": "Bearer " + tok["access_token"]}
    G = "https://graph.microsoft.com/v1.0"

    def call(fn, what):
        # the corporate proxy drops connections now and then: retry every Graph / SharePoint call, never fail silently
        for attempt in range(1, 6):
            try:
                r = fn()
                if r.status_code < 500:
                    r.raise_for_status()
                    return r
                err = f"{r.status_code} {r.text[:120]}"
            except requests.exceptions.HTTPError:
                raise
            except requests.exceptions.RequestException as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
            if attempt == 5:
                raise SystemExit(f"{what} failed after 5 tries: {err}")
            hb(f"  retry {attempt}/4 {what} in {5 * attempt} s ({err[:80]})")
            time.sleep(5 * attempt)

    sid = call(lambda: requests.get(f"{G}/sites/{u.netloc}:{site_path}", headers=h, timeout=60), "site lookup").json()["id"]
    hb(f"uploading to SharePoint {folder}/{zp.name}")
    s = call(lambda: requests.post(f"{G}/sites/{sid}/drive/root:/{folder}/{zp.name}:/createUploadSession", headers=h,
                                   json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}, timeout=60), "upload session")
    up = s.json()["uploadUrl"]
    data, size, chunk = zp.read_bytes(), zp.stat().st_size, 10 * 320 * 1024
    for i in range(0, size, chunk):
        part = data[i:i + chunk]
        # a dropped connection (corporate proxy / TLS EOF) retries the same byte range - the upload session keeps what arrived
        for attempt in range(1, 6):
            try:
                r = requests.put(up, headers={"Content-Length": str(len(part)), "Content-Range": f"bytes {i}-{i + len(part) - 1}/{size}"},
                                 data=part, timeout=300)
                if r.status_code in (200, 201, 202):
                    break
                err = f"{r.status_code} {r.text[:200]}"
            except requests.exceptions.RequestException as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"
            if attempt == 5:
                raise SystemExit(f"upload failed at byte {i} after 5 tries: {err}")
            hb(f"  retry {attempt}/4 at byte {i} in {5 * attempt} s ({err[:80]})")
            time.sleep(5 * attempt)
        hb(f"  {min(i + chunk, size) / 1e6:.1f} / {size / 1e6:.1f} MB")
    item = r.json()
    hb(f"uploaded: {item.get('webUrl')} ({item.get('size')} bytes)")
    A._save_cache(cache)


if __name__ == "__main__":
    main()
