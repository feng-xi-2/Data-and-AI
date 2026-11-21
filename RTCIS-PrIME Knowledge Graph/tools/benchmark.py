"""Benchmark: entity recognition, graph build (Text2KGBench metrics) and graph-assisted query conversion on Cosmos DB.

Gold = the database engines themselves (benchmark/gold.json from gold_extract.py): estimated-plan tables/columns, result-set lineage.
Predictions = what build_graph.py recognised from the SQL text (benchmark/predicted.json, BEFORE the catalog gate) and what is in
the graph (relationships/*.json, AFTER the gate).

  T1 Entity recognition   tables / columns per query, exact match after lower-casing:  P, R, F1 (micro) per side.
  T2 Graph build          Text2KGBench (Mihindukulasooriya et al., ISWC 2023, github.com/cenguix/Text2KGBench):
                          P, R, F1 on triples (locally closed: only subjects present in the gold),
                          OC  ontology conformance  = share of triples whose relation is in the ontology with valid domain/range,
                          SH / RH / OH subject / relation / object hallucination = share of triples whose subject / relation / object
                          does not exist (subject/object: not in the real database catalog; relation: not in the ontology).
                          Triples: Query READS Table, Query READS_COLUMN Column, OutputField DERIVED_FROM Column.
  T3 Conversion           for every output field with engine lineage on BOTH sides (RTCIS column g_r, PrIME 2022 column g_p),
                          ask Cosmos (Gremlin) for the PrIME 2022 counterpart of g_r:  direct MAPS_TO hit, 2-hop inference
                          (RTCIS table -MAPS_TO-> PrIME table -HAS_COLUMN-> same-named column), or no knowledge.
                          Plus worked conversion plans for a few queries and natural-language lookups, all live on Cosmos.

    python benchmark.py            -> benchmark/results.json, benchmark/RESULTS.md
"""
import json
import os
import re
import sys
import time
import warnings
from collections import defaultdict

warnings.filterwarnings("ignore", category=DeprecationWarning)
sys.path.insert(0, os.path.dirname(__file__))
import load_cosmos as lc  # noqa: E402
import graphio  # noqa: E402

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
B = os.path.join(KIT, "benchmark")
GOLD = json.load(open(os.path.join(B, "gold.json"), encoding="utf-8"))["queries"]
PRED = json.load(open(os.path.join(B, "predicted.json"), encoding="utf-8"))
CAT = json.load(open(os.path.join(B, "catalog.json"), encoding="utf-8"))
ONT = json.load(open(os.path.join(KIT, "relationships", "ontology.json"), encoding="utf-8"))
NODES = {n["id"]: n for n in graphio.load("nodes")}
EDGES = graphio.load("edges")
ENGINE = {"rtcis": "RTCIS", "prime": "PrIME2022"}


def prf(pred, gold):
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return {"P": round(p, 3), "R": round(r, 3), "F1": round(2 * p * r / (p + r), 3) if p + r else 0.0, "tp": tp, "pred": len(pred), "gold": len(gold)}


def exists(side, t, c=None):
    tabs = CAT["engines"][ENGINE[side]]
    return t in tabs and (c is None or c in tabs[t])


def t1():
    out, per_q = {}, {}
    for side in ("rtcis", "prime"):
        for kind in ("tables", "columns"):
            P, G = set(), set()
            for q, g in GOLD.items():
                gs = set(g[side].get(kind, []))
                ps = set(PRED[q][side][kind])
                P |= {(q, x) for x in ps}
                G |= {(q, x) for x in gs}
                per_q.setdefault(q, {})[f"{side}_{kind}"] = prf(ps, gs)
            out[f"{side}_{kind}"] = prf(P, G)
    return out, per_q


def triples_pred(source):
    """source='extractor' -> predicted.json (before the gate); 'graph' -> edges in relationships/edges.json (after the gate)."""
    tr = set()
    if source == "extractor":
        for q, sides in PRED.items():
            for side, p in sides.items():
                s = f"Query:{q}:{side}"
                tr |= {(s, "READS", f"Table:{side}:{t}") for t in p["tables"]}
                tr |= {(s, "READS_COLUMN", f"Column:{side}:{c}") for c in p["columns"]}
                for f, cols in p["lineage"].items():
                    tr |= {(f"OutputField:{q}:{f}|{side}", "DERIVED_FROM", f"Column:{side}:{c}") for c in cols}
    else:
        for e in EDGES:
            if e["label"] in ("READS", "READS_COLUMN"):
                tr.add((e["src"], e["label"], e["dst"]))
            elif e["label"] == "DERIVED_FROM":
                side = "rtcis" if e.get("side") == "RTCIS" else "prime"
                tr.add((NODES[e["src"]]["id"].replace(" ", "_") + "|" + side, "DERIVED_FROM", e["dst"]))
    return {(re.sub(r"\s+", "_", s), r, o) for s, r, o in tr}


