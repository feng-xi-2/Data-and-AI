"""Integration tests against the REAL services: Cosmos DB for Apache Gremlin (whs_kg / rtcis_prime), the GenAI platform
(GPT-52, project uvamain) and the replica databases (RTCIS Euskirchen, PrIME 2014 Xiqing, PrIME 2022 DE08).
    python -m pytest tests -m cloud
Needs the signed-in Azure token and the local env (env.local.ps1). Read-only everywhere."""
import pytest

pytestmark = pytest.mark.cloud


@pytest.fixture(scope="module")
def svc():
    import kg_services as S
    s = S.services()
    yield s
    s.graph.close()


# --- Cosmos graph views: catches a view that loses an engine or returns dangling edges ---------------------------
def test_versions_view_shows_the_table_in_all_three_engines(svc):
    g = svc.graph.view("versions", "invlod")
    labels = {n["labels"][0] for n in g["nodes"]}
    assert {"PrIME 2014 table", "PrIME 2022 table", "RTCIS table"} <= labels
    assert {"PrIME 2014 column", "PrIME 2022 column", "RTCIS column"} <= labels      # column lineage across all three
    ids = {n["id"] for n in g["nodes"]}
    assert g["edges"] and all(e["src"] in ids and e["dst"] in ids for e in g["edges"])


def test_sdc_view_links_module_pmc_and_tables_of_both_engines(svc):
    g = svc.graph.view("sdc", "03")
    labels = {n["labels"][0] for n in g["nodes"]}
    assert {"SDCModule", "PMCProcess", "RTCIS table", "PrIME 2022 table"} <= labels
    types = {e["type"] for e in g["edges"]}
    assert {"USES_TABLE", "IN_MODULE", "CONFIGURES"} <= types


def test_sdc_view_for_one_pmc_shows_what_it_configures(svc):
    g = svc.graph.view("sdc", "PMC-03.02.01")
    ids = {n["id"] for n in g["nodes"]}
    assert {"PMCProcess:PMC-03.02.01", "SDCModule:03", "Table:prime:rcvlin"} <= ids


def test_semantic_view_shows_a_concept_with_its_tables_in_the_engines(svc):
    g = svc.graph.view("semantic", "location")
    labels = {n["labels"][0] for n in g["nodes"]}
    assert "SemanticConcept" in labels and {"PrIME 2014 table", "RTCIS table"} & labels
    assert any(e["type"] == "MAPPED_FROM" for e in g["edges"])


def test_semantic_overview_shows_concepts_and_their_relations(svc):
    g = svc.graph.view("semantic", "")
    assert sum(1 for n in g["nodes"] if n["labels"][0] == "SemanticConcept") >= 20
    assert {"INHERITS", "RELATES_TO"} <= {e["type"] for e in g["edges"]}


def test_ontology_schema_and_sample_read_the_live_cosmos_graph(svc):
    s = svc.graph.schema()
    labels = {x["label"]: x["count"] for x in s["labels"]}
    assert s["totals"]["nodes"] > 30000 and s["totals"]["relationships"] > 40000
    assert labels.get("Table:RTCIS", 0) > 100 and labels.get("SemanticConcept", 0) >= 30
    g = svc.graph.sample("Table:PrIME2022", 30)
    assert g["nodes"] and all(n["labels"] for n in g["nodes"]) and g["edges"]


def test_query_view_shows_both_sides_of_a_conversion(svc):
    g = svc.graph.view("query", "R16")
    ids = {n["id"] for n in g["nodes"]}
    assert {"Query:R16:rtcis", "Query:R16:prime"} <= ids
    assert any(e["type"] == "CONVERTS_TO" for e in g["edges"])


def test_context_returns_validated_mappings_from_cosmos(svc):
    ctx = svc.graph.context(["Table:rtcis:untdtl"])
    assert any(m["to"].startswith(("invdtl.", "invsub.", "invlod.")) for m in ctx["mappings"])


# --- replica validation: catches a validator that hides engine errors or misses empty fields ---------------------
def test_validate_reports_the_engine_error_before_executing(svc):
    r = svc.db.validate("SELECT NOPE_COL FROM dbo.invlod", "PRIME22_DE08")
    assert r["ok"] is False and r["stage"] == "describe" and "NOPE_COL" in r["error"]


def test_validate_executes_with_params_and_flags_empty_fields(svc):
    r = svc.db.validate("SELECT TOP 5 LODNUM, CAST(NULL AS int) AS nothing FROM dbo.invlod WHERE WH_ID = @wh_id",
                        "PRIME22_DE08", {"wh_id": "DE08"})
    assert r["ok"] is True and r["columns"] == ["LODNUM", "nothing"]
    assert 0 < len(r["rows"]) <= 5 and r["empty_fields"] == ["nothing"]


@pytest.mark.parametrize("site, sql", [
    ("RTCIS_EUS", "SELECT TOP 3 itmcod FROM [EUSKIRCHEN_simp].live3.itmmst"),
    ("PRIME14_XQ", "SELECT TOP 3 prtnum FROM prodwms.prtmst"),
])
def test_validate_runs_on_rtcis_and_prime2014(svc, site, sql):
    r = svc.db.validate(sql, site)
    assert r["ok"] is True and len(r["rows"]) == 3


def test_validate_refuses_writes_without_touching_the_database(svc):
    r = svc.db.validate("DELETE FROM dbo.invlod", "PRIME22_DE08")
    assert r["ok"] is False and r["stage"] == "guard"


# --- model + end to end ------------------------------------------------------------------------------------------
def test_genai_model_answers(svc):
    import kg_services as S   # svc.llm is only the Deep Agent label; the platform client is GenAiLLM
    assert "ok" in S.GenAiLLM().chat([{"role": "user", "content": "Reply with the single word OK."}]).lower()
    assert "Deep Agent" in svc.llm.model


def test_ask_end_to_end_is_validated_on_de08(svc):
    r = svc.assistant.ask("How many pallets (loads) are stored per location area?", engine="PrIME2022", site="PRIME22_DE08",
                          params={"wh_id": "DE08"})
    assert r["status"] == "validated", (r["sql"], r["validation"])
    assert r["validation"]["rows"]


def test_convert_end_to_end_rtcis_to_prime2022(svc):
    src = "SELECT equip, equip_desc FROM [EUSKIRCHEN_simp].live3.equip"
    r = svc.assistant.convert(src, "RTCIS", "PrIME2022", "RTCIS_EUS", "PRIME22_DE08", params={"wh_id": "DE08"})
    assert r["status"].startswith("validated"), (r["sql"], r["validation"])
    assert r["contract"]["identical"], r["contract"]


def test_validate_fetches_datetimeoffset_columns(svc):
    # catches pyodbc "ODBC SQL type -155 is not yet supported" turning a valid query (AT TIME ZONE) into a failure
    r = svc.db.validate("SELECT TOP 1 itmcod, SYSDATETIMEOFFSET() AS t FROM [EUSKIRCHEN_simp].live3.itmmst", "RTCIS_EUS")
    assert r["ok"] is True and r["rows"][0][1]
