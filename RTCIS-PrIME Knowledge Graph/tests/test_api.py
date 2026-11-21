"""HTTP contract of the RTCIS <-> PrIME graph API used by the knowledge-graph.html tab. Real FastAPI app, fake services."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import kg_api


class G:
    def view(self, kind, key, limit=40):
        return {"nodes": [{"id": f"{kind}:{key}", "labels": ["RTCIS table"], "props": {}}], "edges": []}

    def search(self, text, limit=20):
        return [{"id": "Table:prime:invlod", "name": "invlod", "platform": "PrIME2022"}]


class DB:
    def __init__(self):
        self.calls = []

    def validate(self, sql, site, params=None):
        self.calls.append((sql, site, params))
        if "broken" in sql.lower():
            return {"ok": False, "stage": "executed", "error": "Invalid column name 'broken'."}
        return {"ok": True, "stage": "executed", "columns": ["a"], "rows": [[1]], "empty_fields": []}


class AS:
    def ask(self, question, engine, site, params=None):
        return {"status": "validated", "question": question, "engine": engine, "site": site, "params": params}

    def convert(self, sql, source_engine, target_engine, source_site, target_site, params=None, source_params=None):
        return {"status": "validated", "source": sql, "target_site": target_site}

    def batch(self, items, engine, site, target_engine=None, target_site=None, params=None):
        return {"items": items, "summary": {"validated": len(items)}}


def client(tmp_path):
    svc = SimpleNamespace(graph=G(), db=DB(), assistant=AS(), approved_file=str(tmp_path / "approved.jsonl"),
                          templates=[{"qid": "R16", "engine": "PrIME2022", "title": "Pallets", "intent": "pallets", "sql": "SELECT 1", "params": "wh_id"}])
    svc.assistant.approved = []
    return TestClient(kg_api.create_app(svc), base_url="http://127.0.0.1:8738"), svc


def test_graph_view_and_cors(tmp_path):
    c, _ = client(tmp_path)
    r = c.get("/rp/graph", params={"view": "versions", "key": "invlod"}, headers={"Origin": "null"})
    assert r.status_code == 200 and r.json()["nodes"][0]["id"] == "versions:invlod"
    assert r.headers["access-control-allow-origin"] == "null"  # page opened from file:// must be able to call it


def test_templates_list_hides_nothing_needed_to_run(tmp_path):
    c, _ = client(tmp_path)
    t = c.get("/rp/templates").json()[0]
    assert t["qid"] == "R16" and t["sql"] == "SELECT 1" and t["params"] == "wh_id"


def test_ask_passes_engine_site_and_params(tmp_path):
    c, _ = client(tmp_path)
    r = c.post("/rp/ask", json={"question": "pallets", "engine": "PrIME2022", "site": "PRIME22_DE08", "params": {"wh_id": "DE08"}}).json()
    assert r["status"] == "validated" and r["params"] == {"wh_id": "DE08"}


def test_batch_parses_text_into_items(tmp_path):
    c, _ = client(tmp_path)
    r = c.post("/rp/batch", json={"kind": "ask", "text": "q one\nq two\n", "engine": "PrIME2022", "site": "PRIME22_DE08"}).json()
    assert r["summary"] == {"validated": 2} and [i["question"] for i in r["items"]] == ["q one", "q two"]


def test_validate_runs_on_the_requested_site(tmp_path):
    c, svc = client(tmp_path)
    c.post("/rp/validate", json={"sql": "SELECT 1 AS a", "site": "RTCIS_EUS"})
    assert svc.db.calls == [("SELECT 1 AS a", "RTCIS_EUS", None)]


def test_approve_appends_a_validated_pair_for_few_shot(tmp_path):
    c, svc = client(tmp_path)
    body = {"question": "pallets per area", "engine": "PrIME2022", "sql": "SELECT 1 AS a", "site": "PRIME22_DE08"}
    assert c.post("/rp/approve", json=body).json()["approved"] is True
    assert c.post("/rp/approve", json=dict(body, sql="DELETE FROM t")).status_code == 400
    lines = open(svc.approved_file, encoding="utf-8").read().splitlines()
    assert len(lines) == 1 and '"intent": "pallets per area"' in lines[0]


def test_approve_reruns_the_sql_on_the_replica_and_records_the_approver(tmp_path):
    c, svc = client(tmp_path)
    body = {"question": "pallets per area", "engine": "PrIME2022", "sql": "SELECT 1 AS a", "site": "PRIME22_DE08",
            "params": {"wh_id": "DE08"}, "approved_by": "<user>@<company>"}
    assert c.post("/rp/approve", json=body).json()["approved"] is True
    assert svc.db.calls[-1] == ("SELECT 1 AS a", "PRIME22_DE08", {"wh_id": "DE08"})
    r = c.post("/rp/approve", json=dict(body, sql="SELECT broken FROM t"))
    assert r.status_code == 400 and "did not run" in r.json()["detail"]
    lines = open(svc.approved_file, encoding="utf-8").read().splitlines()
    assert len(lines) == 1 and '"approved_by": "<user>@<company>"' in lines[0]


def test_unknown_site_is_a_client_error(tmp_path):
    c, _ = client(tmp_path)
    assert c.post("/rp/validate", json={"sql": "SELECT 1", "site": "NOPE"}).status_code == 400


# --- review findings: the local API must not be usable by other web sites (it acts as the signed-in user) --------
def test_foreign_origin_is_refused(tmp_path):
    c, svc = client(tmp_path)
    r = c.post("/rp/validate", json={"sql": "SELECT 1 AS a", "site": "RTCIS_EUS"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and svc.db.calls == []


def test_dns_rebinding_host_is_refused(tmp_path):
    c, _ = client(tmp_path)
    assert c.get("/rp/health", headers={"Host": "evil.example:8738"}).status_code == 400


def test_post_without_json_content_type_is_refused(tmp_path):
    # a cross-site <form> can only send text/plain or form data without a CORS preflight
    c, svc = client(tmp_path)
    r = c.post("/rp/validate", content='{"sql": "SELECT 1 AS a", "site": "RTCIS_EUS"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and svc.db.calls == []


def test_approved_pair_is_used_without_restarting(tmp_path):
    c, svc = client(tmp_path)
    c.post("/rp/approve", json={"question": "pallets", "engine": "PrIME2022", "sql": "SELECT 1 AS a", "site": "PRIME22_DE08"})
    assert svc.assistant.approved and svc.assistant.approved[-1]["intent"] == "pallets"

# --- one dialogue box -----------------------------------------------------------------------------------------
class AS2(AS):
    def __init__(self):
        self.calls = []
        self.approved = []

    def ask(self, question, engine, site, params=None):
        self.calls.append(("ask", question, engine, site))
        return {"status": "validated", "question": question}

    def convert(self, sql, source_engine, target_engine, source_site, target_site, params=None, source_params=None):
        self.calls.append(("convert", sql, source_engine, target_engine))
        return {"status": "validated", "source": sql}


def chat_client(tmp_path):
    c, svc = client(tmp_path)
    svc.assistant = AS2()
    return c, svc


def test_chat_question_is_asked_on_the_run_site(tmp_path):
    c, svc = chat_client(tmp_path)
    r = c.post("/rp/chat", json={"text": "pallets per area?", "site": "PRIME22_DE08"}).json()
    assert r["mode"] == "ask" and svc.assistant.calls == [("ask", "pallets per area?", "PrIME2022", "PRIME22_DE08")]
    assert r["results"][0]["status"] == "validated"


def test_chat_sql_with_another_target_is_converted(tmp_path):
    c, svc = chat_client(tmp_path)
    r = c.post("/rp/chat", json={"text": "SELECT ulid FROM live3.unitld", "site": "RTCIS_EUS", "target_site": "PRIME22_DE08"}).json()
    assert r["mode"] == "convert" and svc.assistant.calls[0][2:] == ("RTCIS", "PrIME2022")


def test_chat_sql_without_target_is_validated(tmp_path):
    c, svc = chat_client(tmp_path)
    r = c.post("/rp/chat", json={"text": "SELECT 1 AS a", "site": "RTCIS_EUS"}).json()
    assert r["mode"] == "validate" and svc.db.calls == [("SELECT 1 AS a", "RTCIS_EUS", None)]


def test_chat_several_questions_run_as_a_batch_with_a_summary(tmp_path):
    c, svc = chat_client(tmp_path)
    r = c.post("/rp/chat", json={"text": "a?\nb?", "site": "PRIME22_DE08"}).json()
    assert r["mode"] == "batch_ask" and len(r["results"]) == 2 and r["summary"] == {"validated": 2}


def test_config_tells_the_page_which_sites_and_model_it_uses(tmp_path):
    c, _ = client(tmp_path)
    cfg = c.get("/rp/config").json()
    assert cfg["sites"]["RTCIS_EUS"] == "RTCIS" and "model" in cfg and cfg["replica"] in ("direct", "endpoint")


def test_sites_come_from_the_environment_when_set(monkeypatch):
    import importlib
    monkeypatch.setenv("KG_SITES_JSON", '{"PRIME22_XX01": "PrIME2022"}')
    m = importlib.reload(kg_api)
    try:
        assert m.SITES == {"PRIME22_XX01": "PrIME2022"}
    finally:
        monkeypatch.delenv("KG_SITES_JSON")
        importlib.reload(kg_api)


def test_cloud_host_and_origin_can_be_allowed_by_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("KG_ALLOWED_HOSTS", "kg.example.net")
    monkeypatch.setenv("KG_ALLOWED_ORIGINS", "https://ui.example.net")
    svc = client(tmp_path)[1]
    c = TestClient(kg_api.create_app(svc), base_url="https://kg.example.net")
    assert c.get("/rp/health", headers={"Origin": "https://ui.example.net"}).status_code == 200
    assert c.get("/rp/health", headers={"Origin": "https://evil.example"}).status_code == 403
