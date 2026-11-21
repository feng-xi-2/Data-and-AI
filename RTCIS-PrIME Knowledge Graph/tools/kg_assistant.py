"""Ask / convert / batch orchestration: graph (schema linking + mappings + learnings) -> model -> read-only guard ->
validation on the real database, with one repair round fed by the database's own error message."""
import sqlglot
from sqlglot import exp

import kg_core as k

SIDE = {"RTCIS": "rtcis", "PrIME2014": "prime14", "PrIME2022": "prime"}
ENGINE_HINT = {
    "RTCIS": "RTCIS warehouse database (SQL Server replica of the Oracle RTCIS). Base tables in schema live3, upper-case codes "
             "(itmcls 'F'/'P', subsit '0'/'1'). No wh_id column.",
    "PrIME2014": "PrIME 2014 (Blue Yonder WMS) replica, schema prodwms. Warehouse filter: wh_id = @wh_id.",
    "PrIME2022": "PrIME 2022 (Blue Yonder WMS) replica, schema dbo. Warehouse filter: wh_id = @wh_id; prtmst joins need "
                 "AND prtmst.WH_ID_TMPL = @wh_id.",
}
RULES = ("Return exactly one read-only T-SQL SELECT (a WITH ... SELECT is fine) in a ```sql block, then one short paragraph "
         "explaining it. Use only the tables and columns listed. Use TOP 200 unless the query aggregates. Never write data.")


def _tables_in(sql):
    try:
        return sorted({t.name.lower() for tree in sqlglot.parse(sql, read="tsql") if tree for t in tree.find_all(exp.Table) if t.name})
    except sqlglot.errors.ParseError:
        return []


