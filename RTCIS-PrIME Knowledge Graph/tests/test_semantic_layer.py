"""Semantic layer (Timbr concept / mapping SQL) -> graph, gated by the live replica catalogs. Fixtures copy the real formats."""
import semantic_layer as SL

CONCEPT = '''CREATE OR REPLACE CONCEPT "location" (
    "area" string,
    "usable_flag" integer,
    "warehouse_id" string,
    PRIMARY KEY("location", "warehouse_id"),
    LABEL("area", "location"),
    CONSTRAINT "moved_from_location" FOREIGN KEY ("location", "site_id") REFERENCES "warehouse_movements" ("from_location", "site_id") INVERSEOF "was_from_location"
)
INHERITS ("warehousing")
DESCRIPTION 'This refers to the locations within a warehouse'
WITH TAGS("concept.icon" = 'fa-location-dot');'''

MAPPING = '''-- comment
CREATE MAPPING "location gcfc" INTO "location" USING "gcfc" AS SELECT
    "L"."ARECOD" AS "area",
    "STOLOC" AS "location"
FROM "prodwms"."LOCMST" AS "L"
INNER JOIN "prodwms"."AREMST" AS "A" ON "A"."ARECOD" = "L"."ARECOD"
LEFT JOIN cdl.npi_lines n ON 1 = 1;'''

CATALOG = {"PrIME2014": {"locmst", "aremst"}, "PrIME2022": {"invlod"}, "RTCIS": {"unitld"}}


def test_concept_is_parsed_with_properties_relations_and_parent():
    c = SL.parse_concepts(CONCEPT)[0]
    assert c["name"] == "location" and c["parent"] == "warehousing"
    assert c["properties"] == {"area": "string", "usable_flag": "integer", "warehouse_id": "string"}
    assert c["primary_key"] == ["location", "warehouse_id"]
    assert c["relations"] == [{"name": "moved_from_location", "target": "warehouse_movements", "inverse": "was_from_location"}]
    assert c["description"].startswith("This refers")


def test_mapping_lists_its_concept_datasource_tables_and_properties():
    m = SL.parse_mappings(MAPPING)[0]
    assert (m["name"], m["concept"], m["datasource"]) == ("location gcfc", "location", "gcfc")
    assert m["tables"] == [("prodwms", "locmst"), ("prodwms", "aremst"), ("cdl", "npi_lines")]
    assert m["properties"] == ["area", "location"]


def test_graph_links_concepts_to_catalog_tables_and_flags_the_rest():
    # catches concepts pointing at tables nobody checked: only catalog tables become Table links
    nodes, edges = SL.to_graph(SL.parse_concepts(CONCEPT), SL.parse_mappings(MAPPING), CATALOG)
    e = {(x["label"], x["src"], x["dst"]) for x in edges}
    assert ("MAPPED_FROM", "SemanticConcept:location", "Table:prime14:locmst") in e
    assert ("MAPPED_FROM", "SemanticConcept:location", "Table:prime14:aremst") in e
    assert ("INHERITS", "SemanticConcept:location", "SemanticConcept:warehousing") in e
    assert ("RELATES_TO", "SemanticConcept:location", "SemanticConcept:warehouse_movements") in e
    ext = [n for n in nodes if n["label"] == "ExternalSource"]
    assert [n["id"] for n in ext] == ["ExternalSource:cdl.npi_lines"] and "outside" in ext[0]["validated"]
    assert ("MAPPED_FROM", "SemanticConcept:location", "ExternalSource:cdl.npi_lines") in e
    loc = next(n for n in nodes if n["id"] == "SemanticConcept:location")
    assert loc["n_properties"] == 3 and loc["mappings"] == "location gcfc (gcfc)"
