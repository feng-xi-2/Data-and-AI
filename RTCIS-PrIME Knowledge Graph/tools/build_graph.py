"""Entity recognition + graph build: RTCIS -> PrIME 2022 conversion knowledge as a property graph.

Inputs (the RTCIS-PrIME LLM wiki at WIKI_ROOT, plus benchmark/catalog.json):
  queries/rtcis_tsql/*.sql, queries/prime/*.sql   SQL entity recognition -> Query READS Table / READS_COLUMN Column,
                                                  OutputField DERIVED_FROM Column
  wiki/ground-truth/mappings.md, wiki/entities/tables.md, raw/schema/verified-mappings.json
                                                  curated MAPS_TO (column/table level, with measured agreement + tag)
  results/field_check.json, queries/field_notes.json   OutputField status / fill / agreement, Finding EXPLAINED_BY
  results/expert_rules.json, wiki/experts/ruiz-rs-obs.md   ExpertRule, Query APPLIES_RULE (PASS/N/A/FAIL)
  wiki/learnings/*.md, wiki/ground-truth/data-facts.md    Learning / DataFact MENTIONS Table|Column (prose entity recognition)
  wiki/**/*.md                                    Concept pages, LINKS_TO between pages
  templates/*                                     Template, Query RENDERED_WITH Template

Output: relationships/nodes.json, relationships/edges.json, relationships/ontology.json (copied from ONTOLOGY below),
        benchmark/predicted.json (what the extractor recognised per query - scored by benchmark.py).

    python build_graph.py
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

WIKI = os.environ.get("WIKI_ROOT", os.path.join(os.path.dirname(__file__), "..", "..", "RTCIS-PrIME-LLM-Wiki"))
KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(WIKI, "tools"))
from field_check import source_map, strip_comments  # noqa: E402

ONTOLOGY = {
    "vertices": {
        "Platform": ["name"], "Site": ["name", "engine"], "Domain": ["name"],
        "Table": ["name", "platform", "kind", "n_columns", "description", "theme", "query_occurrences", "validated"],
        "Column": ["name", "table", "platform", "data_type", "description", "primary_key"],
        "Query": ["qid", "side", "title", "file", "intent", "grade", "open_points", "params", "validated_runs"], "OutputField": ["qid", "name", "status", "fill_rtcis", "fill_de08", "fill_athens", "agreement_pct"],
        "Mapping": ["rtcis", "prime", "agreement", "tag", "source"], "Finding": ["category", "kind", "text"],
        "ExpertRule": ["code", "text"], "Learning": ["n", "text", "page"], "DataFact": ["n", "text", "consequence"],
        "Concept": ["page", "title", "type"], "Template": ["name", "purpose"], "JoinPath": ["name", "rtcis_join", "reason"],
        "SDCModule": ["number", "name", "description"], "PMCProcess": ["code", "name", "source_file", "documented"],
    },
    "edges": {   # label: (domain, range)
        "IN_PLATFORM": (["Table"], ["Platform"]), "HAS_COLUMN": (["Table"], ["Column"]),
        "EXISTS_AT": (["Table"], ["Site"]), "IN_DOMAIN": (["Table"], ["Domain"]),
        "READS": (["Query"], ["Table"]), "READS_COLUMN": (["Query"], ["Column"]), "HAS_FIELD": (["Query"], ["OutputField"]),
        "DERIVED_FROM": (["OutputField"], ["Column"]), "CONVERTS_TO": (["Query"], ["Query"]),
        "MAPS_TO": (["Column", "Table"], ["Column", "Table"]), "MAPS_FROM": (["Mapping"], ["Column", "Table"]),
        "MAPS_INTO": (["Mapping"], ["Column", "Table"]), "EXPLAINED_BY": (["OutputField"], ["Finding"]),
        "APPLIES_RULE": (["Query"], ["ExpertRule"]), "MENTIONS": (["Learning", "DataFact", "Finding", "ExpertRule", "Concept", "Mapping"], ["Table", "Column"]),
        "DOCUMENTED_IN": (["Query", "ExpertRule"], ["Concept"]), "LINKS_TO": (["Concept"], ["Concept"]),
        "RENDERED_WITH": (["Query"], ["Template"]), "JOINS_VIA": (["Table"], ["JoinPath"]),
        "USES_TABLE": (["SDCModule"], ["Table"]), "IN_MODULE": (["PMCProcess"], ["SDCModule"]),
        "CONFIGURES": (["PMCProcess"], ["Table"]), "TRANSFORMS_TO": (["Table"], ["Table"]), "JOINS_WITH": (["Column"], ["Column"]),
    },
}
KEYWORDS = set("""select from where join inner left right full outer cross apply on and or not as group by order having union all
distinct top case when then else end is null in like between exists with over partition row_number dense_rank rank cast convert
isnull coalesce nullif sum min max count avg left right substring format datediff dateadd getdate sysdatetimeoffset at time zone
values into set declare floor round decimal int nvarchar varchar numeric datetime date asc desc hash loop merge option openjson
value len trim ltrim rtrim upper lower concat iif string_agg for xml path stuff charindex replace""".split())


class Graph:
    def __init__(self):
        self.v, self.e, self.dropped, self.unvalidated, self.validation_notes = {}, {}, [], [], {}

    @staticmethod
    def vid(label_key):
        return re.sub(r"[/\\?#\s]+", "_", label_key)[:250]

    def node(self, label, key, **props):
        vid = self.vid(f"{label}:{key}")
        cur = self.v.setdefault(vid, {"id": vid, "label": label})
        cur.update({k: v for k, v in props.items() if v is not None and v != ""})
        return vid

    def edge(self, label, src, dst, **props):
        src, dst = self.vid(src or ""), self.vid(dst or "")
        if src not in self.v or dst not in self.v:
            self.dropped.append((label, src, dst))
            return None
        eid = hashlib.sha1(f"{label}|{src}|{dst}".encode()).hexdigest()[:20]
        cur = self.e.setdefault(eid, {"id": eid, "label": label, "src": src, "dst": dst})
        cur.update({k: v for k, v in props.items() if v is not None and v != ""})
        return eid


def rd(*p):
    return open(os.path.join(WIKI, *p), encoding="utf-8").read()


CAT = json.load(open(os.path.join(KIT, "benchmark", "catalog.json"), encoding="utf-8"))
SIDE_ENGINE = {"rtcis": "RTCIS", "prime14": "PrIME2014", "prime": "PrIME2022"}
COLSET = {side: {t: set(c) for t, c in CAT["engines"][eng].items()} for side, eng in SIDE_ENGINE.items()}
PLAT = SIDE_ENGINE
try:
    from build_report import WHAT, STATUS  # noqa: E402  (wiki report builder: business intent + grade per query)
except Exception:
    WHAT, STATUS = {}, {}
PARAMS = json.load(open(os.path.join(WIKI, "queries", "params.json"), encoding="utf-8"))
RUNS = defaultdict(dict)
for _f in os.listdir(os.path.join(WIKI, "results")):
    _m = re.match(r"^(RTCIS_EUS|PRIME_DE08|PRIME_WMD1)__(rtcis_tsql|prime)__(R\d\d)\.json$", _f)
    if _m:
        _r = json.load(open(os.path.join(WIKI, "results", _f), encoding="utf-8"))
        if _r.get("ok"):
            RUNS[(_m.group(3), _m.group(2))][_m.group(1)] = _r


# ------------------------------------------------------------------ SQL entity recognition
TABREF = re.compile(r"\b(?:from|join)\s+((?:\[?[\w$]+\]?\.){0,2}\[?[\w$]+\]?)(?:\s+(?:as\s+)?(?!(?:on|where|join|inner|left|right|full|cross|outer|group|order|"
                    r"with|union|having|option|apply|select)\b)([A-Za-z_]\w*))?", re.I)
CTE = re.compile(r"(?:\bwith|,)\s*([A-Za-z_]\w*)\s+as\s*\(", re.I)
DERIVED = re.compile(r"\)\s*(?:as\s+)?([A-Za-z_]\w*)\b", re.I)
QUALCOL = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)\.\[?([A-Za-z_]\w*)\]?(?!\s*\()")
IDENT = re.compile(r"(?<![\w.@#\]\[])([A-Za-z_]\w*)(?![\w.(])")


def last(name):
    return name.split(".")[-1].strip("[]").lower()


def scan_sql(sql, side):
    """Recognise base tables, alias map, columns. Returns (tables, alias->table, columns set)."""
    s = re.sub(r"'(?:[^']|'')*'", "''", strip_comments(sql))
    ctes = {m.group(1).lower() for m in CTE.finditer(s)}
    derived = {m.group(1).lower() for m in DERIVED.finditer(s)} - KEYWORDS
    alias, tables = {}, set()
    for m in TABREF.finditer(s):
        t = last(m.group(1))
        if t in KEYWORDS:
            continue
        a = (m.group(2) or t).lower()
        if t in ctes:
            alias[a] = ("cte", t)
            continue
        tables.add(t)
        alias[a] = ("table", t)
        alias.setdefault(t, ("table", t))
    cols = set()
    for a, c in QUALCOL.findall(s):
        k = alias.get(a.lower())
        if k and k[0] == "table":
            cols.add(f"{k[1]}.{c.lower()}")
    # bare identifiers: resolve when exactly one recognised table of the query has that column (catalog-guided)
    owners = defaultdict(set)
    for t in tables:
        for c in COLSET[side].get(t, ()):
            owners[c].add(t)
    known_alias = set(alias) | ctes | derived
    for w in IDENT.findall(s):
        lw = w.lower()
        if lw in KEYWORDS or lw in known_alias or lw.startswith("@"):
            continue
        if len(owners.get(lw, ())) == 1:
            cols.add(f"{next(iter(owners[lw]))}.{lw}")
    return tables, alias, cols


def field_sources(path, cols, alias, tables, side):
    """Output field -> recognised base columns (follows CTE aliases through source_map)."""
    exprs, _ = source_map(path, cols)
    sql = open(path, encoding="utf-8").read()
    # CTE column defs: alias.col where alias is a CTE -> look the col up in all select lists (source_map defs)
    owners = defaultdict(set)
    for t in tables:
        for c in COLSET[side].get(t, ()):
            owners[c].add(t)
    out = {}
    for col in cols:
        e = exprs.get(col.lower(), "")
        e = re.sub(r"'(?:[^']|'')*'", "''", e)
        found = set()
        for a, c in QUALCOL.findall(e):
            k = alias.get(a.lower())
            if k and k[0] == "table":
                found.add(f"{k[1]}.{c.lower()}")
            elif k and k[0] == "cte":
                sub, _ = source_map_cte(sql, c)
                for a2, c2 in QUALCOL.findall(sub):
                    k2 = alias.get(a2.lower())
                    if k2 and k2[0] == "table":
                        found.add(f"{k2[1]}.{c2.lower()}")
        if not found:
            for w in IDENT.findall(e):
                if w.lower() not in KEYWORDS and len(owners.get(w.lower(), ())) == 1:
                    found.add(f"{next(iter(owners[w.lower()]))}.{w.lower()}")
        out[col] = sorted(found)
    return out


def source_map_cte(sql, col):
    """Expression that defines `col` inside any CTE / derived select list (first definition wins)."""
    s = strip_comments(sql)
    m = re.search(r"([^,\n(]*?)\s+(?:as\s+)?\b" + re.escape(col) + r"\b\s*(?:,|\n|\s+from\b)", s, re.I)
    return (m.group(1) if m else ""), None


# ------------------------------------------------------------------ prose entity recognition
BACKTICK = re.compile(r"`([^`]{2,80})`")
DOTTED = re.compile(r"\b([A-Za-z_]\w{2,})\.([A-Za-z_]\w{1,})\b")


def prose_entities(text, g, known_cols, known_tabs):
    """Tables/columns mentioned in markdown text, restricted to entities already in the graph (no new nodes from prose)."""
    hits = set()
    for t, c in DOTTED.findall(text):
        for p in ("rtcis", "prime14", "prime"):
            vid = f"Column:{p}:{t.lower()}.{c.lower()}"
            if vid in g.v:
                hits.add(vid)
    for chunk in BACKTICK.findall(text) + re.findall(r"\b[A-Z][A-Z_0-9]{3,}\b", text):
        for tok in re.findall(r"[A-Za-z_]\w+", chunk):
            lt = tok.lower()
            hits.update(known_tabs.get(lt, ()))
            if tok.isupper() or chunk.strip() == tok:
                hits.update(known_cols.get(lt, ()))
    return hits


def main():
    g = Graph()
    for p in PLAT.values():
        g.node("Platform", p, name=p)
    fcheck = json.load(open(os.path.join(WIKI, "results", "field_check.json"), encoding="utf-8"))["queries"]
    notes = json.load(open(os.path.join(WIKI, "queries", "field_notes.json"), encoding="utf-8"))
    rules = json.load(open(os.path.join(WIKI, "results", "expert_rules.json"), encoding="utf-8"))
    predicted = {}

    def table(side, t):
        """Existing (catalog-validated) table vertex, or None - entities not in a real catalog never enter the graph."""
        vid = f"Table:{side}:{t}"
        if vid not in g.v:
            g.unvalidated.append(("table", side, t))
            return None
        return vid

    def column(side, tc):
        vid = f"Column:{side}:{tc}"
        if vid not in g.v:
            g.unvalidated.append(("column", side, tc))
            return None
        return vid

    # ---------------------------------------------------------- schema layer: real catalogs only
    dm = json.load(open(os.path.join(WIKI, "raw", "schema", "prime-datamodel.json"), encoding="utf-8"))
    erd = json.load(open(os.path.join(WIKI, "raw", "schema", "erd-index.json"), encoding="utf-8"))
    dom_of = defaultdict(set)
    for dom, diagrams in erd.get("domain_index", {}).items():
        g.node("Domain", dom, name=dom)
        for dg in diagrams:
            for t in (erd.get("diagrams", {}).get(dg, {}) or {}).get("tables", []) if isinstance(erd.get("diagrams", {}).get(dg), dict) else []:
                dom_of[t.lower()].add(dom)
    for t, dgs in erd.get("table_to_diagrams", {}).items():
        for dom, diagrams in erd.get("domain_index", {}).items():
            if set(dgs) & set(diagrams):
                dom_of[t.lower()].add(dom)
    dm_check = defaultdict(int)
    for key, s in CAT["sites"].items():
        g.node("Site", key, name=s["site"], engine=s["engine"])
    for side, eng in SIDE_ENGINE.items():
        for t, cols in CAT["engines"][eng].items():
            meta = dm["tables"].get(t, {}) if side != "rtcis" else {}
            use = dm.get("usage", {}).get(t, {}) if side != "rtcis" else {}
            tv = g.node("Table", f"{side}:{t}", name=t, platform=eng, kind=CAT["kinds"][eng].get(t, "TABLE"), n_columns=len(cols),
                        description=(meta.get("description") or "")[:400], theme=use.get("classification", ""),
                        query_occurrences=use.get("occurrences"), validated="catalog")
            g.edge("IN_PLATFORM", tv, f"Platform:{eng}")
            for key, s in CAT["sites"].items():
                if s["engine"] == eng and t in s["tables"]:
                    g.edge("EXISTS_AT", tv, f"Site:{key}")
            for dom in dom_of.get(t, ()):
                if side != "rtcis":
                    g.edge("IN_DOMAIN", tv, f"Domain:{dom}")
            fields = meta.get("fields", {}) if isinstance(meta.get("fields"), dict) else {}
            if meta and side != "rtcis":
                flag = "in_2014" if side == "prime14" else "in_2022"
                dm_check[f"datamodel table {flag} claim, present in catalog: {meta.get(flag)}"] += 1
            for c, ty in cols.items():
                fm = fields.get(c, {})
                cv = g.node("Column", f"{side}:{t}.{c}", name=c, table=t, platform=eng, data_type=ty,
                            description=(fm.get("description") or "")[:300], primary_key=fm.get("primary_key"))
                g.edge("HAS_COLUMN", tv, cv)
    for t, meta in dm["tables"].items():   # data-model claims of existence that the catalogs contradict
        for side, flag in (("prime14", "in_2014"), ("prime", "in_2022")):
            if meta.get(flag) and t not in COLSET[side]:
                dm_check[f"datamodel says {flag} but table missing from the {SIDE_ENGINE[side]} catalog"] += 1
    g.validation_notes = dict(dm_check)

    # templates
    tpl = {"report_template.html": "tabbed HTML report (one tab per query, field-by-field section)",
           "sql_header_template.sql": "PrIME SQL deliverable header: mapping tags, evidence, deviations",
           "field_notes_template.json": "reason per empty / mismatched field (rule E1-E3)",
           "query_page_template.md": "wiki page per converted query (generated evidence + notes)",
           "gremlin_queries.md": "reusable traversals for conversion lookups"}
    for n, purpose in tpl.items():
        g.node("Template", n, name=n, purpose=purpose)

    # queries, fields, SQL entity recognition
    for n in range(1, 18):
        qid = f"R{n:02d}"
        fields = fcheck[qid]["fields"]
        cols = [f["column"] for f in fields]
        qv = {}
        predicted[qid] = {}
        for side, folder in (("rtcis", "rtcis_tsql"), ("prime", "prime")):
            d = os.path.join(WIKI, "queries", folder)
            fn = next(f for f in os.listdir(d) if f.startswith(qid))
            path = os.path.join(d, fn)
            tables, alias, colset = scan_sql(open(path, encoding="utf-8").read(), side)
            fsrc = field_sources(path, cols, alias, tables, side)
            predicted[qid][side] = {"tables": sorted(tables), "columns": sorted(colset), "lineage": fsrc}
            v = g.node("Query", f"{qid}:{side}", qid=qid, side=PLAT[side], title=fn[4:-4], file=f"queries/{folder}/{fn}",
                       intent=WHAT.get(qid, "")[:500], grade=STATUS.get(qid, ("", ""))[0], open_points=STATUS.get(qid, ("", ""))[1][:300],
                       params=",".join(sorted(k for k in PARAMS.get(qid, {}).get(folder, {}) if k != "_per_site")
                                       + sorted({k for s in PARAMS.get(qid, {}).get(folder, {}).get("_per_site", {}).values() for k in s})),
                       validated_runs=";".join(f"{s}:{r['rows']} rows" for s, r in RUNS.get((qid, folder), {}).items()))
            qv[side] = v
            for t in tables:
                g.edge("READS", v, table(side, t))
            for tc in colset:
                g.edge("READS_COLUMN", v, column(side, tc))
            g.edge("RENDERED_WITH", v, "Template:report_template.html")
            if side == "prime":
                g.edge("RENDERED_WITH", v, "Template:sql_header_template.sql")
                g.edge("RENDERED_WITH", v, "Template:field_notes_template.json")
                g.edge("RENDERED_WITH", v, "Template:query_page_template.md")
            for f in fields:
                fv = g.node("OutputField", f"{qid}:{f['column']}", qid=qid, name=f["column"], status=f["status"],
                            fill_rtcis=f["fill_pct"]["RTCIS_EUS"], fill_de08=f["fill_pct"]["PRIME_DE08"], fill_athens=f["fill_pct"]["PRIME_WMD1"],
                            agreement_pct=(f["agreement"] or {}).get("pct"), rtcis_source=f["rtcis_source"][:300], prime_source=f["prime_source"][:300])
                g.edge("HAS_FIELD", v, fv)
                for tc in fsrc.get(f["column"], []):
                    g.edge("DERIVED_FROM", fv, column(side, tc), side=PLAT[side])
        g.edge("CONVERTS_TO", qv["rtcis"], qv["prime"])
        for f in fields:
            for kind in ("empty", "diff"):
                txt = notes.get(qid, {}).get(f["column"], {}).get(kind)
                if txt:
                    nv = g.node("Finding", f"{qid}:{f['column']}:{kind}", kind=kind, category=txt.split(":")[0].strip(), text=txt[:600])
                    g.edge("EXPLAINED_BY", f"OutputField:{qid}:{f['column']}", nv)

    # indexes for prose recognition: columns the converted queries use (bare names like ITMCOD exist in dozens of
    # tables - linking prose to all of them would be noise); tables: every catalog table with a distinctive name (>= 4 chars)
    used = {e["dst"] for e in g.e.values() if e["label"] in ("READS_COLUMN", "DERIVED_FROM")}
    known_cols, known_tabs = defaultdict(set), defaultdict(set)
    for vid, v in g.v.items():
        if v["label"] == "Column" and vid in used:
            known_cols[v["name"]].add(vid)
        elif v["label"] == "Table" and len(v["name"]) >= 4:
            known_tabs[v["name"]].add(vid)

    # expert rules
    for code, text in rules["rules"]:
        rv = g.node("ExpertRule", code, code=code, text=text, source="RUIZ.RS (Gino) review" if code.startswith("OBS") else "Euskirchen learnings")
        for vid in prose_entities(text, g, known_cols, known_tabs):
            g.edge("MENTIONS", rv, vid)
    obs = rd("wiki", "experts", "ruiz-rs-obs.md")
    for m in re.finditer(r"^\| \*\*(OBS\d)\*\*[^|]*\|([^|]+)\|", obs, re.M):
        g.v[f"ExpertRule:{m.group(1)}"]["detail"] = m.group(2).strip()[:600]
        for vid in prose_entities(m.group(2), g, known_cols, known_tabs):
            g.edge("MENTIONS", f"ExpertRule:{m.group(1)}", vid)
    for qid, res in rules["queries"].items():
        for code, r in res.items():
            g.edge("APPLIES_RULE", f"Query:{qid}:prime", f"ExpertRule:{code}", result=r.split(" ")[0], detail=r[:200])

    # curated mappings: column level (mappings.md) - RTCIS cell -> PrIME cell
    TABLE_MAP = {(m["src"][1], m["dst"][1]) for m in json.load(open(os.path.join(KIT, "benchmark", "mapping_validation.json"),
                                                                       encoding="utf-8"))["mappings"]
                 if m["checks"]["V1"] == "PASS" and m["src"][0] == "RTCIS" and m["dst"][0] == "PrIME2022" and not m["src"][2]}

    def link_cells(mv, cell, side, rel, scope_cols):
        linked = set()
        for t, c in DOTTED.findall(cell):
            vid = f"Column:{side}:{t.lower()}.{c.lower()}"
            if vid in g.v:
                linked.add(vid)
        if not linked:
            for tok in re.findall(r"[A-Za-z_]\w+", " ".join(BACKTICK.findall(cell)) or cell):
                for vid in known_cols.get(tok.lower(), ()):
                    if g.v[vid]["platform"] == PLAT[side] and (scope_cols is None or vid in scope_cols):
                        linked.add(vid)
        for vid in linked:
            g.edge(rel, mv, vid)
        return linked

    mp = rd("wiki", "ground-truth", "mappings.md")
    for i, m in enumerate(re.finditer(r"^\| ([^|]+?) \| ([^|]+?) \| ([^|]*?) \| ([^|]*?) \|$", mp, re.M)):
        r, p, agr, tag = (x.strip() for x in m.groups())
        if r in ("RTCIS", "---") or set(r) <= set("-"):
            continue
        mv = g.node("Mapping", f"mappings.md:{i}", rtcis=r[:200], prime=p[:300], agreement=agr[:120], tag=tag[:120], source="wiki/ground-truth/mappings.md [DB]")
        src = link_cells(mv, r, "rtcis", "MAPS_FROM", None)
        dst = link_cells(mv, p, "prime", "MAPS_INTO", None)
        # a bare column name (ITMCOD -> PRTNUM) holds only between tables that are themselves mapped: no cross product
        for a in src:
            for b in dst:
                if (g.v[a]["table"], g.v[b]["table"]) in TABLE_MAP or len(src) * len(dst) == 1:
                    g.edge("MAPS_TO", a, b, agreement=agr[:120], tag=tag[:60], via=mv)
    # validated mapping layer (tools/mappings.py): only V1-passing mappings, every source + check kept on the edge
    side_of = {v: k for k, v in SIDE_ENGINE.items()}
    mval = json.load(open(os.path.join(KIT, "benchmark", "mapping_validation.json"), encoding="utf-8"))["mappings"]
    for m in mval:
        if m["checks"]["V1"] != "PASS":
            continue
        (se, st, sc), (de, dt, dc) = m["src"], m["dst"]
        a = f"Column:{side_of[se]}:{st}.{sc}" if sc else f"Table:{side_of[se]}:{st}"
        b = f"Column:{side_of[de]}:{dt}.{dc}" if dc else f"Table:{side_of[de]}:{dt}"
        v3 = m["checks"].get("V3")
        found = v3.get("src_values_found_in_dst_pct") if isinstance(v3, dict) else None
        if not isinstance(v3, dict):
            verdict = "not sampled (catalog-validated)" if any(x.startswith(("H7", "H8")) for x in m["sources"]) else ""
        elif found is None:
            verdict = "not comparable (date or empty sample)"
        elif found >= 80:
            verdict = "CONFIRMED by values"
        elif found > 0:
            verdict = "PARTIAL value match"
        elif v3.get("distinct_src", 0) <= 50:
            verdict = "CODE SET DIFFERS - needs value mapping"
        else:
            verdict = "identifiers not shared (different history / DEV data)"
        if isinstance(v3, dict) and not v3.get("same_site") and found is not None:
            verdict += " (cross-site)"
        g.edge("MAPS_TO", a, b, sources="; ".join(m["sources"])[:300], confidence=m.get("confidence", ""),
               notes=(m.get("notes") or "")[:300], type_check=m["checks"].get("V2", ""),
               value_found_pct=found if not isinstance(found, str) else None, value_verdict=verdict,
               fill_src=v3.get("fill_src") if isinstance(v3, dict) else None, fill_dst=v3.get("fill_dst") if isinstance(v3, dict) else None,
               conflict=",".join(m["checks"].get("CONFLICT", [])), validated="V1" + (" V2" if m["checks"].get("V2") == "PASS" else "") + (" V3" if isinstance(v3, dict) else ""),
               kind="structural" if any(x.startswith(("H7", "H8")) for x in m["sources"]) else "curated")
    vm = json.load(open(os.path.join(WIKI, "raw", "schema", "verified-mappings.json"), encoding="utf-8"))
    for k, v in vm.get("join_paths", {}).items():
        if isinstance(v, dict):
            jv = g.node("JoinPath", k, name=k, rtcis_join=v.get("rtcis_join", ""), reason=str(v.get("reason", ""))[:500])
            for t in re.findall(r"\w+", k):
                if f"Table:rtcis:{t.lower()}" in g.v:
                    g.edge("JOINS_VIA", f"Table:rtcis:{t.lower()}", jv)

    # learnings + data facts (prose recognition)
    for page in ("conversion-lessons.md", "prime-anti-patterns.md", "verification-discipline.md"):
        txt = rd("wiki", "learnings", page)
        items = re.findall(r"^(?:(\d+)\.|-)\s+(.+?)(?=^\s*(?:\d+\.|-)\s|^#|\Z)", txt, re.M | re.S)
        rows = re.findall(r"^\| (\d+) \| ([^|]+)\|([^|]+)\|([^|]*)\|", txt, re.M)
        for idx, (num, body) in enumerate(items):
            lv = g.node("Learning", f"{page}:{num or idx}", n=num or idx, page=f"wiki/learnings/{page}", text=" ".join(body.split())[:700])
            for vid in prose_entities(body, g, known_cols, known_tabs):
                g.edge("MENTIONS", lv, vid)
        for num, a, b, c in rows:
            lv = g.node("Learning", f"{page}:row{num}", n=num, page=f"wiki/learnings/{page}", text=" ".join((a + " | " + b + " | " + c).split())[:700])
            for vid in prose_entities(a + b, g, known_cols, known_tabs):
                g.edge("MENTIONS", lv, vid)
    df = rd("wiki", "ground-truth", "data-facts.md")
    for num, fact, cons in re.findall(r"^\| (\d+) \| ([^|]+)\| ([^|]+)\|", df, re.M):
        dv = g.node("DataFact", num, n=int(num), text=" ".join(fact.split())[:700], consequence=" ".join(cons.split())[:400])
        for vid in prose_entities(fact + cons, g, known_cols, known_tabs):
            g.edge("MENTIONS", dv, vid)
    for vid, v in list(g.v.items()):
        if v["label"] == "Finding":
            for x in prose_entities(v["text"], g, known_cols, known_tabs):
                g.edge("MENTIONS", vid, x)

    # wiki pages as concepts + links
    root = os.path.join(WIKI, "wiki")
    pages = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(dp, f), root).replace("\\", "/")
                txt = open(os.path.join(dp, f), encoding="utf-8").read()
                title = (re.search(r"^title:\s*(.+)$", txt, re.M) or re.search(r"^# (.+)$", txt, re.M))
                typ = re.search(r"^type:\s*(\S+)", txt, re.M)
                pages[rel] = g.node("Concept", rel, page=f"wiki/{rel}", title=title.group(1).strip()[:200] if title else rel,
                                    type=typ.group(1) if typ else "")
                for x in prose_entities(txt, g, known_cols, known_tabs) if rel.startswith("concepts/") else ():
                    g.edge("MENTIONS", pages[rel], x)
    for rel, pv in pages.items():
        txt = open(os.path.join(root, rel), encoding="utf-8").read()
        for link in re.findall(r"\]\(([^)#]+\.md)", txt):
            tgt = os.path.normpath(os.path.join(os.path.dirname(rel), link)).replace("\\", "/")
            if tgt in pages:
                g.edge("LINKS_TO", pv, pages[tgt])
    for n in range(1, 18):
        qid = f"R{n:02d}"
        if f"queries/{qid}.md" in pages:
            g.edge("DOCUMENTED_IN", f"Query:{qid}:prime", pages[f"queries/{qid}.md"])
            g.edge("DOCUMENTED_IN", f"Query:{qid}:rtcis", pages[f"queries/{qid}.md"])
    for code in ("OBS1", "OBS2", "OBS3", "OBS4", "OBS5", "OBS6", "OBS7", "OBS8"):
        g.edge("DOCUMENTED_IN", f"ExpertRule:{code}", pages.get("experts/ruiz-rs-obs.md", ""))

    # SDC module / PMC process layer: PASS-only output of tools/sdc_pmc_run.py (live catalog + data presence)
    layer_f = os.path.join(KIT, "relationships", "sdc_pmc_layer.json")
    if os.path.exists(layer_f):
        layer = json.load(open(layer_f, encoding="utf-8"))
        for n in layer["nodes"]:
            g.node(n["label"], n["id"].split(":", 1)[1], **{k: v for k, v in n.items() if k not in ("id", "label")})
        for e in layer["edges"]:
            g.edge(e["label"], e["src"], e["dst"], **{k: v for k, v in e.items() if k not in ("label", "src", "dst")})

    # validated join paths: equi-joins in the ON clauses of the expert-validated query SQL (columns gated by the catalog)
    from kg_core import join_paths
    for side, sub in (("rtcis", "rtcis_tsql"), ("prime", "prime")):
        folder = os.path.join(WIKI, "queries", sub)
        sqls = [open(os.path.join(folder, f), encoding="utf-8").read() for f in sorted(os.listdir(folder)) if f.endswith(".sql")]
        for (a, b), n in join_paths(sqls).items():
            g.edge("JOINS_WITH", f"Column:{side}:{a}", f"Column:{side}:{b}", n_queries=n, source="ON clause of validated queries")

    rel = os.path.join(KIT, "relationships")
    os.makedirs(rel, exist_ok=True)
    json.dump(list(g.v.values()), open(os.path.join(rel, "nodes.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    json.dump(list(g.e.values()), open(os.path.join(rel, "edges.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    json.dump(ONTOLOGY, open(os.path.join(rel, "ontology.json"), "w", encoding="utf-8"), indent=1)
    json.dump(predicted, open(os.path.join(KIT, "benchmark", "predicted.json"), "w", encoding="utf-8"), indent=1)
    from collections import Counter
    print("nodes", len(g.v), dict(Counter(v["label"] for v in g.v.values())))
    print("edges", len(g.e), dict(Counter(e["label"] for e in g.e.values())))
    print("dropped edges (endpoint missing)", len(g.dropped), Counter(x[0] for x in g.dropped).most_common(8))
    print("entities recognised in SQL but NOT in a real catalog (kept out of the graph):", len(set(g.unvalidated)), sorted(set(g.unvalidated))[:12])
    json.dump({"datamodel_vs_catalog": g.validation_notes, "unvalidated_entities": sorted(set(g.unvalidated)),
               "dropped_edges": Counter(x[0] for x in g.dropped), "nodes": dict(Counter(v["label"] for v in g.v.values())),
               "edges": dict(Counter(e["label"] for e in g.e.values()))},
              open(os.path.join(KIT, "benchmark", "graph_validation.json"), "w", encoding="utf-8"), indent=1, default=list)
    print("datamodel vs catalog:", g.validation_notes)


if __name__ == "__main__":
    main()
