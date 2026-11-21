"""SQL remediation as a LangGraph Deep Agent (deepagents.create_deep_agent), same contract as kg_assistant.Assistant.

Layout follows the official Deep Agents text-to-SQL example: agent/AGENTS.md (always loaded memory) + agent/skills/*/SKILL.md
(loaded on demand, progressive disclosure) + narrow SQL tools. What is enforced in code, not in the prompt:
- tools are built per request and bound to that request's engine, site and @wh_id - the model cannot pick a database;
- run_sql applies the read-only guard before any database call and is capped at MAX_RUNS per request;
- the agent's files are read-only (FilesystemPermission deny write) - it cannot rewrite its own instructions;
- the final SQL is re-validated deterministically on the request site; the model's own claim is never trusted."""
import json
import os
import time

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain_core.tools import StructuredTool

import kg_core as k
from kg_assistant import SIDE, Assistant, _tables_in

AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agent"))
MAX_RUNS = 3
RECURSION_LIMIT = 60


def genai_model(name=None):
    """GenAI platform model. Chat Completions with tool calls works for GPT-5.x (default GPT-5.6 Sol). GPT-6.x only does
    tool calls on the Responses API, and the gateway rejects the multi-turn Responses input LangChain sends (assistant
    'phase' items) - so GPT-6.x stays for single-shot use (kg_assistant) until the gateway accepts it."""
    import azauth
    from langchain_openai import ChatOpenAI
    base = os.environ["KG_GENAI_ENDPOINT"].rstrip("/")
    name = name or os.environ.get("KG_AGENT_MODEL", "GPT-56-SOL-2026-07-09")
    return ChatOpenAI(model=name, base_url=f"{base}/openai/deployments/{name}",
                      api_key=lambda: azauth.token("https://cognitiveservices.azure.com/.default"),
                      default_query={"api-version": "2025-04-01-preview"}, timeout=180, max_retries=2,
                      default_headers={"userid": os.environ.get("KG_GENAI_USER", ""), "project-name": os.environ.get("KG_GENAI_PROJECT", "")})


def _text(content):
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return content or ""


