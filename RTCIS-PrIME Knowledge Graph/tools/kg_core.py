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
    (MENTIONS), SDC module names (USES_TABLE) and RTCIS -> PrIME transformation rules (TRANSFORMS_TO, both ends)."""
    by_id = {n["id"]: n for n in nodes}
    out = {}
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
    return {t: " | ".join(dict.fromkeys(v))[:limit] for t, v in out.items()}


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
