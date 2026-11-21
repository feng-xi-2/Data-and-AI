"""ARM helper on the signed-in user's cached Azure (MSAL) token. No secret is stored by this kit.

Environment (internal names are never hard-coded in the kit):
  KG_COSMOS_ACCOUNT   Cosmos DB account with the Gremlin API enabled
  KG_COSMOS_RG        its resource group
  KG_COSMOS_SUB_NAME  display name of its subscription
  KG_MSAL_HELPER_DIR  folder holding _databricks_session.py (MSAL cache file, client id, authority, user name)
"""
import json
import os
import sys
import urllib.error
import urllib.request

import msal

sys.path.insert(0, os.environ.get("KG_MSAL_HELPER_DIR", "."))
import _databricks_session as dbx  # noqa: E402

os.environ["NO_PROXY"] = ".azure.net,vault.azure.net,management.azure.com,.azure.com"
ACCOUNT = os.environ.get("KG_COSMOS_ACCOUNT", "")
RG = os.environ.get("KG_COSMOS_RG", "")
SUB_NAME = os.environ.get("KG_COSMOS_SUB_NAME", "")


def token(scope):
    cache = msal.SerializableTokenCache()
    cache.deserialize(open(dbx._MSAL_CACHE_FILE).read())
    app = msal.PublicClientApplication(dbx._CLIENT_ID, authority=dbx._AUTHORITY, token_cache=cache)
    acc = (app.get_accounts(username=dbx._USERNAME) or app.get_accounts())[0]
    res = app.acquire_token_silent([scope], account=acc)
    if not res or "access_token" not in res:
        raise SystemExit(f"no cached Azure token for {scope}: sign in again")
    if cache.has_state_changed:
        open(dbx._MSAL_CACHE_FILE, "w").write(cache.serialize())
    return res["access_token"]


def arm(method, path, body=None, api="2024-05-15"):
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(f"https://management.azure.com{path}{sep}api-version={api}", method=method,
                                 data=json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None),
                                 headers={"Authorization": "Bearer " + token("https://management.azure.com/.default"),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else {}), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600], dict(e.headers)


def account_path():
    if not (ACCOUNT and RG and SUB_NAME):
        raise SystemExit("set KG_COSMOS_ACCOUNT, KG_COSMOS_RG and KG_COSMOS_SUB_NAME")
    st, subs, _ = arm("GET", "/subscriptions", api="2022-12-01")
    for s in subs.get("value", []):
        if s["displayName"] == SUB_NAME:
            return f"/subscriptions/{s['subscriptionId']}/resourceGroups/{RG}/providers/Microsoft.DocumentDB/databaseAccounts/{ACCOUNT}"
    raise SystemExit(f"subscription {SUB_NAME} not visible to the signed-in user")