def triples_gold():
    tr = set()
    for q, sides in GOLD.items():
        for side, g in sides.items():
            s = f"Query:{q}:{side}"
            tr |= {(s, "READS", f"Table:{side}:{t}") for t in g.get("tables", [])}
            tr |= {(s, "READS_COLUMN", f"Column:{side}:{c}") for c in g.get("columns", [])}
            for x in g.get("lineage", []):
                if x["column"]:
                    tr.add((re.sub(r"\s+", "_", f"OutputField:{q}:{x['field']}|{side}"), "DERIVED_FROM", f"Column:{side}:{x['table']}.{x['column']}"))
    return tr


def entity_ok(eid):
    m = re.match(r"^(Table|Column):(rtcis|prime):([\w$]+)(?:\.([\w$]+))?$", eid)
    if m:
        return exists(m.group(2), m.group(3), m.group(4)) if m.group(1) == "Column" else exists(m.group(2), m.group(3))
    m = re.match(r"^Query:(R\d\d):(rtcis|prime)$", eid)
    if m:
        return m.group(1) in GOLD
    m = re.match(r"^OutputField:(R\d\d):(.+)\|(rtcis|prime)$", eid)
    return bool(m)


def label_of(eid):
    return eid.split(":", 1)[0]


def t2():
    gold = triples_gold()
    rels = ONT["edges"]
    res = {}
    for source in ("extractor", "graph"):
        pred = triples_pred(source)
        out = {}
        for rel in ("READS", "READS_COLUMN", "DERIVED_FROM", "ALL"):
            g = {t for t in gold if rel in ("ALL", t[1])}
            p = {t for t in pred if rel in ("ALL", t[1])}
            subj = {t[0] for t in g}
            p_closed = {t for t in p if t[0] in subj}          # locally closed (Text2KGBench)
            m = prf(p_closed, g)
            n = len(p) or 1
            m["OC"] = round(sum(1 for s, r, o in p if r in rels and label_of(s) in rels[r][0] and label_of(o) in rels[r][1]) / n, 3)
            m["SH"] = round(sum(1 for s, r, o in p if not entity_ok(s)) / n, 3)
            m["RH"] = round(sum(1 for s, r, o in p if r not in rels) / n, 3)
            m["OH"] = round(sum(1 for s, r, o in p if not entity_ok(o)) / n, 3)
            out[rel] = m
        res[source] = out
    return res


def gq(c, q, b=None):
    return lc.run(c, q, b or {})


def t3(c):
    rows, stats = [], defaultdict(int)
    for q, sides in GOLD.items():
        rl = {x["field"]: x for x in sides["rtcis"].get("lineage", []) if x["column"]}
        pl = {x["field"]: x for x in sides["prime"].get("lineage", []) if x["column"]}
        for f in sorted(set(rl) & set(pl)):
            gr = f"{rl[f]['table']}.{rl[f]['column']}"
            gp = f"{pl[f]['table']}.{pl[f]['column']}"
            src = f"Column:rtcis:{gr}"
            direct = gq(c, "g.V(s).has('pk', 'Column:RTCIS').outE('MAPS_TO').inV().has('platform', 'PrIME2022').values('id')",
                        {"s": src})
            direct = sorted({d.split(":", 2)[2] for d in direct})
            hop = gq(c, "g.V(t).has('pk', 'Table:RTCIS').out('MAPS_TO').has('platform', 'PrIME2022').out('HAS_COLUMN').has('name', n).values('id')",
                     {"t": f"Table:rtcis:{rl[f]['table']}", "n": rl[f]["column"]})
            hop = sorted({d.split(":", 2)[2] for d in hop})
            # learned from OTHER converted queries (leave-one-query-out): a field elsewhere derived from the same RTCIS
            # column, whose PrIME side is derived from ... (extractor lineage, not the gold)
            learned = gq(c, "g.V(s).has('pk', 'Column:RTCIS').in('DERIVED_FROM').has('qid', neq(q)).out('DERIVED_FROM')"
                            ".has('platform', 'PrIME2022').values('id')", {"s": src, "q": q})
            learned = sorted({d.split(":", 2)[2] for d in learned})
            if not exists("rtcis", rl[f]["table"], rl[f]["column"]):
                verdict = "gold column not in catalog"
            elif gp in direct:
                verdict = "direct MAPS_TO hit"
            elif gp in learned:
                verdict = "learned from other converted queries"
            elif gp in hop:
                verdict = "2-hop inference hit"
            elif direct or hop or learned:
                verdict = "knowledge points elsewhere"
            else:
                verdict = "no knowledge"
            stats[verdict] += 1
            rows.append({"query": q, "field": f, "rtcis": gr, "prime_gold": gp, "direct": direct[:5], "learned": learned[:5],
                         "two_hop": hop[:5], "verdict": verdict})
    return dict(stats), rows


