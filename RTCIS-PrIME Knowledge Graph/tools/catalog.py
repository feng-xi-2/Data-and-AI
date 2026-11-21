"""Real catalogs of every engine (names + data types only, read-only): the validation reference for everything in the graph.

    python catalog.py   -> benchmark/catalog.json
      {"engines": {"RTCIS": {table: {col: type}}, "PrIME2014": {...}, "PrIME2022": {...}},
       "sources": {"RTCIS": "<site key>", ...}, "rtcis"/"prime": legacy per-side maps used by build_graph.py}
Sites come from tools/sites.local.json (see sites.example.json). Connection: tools/dbconn.py (signed-in user's token).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dbconn import connect, SITES  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "benchmark", "catalog.json")
SQL = ("SELECT LOWER(c.TABLE_NAME), LOWER(c.COLUMN_NAME), LOWER(c.DATA_TYPE), t.TABLE_TYPE, c.TABLE_SCHEMA FROM [{db}].INFORMATION_SCHEMA.COLUMNS c "
       "JOIN [{db}].INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME "
       "WHERE c.TABLE_SCHEMA IN ({schemas})")


def main():
    eng, src, kinds, sites = {}, {}, {}, {}
    for key, s in SITES.items():
        if not s.get("catalogs"):
            continue
        cur = connect(key).cursor()
        tabs = eng.setdefault(s["engine"], {})
        src.setdefault(s["engine"], key)
        here = sites.setdefault(key, {"engine": s["engine"], "site": s.get("site", key), "tables": {}})
        for db, schemas in s["catalogs"]:
            try:
                cur.execute(SQL.format(db=db, schemas=", ".join(f"'{x}'" for x in schemas)))
                rows = cur.fetchall()
            except Exception as e:
                print("  skip", key, db, str(e)[:120], flush=True)
                continue
            for t, c, ty, tt, sch in rows:
                tabs.setdefault(t, {}).setdefault(c, ty)
                kinds.setdefault(s["engine"], {}).setdefault(t, "VIEW" if tt == "VIEW" else "TABLE")
                here["tables"].setdefault(t, [db, sch])
        print(key, s["engine"], len(here["tables"]), "objects here;", len(tabs), "in engine,", sum(len(v) for v in tabs.values()), "columns", flush=True)
    cat = {"engines": eng, "kinds": kinds, "sources": src, "sites": sites,
           "rtcis": {t: sorted(c) for t, c in eng.get("RTCIS", {}).items()},
           "prime": {t: sorted(c) for t, c in eng.get("PrIME2022", {}).items()}}
    json.dump(cat, open(OUT, "w", encoding="utf-8"))
    print("written", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
