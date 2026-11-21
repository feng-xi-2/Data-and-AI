"""Semantic layer (Timbr) -> knowledge graph: concepts, their properties, relationships and inheritance, and the warehouse
tables each concept is mapped from. Source: the deployed semantic-layer repository (concept / mapping SQL files).
Gate: a mapped table becomes a link to the catalog-validated `Table` vertex only if the live replica catalog has it
(schema prodwms -> PrIME 2014, dbo -> PrIME 2022, live3 -> RTCIS); anything else (lakehouse / Databricks sources) is an
`ExternalSource` vertex marked as not checked against a replica."""
import re

SCHEMA_ENGINE = {"prodwms": ("PrIME2014", "prime14"), "dbo": ("PrIME2022", "prime"), "live3": ("RTCIS", "rtcis")}
CONCEPT_HEAD = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?CONCEPT\s+"([^"]+)"\s*\(', re.I)
MAPPING_RX = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?MAPPING\s+"([^"]+)"\s+INTO\s+\(?\s*"([^"]+)"\s*\)?\s*(?:USING\s+"([^"]+)")?\s*AS\s+(.*?)(?:;|\Z)',
                        re.I | re.S)
TABLE_RX = re.compile(r'\b(?:FROM|JOIN)\s+((?:"[^"]+"|\[[^\]]+\]|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:"[^"]+"|\[[^\]]+\]|[A-Za-z_][\w$]*)){1,2})', re.I)
PROP_RX = re.compile(r'^\s*"([^"]+)"\s+([A-Za-z]+)', re.M)
ALIAS_RX = re.compile(r'\bAS\s+"([^"]+)"', re.I)


def _strip_comments(sql):
    return re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)


def _ident(x):
    return x.strip().strip('"[]').lower()


def _balanced(s, start):
    """Index just after the ')' that closes the '(' at s[start], skipping quoted text."""
    depth, i, q = 0, start, None
    while i < len(s):
        ch = s[i]
        if q:
            q = None if ch == q else q
        elif ch in "'\"":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


def parse_concepts(sql):
    sql, out = _strip_comments(sql), []
    for m in CONCEPT_HEAD.finditer(sql):
        name, open_at = m.group(1), m.end() - 1
        close = _balanced(sql, open_at)
        body, tail = sql[open_at + 1:close - 1], sql[close:close + 4000]
        nxt = CONCEPT_HEAD.search(tail)
        tail = tail[:nxt.start()] if nxt else tail
        parent = re.match(r'\s*INHERITS\s*\(\s*"([^"]+)"', tail, re.I)
        desc = re.search(r"DESCRIPTION\s+'((?:[^']|'')*)'", tail, re.I)
        props = {p: t.lower() for p, t in PROP_RX.findall(body) if t.upper() not in ("PRIMARY", "CONSTRAINT", "LABEL")}
        pk = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", body, re.I)
        rels = [{"name": r, "target": t, "inverse": i} for r, t, i in re.findall(
            r'CONSTRAINT\s+"([^"]+)"\s+FOREIGN\s+KEY\s*\([^)]*\)\s*REFERENCES\s+"([^"]+)"\s*\([^)]*\)\s*(?:INVERSEOF\s+"([^"]+)")?', body, re.I)]
        out.append({"name": name, "parent": parent.group(1) if parent else None, "properties": props,
                    "primary_key": [_ident(x) for x in pk.group(1).split(",")] if pk else [],
                    "relations": rels, "description": desc.group(1).replace("''", "'") if desc else ""})
    return out


def parse_mappings(sql):
    out = []
    for name, concept, ds, body in MAPPING_RX.findall(_strip_comments(sql)):
        tables = []
        for ref in TABLE_RX.findall(body):
            parts = [_ident(p) for p in re.split(r"\s*\.\s*", ref)]
            t = (parts[-2], parts[-1])
            if t not in tables:
                tables.append(t)
        select_list = re.split(r"\bFROM\b", body, maxsplit=1, flags=re.I)[0]
        props = list(dict.fromkeys(ALIAS_RX.findall(select_list)))
        out.append({"name": name, "concept": concept, "datasource": ds or "", "tables": tables, "properties": props})
    return out


def to_graph(concepts, mappings, catalog):
    nodes, edges, seen = {}, [], set()

    def node(nid, label, **p):
        nodes.setdefault(nid, {"id": nid, "label": label}).update({k: v for k, v in p.items() if v not in (None, "")})

    def edge(label, src, dst, **p):
        if (label, src, dst) not in seen:
            seen.add((label, src, dst))
            edges.append(dict({"label": label, "src": src, "dst": dst}, **p))

    by_concept = {}
    for m in mappings:
        by_concept.setdefault(m["concept"], []).append(m)
    names = {c["name"] for c in concepts}
    for c in concepts:
        cid = f"SemanticConcept:{c['name']}"
        ms = by_concept.get(c["name"], [])
        node(cid, "SemanticConcept", name=c["name"], description=c["description"][:600], n_properties=len(c["properties"]),
             properties=", ".join(f"{p} {t}" for p, t in c["properties"].items())[:1400], primary_key=", ".join(c["primary_key"]),
             mappings="; ".join(f"{m['name']} ({m['datasource']})" for m in ms), source="semantic layer (Timbr)")
        if c["parent"]:
            node(f"SemanticConcept:{c['parent']}", "SemanticConcept", name=c["parent"], source="semantic layer (Timbr)")
            edge("INHERITS", cid, f"SemanticConcept:{c['parent']}")
        for r in c["relations"]:
            if r["target"] not in names:
                node(f"SemanticConcept:{r['target']}", "SemanticConcept", name=r["target"], source="semantic layer (Timbr)")
            edge("RELATES_TO", cid, f"SemanticConcept:{r['target']}", name=r["name"], inverse=r["inverse"] or "")
    for m in mappings:
        cid = f"SemanticConcept:{m['concept']}"
        node(cid, "SemanticConcept", name=m["concept"], source="semantic layer (Timbr)")
        for schema, table in m["tables"]:
            eng = SCHEMA_ENGINE.get(schema)
            if eng and table in catalog.get(eng[0], set()):
                edge("MAPPED_FROM", cid, f"Table:{eng[1]}:{table}", mapping=m["name"], datasource=m["datasource"], validated="V1 live catalog")
            else:
                xid = f"ExternalSource:{schema}.{table}"
                node(xid, "ExternalSource", name=f"{schema}.{table}",
                     validated="outside the replica catalogs (lakehouse / other source) - not checked here"
                     if not eng else f"schema {schema} but table not in the live {eng[0]} catalog")
                edge("MAPPED_FROM", cid, xid, mapping=m["name"], datasource=m["datasource"])
    return list(nodes.values()), edges