PLANS = ("R04", "R13", "R16", "R01")


def plans(c):
    out = {}
    for q in PLANS:
        rt = f"Query:{q}:rtcis"
        tabs = gq(c, "g.V(q).has('pk', 'Query').out('READS').values('name')", {"q": rt})
        prop = gq(c, "g.V(q).has('pk', 'Query').out('READS').out('MAPS_TO').has('platform', 'PrIME2022').dedup().values('name')", {"q": rt})
        gold_p = set(GOLD[q]["prime"].get("tables", []))
        learn = gq(c, "g.V(q).has('pk', 'Query').out('READS').in('MENTIONS').hasLabel('Learning', 'DataFact').dedup().limit(6).values('text')", {"q": rt})
        rules = gq(c, "g.V(q).has('pk', 'Query').outE('APPLIES_RULE').has('result', 'PASS').inV().values('code')", {"q": f"Query:{q}:prime"})
        findings = gq(c, "g.V(q).has('pk', 'Query').out('HAS_FIELD').out('EXPLAINED_BY').project('cat', 'text').by('category').by('text')", {"q": f"Query:{q}:prime"})
        out[q] = {"rtcis_tables": sorted(tabs), "proposed_prime_tables": sorted(prop), "gold_prime_tables": sorted(gold_p),
                  "table_prf": prf(set(prop), gold_p), "learnings": [x[:220] for x in learn], "rules_passed": sorted(rules),
                  "findings": [f"{x['cat']}: {x['text'][:160]}" for x in findings[:6]]}
    return out


NL = [
    ("Which PrIME 2022 table holds the pallet (load) number?",
     "g.V().has('pk', 'Column:PrIME2022').has('name', 'lodnum').in('HAS_COLUMN').has('theme', 'Transactional').values('name')", {}),
    ("Where does RTCIS untdtl.casqty go in PrIME 2022, and with which evidence?",
     "g.V('Column:rtcis:untdtl.casqty').has('pk', 'Column:RTCIS').outE('MAPS_TO').project('to', 'evidence', 'verdict').by(inV().values('id'))"
     ".by(coalesce(values('sources'), values('agreement'), constant(''))).by(coalesce(values('value_verdict'), values('tag'), constant('')))", {}),
    ("Which PrIME 2014 columns were renamed in PrIME 2022 (data-model transition map, validated)?",
     "g.V().has('pk', 'Column:PrIME2014').outE('MAPS_TO').has('sources', TextP.containing('H5')).limit(8).project('from', 'to').by(outV().values('id')).by(inV().values('id'))", {}),
    ("Which tables exist in PrIME 2014 but not in PrIME 2022 (no validated mapping)?",
     "g.V().has('pk', 'Table:PrIME2014').not(outE('MAPS_TO')).limit(10).values('name')", {}),
    ("Which converted queries are templates for 'inventory' questions, with grade and parameters?",
     "g.V().has('pk', 'Query').has('side', 'PrIME2022').has('intent', TextP.containing('nventory')).project('q', 'grade', 'params').by('qid').by('grade').by('params')", {}),
    ("What do the experts say about descriptions (prtdsc)?",
     "g.V('Table:prime:prtdsc').has('pk', 'Table:PrIME2022').in('MENTIONS').hasLabel('Learning', 'ExpertRule', 'DataFact').limit(5).values('text')", {}),
    ("Which PrIME 2022 tables are in the 'inventory' ERD domain and replicated at Euskirchen DE08?",
     "g.V('Domain:inventory').has('pk', 'Domain').in('IN_DOMAIN').where(out('EXISTS_AT').has('id', 'Site:PRIME22_DE08')).values('name')", {}),
    ("Which mappings are flagged as conflicting (a person must decide)?",
     "g.V().has('pk', 'Column:RTCIS').outE('MAPS_TO').has('conflict').project('from', 'to', 'alt').by(outV().values('id')).by(inV().values('id')).by('conflict')", {}),
]


