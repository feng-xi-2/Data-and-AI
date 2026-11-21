"""Core logic of the knowledge-graph API (no network): SQL guard, graph shaping for the UI, retrieval, batch parsing,
column-contract comparison, empty-field flags. Expected values are hand-derived literals."""
import pytest

import kg_core as k


# --- read-only guard: catches a guard that lets writes, multiple statements or SELECT INTO through ---------------
@pytest.mark.parametrize("sql", [
    "SELECT TOP 5 PRTNUM FROM dbo.prtmst",
    "WITH a AS (SELECT 1 AS x) SELECT x FROM a",
    "select l.LODNUM from dbo.invlod l -- trailing comment",
])
def test_guard_accepts_single_select(sql):
    assert k.guard_sql(sql).lower().startswith(("select", "with"))


@pytest.mark.parametrize("sql", [
    "DELETE FROM dbo.prtmst",
    "UPDATE dbo.prtmst SET PRTFAM = 'X'",
    "SELECT 1; DROP TABLE dbo.prtmst",
    "SELECT * INTO dbo.copy FROM dbo.prtmst",
    "EXEC sp_who",
    "INSERT INTO dbo.t SELECT 1",
    "",
])
def test_guard_rejects_anything_but_one_select(sql):
    with pytest.raises(k.UnsafeSQL):
        k.guard_sql(sql)


def test_guard_ignores_keywords_inside_strings_and_comments():
    sql = "SELECT 'DELETE FROM x' AS note /* UPDATE y */ FROM dbo.prtmst"
    assert k.guard_sql(sql).startswith("SELECT")


# --- engine labels: catches a wrong engine colour/legend (2014 shown as 2022 etc.) ---------------------------------
@pytest.mark.parametrize("vertex, want", [
    ({"id": "Table:rtcis:untdtl", "label": "Table", "platform": "RTCIS"}, "RTCIS table"),
    ({"id": "Column:prime14:invlod.lodnum", "label": "Column", "platform": "PrIME2014"}, "PrIME 2014 column"),
    ({"id": "Table:prime:invlod", "label": "Table", "platform": "PrIME2022"}, "PrIME 2022 table"),
    ({"id": "Learning:x:1", "label": "Learning"}, "Learning"),
])
def test_ui_label_distinguishes_the_three_engines(vertex, want):
    assert k.ui_label(vertex) == want


def test_to_ui_graph_shapes_nodes_and_drops_dangling_edges():
    vs = [{"id": "Table:rtcis:untdtl", "label": "Table", "platform": "RTCIS", "name": "untdtl", "pk": "Table:RTCIS"},
          {"id": "Table:prime:invdtl", "label": "Table", "platform": "PrIME2022", "name": "invdtl", "pk": "Table:PrIME2022"}]
    es = [{"src": "Table:rtcis:untdtl", "dst": "Table:prime:invdtl", "label": "MAPS_TO"},
          {"src": "Table:rtcis:untdtl", "dst": "Table:prime:missing", "label": "MAPS_TO"}]
    g = k.to_ui_graph(vs, es)
    assert [n["id"] for n in g["nodes"]] == ["Table:rtcis:untdtl", "Table:prime:invdtl"]
    assert g["nodes"][0]["labels"] == ["RTCIS table"]
    assert "pk" not in g["nodes"][0]["props"]
    assert g["edges"] == [{"src": "Table:rtcis:untdtl", "dst": "Table:prime:invdtl", "type": "MAPS_TO"}]


# --- SQL extraction from the model answer: catches losing the SQL or keeping the prose --------------------------
def test_extract_sql_prefers_fenced_block():
    text = "Here you go:\n```sql\nSELECT 1 AS x\n```\nThis returns one."
    assert k.extract_sql(text) == "SELECT 1 AS x"


def test_extract_sql_falls_back_to_first_select():
    assert k.extract_sql("Answer: SELECT a FROM t") == "SELECT a FROM t"


def test_extract_sql_returns_empty_when_no_sql():
    assert k.extract_sql("I cannot answer that.") == ""


