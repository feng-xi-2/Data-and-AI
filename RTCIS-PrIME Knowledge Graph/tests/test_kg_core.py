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


# --- one dialogue box: catches typed input sent to the wrong action ----------------------------------------------
@pytest.mark.parametrize("text, same, mode, n", [
    ("How many pallets are stored per area?", False, "ask", 1),
    ("How many pallets are stored\nper location area, by building?", False, "ask", 1),     # one question over two lines
    ("Pallets per area?\nOpen picks per wave?\n", False, "batch_ask", 2),
    ("1. pallets per area\n2. open picks per wave", False, "batch_ask", 2),
    ("SELECT ulid FROM live3.unitld", False, "convert", 1),
    ("-- RTCIS stock\nWITH s AS (SELECT 1 a) SELECT a FROM s", False, "convert", 1),
    ("SELECT ulid FROM live3.unitld", True, "validate", 1),
    ("SELECT 1 a\n---\nSELECT 2 b", False, "batch_convert", 2),
    ("SELECT 1 a\nGO\nSELECT 2 b", True, "batch_validate", 2),
])
def test_route_picks_the_action_from_what_was_typed(text, same, mode, n):
    r = k.route(text, same_engine=same)
    assert r["mode"] == mode and len(r["items"]) == n


def test_route_strips_list_markers_from_batch_questions():
    assert k.route("- pallets per area\n- open picks", same_engine=False)["items"] == ["pallets per area", "open picks"]


# --- concept-first routing: themes (Domain) and Timbr concepts lead to tables in every engine ---------------------
_CN = [{"id": "Domain:shipment", "label": "Domain", "name": "shipment"},
       {"id": "SemanticConcept:outbound_shipments", "label": "SemanticConcept", "name": "outbound_shipments",
        "description": "Outbound flow of a car move (trailer) through the DC"},
       {"id": "Table:prime:shipment", "label": "Table", "name": "shipment", "platform": "PrIME2022"},
       {"id": "Table:prime14:shipment", "label": "Table", "name": "shipment", "platform": "PrIME2014"},
       {"id": "Table:rtcis:shphdr", "label": "Table", "name": "shphdr", "platform": "RTCIS"},
       {"id": "Table:prime:invlod", "label": "Table", "name": "invlod", "platform": "PrIME2022"}]
_CE = [{"src": "Table:prime:shipment", "dst": "Domain:shipment", "label": "IN_DOMAIN"},
       {"src": "Table:rtcis:shphdr", "dst": "Table:prime:shipment", "label": "MAPS_TO"},
       {"src": "SemanticConcept:outbound_shipments", "dst": "Table:prime14:shipment", "label": "MAPPED_FROM"},
       {"src": "Table:prime14:shipment", "dst": "Table:prime:shipment", "label": "MAPS_TO"}]


def test_concept_map_links_themes_and_concepts_to_tables_in_all_three_engines():
    m = {x["id"]: x for x in k.concept_map(_CN, _CE)}
    theme, concept = m["Domain:shipment"], m["SemanticConcept:outbound_shipments"]
    assert theme["label"] == "Theme" and theme["engine"] is None   # never mixed into the per-engine table search
    assert theme["tables"] == {"PrIME2022": ["shipment"], "RTCIS": ["shphdr"], "PrIME2014": ["shipment"]}
    assert concept["tables"] == {"PrIME2014": ["shipment"], "PrIME2022": ["shipment"], "RTCIS": ["shphdr"]}
    assert "trailer" in concept["description"] and "invlod" not in str(m)


def test_table_descriptions_carry_their_theme_and_concept_words():
    d = k.table_descriptions(_CN, _CE)
    assert "theme shipment" in d["Table:prime:shipment"] and "concept outbound shipments" in d["Table:prime:shipment"]
    assert "concept outbound shipments" in d["Table:prime14:shipment"] and "theme shipment" in d["Table:rtcis:shphdr"]


