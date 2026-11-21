"""Core logic of the knowledge-graph API (pure functions, no network): read-only SQL guard, graph shaping for the UI,
keyword retrieval over graph nodes, batch parsing, column-contract comparison and empty-field flags."""
import re

import sqlglot
from sqlglot import exp

ENGINE_NAME = {"RTCIS": "RTCIS", "PrIME2014": "PrIME 2014", "PrIME2022": "PrIME 2022"}
WRITE = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.Command, exp.TruncateTable)
# T-SQL words that start a statement: sqlglot reads "SELECT 1 DELETE FROM t" as an alias, SQL Server as a second statement
STATEMENT_WORDS = set("""ALTER BACKUP BEGIN BREAK BULK CHECKPOINT CLOSE COMMIT CONTINUE CREATE DBCC DEALLOCATE DECLARE DELETE DENY
DISABLE DROP DUMP ENABLE EXEC EXECUTE FETCH GOTO GRANT IF INSERT KILL LOAD MERGE OPEN PRINT RAISERROR READTEXT RECONFIGURE
RESTORE RETURN REVERT REVOKE ROLLBACK SAVE SET SETUSER SHUTDOWN THROW TRUNCATE UPDATE UPDATETEXT USE WAITFOR WHILE WRITETEXT""".split())
REMOTE = re.compile(r"\bopen(query|rowset|datasource|xml)\s*\(", re.I)


class UnsafeSQL(ValueError):
    """The SQL is not a single read-only SELECT."""