# --- batch parsing: catches merged or lost items ----------------------------------------------------------------
def test_parse_batch_questions_one_per_line():
    assert k.parse_batch("Pallets per item?\n\n  Empty locations by area  \n", "ask") == ["Pallets per item?", "Empty locations by area"]


def test_parse_batch_sql_split_on_separator_lines():
    text = "SELECT 1\n---\nSELECT 2\nFROM t\nGO\nSELECT 3"
    assert k.parse_batch(text, "convert") == ["SELECT 1", "SELECT 2\nFROM t", "SELECT 3"]


# --- retrieval: catches ranking that ignores descriptions or engine filter ---------------------------------------
INDEX = [
    {"id": "Table:prime:invlod", "label": "Table", "engine": "PrIME2022", "name": "invlod", "description": "Inventory LPN (pallet / load)"},
    {"id": "Table:prime:locmst", "label": "Table", "engine": "PrIME2022", "name": "locmst", "description": "Location master"},
    {"id": "Table:rtcis:unitld", "label": "Table", "engine": "RTCIS", "name": "unitld", "description": ""},
    {"id": "Query:R16:prime", "label": "Query", "engine": "PrIME2022", "name": "RPM inventory on SSCC18 level", "description": "pallet inventory per item"},
]


def test_retrieve_ranks_by_name_and_description():
    ids = [x["id"] for x in k.retrieve("how many pallets per location", INDEX, engine="PrIME2022", k=3)]
    assert {"Table:prime:invlod", "Table:prime:locmst"} <= set(ids)


def test_retrieve_respects_engine_filter():
    assert all(x["engine"] == "RTCIS" for x in k.retrieve("pallet unit load", INDEX, engine="RTCIS", k=5))


# --- column contract: catches a converted query that silently renames, drops or reorders a field ----------------
def test_contract_identical():
    assert k.contract(["A", "b"], ["a", "B"]) == {"identical": True, "missing": [], "extra": [], "order_ok": True}


def test_contract_reports_missing_extra_and_order():
    assert k.contract(["A", "B", "C"], ["B", "A", "D"]) == {"identical": False, "missing": ["C"], "extra": ["D"], "order_ok": False}


# --- empty-field rule E1 in the UI: catches flagging a filled column or missing an empty one ---------------------
def test_empty_fields_flags_all_blank_columns():
    cols = ["a", "b", "c"]
    rows = [[1, None, ""], [2, None, " "]]
    assert k.empty_fields(cols, rows) == ["b", "c"]


def test_empty_fields_no_rows_means_no_flags():
    assert k.empty_fields(["a"], []) == []


def test_table_descriptions_come_from_the_knowledge_that_mentions_the_table():
    # catches tables left without words, so business questions ("pallet", "area") can never reach them
    nodes = [{"id": "Table:prime:aremst", "label": "Table", "name": "aremst"},
             {"id": "Query:R1:prime", "label": "Query", "intent": "Pallets per storage area"},
             {"id": "Concept:x", "label": "Concept", "name": "Location area"},
             {"id": "Learning:y", "label": "Learning", "text": "aremst holds the area description"}]
    edges = [{"src": "Query:R1:prime", "dst": "Table:prime:aremst", "label": "READS"},
             {"src": "Concept:x", "dst": "Table:prime:aremst", "label": "MENTIONS"},
             {"src": "Learning:y", "dst": "Table:prime:aremst", "label": "MENTIONS"}]
    d = k.table_descriptions(nodes, edges)["Table:prime:aremst"]
    assert "Pallets per storage area" in d and "Location area" in d and "area description" in d


def test_table_descriptions_use_transformation_rules_and_sdc_modules():
    # catches "unit loads" never reaching unitld: its words live on TRANSFORMS_TO rules and SDC module names
    nodes = [{"id": "Table:rtcis:unitld", "label": "Table", "name": "unitld"}, {"id": "Table:prime:invlod", "label": "Table", "name": "invlod"},
             {"id": "SDCModule:03", "label": "SDCModule", "name": "Receiving, Inventory & Quality"}]
    edges = [{"src": "Table:rtcis:unitld", "dst": "Table:prime:invlod", "label": "TRANSFORMS_TO", "rule": "Unit load -> inventory load"},
             {"src": "SDCModule:03", "dst": "Table:rtcis:unitld", "label": "USES_TABLE"}]
    d = k.table_descriptions(nodes, edges)
    assert "Unit load" in d["Table:rtcis:unitld"] and "Unit load" in d["Table:prime:invlod"]
    assert "Receiving, Inventory & Quality" in d["Table:rtcis:unitld"]


