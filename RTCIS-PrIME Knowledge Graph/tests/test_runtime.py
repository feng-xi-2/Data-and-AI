"""Hosting without a desktop sign-in: the Cosmos graph from endpoint + key, the model token from a service principal,
and one runtime bundle (index, catalog, templates, load record) instead of the full graph files and the wiki."""
import json
import sys
import types

import pytest

import kg_runtime as R
import kg_services as S


class FakeConfidentialApp:
    calls = []

    def __init__(self, client_id, authority=None, client_credential=None):
        FakeConfidentialApp.calls.append((client_id, authority, bool(client_credential)))

    def acquire_token_for_client(self, scopes):
        return {"access_token": "sp-token-for-" + scopes[0]}


def test_service_principal_token_is_used_when_configured_and_the_desktop_login_is_never_imported(monkeypatch):
    monkeypatch.setitem(sys.modules, "azauth", None)          # importing it would raise
    monkeypatch.setitem(sys.modules, "msal", types.SimpleNamespace(ConfidentialClientApplication=FakeConfidentialApp))
    monkeypatch.setenv("KG_SP_CLIENT_ID", "app-id")
    monkeypatch.setenv("KG_SP_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("KG_SP_TENANT_ID", "tenant-1")
    R._apps.clear()
    assert R.token("https://cognitiveservices.azure.com/.default") == "sp-token-for-https://cognitiveservices.azure.com/.default"
    assert FakeConfidentialApp.calls[-1] == ("app-id", "https://login.microsoftonline.com/tenant-1", True)


def test_cosmos_graph_connects_with_endpoint_and_key_without_arm(monkeypatch):
    monkeypatch.setitem(sys.modules, "load_cosmos", None)     # the ARM / listKeys path must not be used
    seen = {}
    monkeypatch.setattr(R, "connect", lambda account, key, graph, db: seen.update(a=account, k=key, g=graph, d=db) or "client")
    monkeypatch.setenv("KG_COSMOS_ACCOUNT", "acct")
    monkeypatch.setenv("KG_COSMOS_KEY", "ro-key")
    g = S.CosmosGraph(graph="rtcis_prime")
    assert seen == {"a": "acct", "k": "ro-key", "g": "rtcis_prime", "d": "whs_kg"} and g._c == "client" and g._lc is R


def test_cosmos_key_is_read_from_the_key_vault_with_the_service_principal_when_no_key_is_set(monkeypatch):
    seen = {}
    monkeypatch.setattr(R, "connect", lambda account, key, graph, db: seen.update(a=account, k=key) or "client")
    monkeypatch.setattr(R, "token", lambda scope: seen.update(scope=scope) or "kv-token")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"value": "ro-key-from-vault"}).encode()

    def urlopen(req, timeout=None):
        seen.update(url=req.full_url, auth=req.headers.get("Authorization"))
        return Resp()
    monkeypatch.setattr(R.urllib.request, "urlopen", urlopen)
    monkeypatch.delenv("KG_COSMOS_KEY", raising=False)
    monkeypatch.setenv("KG_COSMOS_ACCOUNT", "acct")
    monkeypatch.setenv("KG_COSMOS_KEY_VAULT_URL", "https://kv.vault.azure.net/")
    S.CosmosGraph(graph="rtcis_prime")
    assert seen["k"] == "ro-key-from-vault" and seen["scope"] == "https://vault.azure.net/.default"
    assert seen["url"].startswith("https://kv.vault.azure.net/secrets/MM-KG-GREMLIN-READONLY-KEY?api-version=")
    assert seen["auth"] == "Bearer kv-token"


def test_hosted_service_without_a_replica_endpoint_says_so_instead_of_opening_a_desktop_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("KG_BUNDLE_DIR", str(tmp_path))
    monkeypatch.delenv("KG_REPLICA_ENDPOINT", raising=False)
    monkeypatch.setitem(sys.modules, "dbconn", None)          # the desktop ODBC helper is not shipped with the app
    res = S.make_db().validate("SELECT 1 AS x", "DE08")
    assert res["ok"] is False and res["stage"] == "endpoint" and "no replica endpoint" in res["error"]
    assert res["site"] == "DE08" and res["rows"] == []


def test_genai_user_is_the_request_user_inside_as_user_and_the_configured_user_outside(monkeypatch):
    monkeypatch.setenv("KG_GENAI_USER", "<user>@<company>")
    assert R.genai_user() == "<user>@<company>"
    with R.as_user("<user>@<company>"):
        assert R.genai_user() == "<user>@<company>"
    with R.as_user(""):
        assert R.genai_user() == "<user>@<company>"           # no verified user: the configured one
    assert R.genai_user() == "<user>@<company>"


