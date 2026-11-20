"""Validate the CDL (Databricks SAP silver) queries for one site: SAP Plan PO (Has_SAP_Plan = 1) and every sql/cdl/*.sql
(SAP Production when Has_SAP_Prod = 1). Same tokens as the model (fnSiteSql).

    py tools/validate_cdl.py BINHDUONG [MINHANG ...]
"""
import os, re, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replica_auth as auth
from databricks import sql
from validate_sql import tokens, render, read_m_string, ROOT
from m_tokenizer import expand_config_blocks

GATES = {"SAP Plan PO": "Has_SAP_Plan", "SAP Production": "Has_SAP_Prod"}


def queries():
    m = (ROOT / "sql" / "extracted" / "SAP Plan PO.m").read_text(encoding="utf-8")
    out = {"SAP Plan PO": read_m_string(m, m.index('fnSiteSql("') + len("fnSiteSql("), {})[0]}
    for f in sorted((ROOT / "sql" / "cdl").glob("*.sql")):
        out[f.stem] = expand_config_blocks(f.read_text(encoding="utf-8"))
    return out


def run(code):
    site, tok = tokens(code)
    app = auth._load_msal_app()[0]
    t = app.acquire_token_silent(["2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"], account=app.get_accounts()[0])["access_token"]
    cn = sql.connect(server_hostname=site["Databricks_Host"], http_path=site["Databricks_HttpPath"], access_token=t)
    bad = 0
    for name, body in queries().items():
        if site.get(GATES.get(name, ""), "1") != "1":
            print(f"{code}: {name} skipped ({GATES[name]} = 0)", flush=True)
            continue
        q = render(body, tok)
        left = re.findall(r"(?<!\{)\{[A-Za-z_]+\}(?!\})", q)
        if left:
            print(f"{code}: {name} UNRESOLVED {left}", flush=True); bad += 1; continue
        cur = cn.cursor(); t0 = time.time()
        try:
            cur.execute(q); rows = cur.fetchall()
            print(f"{code}: {name} on {site['Databricks_Host']} -> {len(rows)} rows, {len(cur.description)} cols, {time.time() - t0:.0f}s", flush=True)
        except Exception as e:
            bad += 1
            print(f"{code}: {name} FAIL {re.sub(r'\s+', ' ', str(e))[:300]}", flush=True)
    return bad


if __name__ == "__main__":
    stop = threading.Event()
    threading.Thread(target=lambda: [print(f"  [hb {time.strftime('%H:%M:%S')}] CDL query running...", flush=True) for _ in iter(lambda: stop.wait(25), True)],
                     daemon=True).start()
    fails = sum(run(c.upper()) for c in (sys.argv[1:] or ["BINHDUONG"]))
    stop.set()
    sys.exit(1 if fails else 0)
