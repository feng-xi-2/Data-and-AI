"""Assistant orchestration (ask / convert / batch) with in-memory fakes for the three external systems. The fakes record
calls so each test can assert the assistant's contract: what goes into the prompt, when the database is (not) called,
how many repair rounds happen."""
import kg_assistant as A

INDEX = [
    {"id": "Table:prime:invlod", "label": "Table", "engine": "PrIME2022", "name": "invlod", "description": "Inventory LPN (pallet / load)"},
    {"id": "Table:prime:locmst", "label": "Table", "engine": "PrIME2022", "name": "locmst", "description": "Location master"},
    {"id": "Table:rtcis:unitld", "label": "Table", "engine": "RTCIS", "name": "unitld", "description": "unit load"},
]
COLUMNS = {"PrIME2022": {"invlod": {"lodnum": "nvarchar", "stoloc": "nvarchar", "wh_id": "nvarchar"},
                         "locmst": {"stoloc": "nvarchar", "arecod": "nvarchar", "wh_id": "nvarchar"}},
           "RTCIS": {"unitld": {"ulid": "nvarchar", "locatn": "nvarchar"}}}
TEMPLATES = [{"qid": "R16", "engine": "PrIME2022", "intent": "pallet inventory per location",
              "sql": "SELECT l.STOLOC, COUNT(*) AS pallets FROM dbo.invlod l WHERE l.WH_ID = @wh_id GROUP BY l.STOLOC"}]


class FakeLLM:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def chat(self, messages):
        self.calls.append(messages)
        return self.answers.pop(0)


class FakeDB:
    def __init__(self, results):
        self.results, self.calls = list(results), []

    def validate(self, sql, site, params=None):
        self.calls.append((sql, site))
        return self.results.pop(0)


class FakeGraph:
    def __init__(self, mappings=None):
        self.mappings = mappings or []

    def context(self, table_ids):
        return {"mappings": [m for m in self.mappings if m["from_table"] in table_ids],
                "learnings": ["prtmst needs AND WH_ID_TMPL = @wh_id"], "rules": ["OBS5 keep every output column, same order"]}

    def evidence(self, ids):
        return {"nodes": [{"id": i, "labels": ["X"], "props": {}} for i in ids], "edges": []}


OK = {"ok": True, "stage": "executed", "columns": ["STOLOC", "pallets"], "rows": [["A1", 3]], "row_count": 1, "empty_fields": [], "seconds": 0.2}
ERR = {"ok": False, "stage": "describe", "error": "Invalid column name 'LOCATN'.", "columns": [], "rows": []}


def make(llm, db, graph=None):
    return A.Assistant(graph=graph or FakeGraph(), llm=llm, db=db, index=INDEX, columns=COLUMNS, templates=TEMPLATES)


def test_ask_puts_linked_schema_and_validated_example_in_the_prompt():
    llm = FakeLLM(["```sql\nSELECT l.STOLOC, COUNT(*) AS pallets FROM dbo.invlod l GROUP BY l.STOLOC\n```"])
    r = make(llm, FakeDB([OK])).ask("pallets per location", engine="PrIME2022", site="PRIME22_DE08")
    prompt = "\n".join(m["content"] for m in llm.calls[0])
    assert "invlod" in prompt and "lodnum" in prompt          # linked table with its real columns
    assert "GROUP BY l.STOLOC" in prompt                        # validated template as example
    assert "WH_ID_TMPL" in prompt                               # learning from the graph
    assert r["status"] == "validated" and r["attempts"] == 1


def test_ask_repairs_once_with_the_database_error():
    llm = FakeLLM(["```sql\nSELECT LOCATN FROM dbo.invlod\n```", "```sql\nSELECT STOLOC FROM dbo.invlod\n```"])
    db = FakeDB([ERR, OK])
    r = make(llm, db).ask("pallet locations", engine="PrIME2022", site="PRIME22_DE08")
    assert len(llm.calls) == 2 and "Invalid column name 'LOCATN'" in llm.calls[1][-1]["content"]
    assert [c[0] for c in db.calls] == ["SELECT LOCATN FROM dbo.invlod", "SELECT STOLOC FROM dbo.invlod"]
    assert r["status"] == "validated" and r["attempts"] == 2


