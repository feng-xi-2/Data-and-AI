"""Database-grounded gold set for the benchmark (read-only). No result rows are kept: only engine metadata.

For every converted query R01..R17 and both sides of the conversion:
  * tables + columns READ   <- the engine's own estimated plan (SET SHOWPLAN_XML ON; nothing is executed)
                               RTCIS side on RTCIS Euskirchen, PrIME side on PrIME Athens (SHOWPLAN is denied on DE08)
  * output-field lineage    <- sys.dm_exec_describe_first_result_set(..., browse_information_mode = 1)
                               RTCIS side on RTCIS Euskirchen, PrIME side on PrIME DE08 (the conversion target)

    python gold_extract.py            -> benchmark/gold.json
Needs the RTCIS-PrIME LLM wiki checkout (queries/, tools/sites.py) at WIKI_ROOT.
"""
import json
import os
import re
import sys

WIKI = os.environ.get("WIKI_ROOT", os.path.join(os.path.dirname(__file__), "..", "..", "RTCIS-PrIME-LLM-Wiki"))
sys.path.insert(0, os.path.join(WIKI, "tools"))
from sites import connect  # noqa: E402
from run_queries import declare, datetimeoffset  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "benchmark", "gold.json")
PARAMS = json.load(open(os.path.join(WIKI, "queries", "params.json"), encoding="utf-8"))
SIDES = {"rtcis": ("rtcis_tsql", "RTCIS_EUS", "RTCIS_EUS"), "prime": ("prime", "PRIME_WMD1", "PRIME_DE08")}
OBJ = re.compile(r'<Object Database="\[([^\]]+)\]" Schema="\[([^\]]+)\]" Table="\[([^\]]+)\]"')
COL = re.compile(r'<ColumnReference Database="\[[^\]]+\]" Schema="\[[^\]]+\]" Table="\[([^\]]+)\]"(?: Alias="\[[^\]]+\]")? Column="([^"]+)"')


def query_file(folder, qid):
    d = os.path.join(WIKI, "queries", folder)
    return os.path.join(d, next(f for f in os.listdir(d) if f.startswith(qid)))


def params(qid, folder, site):
    spec = PARAMS.get(qid, {}).get(folder, {})
    p = {k: v for k, v in spec.items() if k != "_per_site"}
    p.update(spec.get("_per_site", {}).get(site, {}))
    return p


def typed(p):
    """Plans and result-set metadata need parameter types, not values: lookup-SQL parameters become NULL nvarchar."""
    return {k: (None if isinstance(v, dict) else v) for k, v in p.items()}


def showplan(cur, sql, vals):
    decl = "\n".join(declare(k, v) for k, v in vals.items())
    cur.execute("SET SHOWPLAN_XML ON")
    xml = ""
    try:
        cur.execute(decl + "\n" + sql)
        while True:
            try:
                for r in cur.fetchall():
                    xml += r[0] or ""
            except Exception:
                pass
            if not cur.nextset():
                break
    finally:
        cur.execute("SET SHOWPLAN_XML OFF")
    tables = sorted({t.lower() for _, _, t in OBJ.findall(xml) if not t.startswith("#")})
    cols = sorted({f"{t.lower()}.{c.lower()}" for t, c in COL.findall(xml) if not t.startswith("#")})
    return tables, cols


def lineage(cur, sql, vals):
    pdef = ", ".join(f"@{k} {'int' if isinstance(v, int) and not isinstance(v, bool) else 'nvarchar(4000)'}" for k, v in vals.items())
    cur.execute("SELECT name, source_table, source_column, is_hidden FROM sys.dm_exec_describe_first_result_set(?, ?, 1)", sql, pdef)
    return [{"field": n, "table": (t or "").lower() or None, "column": (c or "").lower() or None}
            for n, t, c, h in cur.fetchall() if not h]


def main():
    conns = {}

    def cur(site):
        if site not in conns:
            conns[site] = connect(site)
            conns[site].timeout = 120
            conns[site].add_output_converter(-155, datetimeoffset)
        return conns[site].cursor()

    gold = {"_about": __doc__.strip().splitlines()[0], "queries": {}}
    for n in range(1, 18):
        qid = f"R{n:02d}"
        gold["queries"][qid] = {}
        for side, (folder, plan_site, lin_site) in SIDES.items():
            sql = open(query_file(folder, qid), encoding="utf-8").read()
            rec = {"plan_site": plan_site, "lineage_site": lin_site}
            try:
                c = cur(plan_site)
                rec["tables"], rec["columns"] = showplan(c, sql, typed(params(qid, folder, plan_site)))
            except Exception as e:
                rec["plan_error"] = str(e)[:200]
                conns.pop(plan_site, None)   # a timed-out SHOWPLAN session is unusable: reconnect
            try:
                c = cur(lin_site)
                rec["lineage"] = lineage(c, sql, typed(params(qid, folder, lin_site)))
            except Exception as e:
                rec["lineage_error"] = str(e)[:200]
            gold["queries"][qid][side] = rec
            print(qid, side, len(rec.get("tables", [])), "tables", len(rec.get("columns", [])), "cols",
                  sum(1 for x in rec.get("lineage", []) if x["column"]), "/", len(rec.get("lineage", [])), "fields resolved",
                  rec.get("plan_error", "") or "", rec.get("lineage_error", "") or "", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(gold, open(OUT, "w", encoding="utf-8"), indent=1)
    print("written", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