class DeepAssistant:
    def __init__(self, graph, db, index, columns, templates, approved=None, model=None, agent_dir=AGENT_DIR):
        self.graph, self.db, self.agent_dir = graph, db, agent_dir
        self.model = model if model is not None else genai_model()
        self.helper = Assistant(graph=graph, llm=None, db=db, index=index, columns=columns, templates=templates, approved=approved)
        self.index, self.columns = index, columns

    @property
    def approved(self):
        return self.helper.approved

    # ------------------------------------------------------------------------------------------------ request tools
    def _tools(self, engine, site, params, runs, source_engine=None):
        h, db = self.helper, self.db

        def search_knowledge(text: str) -> str:
            """Find tables and validated example queries for business words (pallet, area, part, pick ...) in this engine."""
            hits = k.retrieve(text, self.index, engine=engine, k=10)
            return "\n".join(f"- {x['label']} {x['name']}: {x.get('description', '')[:160]}" for x in hits) or "no match - try other words"

        def describe_tables(tables: list[str]) -> str:
            """Real columns and types of tables in this engine's live catalog. Call before using any column."""
            cards = h._schema(engine, [t.lower().split(".")[-1].strip("[]") for t in tables])
            missing = [t for t in tables if t.lower().split(".")[-1].strip("[]") not in self.columns.get(engine, {})]
            return (cards or "") + (f"\nNot in the {engine} catalog: {', '.join(missing)}" if missing else "")

        def join_paths(tables: list[str]) -> str:
            """Join conditions proven by expert-validated queries, touching the given tables."""
            text, _ = h._joins(engine, [t.lower() for t in tables])
            return text or "no validated join path for these tables - check columns with describe_tables"

        def graph_context(tables: list[str]) -> str:
            """Validated mappings, learnings and expert rules from the knowledge graph for these tables."""
            side = SIDE[source_engine or engine]
            try:
                ctx = self.graph.context([f"Table:{side}:{t.lower()}" for t in tables])
            except Exception as e:   # a graph outage must not end the answer: tell the model and let it go on
                return f"graph lookup failed ({type(e).__name__}) - continue with describe_tables / find_examples"
            return h._context_text(ctx) or "nothing in the graph for these tables"

        def find_examples(text: str) -> str:
            """Expert-validated example queries of this engine that match the intent."""
            ex = h._examples(text, engine)
            return "\n\n".join(f"{x.get('qid', 'approved')}: {x.get('intent', '')}\n```sql\n{x['sql'][:3000]}\n```" for x in ex) or "no example"

        def run_sql(sql: str) -> str:
            """Run one read-only SELECT on this request's database (dry-run + execution, first rows only)."""
            try:
                k.guard_sql(sql)
            except k.UnsafeSQL as e:
                return f"REJECTED by the read-only guard: {e}. Only one SELECT is allowed."
            if len(runs) >= MAX_RUNS:
                return f"Run limit of {MAX_RUNS} reached - answer with your best validated SQL."
            res = db.validate(sql, site, params)
            runs.append({"sql": sql, "ok": res.get("ok"), "error": res.get("error")})
            if not res.get("ok"):
                return f"ERROR at {res.get('stage')}: {res.get('error')}"
            return json.dumps({"columns": res.get("columns"), "first_rows": (res.get("rows") or [])[:5], "row_count": res.get("row_count"),
                               "empty_fields": res.get("empty_fields")}, default=str)[:4000]

        def concept_context(text: str) -> str:
            """Business theme (inventory, outbound, receiving, automation ...) and Timbr semantic concept of the question,
            with their tables in this engine (checked in the live catalog) and the matching tables in the other engines.
            Call this first, then describe_tables on the tables it names."""
            entries = [x for x in self.index if x.get("label") in ("Theme", "SemanticConcept")]
            hits = k.route_concepts(text, entries, self.index, engine, k=3)
            if not hits:
                return "no theme or concept matches - use search_knowledge"
            cat = self.columns.get(engine, {})
            lines = []
            for x in hits:
                kind = "theme" if x["label"] == "Theme" else "concept"
                direct = set(x["direct"].get(engine, [])) if "direct" in x else set(x["tables"].get(engine, []))
                # only tables linked directly to the theme / concept: ones inferred through mappings misled the agent
                # (RTCIS zones -> agv_inventory_view via the inventory_view hub)
                mine = [t for t in x["ranked"].get(engine, []) if t in direct][:8]
                if not mine:
                    continue   # a theme with no table in this engine is noise for this request
                usable = [t for t in mine if t.lower() in cat]
                missing = [f"{t} (not in the {engine} catalog)" for t in mine if t.lower() not in cat]
                others = "; ".join(f"{e}: {', '.join(ts)}" for e, ts in x["tables"].items() if e != engine and ts)
                lines.append(f"- {kind} {x['name']}: {x['description'][:200]}\n  {engine} tables: " + ", ".join(usable + missing)
                             + (f"\n  other engines: {others}" if others else ""))
            return "\n".join(lines) or f"no theme or concept with {engine} tables - use search_knowledge"

        fns = [concept_context, search_knowledge, describe_tables, join_paths, graph_context, find_examples, run_sql]
        return [StructuredTool.from_function(f) for f in fns]

    def _agent(self, tools):
        return create_deep_agent(model=self.model, tools=tools, memory=["/AGENTS.md"], skills=["/skills/"],
                                 backend=FilesystemBackend(root_dir=self.agent_dir, virtual_mode=True),
                                 permissions=[FilesystemPermission(operations=["write"], paths=["/**"], mode="deny")],
                                 name="sql_remediation")

    def _run(self, prompt, engine, site, params, source_engine=None):
        runs = []
        agent = self._agent(self._tools(engine, site, params, runs, source_engine))
        t0 = time.time()
        state = agent.invoke({"messages": [{"role": "user", "content": prompt}]}, config={"recursion_limit": RECURSION_LIMIT})
        msgs = state["messages"]
        trace = [{"tool": c["name"], "args": json.dumps(c["args"], default=str)[:200]} for m in msgs if m.type == "ai" for c in (m.tool_calls or [])]
        answer = _text(msgs[-1].content) if msgs else ""
        return answer, runs, trace, round(time.time() - t0, 1)

    def _final(self, answer, site, params, runs):
        sql = k.extract_sql(answer)
        fallback = ""
        if not (sql or "").strip():
            ok_runs = [r for r in runs if r.get("ok")]
            if ok_runs:
                sql = ok_runs[-1]["sql"]
                fallback = "The answer had no SQL block - showing the last successful SQL the agent ran."
        base = {"sql": sql, "answer": answer, "attempts": max(1, len(runs)), "warnings": [fallback] if fallback else []}
        try:
            k.guard_sql(sql)
        except k.UnsafeSQL as e:
            return dict(base, status="rejected", validation={"ok": False, "stage": "guard", "error": str(e)})
        res = self.db.validate(sql, site, params)
        if not res.get("ok"):
            return dict(base, status="failed validation", validation=res)
        warn = list(base["warnings"])
        if not res.get("rows"):
            warn.append("Executed but returned 0 rows - check filters / parameter values before trusting it.")
        if res.get("empty_fields"):
            warn.append("Empty in every returned row: " + ", ".join(res["empty_fields"]))
        return dict(base, status="validated", validation=res, warnings=warn)

    # ------------------------------------------------------------------------------------------------ contract
    def ask(self, question, engine, site, params=None):
        prompt = (f"Engine: {engine} (database {site}" + (f", @wh_id = '{params['wh_id']}'" if params and params.get("wh_id") else "")
                  + f").\nQuestion: {question}\nUse the warehouse-query-writing skill.")
        answer, runs, trace, secs = self._run(prompt, engine, site, params)
        out = self._final(answer, site, params, runs)
        linked = [f"Table:{SIDE[engine]}:{t}" for t in _tables_in(out["sql"])] if out["sql"] else []
        out.update(question=question, engine=engine, site=site, linked=linked, trace=trace, agent_seconds=secs,
                   evidence=self.graph.evidence(linked), engine_kind="deep-agent")
        return out

    def convert(self, sql, source_engine, target_engine, source_site, target_site, params=None, source_params=None):
        src = self.db.validate(sql, source_site, source_params)
        tables = _tables_in(sql)
        prompt = (f"Convert this {source_engine} query (it ran on {source_site}) to {target_engine} for database {target_site}"
                  + (f" with @wh_id = '{params['wh_id']}'" if params and params.get("wh_id") else "") + ".\n"
                  f"Source output columns (keep all, same names and order): {', '.join(src.get('columns') or []) or 'unknown'}\n"
                  f"Source tables: {', '.join(tables)}\n```sql\n{sql}\n```\nUse the rtcis-prime-conversion skill; "
                  f"graph_context takes the SOURCE table names, the other tools answer for {target_engine}.")
        answer, runs, trace, secs = self._run(prompt, target_engine, target_site, params, source_engine)
        out = self._final(answer, target_site, params, runs)
        out["contract"] = k.contract(src.get("columns") or [], (out["validation"] or {}).get("columns") or [])
        if out["status"] == "validated" and not out["contract"]["identical"]:
            out["status"] = "validated, contract differs"
        ids = [f"Table:{SIDE[source_engine]}:{t}" for t in tables]
        out.update(source=sql, source_validation=src, source_engine=source_engine, target_engine=target_engine, trace=trace,
                   agent_seconds=secs, evidence=self.graph.evidence(ids), engine_kind="deep-agent")
        return out

    def batch(self, items, engine, site, target_engine=None, target_site=None, params=None):
        results = [self.ask(it["question"], engine, site, params) if it["kind"] == "ask"
                   else self.convert(it["sql"], engine, target_engine, site, target_site, params) for it in items]
        summary = {}
        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        return {"items": results, "summary": summary}
