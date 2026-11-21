"""Publish the multi-site build (dist/ALL_SITES) to a Power BI / Fabric workspace via the Fabric item-definition REST API.

    py tools/publish.py                               # -> My workspace
    py tools/publish.py --workspace "WH Hypercare"
    py tools/publish.py --workspace "<workspace>" --bind-only [--name "<model name>"]
                                                      # after a Fabric Git sync: bind each site's gateway connection to the model

Auth: reuses the MSAL cache of the replica helper (silent). Creates or updates the semantic model + report,
then binds the report to the model. Credentials for the replica (OAuth2) must be set once per server in the
Service: semantic model > Settings > Data source credentials > Edit credentials > OAuth2.
"""
import base64
import json
import sys
import time
from pathlib import Path

import requests

try:  # corporate TLS inspection: trust the Windows certificate store
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replica_auth as auth  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAB = "https://api.fabric.microsoft.com/v1"


def token(scope="https://api.fabric.microsoft.com/.default"):
    app = auth._load_msal_app()[0]
    acc = app.get_accounts()
    r = app.acquire_token_silent([scope], account=acc[0]) if acc else None
    if not r or "access_token" not in r:
        raise SystemExit("No cached token - run any replica script once (device-code login) and retry")
    return r["access_token"]


def H():
    return {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}


def wait_lro(resp):
    if resp.status_code not in (202,):
        return resp
    loc = resp.headers.get("Location")
    while True:
        time.sleep(int(resp.headers.get("Retry-After", 5)))
        s = requests.get(loc, headers=H(), timeout=60)
        st = s.json().get("status") if s.content else None
        print("   LRO", st, flush=True)
        if st in ("Succeeded", "Failed", "Cancelled"):
            if st != "Succeeded":
                raise SystemExit(json.dumps(s.json(), indent=1)[:3000])
            r = requests.get(loc + "/result", headers=H(), timeout=60)
            return r if r.status_code < 300 else s


def _service_inputs(f: Path, data: bytes) -> bytes:
    """The Desktop build reads the OneDrive-synced inputs file (File.Contents); the Service has no access to a laptop path -> the
    published Cfg_TargetInput reads the same file from SharePoint (config/inputs_source.csv SharePoint_Url, OAuth2 once)."""
    if f.name not in ("Cfg_TargetInput.tmdl", "expressions.tmdl"):
        return data
    import csv as _csv
    import os as _os
    src = {r["Key"]: r["Value"] for r in _csv.DictReader(open(ROOT / "config" / "inputs_source.csv", encoding="utf-8-sig"))}
    local = _os.path.expandvars(src["Local_Path"]).replace('"', '""')
    url = src["SharePoint_Url"].replace('"', '""')
    t = data.decode("utf-8")
    if 'Book = "embedded"' in t or "Cfg_TargetInput_Src" in t and f.name == "Cfg_TargetInput.tmdl":
        return data                                # embedded targets / the M lives in the staging expression (stage_config_queries)
    if f.name == "expressions.tmdl" and f'File.Contents("{local}")' not in t:
        return data
    t2 = t.replace(f'File.Contents("{local}")', f'Web.Contents("{url}")').replace(f'Where = "{local}"', f'Where = "{url}"')
    if t2 == t and "Web.Contents" not in t:
        raise SystemExit("publish: Cfg_TargetInput source not recognised - rebuild with py tools/build_pbip.py")
    return t2.encode("utf-8")


def parts(folder: Path, skip=()):
    out = []
    for f in sorted(folder.rglob("*")):
        if f.is_file() and ".pbi" not in f.parts and f.name not in skip:
            out.append({"path": f.relative_to(folder).as_posix(), "payload": base64.b64encode(_service_inputs(f, f.read_bytes())).decode(),
                        "payloadType": "InlineBase64"})
    return out


def workspace_id(name):
    ws = requests.get(f"{FAB}/workspaces", headers=H(), timeout=60).json()["value"]
    if name is None:
        w = next((w for w in ws if w["type"] == "Personal"), None)
        if not w:
            raise SystemExit("Personal workspace not listed by the Fabric API")
    else:
        w = next((w for w in ws if w["displayName"].lower() == name.lower()), None)
        if not w:
            raise SystemExit(f"workspace {name!r} not found")
    return w["id"], w["displayName"]


UPDATED = {}


