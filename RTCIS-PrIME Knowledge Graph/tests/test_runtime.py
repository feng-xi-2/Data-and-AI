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
