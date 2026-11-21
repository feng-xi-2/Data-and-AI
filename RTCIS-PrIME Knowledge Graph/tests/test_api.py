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