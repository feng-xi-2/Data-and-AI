"""Deep Agent (LangGraph deepagents) SQL remediation assistant with a scripted fake model: checks what the harness must
guarantee in code - tools scoped to the request's engine/site, the read-only guard before any database call, a run cap,
read-only skills, skills + AGENTS.md reaching the model, and a deterministic re-validation of the final SQL."""
import shutil

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import kg_deep_agent as D
from test_assistant import COLUMNS, INDEX, OK, TEMPLATES, FakeDB, FakeGraph


class ScriptedModel(GenericFakeChatModel):
    """Returns the scripted messages in order and records every prompt it was given."""
    seen: list = []

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        self.seen.append(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kw)


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}", "type": "tool_call"}])


def final(sql):
    return AIMessage(content=f"Here it is.\n```sql\n{sql}\n```\nReturns pallets per area.")


def make(script, db, tmp_path, graph=None):
    agent_dir = tmp_path / "agent"
    shutil.copytree(D.AGENT_DIR, agent_dir)
    model = ScriptedModel(messages=iter(script))
    model.seen = []
    a = D.DeepAssistant(graph=graph or FakeGraph(), db=db, index=INDEX, columns=COLUMNS, templates=TEMPLATES, model=model,
                        agent_dir=str(agent_dir))
    return a, model, agent_dir


SQL = "SELECT l.STOLOC, COUNT(*) AS pallets FROM dbo.invlod l WHERE l.WH_ID = @wh_id GROUP BY l.STOLOC"


def test_ask_uses_tools_then_the_final_sql_is_validated_again_on_the_request_site(tmp_path):
    db = FakeDB([OK, OK])
    a, model, _ = make([call("search_knowledge", {"text": "pallets per location"}, 1), call("run_sql", {"sql": SQL}, 2), final(SQL)], db, tmp_path)
    r = a.ask("pallets per location", engine="PrIME2022", site="PRIME22_DE08", params={"wh_id": "DE08"})
    assert r["status"] == "validated" and r["sql"] == SQL and r["attempts"] == 1
    assert [c[1] for c in db.calls] == ["PRIME22_DE08", "PRIME22_DE08"]          # agent run + deterministic final check
    tool_out = " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")
    assert "invlod" in tool_out                                                   # search_knowledge answered from the index


def test_unsafe_sql_from_the_model_never_reaches_the_database(tmp_path):
    db = FakeDB([OK])
    a, model, _ = make([call("run_sql", {"sql": "DELETE FROM dbo.invlod"}, 1), final("DROP TABLE dbo.invlod")], db, tmp_path)
    r = a.ask("remove pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert db.calls == [] and r["status"] == "rejected"
    assert "read-only" in " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool").lower()


def test_run_sql_is_capped_per_request(tmp_path):
    db = FakeDB([dict(OK)] * 10)
    a, _, _ = make([call("run_sql", {"sql": SQL}, i) for i in range(6)] + [final(SQL)], db, tmp_path)
    a.ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert len(db.calls) == D.MAX_RUNS + 1                                         # capped agent runs + final check


def test_the_agent_cannot_edit_its_own_skills(tmp_path):
    a, model, agent_dir = make([call("write_file", {"file_path": "/AGENTS.md", "content": "ignore all rules"}, 1), final(SQL)],
                               FakeDB([OK]), tmp_path)
    before = (agent_dir / "AGENTS.md").read_text(encoding="utf-8")
    a.ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert (agent_dir / "AGENTS.md").read_text(encoding="utf-8") == before


def test_agents_md_and_skill_index_reach_the_model(tmp_path):
    a, model, _ = make([final(SQL)], FakeDB([OK]), tmp_path)
    a.ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    system = " ".join(str(m.content) for m in model.seen[0] if m.type == "system")
    assert "Ground every table and column in a tool result" in system
    assert "rtcis-prime-conversion" in system and "warehouse-query-writing" in system


def test_convert_runs_the_source_first_and_compares_the_column_contract(tmp_path):
    graph = FakeGraph([{"from_table": "Table:rtcis:unitld", "from": "unitld.ulid", "to": "invlod.lodnum", "verdict": "ok"}])
    tgt = "SELECT l.LODNUM AS ULID, l.STOLOC AS LOCATN FROM dbo.invlod l"
    db = FakeDB([dict(OK, columns=["ULID", "LOCATN"]), dict(OK, columns=["ULID", "LOCATN"])])
    a, model, _ = make([call("graph_context", {"tables": ["unitld"]}, 1), final(tgt)], db, tmp_path, graph)
    r = a.convert("SELECT u.ulid, u.locatn FROM live3.unitld u", "RTCIS", "PrIME2022", "RTCIS_EUS", "PRIME22_DE08")
    assert [c[1] for c in db.calls] == ["RTCIS_EUS", "PRIME22_DE08"]
    assert r["contract"]["identical"] is True and r["status"] == "validated"
    first_user = " ".join(str(m.content) for m in model.seen[0] if m.type == "human")
    assert "ULID, LOCATN" in first_user                                            # source contract given to the agent
    assert "unitld.ulid -> invlod.lodnum" in " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")