def test_retrieve_weights_rare_words_above_common_ones():
    # catches "items by unit loads" ranking every item_* table above unitld because "item" is in many names
    index = [{"id": f"T{i}", "label": "Table", "engine": "RTCIS", "name": f"item_x{i}", "description": ""} for i in range(8)] + \
            [{"id": "Tu", "label": "Table", "engine": "RTCIS", "name": "unitld", "description": "Unit load -> inventory load"}]
    assert k.retrieve("items by unit loads", index, engine="RTCIS", k=3)[0]["id"] == "Tu"


# --- validated join paths: catches prompts that leave the model to guess how tables join -------------------------
def test_join_paths_resolve_aliases_and_count_queries():
    sqls = ["SELECT 1 FROM dbo.invlod l JOIN dbo.invsub s ON s.lodnum = l.lodnum JOIN dbo.invdtl d ON d.subnum = s.subnum AND d.wh_id = @wh_id",
            "SELECT 1 FROM dbo.invsub x INNER JOIN dbo.invlod y ON y.LODNUM = x.LODNUM"]
    j = k.join_paths(sqls)
    assert j[("invlod.lodnum", "invsub.lodnum")] == 2
    assert j[("invdtl.subnum", "invsub.subnum")] == 1
    assert not any("wh_id" in a or "wh_id" in b for a, b in j)       # parameter filters are not joins


# --- execution accuracy: catches "validated" SQL that runs but answers a different question ----------------------
def test_exec_match_ignores_row_order_column_order_and_extra_columns():
    gold = [["A1", 3], ["B2", 5]]
    model = [[5, "B2", "DE08"], [3, "A1", "DE08"]]
    assert k.exec_match(gold, model) is True


def test_exec_match_fails_on_a_different_answer():
    assert k.exec_match([["A1", 3], ["B2", 5]], [["A1", 3], ["B2", 4]]) is False
    assert k.exec_match([["A1", 3]], [["A1", 3], ["A1", 3]]) is False          # extra rows
    assert k.exec_match([["A1", 3]], [["A1", 3.0]]) is True                       # numeric types compare by value


# --- review findings: guard bypasses that sqlglot parses as aliases but SQL Server runs as a second statement ----
@pytest.mark.parametrize("sql", [
    "SELECT 1 DELETE FROM dbo.invlod",
    "SELECT 1 --\nDELETE FROM t",
    "SELECT a FROM t SHUTDOWN",
    "SELECT 1 UNION SELECT 2 RECONFIGURE",
    "SELECT 1 EXEC sp_who",
    "SELECT a FROM t MERGE INTO t USING s ON 1 = 1 WHEN MATCHED THEN DELETE;",
])
def test_guard_blocks_a_second_statement_hidden_as_an_alias(sql):
    with pytest.raises(k.UnsafeSQL):
        k.guard_sql(sql)


@pytest.mark.parametrize("sql", ["SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')",
                                 "SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'SELECT 1')",
                                 "SELECT * FROM OPENDATASOURCE('SQLNCLI', 'x').db.dbo.t"])
def test_guard_blocks_remote_execution_functions(sql):
    with pytest.raises(k.UnsafeSQL):
        k.guard_sql(sql)


def test_guard_still_allows_quoted_reserved_names_and_normal_aliases():
    assert k.guard_sql('SELECT [delete] AS d, l.lodnum AS "exec" FROM dbo.invlod l')
    assert k.guard_sql("-- transliteration of the OpenQuery(RTCIS, ...) Oracle text\nSELECT 1 AS a /* not OPENROWSET( */")