class Assistant:
    def __init__(self, graph, llm, db, index, columns, templates, approved=None):
        self.graph, self.llm, self.db = graph, llm, db
        self.index, self.columns, self.templates = index, columns, templates
        self.approved = approved if approved is not None else []

    # ----------------------------------------------------------------------------------------------- prompt parts
    def _schema(self, engine, table_names):
        cols = self.columns.get(engine, {})
        lines = []
        for t in table_names:
            if t in cols:
                lines.append(f"- {t}(" + ", ".join(f"{c} {ty}" for c, ty in list(cols[t].items())[:60]) + ")")
        return "\n".join(lines)

    def _examples(self, question, engine):
        pool = [x for x in self.approved + self.templates if x["engine"] == engine]
        ranked = k.retrieve(question, [{"id": f"ex{i}", "engine": x["engine"], "name": x.get("intent", ""),
                                        "description": x.get("intent", ""), "x": x} for i, x in enumerate(pool)], engine=engine, k=2)
        return [r["x"] for r in ranked]

    def _joins(self, engine, tables, limit=15):
        """Join pairs proven by validated queries of this engine (PrIME 2014 borrows PrIME 2022's where its own catalog
        has both columns) that touch one of the linked tables. Returns (prompt text, partner tables)."""
        src = "PrIME2022" if engine == "PrIME2014" else engine
        pool = [x["sql"] for x in self.templates + self.approved if x["engine"] == src]
        key = (engine, len(pool))
        if getattr(self, "_join_cache", {}).get("key") != key:
            self._join_cache = {"key": key, "joins": k.join_paths(pool)}
        cols = self.columns.get(engine, {})

        def known(tc):
            t, c = tc.split(".", 1)
            return c in {x.lower() for x in cols.get(t, {})}

        linked = set(tables)
        pairs = [(p, n) for p, n in self._join_cache["joins"].items()
                 if (p[0].split(".")[0] in linked or p[1].split(".")[0] in linked) and known(p[0]) and known(p[1])]
        pairs.sort(key=lambda x: (-x[1], x[0]))
        pairs = pairs[:limit]
        if not pairs:
            return "", []
        partners = [t for p, _ in pairs for t in (p[0].split(".")[0], p[1].split(".")[0]) if t not in linked]
        text = "Validated join paths (used by expert-validated queries; prefer these over guessing):\n" + \
               "\n".join(f"- {a} = {b}  ({n} queries)" for (a, b), n in pairs)
        return text, list(dict.fromkeys(partners))

    def _context_text(self, ctx):
        out = []
        if ctx.get("mappings"):
            out.append("Validated mappings (graph):\n" + "\n".join(f"- {m['from']} -> {m['to']} ({m.get('verdict', '')})" for m in ctx["mappings"][:40]))
        if ctx.get("learnings"):
            out.append("Learnings:\n" + "\n".join(f"- {x[:300]}" for x in ctx["learnings"][:8]))
        if ctx.get("rules"):
            out.append("Expert rules:\n" + "\n".join(f"- {x[:200]}" for x in ctx["rules"][:12]))
        return "\n\n".join(out)

    # ----------------------------------------------------------------------------------------------- generate + validate
    def _generate_validated(self, messages, site, params, engine=None):
        attempts, sql, res, status = 0, "", None, "rejected"
        for _ in range(2):
            attempts += 1
            sql = k.extract_sql(self.llm.chat(messages))
            try:
                k.guard_sql(sql)
            except k.UnsafeSQL as e:
                feedback = f"That was rejected by the read-only guard: {e}. Return one SELECT only."
                status, res = "rejected", {"ok": False, "stage": "guard", "error": str(e)}
            else:
                res = self.db.validate(sql, site, params)
                if res.get("ok"):
                    warn = []
                    if not res.get("rows"):
                        warn.append("Executed but returned 0 rows - check filters / parameter values before trusting it.")
                    if res.get("empty_fields"):
                        warn.append("Empty in every returned row: " + ", ".join(res["empty_fields"]))
                    return {"sql": sql, "validation": res, "attempts": attempts, "status": "validated", "warnings": warn}
                status = "failed validation"
                feedback = f"The database returned an error at the {res.get('stage')} step: {res.get('error')}. Fix the SQL."
                cards = self._schema(engine, _tables_in(sql)) if engine else ""
                if cards:
                    feedback += f"\nReal columns of the tables your SQL used (live catalog):\n{cards}"
            messages = messages + [{"role": "assistant", "content": f"```sql\n{sql}\n```"}, {"role": "user", "content": feedback}]
        return {"sql": sql, "validation": res, "attempts": attempts, "status": status, "warnings": []}

    def ask(self, question, engine, site, params=None):
        hits = k.retrieve(question, self.index, engine=engine, k=8)
        tables = [h["name"] for h in hits if h["label"] == "Table"]
        tables = list(dict.fromkeys(tables + [t for h in hits if h["label"] == "Query" for t in h.get("reads", [])]))[:12]
        joins, partners = self._joins(engine, tables)
        tables = list(dict.fromkeys(tables + partners))[:16]
        ctx = self.graph.context([h["id"] for h in hits if h["label"] == "Table"])
        ex = self._examples(question, engine)
        system = f"{ENGINE_HINT[engine]}\n{RULES}"
        user = (f"Question: {question}\n\nTables (real catalog):\n{self._schema(engine, tables)}\n\n{joins}\n\n{self._context_text(ctx)}\n\n"
                + "\n\n".join(f"Validated example ({x.get('qid', 'approved')}): {x.get('intent', '')}\n```sql\n{x['sql']}\n```" for x in ex))
        out = self._generate_validated([{"role": "system", "content": system}, {"role": "user", "content": user}], site, params, engine)
        out.update(question=question, engine=engine, site=site, linked=[h["id"] for h in hits], examples=[x.get("qid") for x in ex],
                   evidence=self.graph.evidence([h["id"] for h in hits]))
        return out

    def convert(self, sql, source_engine, target_engine, source_site, target_site, params=None, source_params=None):
        src = self.db.validate(sql, source_site, source_params)
        tables = _tables_in(sql)
        ids = [f"Table:{SIDE[source_engine]}:{t}" for t in tables]
        ctx = self.graph.context(ids)
        targets = sorted({m["to"].split(".")[0] for m in ctx.get("mappings", [])})
        joins, partners = self._joins(target_engine, targets)
        targets = list(dict.fromkeys(targets + partners))[:20]
        system = f"Convert a query to {ENGINE_HINT[target_engine]}\n{RULES} Keep every output column of the source with the same name and order."
        user = (f"Source ({source_engine}):\n```sql\n{sql}\n```\nSource output columns: {', '.join(src.get('columns', [])) or 'unknown'}\n\n"
                f"Target tables (real catalog):\n{self._schema(target_engine, targets)}\n\n{joins}\n\n{self._context_text(ctx)}")
        out = self._generate_validated([{"role": "system", "content": system}, {"role": "user", "content": user}], target_site, params,
                                       target_engine)
        out["contract"] = k.contract(src.get("columns", []), (out["validation"] or {}).get("columns", []))
        if out["status"] == "validated" and not out["contract"]["identical"]:
            out["status"] = "validated, contract differs"
        out.update(source=sql, source_validation=src, source_engine=source_engine, target_engine=target_engine, evidence=self.graph.evidence(ids))
        return out

    def batch(self, items, engine, site, target_engine=None, target_site=None, params=None):
        results = []
        for it in items:
            if it["kind"] == "ask":
                results.append(self.ask(it["question"], engine, site, params))
            else:
                results.append(self.convert(it["sql"], engine, target_engine, site, target_site, params))
        summary = {}
        for r in results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        return {"items": results, "summary": summary}
