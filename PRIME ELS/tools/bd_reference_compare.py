"""BD reference comparison: the ORIGINAL BD Throughput queries (exported from the BD pbix, _src_oct/tmdl_original) against the
generated BINHDUONG queries (tokenised + warehouse-scoped + documented fixes), both run now on the BD replica.

    py tools/bd_reference_compare.py [TABLE ...]

Per table: rows original / generated, rows only in one side (multiset compare on the common columns, values normalised), and
the documented reason when they differ (config/bd_reference_changes.csv). Writes docs/BD_REFERENCE_COMPARE.md.
A difference WITHOUT a documented reason is a regression (exit code 1).
"""
import csv
import re
import sys
import time
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.argv, ONLY = [sys.argv[0]], set(sys.argv[1:])
sys.path.insert(0, str(HERE))
import validate_sql as v  # noqa: E402
from probe_replica_schema import connect  # noqa: E402

REASONS = {r["Table"]: r["Reason"] for r in csv.DictReader(open(ROOT / "config" / "bd_reference_changes.csv", encoding="utf-8-sig"))}


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def original_sql(table):
    f = ROOT / "_src_oct" / "tmdl_original" / "tables" / f"{table}.tmdl"
    t = f.read_text(encoding="utf-8")
    m = re.search(r'\[Query\s*=\s*"', t) or re.search(r'(?:SqlQuery|SQL)\s*=\s*"', t)
    if not m:
        return None
    sql = v.read_m_string(t, m.end() - 1, {"StartDateValue": "2026-07-26 00:00:00", "FormattedDate": "2026-07-26 00:00:00"})[0]
    return sql


def norm(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, Decimal):
        return round(float(x), 4)
    if isinstance(x, datetime):
        return x.replace(microsecond=0)
    if isinstance(x, str):
        return x.strip()
    return x


def fetch(cur, sql):
    t0 = time.time()
    cur.execute(sql)
    while cur.description is None and cur.nextset():
        pass
    cols = [c[0].lower() for c in cur.description]
    rows = cur.fetchall()
    return cols, rows, time.time() - t0


site, tok = v.tokens("BINHDUONG")
cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
cn.timeout = 110
cur = cn.cursor()
gen = v.queries()
out, bad = [], 0
for f in sorted((ROOT / "_src_oct" / "tmdl_original" / "tables").glob("*.tmdl")):
    table = f.stem
    if ONLY and table not in ONLY:
        continue
    osql = original_sql(table)
    if not osql or table not in gen:
        continue
    kind, body = gen[table]
    gsql = v.render(v.sql_from_m(body, tok) if kind == "orig" else body, tok)
    try:
        oc, orows, ot = fetch(cur, osql)
        gc, grows, gt = fetch(cur, gsql)
    except Exception as e:
        out.append((table, "", "", "", "", f"ERROR {re.sub(r'\s+', ' ', str(e))[:160]}", ""))
        say(f"!! {table}: {e}")
        bad += 1
        continue
    common = [c for c in oc if c in gc]
    oi, gi = [oc.index(c) for c in common], [gc.index(c) for c in common]
    ocnt = Counter(tuple(norm(r[i]) for i in oi) for r in orows)
    gcnt = Counter(tuple(norm(r[i]) for i in gi) for r in grows)
    only_o, only_g = sum((ocnt - gcnt).values()), sum((gcnt - ocnt).values())
    same = only_o == 0 and only_g == 0
    reason = REASONS.get(table, "")
    status = "IDENTICAL" if same else ("DIFF - documented" if reason else "DIFF - NOT DOCUMENTED")
    bad += status.endswith("NOT DOCUMENTED")
    cols_note = "" if oc == gc else f"columns: +{sorted(set(gc) - set(oc))} -{sorted(set(oc) - set(gc))}"
    out.append((table, len(orows), len(grows), only_o, only_g, status, (reason if not same else "") + (" " + cols_note if cols_note else "")))
    say(f"{table:42s} original {len(orows):>7} ({ot:.1f}s)  generated {len(grows):>7} ({gt:.1f}s)  only-original {only_o:>6}  only-generated {only_g:>6}  {status}")

md = ["# BD reference comparison - original BD Throughput queries vs generated BINHDUONG queries", "",
      f"Run {datetime.now():%Y-%m-%d %H:%M} by `py tools/bd_reference_compare.py` on the BD replica (both queries executed back to back). "
      "Rows compared as multisets on the columns both queries return. Reasons for intended differences: `config/bd_reference_changes.csv`.", "",
      "| Table | Rows original | Rows generated | Only in original | Only in generated | Result | Reason / note |", "|---|---|---|---|---|---|---|"]
md += [f"| {' | '.join(str(x) for x in r)} |" for r in out]
(ROOT / "docs" / "BD_REFERENCE_COMPARE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
say(f"DONE {len(out)} tables, {sum(1 for r in out if r[5] == 'IDENTICAL')} identical, {bad} undocumented difference(s) -> docs/BD_REFERENCE_COMPARE.md")
sys.exit(1 if bad else 0)
