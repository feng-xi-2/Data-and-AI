"""Real adapters for the knowledge-graph assistant, all on cloud services with the signed-in user's Entra token:
  CosmosGraph  - Azure Cosmos DB for Apache Gremlin (whs_kg / rtcis_prime): graph views for the UI, mapping context
  GenAiLLM     - P&G GenAI platform (Azure OpenAI compatible), GenAI project from KG_GENAI_PROJECT
  ReplicaDB    - replica databases: read-only guard -> dry-run (describe_first_result_set) -> capped execution
services() wires them into kg_assistant.Assistant with the catalog-validated index and the Git SQL templates."""
import json
import os
import re
import threading
import time
import urllib.request
from types import SimpleNamespace

import kg_core as k
from kg_assistant import Assistant, SIDE

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WIKI = os.environ.get("WIKI_ROOT", os.path.join(KIT, "..", "RTCIS-PrIME-LLM-Wiki"))
SITE_ENGINE = {"RTCIS_EUS": "RTCIS", "RTCIS_LON": "RTCIS", "PRIME14_XQ": "PrIME2014", "PRIME22_DE08": "PrIME2022", "PRIME22_WMD1": "PrIME2022"}
PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
TABLE_PK = {"RTCIS": "Table:RTCIS", "PrIME2014": "Table:PrIME2014", "PrIME2022": "Table:PrIME2022"}