def upsert(ws, kind, name, definition):
    items = requests.get(f"{FAB}/workspaces/{ws}/{kind}", headers=H(), timeout=60).json().get("value", [])
    cur = next((i for i in items if i["displayName"] == name), None)
    if cur:
        print(f" update {kind} {name} ({cur['id']})", flush=True)
        UPDATED[kind] = True
        for attempt in range(13):   # 'Can't deploy as target because model is refreshing' (hourly schedule): wait for it, retry
            try:
                r = wait_lro(requests.post(f"{FAB}/workspaces/{ws}/{kind}/{cur['id']}/updateDefinition", headers=H(),
                                           json={"definition": definition}, timeout=300))
                if r.status_code >= 500 and attempt < 3:      # transient Service error (21-Nov: 500 InternalServerError) - retry
                    print(f"   HTTP {r.status_code} from the Service - retry in 60 s ({attempt + 1}/3)", flush=True)
                    time.sleep(60)
                    continue
                break
            except SystemExit as e:
                if "model is refreshing" not in str(e) or attempt == 12:
                    raise
                print(f"   the model is refreshing (schedule) - retry in 5 min ({attempt + 1}/12)", flush=True)
                time.sleep(300)
        if r.status_code >= 300:
            raise SystemExit(f"{r.status_code} {r.text[:2000]}")
        return cur["id"]
    print(f" create {kind} {name}", flush=True)
    r = wait_lro(requests.post(f"{FAB}/workspaces/{ws}/{kind}", headers=H(),
                               json={"displayName": name, "definition": definition}, timeout=300))
    if r.status_code >= 300:
        raise SystemExit(f"{r.status_code} {r.text[:2000]}")
    if r.content and r.json().get("id") and r.json().get("type"):
        return r.json()["id"]
    items = requests.get(f"{FAB}/workspaces/{ws}/{kind}", headers=H(), timeout=60).json().get("value", [])
    return next(i["id"] for i in items if i["displayName"] == name)


def bind_gateway(sm_id, sites):
    """Bind the model to each site's gateway connection (Cfg_Site.Gateway_Connection) this account can see; report the others."""
    conns, u = [], f"{FAB}/connections"
    while u:
        j = requests.get(u, headers=H(), timeout=60).json()
        conns += j.get("value", [])
        u = j.get("continuationUri")
    by_gw, msgs = {}, {}
    for row in sites:
        name = (row.get("Gateway_Connection") or "").split(" (")[0].strip()
        if name.startswith("("):
            name = ""
        c = next((c for c in conns if name and (c.get("displayName") or "").lower() == name.lower()), None)
        if not c:   # any shared gateway connection to the same replica server + database (e.g. ZONING-AVR-JAKARTA, 20-Nov)
            want = f"{row.get('ReplicaServer', '').split(',')[0].lower()};{row.get('ReplicaDatabase', '').lower()}"
            c = next((c for c in conns if c.get("connectivityType") == "OnPremisesGateway"
                      and ((c.get("connectionDetails") or {}).get("path") or "").lower() == want), None)
            if c:
                name = c.get("displayName") or c["id"]
        if not c:
            msgs[row["SiteCode"]] = (f"'{name}' not shared with this account - ask the replica owner to add you, then re-run publish" if name else
                                     f"no gateway connection to {row.get('ReplicaServer')};{row.get('ReplicaDatabase')} is shared with this account")
            continue
        by_gw.setdefault(c.get("gatewayId"), []).append((row["SiteCode"], c["id"], name))
    pbi = {"Authorization": "Bearer " + token("https://analysis.windows.net/powerbi/api/.default"), "Content-Type": "application/json"}
    for gw, items in by_gw.items():
        r = requests.post(f"https://api.powerbi.com/v1.0/myorg/datasets/{sm_id}/Default.BindToGateway", headers=pbi,
                          json={"gatewayObjectId": gw, "datasourceObjectIds": [i[1] for i in items]}, timeout=120)
        for code, _, name in items:
            msgs[code] = f"bound to '{name}'" if r.status_code < 300 else f"bind failed {r.status_code} {r.text[:200]}"
    return msgs


def service_name(base, wsdisp):
    """Display name in the target workspace: config/publish_names.csv (Workspace, Display_Name) or the file name.
    Lets a shared workspace hold this build under a suffixed name (e.g. 'WH Hypercare KPI-<copy>') next to other people's copies."""
    import csv
    f = ROOT / "config" / "publish_names.csv"
    if f.exists():
        for row in csv.DictReader(open(f, encoding="utf-8-sig")):
            if (row.get("Workspace") or "").strip().lower() == (wsdisp or "").lower() and (row.get("Display_Name") or "").strip():
                return row["Display_Name"].strip()
    return base


def bind_only(wsname, name, codes=None):
    """After a Fabric Git sync (the workspace created / updated the model from the repo): find the model by name, bind each site's
    gateway connection, set the refresh schedule, and report what is still missing. Never changes the model definition."""
    from pbi_common import report_sites
    ws, wsdisp = workspace_id(wsname)
    items = requests.get(f"{FAB}/workspaces/{ws}/semanticModels", headers=H(), timeout=60).json().get("value", [])
    sm = next((i["id"] for i in items if i["displayName"] == name), None)
    if not sm:
        raise SystemExit(f"semantic model {name!r} not in workspace {wsdisp} - sync the workspace from Git first "
                         f"(models there: {', '.join(i['displayName'] for i in items)})")
    print(f"workspace: {wsdisp} | model {name} ({sm})", flush=True)
    import csv
    rows = report_sites() if not codes else [r for r in csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig"))
                                             if r["SiteCode"] in codes]
    gw = bind_gateway(sm, rows)
    for k, v in gw.items():
        print(f" gateway {k}: {v}", flush=True)
    ok = all(v.startswith("bound") for v in gw.values())
    print("all sites bound - start a refresh in the Service (or wait for the schedule)" if ok else
          "NOT all sites bound - the refresh will fail for the sites above until their connection is shared with this account")
    return 0 if ok else 1