def guard_sql(sql):
    """Return the statement if it is exactly one read-only SELECT / WITH ... SELECT (T-SQL), else raise UnsafeSQL."""
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        raise UnsafeSQL("empty SQL")
    try:
        trees = [t for t in sqlglot.parse(text, read="tsql") if t is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQL(f"does not parse as T-SQL: {str(e)[:160]}") from e
    if len(trees) != 1:
        raise UnsafeSQL(f"{len(trees)} statements - only one SELECT is allowed")
    tree = trees[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL(f"{type(tree).__name__} statement - only SELECT is allowed")
    if any(True for _ in tree.find_all(*WRITE)):
        raise UnsafeSQL("contains a write / DDL / command")
    hidden = sorted({i.name.upper() for i in tree.find_all(exp.Identifier) if not i.quoted and i.name.upper() in STATEMENT_WORDS})
    if hidden:
        raise UnsafeSQL(f"unquoted statement keyword used as a name ({', '.join(hidden)}) - SQL Server would run it as a second statement")
    if REMOTE.search(re.sub(r"--[^\n]*|/\*.*?\*/", " ", text, flags=re.S)):
        raise UnsafeSQL("OPENQUERY / OPENROWSET / OPENDATASOURCE / OPENXML run outside the read-only scope")
    if tree.args.get("into") is not None or any(n.args.get("into") is not None for n in tree.find_all(exp.Select)):
        raise UnsafeSQL("SELECT INTO writes a table")
    return text


def ui_label(v):
    """Legend / colour key: Table and Column carry their engine, everything else its label."""
    if v.get("label") in ("Table", "Column") and v.get("platform") in ENGINE_NAME:
        return f"{ENGINE_NAME[v['platform']]} {v['label'].lower()}"
    return v.get("label", "Node")


def to_ui_graph(vertices, edges):
    """Shape vertices / edges for the force-directed graph of knowledge-graph.html: {nodes:[{id,labels,props}], edges:[{src,dst,type}]}."""
    nodes, seen = [], set()
    for v in vertices:
        if v["id"] in seen:
            continue
        seen.add(v["id"])
        props = {k: v[k] for k in v if k not in ("id", "label", "pk") and v[k] not in (None, "")}
        nodes.append({"id": v["id"], "labels": [ui_label(v)], "props": props})
    out = [{"src": e["src"], "dst": e["dst"], "type": e["label"]} for e in edges if e["src"] in seen and e["dst"] in seen]
    return {"nodes": nodes, "edges": out}


def extract_sql(text):
    """SQL from a model answer: a ```sql fenced block if present, else the first SELECT / WITH ... to the end."""
    m = re.search(r"```(?:sql|tsql)?\s*\n(.*?)```", text or "", re.S | re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(WITH|SELECT)\b.*", text or "", re.S | re.I)
    return m.group(0).strip() if m else ""


def parse_batch(text, kind):
    """Questions: one per non-empty line. SQL: split on separator lines (--- or GO)."""
    if kind == "ask":
        return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    parts = re.split(r"(?im)^\s*(?:-{3,}|go)\s*$", text or "")
    return [p.strip() for p in parts if p.strip()]


STOP = set("a an the of for to in on by per and or with what which how many much is are show list me all from at as each".split())

SQL_START = re.compile(r"^\s*(?:(?:--[^\n]*\n)|(?:/\*.*?\*/))*\s*(select|with)\b", re.I | re.S)
LIST_MARK = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")


def route(text, same_engine):
    """One dialogue box: SQL -> validate (same engine) or convert; several SQL (--- / GO) -> batch; one question -> ask;
    several questions (each line a list item or ending with '?') -> batch of questions."""
    text = (text or "").strip()
    if SQL_START.match(text):
        parts = parse_batch(text, "convert")
        kind = "validate" if same_engine else "convert"
        return {"mode": ("batch_" + kind) if len(parts) > 1 else kind, "items": parts}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1 and all(LIST_MARK.match(ln) or ln.endswith("?") for ln in lines):
        return {"mode": "batch_ask", "items": [LIST_MARK.sub("", ln) for ln in lines]}
    return {"mode": "ask", "items": [" ".join(lines)]}


def _tokens(s):
    out = set()
    for t in re.findall(r"[a-z0-9]+", (s or "").lower()):
        if t in STOP or len(t) < 3:
            continue
        out.add(t[:-1] if t.endswith("s") and len(t) > 4 else t)
    return out


def _norm(v):
    if v is None:
        return "NULL"
    try:
        f = float(v)
        return repr(int(f)) if f == int(f) else repr(round(f, 6))
    except (TypeError, ValueError):
        return str(v).strip()


def exec_match(gold_rows, model_rows):
    """Lenient execution accuracy: same number of rows, and every reference row's values are contained (as a multiset)
    in a distinct model row - row order, column order, column names and extra model columns do not matter."""
    from collections import Counter
    if len(gold_rows) != len(model_rows):
        return False
    pool = [Counter(_norm(v) for v in r) for r in model_rows]
    for g in sorted((Counter(_norm(v) for v in r) for r in gold_rows), key=lambda c: -sum(c.values())):
        hit = next((i for i, m in enumerate(pool) if not g - m), None)
        if hit is None:
            return False
        pool.pop(hit)
    return True


def join_paths(sqls):
    """Equi-join column pairs used in ON clauses of (validated) SQL, aliases resolved to table names, counted per query.
    Returns {("a.col", "b.col") sorted: n_queries}; parameter / literal filters are ignored."""
    out = {}
    for sql in sqls:
        try:
            trees = [t for t in sqlglot.parse(sql, read="tsql") if t]
        except sqlglot.errors.ParseError:
            continue
        seen = set()
        for tree in trees:
            alias = {}
            for t in tree.find_all(exp.Table):
                if t.name:
                    alias[(t.alias_or_name or t.name).lower()] = t.name.lower()
            for j in tree.find_all(exp.Join):
                on = j.args.get("on")
                if on is None:
                    continue
                for eq in on.find_all(exp.EQ):
                    a, b = eq.left, eq.right
                    if not (isinstance(a, exp.Column) and isinstance(b, exp.Column) and a.table and b.table):
                        continue
                    ta, tb = alias.get(a.table.lower()), alias.get(b.table.lower())
                    if ta and tb and ta != tb:
                        seen.add(tuple(sorted((f"{ta}.{a.name.lower()}", f"{tb}.{b.name.lower()}"))))
        for p in seen:
            out[p] = out.get(p, 0) + 1
    return out


def table_descriptions(nodes, edges, limit=600):
    """Words for every table from the knowledge that points at it: query intents (READS), concepts / learnings / facts
    (MENTIONS), SDC module names (USES_TABLE) and RTCIS -> PrIME transformation rules (TRANSFORMS_TO, both ends).
    Each table is also tagged with its business themes and Timbr concepts (concept_map), so a theme word finds it."""
    out = _knowledge_words(nodes, edges)
    table_id = {(n.get("platform"), n.get("name")): n["id"] for n in nodes if n.get("label") == "Table"}
    tags = {}
    for c in concept_map(nodes, edges):
        tag = ("theme " if c["label"] == "Theme" else "concept ") + c["name"].replace("_", " ")
        for eng, names in c["tables"].items():
            for name in names:
                tid = table_id.get((eng, name))
                if tid:
                    tags.setdefault(tid, []).append(tag)
    res = {t: " | ".join(dict.fromkeys(v))[:limit] for t, v in out.items()}
    for t, v in tags.items():
        res[t] = "; ".join(dict.fromkeys(v)) + (" | " + res[t] if res.get(t) else "")
    return res


def _knowledge_words(nodes, edges):
    by_id = {n["id"]: n for n in nodes}
    out = {n["id"]: [n["description"][:200]] for n in nodes if n.get("label") == "Table" and n.get("description")}   # PrIME docs
    for e in edges:
        if e["label"] == "TRANSFORMS_TO" and e.get("rule"):
            for t in (e["src"], e["dst"]):
                out.setdefault(t, []).append(e["rule"][:200])
            continue
        if e["label"] not in ("READS", "MENTIONS", "USES_TABLE") or not e["dst"].startswith("Table:"):
            continue
        n = by_id.get(e["src"], {})
        text = n.get("intent") or n.get("name") or n.get("text") or ""
        if text:
            out.setdefault(e["dst"], []).append(text[:200])
    return out


ROUTE_STOP = set("status number total there exist exists recorded configured most recent top type ids each are were have "
                 "list give find show".split())


def route_concepts(question, entries, table_index, engine, k=3):
    """Themes / Timbr concepts for a question, with each hit's tables in `engine` ranked by how well they fit the question
    (table name + knowledge words), the rest in curated order. Filler words (status, number, total ...) do not route."""
    q = " ".join(w for w in re.findall(r"[A-Za-z0-9_]+", question or "") if w.lower() not in ROUTE_STOP)
    hits = retrieve(q, entries, k=k) if q.strip() else []
    out = []
    for h in hits:
        names = h["tables"].get(engine, [])
        direct = [n for n in names if n in h.get("direct", {}).get(engine, names)]
        ranked = []
        for group in (direct, [n for n in names if n not in direct]):
            cand = [x for x in table_index if x.get("label") == "Table" and x.get("engine") == engine and x.get("name") in group]
            fit = [x["name"] for x in retrieve(q, cand, engine=engine, k=len(cand))] if cand else []
            ranked += fit + [n for n in group if n not in fit]
        out.append(dict(h, ranked={**h["tables"], engine: ranked}))
    return out


ENGINE_OF_SIDE = {"rtcis": "RTCIS", "prime14": "PrIME2014", "prime": "PrIME2022"}


def concept_map(nodes, edges, per_engine=12):
    """Business themes (Domain, via IN_DOMAIN) and Timbr semantic concepts (via MAPPED_FROM) with their tables in each
    engine. The direct links are extended by up to two hops of table-level MAPS_TO (RTCIS <-> PrIME 2014 <-> PrIME 2022),
    direct tables first, at most `per_engine` per engine. Entries have no engine, so per-engine table search skips them.
    A theme is described by its own name plus the names and knowledge words of its tables (the curated Domain names alone
    are too thin to route a question); a table that sits in more than half of the themes (e.g. wh) is generic and left out."""
    by_id = {n["id"]: n for n in nodes}
    direct, maps = {}, {}
    for e in edges:
        if e["label"] == "IN_DOMAIN" and e["src"].startswith("Table:"):
            direct.setdefault(e["dst"], []).append(e["src"])
        elif e["label"] == "MAPPED_FROM" and e["dst"].startswith("Table:"):
            direct.setdefault(e["src"], []).append(e["dst"])
        elif e["label"] == "MAPS_TO" and e["src"].startswith("Table:") and e["dst"].startswith("Table:"):
            maps.setdefault(e["src"], []).append(e["dst"])
            maps.setdefault(e["dst"], []).append(e["src"])

    themes = [d for d, n in ((d, by_id.get(d, {})) for d in direct) if n.get("label") == "Domain"]
    in_themes = {}
    for d in themes:
        for t in set(direct[d]):
            in_themes[t] = in_themes.get(t, 0) + 1
    generic = {t for t, c in in_themes.items() if len(themes) >= 3 and c > len(themes) / 2}
    words = _knowledge_words(nodes, edges)

    def engine(tid):
        return by_id.get(tid, {}).get("platform") or ENGINE_OF_SIDE.get(tid.split(":")[1])

    out = []
    for cid, start in sorted(direct.items()):
        n = by_id.get(cid)
        if not n or n["label"] not in ("Domain", "SemanticConcept"):
            continue
        start = [t for t in dict.fromkeys(start) if t not in generic]
        order, frontier = list(start), list(start)
        for _ in range(2):
            frontier = [m for t in frontier for m in maps.get(t, []) if m not in order and m not in generic]
            order += list(dict.fromkeys(frontier))
        label = "Theme" if n["label"] == "Domain" else "SemanticConcept"
        tables, first = {}, {}
        for t in order:
            eng = engine(t)
            if eng and len(tables.setdefault(eng, [])) < per_engine:
                tables[eng].append(by_id.get(t, {}).get("name") or t.split(":", 2)[2])
                if t in start:
                    first.setdefault(eng, []).append(tables[eng][-1])
        own = [n.get("name", "").replace("_", " "), n.get("description", "")[:300], n.get("theme", "")]
        if label == "Theme":
            for t in start[:10]:
                own.append(by_id.get(t, {}).get("name", t.split(":", 2)[2]).replace("_", " "))
                own.append(" ".join(words.get(t, []))[:120])
        desc = " ".join(x for x in own if x)
        out.append({"id": cid, "label": label, "engine": None, "name": n.get("name", cid.split(":", 1)[1]),
                    "description": desc, "tables": tables, "direct": first})
    return out


def retrieve(question, index, engine=None, k=8):
    """Rank graph nodes by token overlap with name (weight 2) and description (weight 1), each token weighted by its
    rarity in the candidate set (IDF), optionally one engine only."""
    import math
    q = _tokens(question)
    cands = []
    for x in index:
        if engine and x.get("engine") != engine:
            continue
        cands.append((x, _tokens(x.get("name", "").replace("_", " ")), _tokens(x.get("description", ""))))
    df = {}
    for _, name, desc in cands:
        for t in q & (name | desc):
            df[t] = df.get(t, 0) + 1
    idf = {t: math.log(1 + len(cands) / n) for t, n in df.items()}
    scored = []
    for x, name, desc in cands:
        s = sum(2 * idf[t] for t in q & name) + sum(idf[t] for t in q & desc)
        if s:
            scored.append((-round(s, 9), x["id"], x))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [x for _, _, x in scored[:k]]


def contract(original, converted):
    """Column contract of a conversion (case-insensitive): same names, same order."""
    a, b = [c.lower() for c in original], [c.lower() for c in converted]
    missing = [c for c in original if c.lower() not in b]
    extra = [c for c in converted if c.lower() not in a]
    common_a, common_b = [c for c in a if c in b], [c for c in b if c in a]
    return {"identical": a == b, "missing": missing, "extra": extra, "order_ok": common_a == common_b}


def empty_fields(columns, rows):
    """Columns that are NULL / blank on every returned row (rule E1); none when there are no rows."""
    if not rows:
        return []
    return [c for i, c in enumerate(columns) if all(r[i] is None or str(r[i]).strip() == "" for r in rows)]
