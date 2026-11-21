"""Deploy from Git: make a Fabric workspace that is connected to the repo (Workspace settings > Git integration) pull the newest commit.

    py tools/fabric_git_update.py --workspace "<workspace>"            # status + update (as you, MSAL cache)
    py tools/fabric_git_update.py --workspace "<workspace>" --status   # only show what Git would change
    py tools/fabric_git_update.py ... --bind                                       # then bind the gateway connections (publish.py --bind-only)

In a pipeline (e.g. a GitHub Action on push to the PRIME ELS folder) set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET of a service
principal that is Contributor on the workspace (tenant setting 'Service principals can use Fabric APIs' must allow it). No secret is
stored in the repo. Every step prints what it does; a conflict or a failed update stops with the Fabric error - nothing fails silently.
"""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAB = "https://api.fabric.microsoft.com/v1"


def token():
    if os.environ.get("AZURE_CLIENT_SECRET"):
        r = requests.post(f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token", timeout=60, data={
            "grant_type": "client_credentials", "client_id": os.environ["AZURE_CLIENT_ID"], "client_secret": os.environ["AZURE_CLIENT_SECRET"],
            "scope": "https://api.fabric.microsoft.com/.default"})
        r.raise_for_status()
        return r.json()["access_token"]
    import publish
    return publish.token()


def H():
    return {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}


def wait(r, what):
    if r.status_code >= 400:
        try:
            j = r.json()
            msg = f"{j.get('errorCode')}: {j.get('message')}"
        except ValueError:
            msg = r.text[:500]
        hint = (" - set your Git credentials once: workspace > Source control > (gear) or Fabric 'Git credentials' with a GitHub "
                "connection" if "GitCredentialsNotConfigured" in msg else "")
        raise SystemExit(f"{what} refused ({r.status_code}) {msg}{hint}")
    if r.status_code != 202:
        return r
    loc, t0 = r.headers["Location"], time.time()
    while True:
        time.sleep(int(r.headers.get("Retry-After", 10)))
        s = requests.get(loc, headers=H(), timeout=60)
        st = (s.json() or {}).get("status") if s.content else None
        print(f"   {what}: {st} ({int(time.time() - t0)} s)", flush=True)
        if st in ("Succeeded", "Failed", "Cancelled"):
            if st != "Succeeded":
                raise SystemExit(f"{what} {st}: {s.text[:1500]}")
            res = requests.get(loc + "/result", headers=H(), timeout=60)
            return res if res.status_code < 300 else s


def main(argv):
    name = argv[argv.index("--workspace") + 1]
    ws = next((w for w in requests.get(f"{FAB}/workspaces", headers=H(), timeout=60).json()["value"]
               if w["displayName"].lower() == name.lower()), None)
    if not ws:
        raise SystemExit(f"workspace {name!r} not found for this identity")
    conn = requests.get(f"{FAB}/workspaces/{ws['id']}/git/connection", headers=H(), timeout=60).json()
    if conn.get("gitConnectionState") != "ConnectedAndInitialized":
        raise SystemExit(f"workspace {name} is not connected to Git ({conn.get('gitConnectionState')}) - Workspace settings > Git integration")
    gp = conn.get("gitProviderDetails", {})
    print(f"workspace {name} <- {gp.get('ownerName', gp.get('organizationName', ''))}/{gp.get('repositoryName')} "
          f"branch {gp.get('branchName')} folder {gp.get('directoryName')}", flush=True)
    st = wait(requests.get(f"{FAB}/workspaces/{ws['id']}/git/status", headers=H(), timeout=120), "git status").json()
    changes = st.get("changes", [])
    for c in changes:
        m = c.get("itemMetadata", {})
        print(f"   {m.get('itemType')} {m.get('displayName')}: remote {c.get('remoteChange')} / workspace {c.get('workspaceChange')} "
              f"{'CONFLICT' if c.get('conflictType') not in (None, 'None') else ''}", flush=True)
    if "--status" in argv:
        return 0
    if not changes:
        print("workspace already at the newest commit - nothing to update")
    else:
        body = {"remoteCommitHash": st["remoteCommitHash"], "workspaceHead": st.get("workspaceHead"),
                "conflictResolution": {"conflictResolutionType": "Workspace", "conflictResolutionPolicy": "PreferRemote"},
                "options": {"allowOverrideItems": True}}
        wait(requests.post(f"{FAB}/workspaces/{ws['id']}/git/updateFromGit", headers=H(), json=body, timeout=120), "update from Git")
        print(f"updated to commit {st['remoteCommitHash'][:10]}")
    if "--bind" in argv:
        import publish
        return publish.bind_only(name, (argv[argv.index("--name") + 1] if "--name" in argv else "WH Hypercare KPI"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