def main():
    import csv
    from pbi_common import report_sites
    args = sys.argv[1:]
    wsname = args[args.index("--workspace") + 1] if "--workspace" in args else None
    base = "WH Hypercare KPI"
    if "--bind-only" in args:
        opts = {r["Setting"]: r["Value"].strip() for r in csv.DictReader(open(ROOT / "config" / "build_options.csv", encoding="utf-8-sig"))}
        if "--site" in args:
            code = args[args.index("--site") + 1].upper()
            sys.exit(bind_only(wsname, f"{base} - {code}", {code}))
        sys.exit(bind_only(wsname, args[args.index("--name") + 1] if "--name" in args else (opts.get("Fabric_DisplayName") or base)))
    d = ROOT / "dist" / "ALL_SITES"
    sites = report_sites()
    if "--site" in args:      # one site's own model (py tools/build_pbip.py <SITE> --service): needs only that site's connection
        code = args[args.index("--site") + 1].upper()
        base = f"{base} - {code}"
        d = ROOT / "dist" / ("_service" if "--service" in args else "") / code
        sites = [r for r in csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig")) if r["SiteCode"] == code]
        if "--test-server" in args:   # the TEST build (build_pbip.py <SITE> --service --test-server S): bind the connection of S + database
            srv = args[args.index("--test-server") + 1]
            base, d = f"{base} (TEST)", ROOT / "dist" / "_service_test" / code
            sites = [dict(r, ReplicaServer=srv, Gateway_Connection="") for r in sites]
        if not sites or not (d / f"{base}.SemanticModel").exists():
            raise SystemExit(f"{d / (base + '.SemanticModel')} missing - build it first: py tools/build_pbip.py {code}"
                             + (" --service" if "--service" in args else ""))
    ws, wsdisp = workspace_id(wsname)
    name = base if "--site" in args else service_name(base, wsdisp)
    print(f"workspace: {wsdisp} ({ws}) | name: {name}", flush=True)
    sm = upsert(ws, "semanticModels", name, {"format": "TMDL", "parts": parts(d / f"{base}.SemanticModel")})
    rp = parts(d / f"{base}.Report", skip=("definition.pbir",))
    pbir = {"version": "4.0", "datasetReference": {"byConnection": {
        "connectionString": f"semanticmodelid={sm}", "pbiServiceModelId": None, "pbiModelVirtualServerName": "sobe_wowvirtualserver",
        "pbiModelDatabaseName": sm, "name": "EntityDataSource", "connectionType": "pbiServiceXmlaStyleLive"}}}
    rp.append({"path": "definition.pbir", "payload": base64.b64encode(json.dumps(pbir).encode()).decode(), "payloadType": "InlineBase64"})
    rid = upsert(ws, "reports", name, {"parts": rp})
    gw = bind_gateway(sm, sites)
    for k, v in gw.items():
        print(f" gateway {k}: {v}", flush=True)
    out = {"workspace": wsdisp, "workspaceId": ws, "semanticModelId": sm, "reportId": rid, "gateway": gw,
           "reportUrl": f"https://app.powerbi.com/groups/{'me' if wsname is None else ws}/reports/{rid}",
           "settingsUrl": f"https://app.powerbi.com/groups/{'me' if wsname is None else ws}/settings/datasets/{sm}"}
    (d / ("_published.json" if "--site" not in args else f"_published_{wsdisp}.json")).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    if UPDATED.get("semanticModels") and "--site" in args and "--no-reload" not in args:
        # a changed definition leaves the changed tables 'needs refresh' (warning icon in the model view, 'calculated table ... needs to
        # be recalculated' in visuals) until processed: reload the embedded tables + recalculate now (no replica query, ~2-4 min)
        import subprocess
        cmd = [sys.executable, "-u", str(Path(__file__).with_name("service_refresh.py")), "--site", code, "--config"] + \
              (["--workspace", wsname] if wsname else []) + (["--test"] if "--test-server" in args else [])
        print("reloading embedded tables + recalculating after the republish:", flush=True)
        rc = subprocess.call(cmd)
        if rc:
            raise SystemExit("reload after publish failed - run: " + " ".join(cmd[1:]))


if __name__ == "__main__":
    main()
