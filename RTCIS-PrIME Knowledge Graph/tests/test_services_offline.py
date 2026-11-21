"""ReplicaDB / CosmosGraph safety without any network: stub connections record what would reach the server."""
import threading
import time

import pytest

import kg_services as S


class StubCursor:
    def __init__(self, log, busy):
        self.log, self.busy, self.description = log, busy, None

    def execute(self, sql, *a):
        if self.busy["on"]:
            self.busy["overlap"] = True
        self.busy["on"] = True
        time.sleep(0.05)
        self.busy["on"] = False
        self.log.append(sql)
        self.description = [("a",)]

    def fetchall(self):
        return [("a", "int", None)]

    def fetchmany(self, n):
        return [(1,)]

    def nextset(self):
        return False

    def cancel(self):
        pass


class StubConn:
    def __init__(self, log, busy):
        self.log, self.busy = log, busy

    def add_output_converter(self, *a):
        pass

    def cursor(self):
        return StubCursor(self.log, self.busy)


class StubDbconn:
    def __init__(self):
        self.log, self.busy, self.conn = [], {"on": False, "overlap": False}, None

    def connect(self, site, database=None, timeout=120):
        self.conn = self.conn or StubConn(self.log, self.busy)
        return self.conn


def db():
    d = S.ReplicaDB.__new__(S.ReplicaDB)
    d._dbconn = StubDbconn()
    return d


@pytest.mark.parametrize("name", ["wh_id int = 1; DELETE FROM dbo.invlod; --", "x int --", "1abc", "a b"])
def test_validate_rejects_unsafe_parameter_names_before_any_database_call(name):
    d = db()
    r = d.validate("SELECT 1 AS a", "PRIME22_DE08", {name: 1})
    assert r["ok"] is False and r["stage"] == "params" and d._dbconn.log == []


def test_validate_accepts_normal_parameter_names():
    d = db()
    assert d.validate("SELECT 1 AS a", "PRIME22_DE08", {"wh_id": "DE08"})["ok"] is True


def test_validate_never_uses_one_connection_from_two_threads_at_once():
    d = db()
    ts = [threading.Thread(target=d.validate, args=("SELECT 1 AS a", "PRIME22_DE08")) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert d._dbconn.busy["overlap"] is False and len(d._dbconn.log) == 8


def test_query_view_passes_the_key_only_as_a_binding():
    g = S.CosmosGraph.__new__(S.CosmosGraph)
    seen = []
    g.q = lambda gremlin, **b: (seen.append(gremlin), [])[1]
    evil = "x').V().drop().V('"
    g.view("query", evil)
    assert seen and not any(evil in s or "drop()" in s for s in seen)


# --- replica endpoint you host: the guard runs here first, the endpoint only receives read-only SQL ---------------
def test_http_replica_sends_only_guarded_sql(monkeypatch):
    sent = []

    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        import json
        sent.append((req.full_url, json.loads(req.data), dict(req.headers)))
        return Resp(json.dumps({"ok": True, "columns": ["a"], "rows": [[None]], "row_count": 1}).encode())

    monkeypatch.setattr(S.urllib.request, "urlopen", fake_urlopen)
    db = S.HttpReplicaDB("https://replica.example/validate", token="t0k")
    assert db.validate("DELETE FROM t", "RTCIS_EUS")["stage"] == "guard" and sent == []
    r = db.validate("SELECT NULL AS a", "RTCIS_EUS", {"wh_id": "DE08"})
    assert sent[0][1] == {"sql": "SELECT NULL AS a", "site": "RTCIS_EUS", "params": {"wh_id": "DE08"}, "max_rows": 50}
    assert sent[0][2]["Authorization"] == "Bearer t0k"
    assert r["ok"] is True and r["empty_fields"] == ["a"] and r["stage"] == "executed"
    assert db.validate("SELECT 1 AS a", "RTCIS_EUS", {"x int --": 1})["stage"] == "params"