def nl(c):
    out = []
    for question, q, b in NL:
        t = time.time()
        try:
            r = gq(c, q, b)
            out.append({"question": question, "gremlin": q, "answer": r[:10], "n": len(r), "ms": int(1000 * (time.time() - t))})
        except Exception as e:
            out.append({"question": question, "gremlin": q, "error": str(e)[:300]})
    return out


def md(res):
    L = ["# Benchmark results", "", f"Run {res['run_at']}. Gold = the database engines (plan + result-set lineage); see tools/benchmark.py.", ""]
    L += ["## T1 Entity recognition (SQL text -> tables / columns)", "", "| side | entity | P | R | F1 | tp / pred / gold |", "|---|---|---|---|---|---|"]
    for k, v in res["T1"].items():
        s, e = k.split("_")
        L.append(f"| {s} | {e} | {v['P']} | {v['R']} | {v['F1']} | {v['tp']} / {v['pred']} / {v['gold']} |")
    L += ["", "## T2 Graph build (Text2KGBench metrics)", "",
          "| stage | relation | P | R | F1 | OC | SH | RH | OH |", "|---|---|---|---|---|---|---|---|---|"]
    for stage, rels in res["T2"].items():
        for r, v in rels.items():
            L.append(f"| {stage} | {r} | {v['P']} | {v['R']} | {v['F1']} | {v['OC']} | {v['SH']} | {v['RH']} | {v['OH']} |")
    L += ["", "`extractor` = before the catalog gate, `graph` = what was loaded. OC/SH/RH/OH as defined in Text2KGBench.", "",
          "## T3 Conversion lookup on Cosmos (RTCIS column -> PrIME 2022 column)", ""]
    tot = sum(res["T3"]["stats"].values()) or 1
    L += ["| verdict | fields | share |", "|---|---|---|"] + [f"| {k} | {v} | {100 * v / tot:.0f}% |" for k, v in sorted(res["T3"]["stats"].items(), key=lambda x: -x[1])]
    L += ["", "| query | field | RTCIS (engine) | PrIME 2022 (engine) | graph direct | learned (other queries) | verdict |", "|---|---|---|---|---|---|---|"]
    for r in res["T3"]["rows"]:
        L.append(f"| {r['query']} | {r['field']} | `{r['rtcis']}` | `{r['prime_gold']}` | {', '.join(r['direct'][:3]) or '-'} | "
                 f"{', '.join(r.get('learned', [])[:3]) or '-'} | {r['verdict']} |")
    L += ["", "## Worked conversion plans (live Gremlin)", ""]
    for q, p in res["plans"].items():
        L += [f"### {q}", f"- RTCIS tables read: {', '.join(p['rtcis_tables'])}",
              f"- PrIME 2022 tables proposed by MAPS_TO: {', '.join(p['proposed_prime_tables']) or '-'}",
              f"- PrIME 2022 tables the delivered conversion reads (engine plan): {', '.join(p['gold_prime_tables'])}",
              f"- table P/R/F1: {p['table_prf']['P']} / {p['table_prf']['R']} / {p['table_prf']['F1']}",
              f"- expert rules passed: {', '.join(p['rules_passed'])}"]
        L += [f"- learning: {x}" for x in p["learnings"][:3]] + [f"- finding: {x}" for x in p["findings"][:3]] + [""]
    L += ["## Natural-language lookups (live Gremlin)", ""]
    for x in res["NL"]:
        L += [f"**{x['question']}**", "", f"`{x['gremlin']}`", "",
              f"-> {json.dumps(x.get('answer'), ensure_ascii=False)[:600]}" + (f" ({x['n']} results, {x['ms']} ms)" if "n" in x else f" ERROR {x.get('error')}"), ""]
    return "\n".join(L)


def main():
    res = {"run_at": time.strftime("%Y-%m-%d %H:%M")}
    res["T1"], res["T1_per_query"] = t1()
    res["T2"] = t2()
    graph = os.environ.get("KG_GRAPH", "rtcis_prime")
    key = lc.ensure(graph, reset=False)
    c = lc.connect(key, graph)
    try:
        st, rows = t3(c)
        res["T3"] = {"stats": st, "rows": rows}
        res["plans"] = plans(c)
        res["NL"] = nl(c)
    finally:
        c.close()
    json.dump(res, open(os.path.join(B, "results.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    open(os.path.join(B, "RESULTS.md"), "w", encoding="utf-8").write(md(res))
    print(json.dumps({"T1": res["T1"], "T2_graph_ALL": res["T2"]["graph"]["ALL"], "T2_extractor_ALL": res["T2"]["extractor"]["ALL"],
                      "T3": res["T3"]["stats"]}, indent=1))


if __name__ == "__main__":
    main()

