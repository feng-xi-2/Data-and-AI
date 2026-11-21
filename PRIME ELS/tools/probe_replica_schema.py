"""Probe WMS replica schemas for the Hypercare KPI kit (read-only, metadata only).

    py tools/probe_replica_schema.py <SITE> [<SITE> ...]     # sites from config/site_config.csv (+ EXTRA_SITES aliases)
"""
import sys, os, json, datetime, csv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyodbc
from replica_auth import get_access_token, _token_struct, DRIVER, SQL_COPT_SS_ACCESS_TOKEN

_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "site_config.csv")
SITES = {r["SiteCode"]: (r["ReplicaServer"], r["ReplicaDatabase"]) for r in csv.DictReader(open(_CFG, encoding="utf-8-sig"))}
# ad-hoc aliases for probing a server that is not (yet) the configured one
EXTRA_SITES = {
    "JAKARTA_PROD": ("<replica-server>.database.windows.net", "JAKARTA"),
    "JAKARTA_NP": ("<replica-server>.database.windows.net", "JAKARTA"),
    "XIQING": ("<replica-server>.database.windows.net", "XIQING"),
    "ATHENS": ("<replica-server>.database.windows.net", "ATHENS_REPLICA"),
}
SITES.update(EXTRA_SITES)
OBJS = ["dlytrn","locmst","sto_zone","inventory_view","invsum","pckwrk_view","pckwrk","pckwrk_hdr","prtftp_view","prtftp_dtl",
        "footprint_md","prtmst","prtdsc","wkohdr","wkodtl","trlr","trlract","car_move","stop","shipment","shipment_line",
        "ord","ord_line","adrmst","usr_prfmst","kvi_summary","wrkque"]

def connect(server, db):
    tok = get_access_token()
    cs = f"Driver={{{DRIVER}}};Server=tcp:{server},1433;Database={db};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    return pyodbc.connect(cs, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: _token_struct(tok)}, timeout=30)

out = {}
for site in ((sys.argv[1:] or SITES) if __name__ == '__main__' else []):
    srv, db = SITES[site]
    print(f"[{datetime.datetime.now():%H:%M:%S}] {site} -> {srv}/{db}", flush=True)
    try:
        cn = connect(srv, db); cn.timeout = 90; cur = cn.cursor()
        q = "SELECT s.name, o.name, o.type_desc FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE lower(o.name) IN (%s)" % ",".join("'%s'" % o for o in OBJS)
        rows = cur.execute(q).fetchall()
        found = {}
        for sch, nm, typ in rows: found.setdefault(nm.lower(), []).append(f"{sch}:{typ}")
        out[site] = found
        for o in OBJS: print(f"   {o:16s} {found.get(o, 'MISSING')}")
        sch = "prodwms" if any("prodwms" in x for x in found.get("dlytrn", [])) else "dbo"
        cur.execute(f"SELECT TOP 1 wh_id FROM {sch}.locmst GROUP BY wh_id ORDER BY COUNT(*) DESC"); print("   wh_id:", cur.fetchone())
        cur.execute(f"SELECT MAX(trndte) FROM {sch}.dlytrn"); print("   max trndte:", cur.fetchone()[0])
    except Exception as e:
        print("   ERROR", repr(e)[:400]); out[site] = {"error": repr(e)[:400]}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "_probe_schema.json"), "w"), indent=1, default=str)
