"""Run read-only SQL on the CDL Databricks SQL warehouse (SAP silver tables) with the cached Entra token.

    py tools/cdl_query.py "SELECT ... LIMIT 20"           # prints rows (tab separated) + elapsed time
    py tools/cdl_query.py --file q.sql [--csv out.csv]

Host / HTTP path from config/site_config.csv (first site with Databricks_Host). Warehouse start-up can take 1-3 min.
"""
import csv
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replica_auth as auth  # noqa: E402
from databricks import sql  # noqa: E402
from validate_sql import rows as cfg_rows  # noqa: E402

args = sys.argv[1:]
out_csv = args[args.index("--csv") + 1] if "--csv" in args else None
if "--file" in args:
    q = open(args[args.index("--file") + 1], encoding="utf-8").read()
else:
    q = next(a for a in args if not a.startswith("--") and a != out_csv)
site = next(r for r in cfg_rows("site_config.csv") if r.get("Databricks_Host"))
app = auth._load_msal_app()[0]
tok = app.acquire_token_silent(["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"], account=app.get_accounts()[0])["access_token"]
t0 = time.time()
done = threading.Event()


def beat():
    while not done.wait(30):
        print(f"[{time.strftime('%H:%M:%S')}] heartbeat: CDL query running {time.time() - t0:.0f}s", flush=True)


threading.Thread(target=beat, daemon=True).start()
try:
    cn = sql.connect(server_hostname=site["Databricks_Host"], http_path=site["Databricks_HttpPath"], access_token=tok)
    cur = cn.cursor()
    cur.execute(q)
    rows = cur.fetchall()
    cols = [c[0] for c in cur.description]
finally:
    done.set()
print("\t".join(cols))
for r in rows[:200]:
    print("\t".join("" if v is None else str(v) for v in r))
print(f"-- {len(rows)} rows, {time.time() - t0:.1f}s")
if out_csv:
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