# ================================================================================================= Cosmos graph
class CosmosGraph:
    def __init__(self, graph=os.environ.get("KG_GRAPH", "rtcis_prime")):
        import load_cosmos as lc
        self._lc, self.graph = lc, graph
        self._c = lc.connect(lc.ensure(graph, reset=False), graph)
        self._rules = None

    def q(self, gremlin, **b):
        return self._lc.run(self._c, gremlin, b)

    def close(self):
        self._c.close()

    def vertices(self, ids):
        ids = list(dict.fromkeys(i for i in ids if i))
        out = []
        for i in range(0, len(ids), 100):
            rows = self.q("g.V().has('id', within(ids)).project('id', 'label', 'p').by(id).by(label).by(valueMap())", ids=ids[i:i + 100])
            for r in rows:
                v = {kk: (vv[0] if isinstance(vv, list) and vv else vv) for kk, vv in r["p"].items()}
                v.update(id=r["id"], label=r["label"])
                out.append(v)
        order = {x: n for n, x in enumerate(ids)}
        return sorted(out, key=lambda v: order.get(v["id"], 1e9))

    def edges_among(self, ids):
        ids = list(dict.fromkeys(ids))
        out = []
        for i in range(0, len(ids), 100):
            out += [{"src": r["s"], "dst": r["d"], "label": r["l"]} for r in self.q(
                "g.V().has('id', within(chunk)).outE().where(inV().has('id', within(ids)))"
                ".project('s', 'd', 'l').by(outV().id()).by(inV().id()).by(label)", chunk=ids[i:i + 100], ids=ids)]
        return out

    def _graph(self, ids, with_platforms=True):
        vs = self.vertices(ids)
        if with_platforms:
            plats = sorted({f"Platform:{v['platform']}" for v in vs if v["label"] in ("Table",) and v.get("platform")})
            vs += self.vertices(plats)
        return k.to_ui_graph(vs, self.edges_among([v["id"] for v in vs]))

    # ---- views (templates of the graph tab) ----
    def view(self, kind, key, limit=40):
        if kind == "versions":
            start = self.q("g.V().has('pk', within(pks)).has('name', n).id()", pks=list(TABLE_PK.values()), n=key.lower())
            tabs = self.q("g.V().has('id', within(s)).both('MAPS_TO').hasLabel('Table').dedup().limit(14).id()", s=start) if start else []
            tabs = list(dict.fromkeys(start + tabs))
            rt = [t for t in tabs if t.startswith("Table:rtcis:")]
            pt = [t for t in tabs if t.startswith("Table:prime:")]
            # column lineage RTCIS -> PrIME 2022 <- PrIME 2014, limited so the force graph stays readable
            rc = self.q("g.V().has('id', within(t)).out('HAS_COLUMN').where(outE('MAPS_TO')).limit(12).id()", t=rt) if rt else []
            pc = self.q("g.V().has('id', within(c)).out('MAPS_TO').hasLabel('Column').dedup().limit(14).id()", c=rc) if rc else []
            if pt:
                pc += self.q("g.V().has('id', within(t)).out('HAS_COLUMN').where(inE('MAPS_TO')).limit(8).id()", t=pt)
            p14 = self.q("g.V().has('id', within(c)).in('MAPS_TO').has('pk', 'Column:PrIME2014').dedup().limit(12).id()", c=pc) if pc else []
            p14t = self.q("g.V().has('id', within(c)).in('HAS_COLUMN').dedup().id()", c=p14) if p14 else []
            return self._graph(tabs + p14t + rc + pc + p14)
        if kind == "sdc":
            if key.upper().startswith("PMC"):
                pmc = [f"PMCProcess:{key.upper()}"]
                mod = self.q("g.V().has('pk', 'PMCProcess').has('id', p).out('IN_MODULE').id()", p=pmc[0])
                pt = self.q("g.V().has('pk', 'PMCProcess').has('id', p).out('CONFIGURES').id()", p=pmc[0])
            else:
                mod = [f"SDCModule:{key}"]
                pmc = self.q("g.V().has('pk', 'SDCModule').has('id', m).in('IN_MODULE').limit(14).id()", m=mod[0])
                pt = self.q("g.V().has('pk', 'SDCModule').has('id', m).out('USES_TABLE').limit(30).id()", m=mod[0])
            rt = self.q("g.V().has('id', within(t)).in('TRANSFORMS_TO').dedup().id()", t=[t for t in pt if t.startswith("Table:prime:")]) if pt else []
            return self._graph(mod + pmc + pt + rt)
        if kind == "query":
            q = [f"Query:{key}:rtcis", f"Query:{key}:prime"]
            tabs = self.q("g.V().has('id', within(q)).out('READS').dedup().limit(24).id()", q=q)
            fields = self.q("g.V().has('pk', 'Query').has('id', qid).out('HAS_FIELD').limit(12).id()", qid=q[1])
            der = self.q("g.V().has('id', within(f)).out('DERIVED_FROM').dedup().limit(24).id()", f=fields) if fields else []
            rules = self.q("g.V().has('pk', 'Query').has('id', qid).outE('APPLIES_RULE').has('result', 'PASS').inV().id()", qid=q[1])
            finds = self.q("g.V().has('id', within(f)).out('EXPLAINED_BY').limit(8).id()", f=fields) if fields else []
            return self._graph(q + tabs + fields + der + rules + finds, with_platforms=False)
        if kind == "domain":
            tabs = self.q("g.V().has('pk', 'Domain').has('id', did).in('IN_DOMAIN').limit(lim).id()", did=f"Domain:{key}", lim=min(limit, 30))
            more = self.q("g.V().has('id', within(t)).both('MAPS_TO').hasLabel('Table').dedup().limit(20).id()", t=tabs) if tabs else []
            return self._graph([f"Domain:{key}"] + tabs + more)
        if kind == "issues":
            rows = self.q("g.V().has('pk', 'Column:RTCIS').outE('MAPS_TO').or(has('conflict'), has('value_verdict', TextP.containing('CODE SET')))"
                          ".limit(lim).project('s', 'd').by(outV().id()).by(inV().id())", lim=limit)
            ids = [x for r in rows for x in (r["s"], r["d"])]
            tabs = self.q("g.V().has('id', within(c)).in('HAS_COLUMN').dedup().id()", c=ids) if ids else []
            return self._graph(ids + tabs)
        if kind == "rules":
            rules = self.q("g.V().has('pk', 'ExpertRule').id()")
            qs = self.q("g.V().has('pk', 'ExpertRule').inE('APPLIES_RULE').has('result', 'PASS').outV().dedup().limit(17).id()")
            return self._graph(rules + qs, with_platforms=False)
        # any vertex: its neighbourhood
        nb = self.q("g.V().has('id', v).both().dedup().limit(lim).id()", v=key, lim=limit)
        return self._graph([key] + nb)

    def search(self, text, limit=20):
        t = text.lower().strip()
        rows = self.q("g.V().has('pk', within(pks)).has('name', TextP.startingWith(t)).limit(lim).project('id', 'name', 'platform')"
                      ".by(id).by('name').by('platform')", pks=list(TABLE_PK.values()), t=t, lim=limit)
        return rows

    # ---- assistant context ----
    def context(self, table_ids, target_platform=None):
        if not table_ids:
            return {"mappings": [], "learnings": [], "rules": self.rules()}
        rows = self.q("g.V().has('id', within(t)).out('HAS_COLUMN').outE('MAPS_TO')"
                      ".project('ft', 'fc', 'tt', 'tc', 'tp', 'v', 's').by(outV().values('table')).by(outV().values('name'))"
                      ".by(inV().values('table')).by(inV().values('name')).by(inV().values('platform'))"
                      ".by(coalesce(values('value_verdict'), values('tag'), constant(''))).by(outV().in('HAS_COLUMN').id())", t=table_ids)
        trows = self.q("g.V().has('id', within(t)).outE('MAPS_TO').project('ft', 'tt', 'tp', 'v', 's').by(outV().values('name'))"
                       ".by(inV().values('name')).by(inV().values('platform')).by(coalesce(values('sources'), constant(''))).by(outV().id())", t=table_ids)
        maps = [{"from_table": r["s"], "from": f"{r['ft']}.{r['fc']}", "to": f"{r['tt']}.{r['tc']}", "to_platform": r["tp"], "verdict": r["v"]}
                for r in rows if not target_platform or r["tp"] == target_platform]
        maps += [{"from_table": r["s"], "from": r["ft"], "to": r["tt"], "to_platform": r["tp"], "verdict": "table map: " + r["v"][:60]}
                 for r in trows if not target_platform or r["tp"] == target_platform]
        learn = self.q("g.V().has('id', within(t)).in('MENTIONS').hasLabel('Learning', 'DataFact').dedup().limit(8).values('text')", t=table_ids)
        return {"mappings": maps, "learnings": learn, "rules": self.rules()}

    def rules(self):
        if self._rules is None:
            self._rules = [f"{r['c']}: {r['t']}" for r in self.q("g.V().has('pk', 'ExpertRule').project('c', 't').by('code').by('text')")]
        return self._rules

    def evidence(self, ids):
        ids = [i for i in ids if i]
        nb = self.q("g.V().has('id', within(i)).out('MAPS_TO').dedup().limit(20).id()", i=ids) if ids else []
        return self._graph(ids + nb)


