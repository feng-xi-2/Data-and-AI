"""SDC module / PMC process layer: parse the curated sources, gate every table on the live catalogs, only PASS rows
become graph edges. Fixtures are tiny literal copies of the real source formats."""
import sdc_pmc as S

SCRIPT = '''
SDC_RTCIS = {
    "03": {  # Receiving, Inventory & Quality
        "tables": ["rcphdr", "unitld", "ghost_tbl"],
        "views": ["AS_RTCIS_RCPHDR"],
    },
}
SDC_PRIME = {
    "03": {  # Receiving, Inventory & Quality
        "tables": ["rcvtrk", "invlod"],
        "config": ["poldat"],
        "description": "Receiving and inventory",
    },
}
PMC_PRIME_CONFIG = {
    "PMC-03.02.01": ["rcvtrk", "invlod", "nope"],
}
TRANSFORMATIONS = [
    ("unitld", "invlod", "RENAME", "Unit load -> inventory load"),
    ("rcphdr", "rcvtrk", "SPLIT", "Receipt header splits"),
    ("blditm", None, "ELIMINATE", "absorbed"),
]
print("never executed")
'''
STANDARDS = {"03.02.01": {"pmc": "03.02.01", "title": "Receiving Inbound", "source_file": "PMC 03-02-01 Receiving Inbound.xlsx"}}
CATALOG = {"RTCIS": {"rcphdr", "unitld", "blditm", "as_rtcis_rcphdr"}, "PrIME2022": {"rcvtrk", "invlod", "poldat"}, "PrIME2014": {"invlod"}}
MAPS = {("unitld", "invlod")}


def layer():
    return S.parse_sources(SCRIPT, STANDARDS)


def test_parse_reads_modules_with_their_names_without_running_the_script():
    m = layer()["modules"]["03"]
    assert m["name"] == "Receiving, Inventory & Quality"
    assert m["rtcis_tables"] == ["rcphdr", "unitld", "ghost_tbl"] and m["prime_config"] == ["poldat"]


def test_parse_joins_pmc_titles_from_the_sdc_standard_documents():
    p = layer()["pmc"]["PMC-03.02.01"]
    assert p["module"] == "03" and p["title"] == "Receiving Inbound" and p["source_file"].endswith(".xlsx")


def test_validate_rejects_tables_missing_from_the_live_catalog():
    # catches a layer that lets invented table names into the graph
    checks = S.validate(layer(), CATALOG, MAPS)
    bad = {(c["subject"], c["object"]) for c in checks if c["verdict"] != "PASS"}
    assert ("SDCModule:03", "ghost_tbl") in bad and ("PMCProcess:PMC-03.02.01", "nope") in bad
    assert ("SDCModule:03", "rcphdr") not in bad


def test_validate_compares_transformations_with_the_validated_mappings():
    t = {c["object"]: c for c in S.validate(layer(), CATALOG, MAPS) if c["kind"] == "transformation"}
    assert t["unitld->invlod"]["verdict"] == "PASS" and "agrees" in t["unitld->invlod"]["detail"]
    assert t["rcphdr->rcvtrk"]["verdict"] == "PASS" and "not in the validated mappings" in t["rcphdr->rcvtrk"]["detail"]
    assert t["blditm->(none)"]["verdict"] == "PASS"


def test_graph_gets_only_passing_edges_with_their_evidence():
    layer_ = layer()
    checks = S.validate(layer_, CATALOG, MAPS)
    nodes, edges = S.to_graph(layer_, checks)
    ids = {n["id"] for n in nodes}
    assert {"SDCModule:03", "PMCProcess:PMC-03.02.01"} <= ids
    e = {(x["label"], x["src"], x["dst"]) for x in edges}
    assert ("USES_TABLE", "SDCModule:03", "Table:rtcis:unitld") in e
    assert ("CONFIGURES", "PMCProcess:PMC-03.02.01", "Table:prime:rcvtrk") in e
    assert ("IN_MODULE", "PMCProcess:PMC-03.02.01", "SDCModule:03") in e
    assert ("TRANSFORMS_TO", "Table:rtcis:unitld", "Table:prime:invlod") in e
    assert not any("ghost_tbl" in x[2] or "nope" in x[2] for x in e)
    assert all(x.get("validated") for x in edges if x["label"] in ("USES_TABLE", "CONFIGURES"))


def test_presence_is_attached_per_engine_when_a_module_lists_the_same_name_twice():
    # review finding: RTCIS edges got the PrIME table's presence when both engines list e.g. prtmst
    edges = [{"label": "USES_TABLE", "src": "SDCModule:03", "dst": "Table:rtcis:prtmst"},
             {"label": "USES_TABLE", "src": "SDCModule:03", "dst": "Table:prime:prtmst"}]
    checks = [{"subject": "SDCModule:03", "object": "prtmst", "engine": "RTCIS", "populated": False, "presence": {"RTCIS_EUS": "empty"}},
              {"subject": "SDCModule:03", "object": "prtmst", "engine": "PrIME2022", "populated": True, "presence": {"PRIME22_DE08": "rows"}}]
    S.annotate_presence(edges, checks)
    assert edges[0]["populated"] == "no rows at checked sites" and edges[1]["populated"] == "rows at PRIME22_DE08"