def test_ask_stops_after_one_repair():
    r = make(FakeLLM(["```sql\nSELECT a FROM dbo.invlod\n```", "```sql\nSELECT b FROM dbo.invlod\n```"]), FakeDB([ERR, ERR])) \
        .ask("x", engine="PrIME2022", site="PRIME22_DE08")
    assert r["status"] == "failed validation" and r["attempts"] == 2


def test_ask_never_executes_unsafe_sql():
    db = FakeDB([OK])
    r = make(FakeLLM(["```sql\nDELETE FROM dbo.invlod\n```", "```sql\nDROP TABLE dbo.invlod\n```"]), db) \
        .ask("remove pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert db.calls == [] and r["status"] == "rejected"


def test_convert_uses_graph_mappings_and_checks_the_column_contract():
    graph = FakeGraph([{"from_table": "Table:rtcis:unitld", "from": "unitld.ulid", "to": "invlod.lodnum", "verdict": "CONFIRMED by values"}])
    llm = FakeLLM(["```sql\nSELECT l.LODNUM AS ULID, l.STOLOC AS LOCATN FROM dbo.invlod l\n```"])
    src_ok = dict(OK, columns=["ULID", "LOCATN"])
    db = FakeDB([src_ok, dict(OK, columns=["ULID", "LOCATN"])])
    r = make(llm, db, graph).convert("SELECT u.ulid, u.locatn FROM live3.unitld u", "RTCIS", "PrIME2022", source_site="RTCIS_EUS",
                                     target_site="PRIME22_DE08")
    prompt = "\n".join(m["content"] for m in llm.calls[0])
    assert "unitld.ulid -> invlod.lodnum" in prompt
    assert r["contract"]["identical"] is True and r["status"] == "validated"
    assert [c[1] for c in db.calls] == ["RTCIS_EUS", "PRIME22_DE08"]   # source described on its own engine first


def test_convert_flags_a_broken_contract():
    llm = FakeLLM(["```sql\nSELECT l.LODNUM FROM dbo.invlod l\n```"])
    db = FakeDB([dict(OK, columns=["ULID", "LOCATN"]), dict(OK, columns=["LODNUM"])])
    r = make(llm, db).convert("SELECT u.ulid, u.locatn FROM live3.unitld u", "RTCIS", "PrIME2022", "RTCIS_EUS", "PRIME22_DE08")
    assert r["status"] == "validated, contract differs"
    assert r["contract"]["missing"] == ["ULID", "LOCATN"]


def test_batch_runs_every_item_and_counts_outcomes():
    llm = FakeLLM(["```sql\nSELECT 1 AS a\n```", "```sql\nDELETE FROM t\n```", "```sql\nUPDATE t SET a=1\n```"])
    r = make(llm, FakeDB([OK])).batch([{"kind": "ask", "question": "q1"}, {"kind": "ask", "question": "q2"}],
                                      engine="PrIME2022", site="PRIME22_DE08")
    assert len(r["items"]) == 2
    assert r["summary"] == {"validated": 1, "rejected": 1}


def test_ask_adds_the_tables_a_matched_validated_query_reads():
    # catches schema linking that misses tables only reachable through a validated query (locmst has no question word here)
    index = INDEX + [{"id": "Query:R16:prime", "label": "Query", "engine": "PrIME2022", "name": "pallet stock report",
                      "description": "pallet stock", "reads": ["locmst"]}]
    llm = FakeLLM(["```sql\nSELECT 1 AS a\n```"])
    A.Assistant(graph=FakeGraph(), llm=llm, db=FakeDB([OK]), index=index, columns=COLUMNS, templates=TEMPLATES) \
        .ask("pallet stock report", engine="PrIME2022", site="PRIME22_DE08")
    prompt = "\n".join(m["content"] for m in llm.calls[0])
    assert "locmst(" in prompt and "arecod" in prompt


def test_ask_warns_when_the_validated_sql_returns_no_rows():
    llm = FakeLLM(["```sql\nSELECT a FROM dbo.invlod\n```"])
    r = make(llm, FakeDB([dict(OK, rows=[], row_count=0)])).ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert r["status"] == "validated" and any("0 rows" in w for w in r["warnings"])


def test_repair_round_lists_the_real_columns_of_the_tables_the_failed_sql_used():
    # catches a repair that only repeats the error, so the model guesses another non-existent column
    llm = FakeLLM(["```sql\nSELECT l.LOCATN FROM dbo.locmst l\n```", "```sql\nSELECT l.STOLOC FROM dbo.locmst l\n```"])
    make(llm, FakeDB([ERR, OK])).ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    repair = llm.calls[1][-1]["content"]
    assert "locmst(" in repair and "arecod" in repair and "stoloc" in repair


def test_ask_gives_the_validated_join_paths_between_linked_tables():
    templates = TEMPLATES + [{"qid": "R01", "engine": "PrIME2022", "intent": "stock",
                              "sql": "SELECT 1 FROM dbo.invlod l JOIN dbo.locmst m ON m.stoloc = l.stoloc AND m.wh_id = l.wh_id"}]
    llm = FakeLLM(["```sql\nSELECT 1 AS a\n```"])
    A.Assistant(graph=FakeGraph(), llm=llm, db=FakeDB([OK]), index=INDEX, columns=COLUMNS, templates=templates) \
        .ask("pallets per location", engine="PrIME2022", site="PRIME22_DE08")
    prompt = "\n".join(m["content"] for m in llm.calls[0])
    assert "invlod.stoloc = locmst.stoloc" in prompt


def test_prime2014_borrows_prime2022_joins_only_where_its_catalog_has_the_columns():
    templates = [{"qid": "R01", "engine": "PrIME2022", "intent": "stock",
                  "sql": "SELECT 1 FROM dbo.invlod l JOIN dbo.locmst m ON m.stoloc = l.stoloc JOIN dbo.new22 n ON n.x = l.lodnum"}]
    cols = {"PrIME2014": {"invlod": {"lodnum": "nvarchar", "stoloc": "nvarchar"}, "locmst": {"stoloc": "nvarchar", "arecod": "nvarchar"}}}
    index = [{"id": "Table:prime14:invlod", "label": "Table", "engine": "PrIME2014", "name": "invlod", "description": "pallet load"},
             {"id": "Table:prime14:locmst", "label": "Table", "engine": "PrIME2014", "name": "locmst", "description": "location"}]
    llm = FakeLLM(["```sql\nSELECT 1 AS a\n```"])
    A.Assistant(graph=FakeGraph(), llm=llm, db=FakeDB([OK]), index=index, columns=cols, templates=templates) \
        .ask("pallets per location", engine="PrIME2014", site="PRIME14_XQ")
    prompt = "\n".join(m["content"] for m in llm.calls[0])
    assert "invlod.stoloc = locmst.stoloc" in prompt and "new22" not in prompt


def test_convert_gives_validated_joins_between_the_target_tables():
    graph = FakeGraph([{"from_table": "Table:rtcis:unitld", "from": "unitld.ulid", "to": "invlod.lodnum", "verdict": "ok"},
                       {"from_table": "Table:rtcis:unitld", "from": "unitld.locatn", "to": "locmst.stoloc", "verdict": "ok"}])
    templates = [{"qid": "R01", "engine": "PrIME2022", "intent": "stock",
                  "sql": "SELECT 1 FROM dbo.invlod l JOIN dbo.locmst m ON m.stoloc = l.stoloc"}]
    llm = FakeLLM(["```sql\nSELECT l.LODNUM AS ULID FROM dbo.invlod l\n```"])
    db = FakeDB([dict(OK, columns=["ULID"]), dict(OK, columns=["ULID"])])
    A.Assistant(graph=graph, llm=llm, db=db, index=INDEX, columns=COLUMNS, templates=templates) \
        .convert("SELECT u.ulid FROM live3.unitld u", "RTCIS", "PrIME2022", "RTCIS_EUS", "PRIME22_DE08")
    assert "invlod.stoloc = locmst.stoloc" in "\n".join(m["content"] for m in llm.calls[0])