# ================================================================================================= GenAI model
class GenAiLLM:
    def __init__(self):
        import azauth
        self._token = lambda: azauth.token("https://cognitiveservices.azure.com/.default")
        self.endpoint = os.environ.get("KG_GENAI_ENDPOINT", "").rstrip("/")
        self.model = os.environ.get("KG_GENAI_MODEL", "GPT-52-2025-12-11")
        self.project = os.environ.get("KG_GENAI_PROJECT", "")
        self.user = os.environ.get("KG_GENAI_USER", "")
        if not (self.endpoint and self.project and self.user):
            raise SystemExit("set KG_GENAI_ENDPOINT, KG_GENAI_PROJECT and KG_GENAI_USER")

    def chat(self, messages, max_tokens=2000):
        url = f"{self.endpoint}/openai/deployments/{self.model}/chat/completions?api-version=2024-02-01"
        body = {"messages": messages, "max_completion_tokens": max_tokens}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + self._token(), "Content-Type": "application/json",
                                              "userid": self.user, "project-name": self.project})
        for i in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)["choices"][0]["message"]["content"] or ""
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503) or i == 2:
                    raise RuntimeError(f"GenAI {e.code}: {e.read().decode()[:300]}")
                time.sleep(3 * (i + 1))


# ================================================================================================= replica databases
def _jsonable(v):
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def _dto(raw):
    """datetimeoffset (ODBC type -155): 20-byte struct -> ISO text; pyodbc has no native converter."""
    import struct
    y, mo, d, h, mi, s, ns, th, tm = struct.unpack("<6hI2h", raw)
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}.{ns // 1000:06d} {th:+03d}:{abs(tm):02d}"


class ReplicaDB:
    MAX_ROWS = 50

    def __init__(self):
        import dbconn
        self._dbconn = dbconn

    def validate(self, sql, site, params=None):
        t0 = time.time()
        try:
            sql = k.guard_sql(sql)
        except k.UnsafeSQL as e:
            return {"ok": False, "stage": "guard", "error": str(e), "columns": [], "rows": [], "site": site}
        params = params or {}
        bad = [n for n in params if not PARAM_NAME.match(str(n))]
        if bad:
            return {"ok": False, "stage": "params", "error": f"invalid parameter name(s): {bad!r}", "columns": [], "rows": [], "site": site}
        decl = "".join(f"DECLARE @{n} {'int' if isinstance(v, int) else 'nvarchar(4000)'} = "
                       f"{int(v) if isinstance(v, int) else chr(39) + str(v).replace(chr(39), chr(39) * 2) + chr(39)};\n" for n, v in params.items())
        pdef = ", ".join(f"@{n} {'int' if isinstance(v, int) else 'nvarchar(4000)'}" for n, v in params.items())
        with self._lock(site):     # pyodbc connections are not thread-safe; the API serves requests from a thread pool
            return self._run(sql, site, decl, pdef, t0)

    _locks_guard = threading.Lock()

    def _lock(self, site):
        with self._locks_guard:
            locks = self.__dict__.setdefault("_locks", {})
            return locks.setdefault(site, threading.Lock())

    def _run(self, sql, site, decl, pdef, t0):
        try:
            conn = self._dbconn.connect(site, timeout=60)
            conn.add_output_converter(-155, _dto)
            cur = conn.cursor()
            cur.execute("SELECT name, system_type_name, error_message FROM sys.dm_exec_describe_first_result_set(?, ?, 0)", sql, pdef or None)
            desc = cur.fetchall()
        except Exception as e:
            return {"ok": False, "stage": "describe", "error": _clean(e), "columns": [], "rows": [], "site": site}
        err = next((d[2] for d in desc if d[2]), None)
        if err:
            return {"ok": False, "stage": "describe", "error": err, "columns": [], "rows": [], "site": site}
        types = [d[1] for d in desc]
        try:
            cur.execute(decl + sql)
            while cur.description is None and cur.nextset():
                pass
            cols = [c[0] for c in cur.description]
            rows = [[_jsonable(v) for v in r] for r in cur.fetchmany(self.MAX_ROWS + 1)]
            try:
                cur.cancel()
            except Exception:
                pass
        except Exception as e:
            return {"ok": False, "stage": "execute", "error": _clean(e), "columns": [], "rows": [], "site": site, "types": types}
        trunc = len(rows) > self.MAX_ROWS
        rows = rows[:self.MAX_ROWS]
        return {"ok": True, "stage": "executed", "columns": cols, "types": types, "rows": rows, "row_count": len(rows),
                "truncated": trunc, "empty_fields": k.empty_fields(cols, rows), "seconds": round(time.time() - t0, 2), "site": site}


def _clean(e):
    m = re.findall(r"\[SQL Server\]([^\[\(]+)", str(e))
    return (m[-1] if m else str(e)).strip()[:400]


# ================================================================================================= wiring
def load_index_and_templates():
    import graphio
    nodes, edges = graphio.load("nodes"), graphio.load("edges")
    desc = k.table_descriptions(nodes, edges)
    reads = {}
    for e in edges:
        if e["label"] == "READS":
            reads.setdefault(e["src"], []).append(e["dst"].split(":", 2)[2])
    index = [{"id": n["id"], "label": n["label"], "engine": n.get("platform"), "name": n.get("name", ""),
              "description": desc.get(n["id"], "")} for n in nodes if n["label"] == "Table"]
    cat = json.load(open(os.path.join(KIT, "benchmark", "catalog.json"), encoding="utf-8"))["engines"]
    templates = []
    for n in nodes:
        if n["label"] != "Query" or not n.get("file"):
            continue
        p = os.path.join(WIKI, n["file"])
        if os.path.exists(p):
            templates.append({"qid": n["qid"], "engine": n["side"], "intent": n.get("intent", "") or n.get("title", ""),
                              "title": n.get("title", ""), "grade": n.get("grade", ""), "params": n.get("params", ""),
                              "sql": open(p, encoding="utf-8").read()})
            index.append({"id": n["id"], "label": "Query", "engine": n["side"], "name": n.get("title", "").replace("_", " "),
                          "description": n.get("intent", ""), "reads": reads.get(n["id"], [])})
    return index, cat, templates


def services():
    graph, llm, db = CosmosGraph(), GenAiLLM(), ReplicaDB()
    index, cat, templates = load_index_and_templates()
    approved_f = os.path.join(KIT, "benchmark", "approved_pairs.jsonl")
    approved = [json.loads(x) for x in open(approved_f, encoding="utf-8")] if os.path.exists(approved_f) else []
    return SimpleNamespace(graph=graph, llm=llm, db=db, index=index, templates=templates, approved_file=approved_f,
                           assistant=Assistant(graph=graph, llm=llm, db=db, index=index, columns=cat, templates=templates, approved=approved))