def test_a_theme_is_found_by_the_names_and_descriptions_of_its_tables_and_generic_tables_are_left_out():
    nodes = [{"id": f"Domain:{d}", "label": "Domain", "name": d} for d in ("outbound", "receiving", "trailer")] + [
        {"id": "Table:prime:shipment_line", "label": "Table", "name": "shipment_line", "platform": "PrIME2022"},
        {"id": "Table:prime:wcsmst", "label": "Table", "name": "wcsmst", "platform": "PrIME2022"},
        {"id": "Table:prime:wh", "label": "Table", "name": "wh", "platform": "PrIME2022"},
        {"id": "Query:R1:prime", "label": "Query", "intent": "WCS warehouse control system setup"}]
    edges = [{"src": "Table:prime:shipment_line", "dst": "Domain:outbound", "label": "IN_DOMAIN"},
             {"src": "Table:prime:wcsmst", "dst": "Domain:receiving", "label": "IN_DOMAIN"},
             {"src": "Query:R1:prime", "dst": "Table:prime:wcsmst", "label": "READS"}] + [
        {"src": "Table:prime:wh", "dst": f"Domain:{d}", "label": "IN_DOMAIN"} for d in ("outbound", "receiving", "trailer")]
    m = k.concept_map(nodes, edges)
    assert k.retrieve("How many shipments per status?", m, k=1)[0]["name"] == "outbound"
    assert k.retrieve("Which WCS ids are configured?", m, k=1)[0]["name"] == "receiving"
    assert all("wh" not in x["tables"].get("PrIME2022", []) for x in m)   # in every theme = says nothing about the question


def test_route_concepts_ignores_question_filler_words_and_ranks_the_theme_tables_by_the_question():
    entries = [{"id": "SemanticConcept:short_status", "label": "SemanticConcept", "engine": None, "name": "short_status",
                "description": "short status of an order line", "tables": {"PrIME2022": ["prtftp"]}},
               {"id": "Domain:receiving", "label": "Theme", "engine": None, "name": "receiving",
                "description": "receiving trlr wkohdr rcvtrk receiving truck", "tables": {"PrIME2022": ["trlr", "wkohdr", "rcvtrk"]}}]
    tables = [{"id": "Table:prime:rcvtrk", "label": "Table", "engine": "PrIME2022", "name": "rcvtrk", "description": "receiving truck header"},
              {"id": "Table:prime:trlr", "label": "Table", "engine": "PrIME2022", "name": "trlr", "description": "trailer"},
              {"id": "Table:prime:wkohdr", "label": "Table", "engine": "PrIME2022", "name": "wkohdr", "description": "work order"}]
    hits = k.route_concepts("How many receiving trucks are there in each receiving status?", entries, tables, "PrIME2022")
    assert hits[0]["name"] == "receiving" and hits[0]["ranked"]["PrIME2022"][0] == "rcvtrk"
    assert all(h["name"] != "short_status" for h in hits)    # 'status' alone does not pick a concept


def test_table_descriptions_start_with_the_official_prime_description():
    nodes = [{"id": "Table:prime:wcsmst", "label": "Table", "name": "wcsmst", "platform": "PrIME2022",
              "description": "The main Warehouse Control System table."}]
    assert k.table_descriptions(nodes, [])["Table:prime:wcsmst"].startswith("The main Warehouse Control System table.")


def test_route_concepts_lists_the_direct_theme_tables_before_those_reached_through_mappings():
    nodes = [{"id": "Domain:receiving", "label": "Domain", "name": "receiving"},
             {"id": "Table:prime:rcvtrk", "label": "Table", "name": "rcvtrk", "platform": "PrIME2022", "description": "Inbound Shipment"},
             {"id": "Table:prime14:rcvtrk", "label": "Table", "name": "rcvtrk", "platform": "PrIME2014"},
             {"id": "Table:prime:invdtl", "label": "Table", "name": "invdtl", "platform": "PrIME2022",
              "description": "receiving inbound receipt inventory detail"}]
    edges = [{"src": "Table:prime:rcvtrk", "dst": "Domain:receiving", "label": "IN_DOMAIN"},
             {"src": "Table:prime14:rcvtrk", "dst": "Table:prime:rcvtrk", "label": "MAPS_TO"},
             {"src": "Table:prime14:rcvtrk", "dst": "Table:prime:invdtl", "label": "MAPS_TO"}]
    desc = k.table_descriptions(nodes, edges)
    index = [{"id": n["id"], "label": "Table", "engine": n["platform"], "name": n["name"], "description": desc.get(n["id"], "")}
             for n in nodes if n["label"] == "Table"]
    hits = k.route_concepts("receiving inbound receipts", k.concept_map(nodes, edges), index, "PrIME2022")
    assert hits[0]["ranked"]["PrIME2022"] == ["rcvtrk", "invdtl"]