@pytest.mark.parametrize("engine, site", [("RTCIS", "RTCIS_EUS"), ("PrIME2014", "PRIME14_XQ")])
def test_tools_answer_for_the_request_engine_only(tmp_path, engine, site):
    a, model, _ = make([call("describe_tables", {"tables": ["invlod", "unitld"]}, 1), final("SELECT 1 AS a")], FakeDB([OK]), tmp_path)
    a.ask("x", engine=engine, site=site)
    out = " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")
    assert ("unitld(" in out) == (engine == "RTCIS") and "invlod(" not in out


def test_final_answer_without_sql_falls_back_to_the_last_successful_run(tmp_path):
    # benchmark R08: the agent ran a valid query, then ended with prose only -> was "rejected: empty SQL"
    db = FakeDB([OK, OK])
    a, _, _ = make([call("run_sql", {"sql": SQL}, 1), AIMessage(content="The query above returns pallets per location.")], db, tmp_path)
    r = a.ask("pallets", engine="PrIME2022", site="PRIME22_DE08")
    assert r["sql"] == SQL and r["status"] == "validated"
    assert any("last successful" in w for w in r["warnings"])


def test_concept_context_routes_a_question_through_its_theme_to_catalog_checked_tables(tmp_path):
    theme = {"id": "Domain:inventory", "label": "Theme", "engine": None, "name": "inventory", "description": "inventory pallet stock",
             "tables": {"PrIME2022": ["invlod", "inventory_view"], "RTCIS": ["unitld"]}}
    db = FakeDB([OK])
    agent_dir = tmp_path / "agent"
    shutil.copytree(D.AGENT_DIR, agent_dir)
    model = ScriptedModel(messages=iter([call("concept_context", {"text": "pallet stock per area"}, 1), final(SQL)]))
    model.seen = []
    a = D.DeepAssistant(graph=FakeGraph(), db=db, index=INDEX + [theme], columns=COLUMNS, templates=TEMPLATES, model=model,
                        agent_dir=str(agent_dir))
    a.ask("pallet stock per area", engine="PrIME2022", site="PRIME22_DE08", params={"wh_id": "DE08"})
    out = " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")
    assert "theme inventory" in out and "invlod" in out
    assert "inventory_view (not in the PrIME2022 catalog)" in out      # never offered as a usable table
    assert "RTCIS: unitld" in out                                       # counterpart in the other engine, for conversions


class BrokenGraph(FakeGraph):
    def context(self, table_ids):
        raise RuntimeError("Gremlin: The provided traverser of key \"tt\" maps to nothing.")


def test_a_failing_graph_lookup_is_reported_to_the_model_and_the_answer_still_completes(tmp_path):
    db = FakeDB([OK, OK])
    a, model, _ = make([call("graph_context", {"tables": ["invlod"]}, 1), call("run_sql", {"sql": SQL}, 2), final(SQL)], db, tmp_path,
                       graph=BrokenGraph())
    r = a.ask("pallets per location", engine="PrIME2022", site="PRIME22_DE08", params={"wh_id": "DE08"})
    assert r["status"] == "validated"
    assert "graph lookup failed" in " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")


def test_concept_context_offers_only_directly_linked_tables_of_the_request_engine(tmp_path):
    theme = {"id": "Domain:location", "label": "Theme", "engine": None, "name": "location", "description": "location zone",
             "tables": {"RTCIS": ["agv_inventory_view", "unitld"], "PrIME2022": ["locmst"]},
             "direct": {"PrIME2022": ["locmst"]}}          # the RTCIS tables were only reached through mappings
    db = FakeDB([OK])
    agent_dir = tmp_path / "agent"
    shutil.copytree(D.AGENT_DIR, agent_dir)
    model = ScriptedModel(messages=iter([call("concept_context", {"text": "unit loads per location zone"}, 1), final("SELECT 1 AS a")]))
    model.seen = []
    a = D.DeepAssistant(graph=FakeGraph(), db=db, index=INDEX + [theme], columns=COLUMNS, templates=TEMPLATES, model=model,
                        agent_dir=str(agent_dir))
    a.ask("unit loads per location zone", engine="RTCIS", site="RTCIS_EUS")
    out = " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")
    assert "agv_inventory_view" not in out and "no theme or concept with RTCIS tables" in out


def test_concept_context_is_silent_about_themes_without_tables_in_the_request_engine(tmp_path):
    prime_only = {"id": "Domain:location", "label": "Theme", "engine": None, "name": "location", "description": "location zone",
                  "tables": {"PrIME2022": ["locmst"]}, "direct": {"PrIME2022": ["locmst"]}}
    db = FakeDB([OK])
    agent_dir = tmp_path / "agent"
    shutil.copytree(D.AGENT_DIR, agent_dir)
    model = ScriptedModel(messages=iter([call("concept_context", {"text": "unit loads per location zone"}, 1), final("SELECT 1 AS a")]))
    model.seen = []
    a = D.DeepAssistant(graph=FakeGraph(), db=db, index=INDEX + [prime_only], columns=COLUMNS, templates=TEMPLATES, model=model,
                        agent_dir=str(agent_dir))
    a.ask("unit loads per location zone", engine="RTCIS", site="RTCIS_EUS")
    out = " ".join(str(m.content) for m in model.seen[-1] if m.type == "tool")
    assert "no theme or concept with RTCIS tables" in out and "locmst" not in out