def test_genai_model_sends_the_request_user_on_every_call(monkeypatch):
    pytest.importorskip("langchain_openai")
    import httpx
    import kg_deep_agent as D
    monkeypatch.setenv("KG_GENAI_ENDPOINT", "https://genai.example/v1")
    monkeypatch.setenv("KG_GENAI_PROJECT", "proj")
    monkeypatch.delenv("KG_GENAI_USER", raising=False)
    monkeypatch.setattr(R, "token", lambda scope: "t")
    seen = []

    def handler(request):
        seen.append((request.headers.get("userid"), request.headers.get("project-name")))
        return httpx.Response(200, json={"id": "1", "object": "chat.completion", "created": 0, "model": "m", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]})
    monkeypatch.setattr(D, "_transport", lambda: httpx.MockTransport(handler))
    m = D.genai_model()
    with R.as_user("<user>@<company>"):
        m.invoke("hi")
    with R.as_user("<user>@<company>"):
        m.invoke("hi")
    assert seen == [("<user>@<company>", "proj"), ("<user>@<company>", "proj")]


def test_chat_runs_as_the_user_sent_by_the_host_app(monkeypatch):
    import kg_api
    from fastapi.testclient import TestClient
    seen = []

    class Svc:
        templates, db, llm = [], None, None

    def fake_route(text, same_engine=True):
        seen.append(R.genai_user())
        return {"mode": "validate", "items": []}
    monkeypatch.setattr(kg_api.k, "route", fake_route)
    monkeypatch.delenv("KG_GENAI_USER", raising=False)
    c = TestClient(kg_api.create_app(Svc()), base_url="http://127.0.0.1")
    assert c.post("/rp/chat", json={"text": "x", "site": "PRIME22_DE08", "user": "<user>@<company>"}).status_code == 200
    assert seen == ["<user>@<company>"] and R.genai_user() == ""


def test_runtime_bundle_round_trips_what_the_service_needs(tmp_path):
    index = [{"id": "Table:prime:invlod", "label": "Table", "engine": "PrIME2022", "name": "invlod", "description": "LPN"}]
    cat = {"PrIME2022": {"invlod": {"lodnum": "nvarchar"}}}
    templates = [{"qid": "R16", "engine": "PrIME2022", "intent": "pallets", "sql": "SELECT 1"}]
    record = {"vertices": {"Table:PrIME2022": 1}, "edge_types": {"MAPS_TO": 1}}
    R.write_bundle(str(tmp_path), index, cat, templates, record)
    b = R.load_bundle(str(tmp_path))
    assert (b.index, b.catalog, b.templates) == (index, cat, templates)
    assert json.load(open(b.load_record, encoding="utf-8")) == record


def test_services_read_the_bundle_instead_of_the_graph_files(tmp_path, monkeypatch):
    R.write_bundle(str(tmp_path), [{"id": "Table:prime:x", "label": "Table", "engine": "PrIME2022", "name": "x", "description": ""}],
                   {"PrIME2022": {"x": {"a": "int"}}}, [], {"vertices": {}, "edge_types": {}})
    monkeypatch.setenv("KG_BUNDLE_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "graphio", None)         # the full graph files are not shipped with the app
    index, cat, templates = S.load_index_and_templates()
    assert index[0]["name"] == "x" and cat == {"PrIME2022": {"x": {"a": "int"}}} and templates == []


def test_missing_service_principal_settings_fall_back_to_the_desktop_login(monkeypatch):
    for v in ("KG_SP_CLIENT_ID", "KG_SP_CLIENT_SECRET", "KG_SP_TENANT_ID"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setitem(sys.modules, "azauth", types.SimpleNamespace(token=lambda scope: "user-token"))
    assert R.token("scope") == "user-token"


@pytest.fixture(autouse=True)
def _clear_cache():
    R._apps.clear()
    yield
    R._apps.clear()


def test_services_close_the_graph_client_when_a_later_step_fails(monkeypatch):
    closed = []

    class Graph:
        def close(self):
            closed.append(1)

    monkeypatch.setattr(S, "CosmosGraph", Graph)
    monkeypatch.setattr(S, "GenAiLLM", lambda: object())
    monkeypatch.setattr(S, "make_db", lambda: object())

    def broken():
        raise FileNotFoundError("bundle missing")
    monkeypatch.setattr(S, "load_index_and_templates", broken)
    with pytest.raises(FileNotFoundError):
        S.services()
    assert closed == [1]                                      # no Cosmos connection pool left open
