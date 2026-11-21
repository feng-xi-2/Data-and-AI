"""Hosting helpers for running the knowledge-graph service inside an application (no desktop sign-in, no full graph files).

  token(scope)      Entra token: a service principal when KG_SP_CLIENT_ID / KG_SP_CLIENT_SECRET / KG_SP_TENANT_ID are set,
                    otherwise the signed-in user's cached token (tools/azauth.py, desktop use)
  connect(...)      Cosmos DB for Apache Gremlin client from account name + key (KG_COSMOS_ACCOUNT / KG_COSMOS_KEY)
  cosmos_key()      KG_COSMOS_KEY, or the read-only key read from the Key Vault KG_COSMOS_KEY_VAULT_URL with token()
  genai_user() / as_user(email)   the GenAI `userid` of the current request (host app's verified user, else KG_GENAI_USER)
  run(c, q, b)      a Gremlin request with bindings, retried on throttling / transient errors
  write_bundle / load_bundle   the runtime bundle (KG_BUNDLE_DIR): index.json, catalog.json, templates.json,
                    cosmos_load_<graph>.json - everything the service reads besides the live graph and the replicas
"""
import contextlib
import contextvars
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from types import SimpleNamespace

RETRY = ("429", "RequestRateTooLarge", "408", "Timeout", "ServiceUnavailable", "1009", "Connection", "449")
KEY_SECRET = "MM-KG-GREMLIN-READONLY-KEY"
_apps = {}
_lock = threading.Lock()
_user = contextvars.ContextVar("kg_genai_user", default="")


def genai_user():
    """The GenAI platform `userid` of this request: the user the host app verified (as_user), else KG_GENAI_USER."""
    return _user.get() or os.environ.get("KG_GENAI_USER", "")


@contextlib.contextmanager
def as_user(email):
    reset = _user.set(email or "")
    try:
        yield
    finally:
        _user.reset(reset)


def token(scope):
    cid, secret, tenant = (os.environ.get(v, "") for v in ("KG_SP_CLIENT_ID", "KG_SP_CLIENT_SECRET", "KG_SP_TENANT_ID"))
    if not (cid and secret and tenant):
        import azauth   # desktop: the signed-in user's MSAL cache
        return azauth.token(scope)
    import msal
    with _lock:
        app = _apps.get(cid)
        if app is None:
            app = _apps[cid] = msal.ConfidentialClientApplication(cid, authority=f"https://login.microsoftonline.com/{tenant}",
                                                                  client_credential=secret)
    res = app.acquire_token_for_client(scopes=[scope])   # msal caches the token until shortly before it expires
    if "access_token" not in res:
        raise RuntimeError(f"service principal token for {scope}: {res.get('error', 'no token')}")
    return res["access_token"]


def cosmos_key():
    """KG_COSMOS_KEY, else the secret KG_COSMOS_KEY_SECRET (default MM-KG-GREMLIN-READONLY-KEY) read from the Key Vault
    KG_COSMOS_KEY_VAULT_URL with token() - for platforms that inject no custom secrets into the app."""
    if os.environ.get("KG_COSMOS_KEY"):
        return os.environ["KG_COSMOS_KEY"]
    vault = os.environ.get("KG_COSMOS_KEY_VAULT_URL", "").rstrip("/")
    if not vault:
        raise RuntimeError("set KG_COSMOS_KEY or KG_COSMOS_KEY_VAULT_URL")
    name = urllib.parse.quote(os.environ.get("KG_COSMOS_KEY_SECRET") or KEY_SECRET)
    req = urllib.request.Request(f"{vault}/secrets/{name}?api-version=7.4",
                                 headers={"Authorization": "Bearer " + token("https://vault.azure.net/.default")})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["value"]


def connect(account, key, graph, db):
    from gremlin_python.driver import client, serializer
    return client.Client(f"wss://{account}.gremlin.cosmos.azure.com:443/", "g", username=f"/dbs/{db}/colls/{graph}", password=key,
                         message_serializer=serializer.GraphSONSerializersV2d0(), pool_size=8, max_workers=8)


def run(c, q, b=None, tries=6):
    for i in range(tries):
        try:
            return c.submit(q, b or {}).all().result()
        except Exception as e:
            if i == tries - 1 or not any(x in str(e) for x in RETRY):
                raise
            time.sleep(min(10, 0.5 * 2 ** i))


def write_bundle(path, index, catalog, templates, load_record, graph="rtcis_prime"):
    os.makedirs(path, exist_ok=True)
    for name, data in (("index.json", index), ("catalog.json", catalog), ("templates.json", templates),
                       (f"cosmos_load_{graph}.json", load_record)):
        with open(os.path.join(path, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def load_bundle(path, graph="rtcis_prime"):
    def read(name):
        with open(os.path.join(path, name), encoding="utf-8") as f:
            return json.load(f)
    return SimpleNamespace(index=read("index.json"), catalog=read("catalog.json"), templates=read("templates.json"),
                           load_record=os.path.join(path, f"cosmos_load_{graph}.json"))
