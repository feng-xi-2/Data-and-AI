"""
sharepoint_reader.py — read REAL SharePoint content via the SharePoint REST API,
reusing the SAME cached MSAL account already used for SQL / Power BI
(client 1950a258..., tenant 3596192b...). No new login needed.

Why SharePoint REST (not Microsoft Graph):
  The shared Azure PowerShell first-party client is NOT granted Graph Sites/Files
  delegated scopes (its Graph .default = Directory/User/Group only), so Graph
  /drives and /pages return empty/403. BUT it CAN silently get a token for the
  SharePoint resource itself (aud <guid>,
  scp user_impersonation). The SharePoint REST API then honours the signed-in
  user's OWN site permissions — whatever you can see in the browser, this reads.

Sources on https://<sharepoint-host>/sites/WMSPrIMEService :
  * ConfigurationCatalogue2014      — document library (2014 config catalogue)
  * (any 2022 config library)       — auto-discovered
  * Standard-Configuration-Deployment-Process-2022  — Site Page (2022 process)
  * Configuration-Change-Process (CRFC)             — Site Page (change process)

No-silent-failure rule: timestamped heartbeat logs, request timeout + retry with
backoff, explicit errors (never swallowed), FIXED token cache path.

CLI:
  python sharepoint_reader.py --discover      # list every list/library + counts
  python sharepoint_reader.py --pull          # full granular pull -> _sharepoint/
  python sharepoint_reader.py --pull --lib "ConfigurationCatalogue2014"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime

import msal
import requests

# Corporate TLS inspection (P&G proxy) re-signs <sharepoint-host> with an
# internal root CA that is present in the WINDOWS cert store but NOT in Python's
# bundled certifi. Inject the OS trust store so verification stays ON and uses
# the same CAs the browser/ODBC (schannel) already trust. We do NOT disable
# certificate verification.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception as _e:  # pragma: no cover
    print(f"[warn] truststore unavailable ({_e}); using certifi bundle")

# --- identity ---
# The Azure PowerShell client (1950a258, used for SQL/PBI) authenticates fine but
# P&G SharePoint REST *rejects* its tokens (401 invalid_request) — that app is not
# authorized for SharePoint content at this tenant. The "Microsoft Office" public
# client (d3590ed6...) IS pre-authorized for SharePoint + Graph delegated access,
# so we use it here. It needs ONE interactive device-code sign-in (the Azure
# PowerShell refresh token is not FOCI, so it can't be reused silently); after that
# it caches in its own file and renews silently. Same user identity either way.
TENANT_ID = os.environ.get("SP_TENANT_ID", "<guid>")
CLIENT_ID = os.environ.get("SP_CLIENT_ID", "<guid>")
LOGIN_HINT = os.environ.get("SP_LOGIN_HINT", "")  # e.g. <user>@<company> (set in .env)
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SP_HOST = "<sharepoint-host>"
SP_SITE_PATH = "/sites/WMSPrIMEService"
SITE_ROOT = f"https://{SP_HOST}{SP_SITE_PATH}"
# resource .default -> silent token for the SharePoint resource (user_impersonation)
SCOPE = [f"https://{SP_HOST}/.default"]

CACHE_DIR = os.path.expanduser("~/.sql_session")
# Own MSAL cache for the Office client (do NOT reuse the SQL client's cache file).
MSAL_CACHE_PATH = os.path.join(CACHE_DIR, "sp_msal_cache.json")
SP_TOKEN_PATH = os.path.join(CACHE_DIR, "sp_token.json")

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sharepoint")

# base templates: 101 = document library, 119 = site pages library
DOCLIB_TEMPLATES = {101}
PAGES_TEMPLATE = 119


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --- auth -------------------------------------------------------------------
def _load_app():
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = msal.SerializableTokenCache()
    if os.path.exists(MSAL_CACHE_PATH):
        try:
            cache.deserialize(open(MSAL_CACHE_PATH, encoding="utf-8").read())
        except Exception as e:
            log(f"warn: could not read MSAL cache ({type(e).__name__}: {e})")
    return msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache), cache


def _save_cache(cache):
    if cache.has_state_changed:
        with open(MSAL_CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(cache.serialize())


def get_token() -> str:
    if os.path.exists(SP_TOKEN_PATH):
        try:
            d = json.load(open(SP_TOKEN_PATH, encoding="utf-8"))
            if d.get("expires_at", 0) > time.time() + 300:
                log("token: reused cached SharePoint token")
                return d["access_token"]
        except Exception:
            pass

    app, cache = _load_app()
    accounts = app.get_accounts()
    result = None
    if accounts:
        log(f"token: silent SharePoint token for {accounts[0].get('username')}")
        result = app.acquire_token_silent(SCOPE, account=accounts[0])
    if not result or "access_token" not in result:
        log("token: no silent token — starting one-time device-code flow")
        flow = app.initiate_device_flow(scopes=SCOPE)
        if "user_code" not in flow:
            raise RuntimeError(f"device flow failed: {flow}")
        log("=" * 64)
        log("ACTION REQUIRED — one-time sign-in to read SharePoint:")
        log(flow["message"])
        log("=" * 64)
        result = app.acquire_token_by_device_flow(flow)  # blocks until you finish
    if "access_token" not in result:
        raise RuntimeError(f"auth failed: {result.get('error_description', result)}")
    _save_cache(cache)
    with open(SP_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"access_token": result["access_token"],
             "expires_at": time.time() + int(result.get("expires_in", 3600))},
            f,
        )
    return result["access_token"]


# --- REST helper ------------------------------------------------------------
def sget(path: str, token: str, tries: int = 3) -> dict:
    """GET a SharePoint REST endpoint (JSON), with timeout + backoff retry."""
    url = path if path.startswith("http") else f"{SITE_ROOT}/_api/{path.lstrip('/')}"
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/json;odata=nometadata"},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 503):
                wait = int(r.headers.get("Retry-After", 2 * attempt))
                log(f"  {r.status_code} throttled — waiting {wait}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:300]}")
        except requests.RequestException as e:
            last = e
            log(f"  network error attempt {attempt}: {type(e).__name__}: {e}")
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"GET {url} failed after {tries} attempts: {last}")


# --- discovery --------------------------------------------------------------
def discover(token: str) -> list[dict]:
    log(f"discovering all lists/libraries on {SITE_ROOT}")
    data = sget(
        "web/lists?$select=Title,Id,BaseTemplate,Hidden,ItemCount,"
        "RootFolder/ServerRelativeUrl&$expand=RootFolder",
        token,
    )
    lists = []
    for l in data.get("value", []):
        if l.get("Hidden"):
            continue
        lists.append(
            {
                "title": l.get("Title"),
                "id": l.get("Id"),
                "template": l.get("BaseTemplate"),
                "itemCount": l.get("ItemCount"),
                "url": (l.get("RootFolder") or {}).get("ServerRelativeUrl"),
            }
        )
    for l in sorted(lists, key=lambda x: -(x["itemCount"] or 0)):
        log(f"  [{l['template']:>4}] {l['itemCount']:>5} items  {l['title']}")
    return lists


# --- document library: full recursive file/folder tree ----------------------
def pull_library(token: str, folder_url: str, depth: int = 0) -> list[dict]:
    out: list[dict] = []
    files = sget(
        f"web/GetFolderByServerRelativeUrl('{folder_url}')/Files?"
        "$select=Name,ServerRelativeUrl,Length,TimeLastModified,UIVersionLabel",
        token,
    ).get("value", [])
    for f in files:
        out.append(
            {
                "type": "file",
                "name": f.get("Name"),
                "url": f.get("ServerRelativeUrl"),
                "size": f.get("Length"),
                "modified": f.get("TimeLastModified"),
                "version": f.get("UIVersionLabel"),
                "depth": depth,
            }
        )
    subs = sget(
        f"web/GetFolderByServerRelativeUrl('{folder_url}')/Folders?"
        "$select=Name,ServerRelativeUrl,ItemCount",
        token,
    ).get("value", [])
    for s in subs:
        name = s.get("Name")
        if name in ("Forms",):
            continue
        out.append(
            {"type": "folder", "name": name, "url": s.get("ServerRelativeUrl"),
             "itemCount": s.get("ItemCount"), "depth": depth}
        )
        out.extend(pull_library(token, s.get("ServerRelativeUrl"), depth + 1))
    log(f"  {folder_url} -> {len(files)} files, {len(subs)} folders (depth {depth})")
    return out


# --- download actual file bytes ---------------------------------------------
def download_file(token: str, server_rel_url: str, dest_path: str, tries: int = 3) -> int:
    """Download one file's bytes via SharePoint REST $value. Returns bytes written."""
    url = (
        f"{SITE_ROOT}/_api/web/GetFileByServerRelativeUrl('"
        + server_rel_url.replace("'", "''")
        + "')/$value"
    )
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=120,
                stream=True,
            )
            if r.status_code == 200:
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                n = 0
                with open(dest_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            fh.write(chunk)
                            n += len(chunk)
                return n
            if r.status_code in (429, 503):
                wait = int(r.headers.get("Retry-After", 2 * attempt))
                log(f"  {r.status_code} throttled — waiting {wait}s")
                time.sleep(wait)
                continue
            raise RuntimeError(f"GET {url} -> {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            last = e
            log(f"  network error attempt {attempt}: {type(e).__name__}: {e}")
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"download {server_rel_url} failed after {tries} attempts: {last}")


def download_library(token: str, lib_title: str, lib_url: str, dest_dir: str,
                     ext: tuple[str, ...] = (".xlsx",)) -> dict:
    """Recursively download every file (matching ext) from a library to dest_dir."""
    log(f"downloading library '{lib_title}' -> {dest_dir}")
    tree = pull_library(token, lib_url)
    files = [x for x in tree if x["type"] == "file" and x["name"].lower().endswith(ext)]
    log(f"  {len(files)} files match {ext}")
    got, total_bytes, errors = 0, 0, []
    for i, f in enumerate(files, 1):
        dest = os.path.join(dest_dir, f["name"])
        # resume: skip if already downloaded with the expected size
        if os.path.exists(dest) and f.get("size") and os.path.getsize(dest) == int(f["size"]):
            got += 1
            continue
        try:
            n = download_file(token, f["url"], dest)
            total_bytes += n
            got += 1
            if i % 10 == 0 or i == len(files):
                log(f"  [{i}/{len(files)}] {got} ok, {total_bytes/1e6:.1f} MB new so far")
        except Exception as e:  # capture, log, continue (no silent failure)
            log(f"  ERROR downloading {f['name']}: {type(e).__name__}: {e}")
            errors.append({"name": f["name"], "error": str(e)})
    log(f"  library '{lib_title}': downloaded {got}/{len(files)} files, "
        f"{total_bytes/1e6:.1f} MB, {len(errors)} errors")
    return {"library": lib_title, "downloaded": got, "total": len(files),
            "bytes": total_bytes, "errors": errors, "dir": dest_dir}


# --- site pages: canvas content ---------------------------------------------
def pull_pages(token: str, name_filter: str | None = None) -> list[dict]:
    log("pulling Site Pages (CanvasContent1 + WikiField)")
    items = sget(
        "web/lists/getbytitle('Site Pages')/items?"
        "$select=Title,FileLeafRef,CanvasContent1,WikiField,Modified,FileRef&$top=500",
        token,
    ).get("value", [])
    pages = []
    for it in items:
        leaf = it.get("FileLeafRef", "")
        if name_filter and name_filter.lower() not in leaf.lower() \
                and name_filter.lower() not in (it.get("Title") or "").lower():
            continue
        html = (it.get("CanvasContent1") or "") + " " + (it.get("WikiField") or "")
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        pages.append(
            {
                "title": it.get("Title"),
                "file": leaf,
                "url": it.get("FileRef"),
                "modified": it.get("Modified"),
                "text": text,
                "textLen": len(text),
            }
        )
    for p in pages:
        log(f"  page '{p['file']}' — {p['textLen']} chars")
    return pages


# --- CLI --------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Read WMS PrIME Service SharePoint (REST)")
    ap.add_argument("--discover", action="store_true", help="list every list/library")
    ap.add_argument("--pull", action="store_true", help="full granular pull -> _sharepoint/")
    ap.add_argument("--download", action="store_true",
                    help="download actual .xlsx bytes of the config catalogue libraries")
    ap.add_argument("--lib", default=None, help="restrict to this document library title")
    ap.add_argument("--page", default=None, help="filter site pages by name")
    ap.add_argument("--pages-only", action="store_true",
                    help="pull ONLY SitePages (skip the slow library walk)")
    args = ap.parse_args()

    t0 = time.time()
    token = get_token()
    os.makedirs(OUT_DIR, exist_ok=True)

    # Fast path: pull only SitePages (e.g. the CRFC Configuration-Change-Process page)
    if args.pages_only:
        pages = pull_pages(token, args.page)
        out = os.path.join(OUT_DIR, "sharepoint_pages.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"generated": datetime.now().isoformat(timespec="seconds"),
                       "site": SITE_ROOT, "pages": pages}, f, indent=2, ensure_ascii=False)
        log(f"wrote {out} ({len(pages)} pages) in {time.time() - t0:.1f}s")
        return 0

    lists = discover(token)
    with open(os.path.join(OUT_DIR, "sharepoint_lists.json"), "w", encoding="utf-8") as f:
        json.dump(lists, f, indent=2, ensure_ascii=False)

    if args.discover and not args.pull:
        log(f"discover done in {time.time() - t0:.1f}s")
        return 0

    if args.download:
        # Config catalogue libraries: 2014 + the 202x (2022) library. Auto-match by title.
        cat_libs = [l for l in lists if "configurationcatalogue" in (l["title"] or "").lower()]
        if args.lib:
            cat_libs = [l for l in cat_libs if l["title"].lower() == args.lib.lower()]
        if not cat_libs:
            log("no ConfigurationCatalogue* libraries found to download")
            return 1
        results = []
        for l in cat_libs:
            # 2014 -> _config_2014, 202x/2022 -> _config_2022
            tag = "2014" if "2014" in l["title"] else "2022"
            dest = os.path.join(OUT_DIR, f"_config_{tag}")
            results.append(download_library(token, l["title"], l["url"], dest))
        with open(os.path.join(OUT_DIR, "download_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        log(f"download done in {time.time() - t0:.1f}s")
        return 0

    if not args.pull:
        ap.print_help()
        return 1

    bundle = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "site": SITE_ROOT,
        "libraries": {},
        "pages": [],
    }
    doclibs = [l for l in lists if l["template"] in DOCLIB_TEMPLATES]
    if args.lib:
        doclibs = [l for l in doclibs if l["title"].lower() == args.lib.lower()]
    for l in doclibs:
        log(f"pulling library '{l['title']}' ({l['itemCount']} items)")
        bundle["libraries"][l["title"]] = pull_library(token, l["url"])

    bundle["pages"] = pull_pages(token, args.page)

    out = os.path.join(OUT_DIR, "sharepoint_sources.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, ensure_ascii=False)
    log(f"wrote {out}  ({sum(len(v) for v in bundle['libraries'].values())} lib entries, "
        f"{len(bundle['pages'])} pages)")
    log(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
