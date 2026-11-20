"""Replica freshness per site (data-replica-latency skill logic, using this kit's connection helper):
  HVR capture latency = UTC now - trailer_cap_begin (hvr_is* tables), integ blocked flag (hvr_ic*),
  data latency        = site-local now - newest dlytrn row of the configured warehouse,
  history             = oldest dlytrn row of the warehouse, and the newest row of every busy table we read.

    py tools/replica_health.py [SITE ...]      -> docs/REPLICA_HEALTH.md (+ console)
"""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.argv, ONLY = [sys.argv[0]], [a.upper() for a in sys.argv[1:]]
sys.path.insert(0, str(HERE))
import validate_sql as v  # noqa: E402
from probe_replica_schema import connect  # noqa: E402


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


rows = []
for site in v.rows("site_config.csv"):
    code = site["SiteCode"]
    if ONLY and code not in ONLY:
        continue
    _, tok = v.tokens(code)
    S, W, off = tok["S"], site["WH_ID"], float(site.get("UTC_Offset_h") or 0)
    r = {"Site": code, "Server": site["ReplicaServer"].split(".")[0], "DB": site["ReplicaDatabase"], "WH": W}
    try:
        cn = connect(site["ReplicaServer"], "master")
        cn.timeout = 60
        dbs = [x[0] for x in cn.cursor().execute("SELECT name FROM sys.databases").fetchall()]
        r["Databases"] = ", ".join(sorted(dbs))
        cap, blocked = [], []
        for db in [d for d in dbs if d.upper().startswith(site["ReplicaDatabase"].upper().replace("_REPLICA", ""))]:
            try:
                c2 = connect(site["ReplicaServer"], db)
                c2.timeout = 60
                cur = c2.cursor()
                for sch, tbl in cur.execute("SELECT s.name, t.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
                                            "WHERE t.name LIKE 'hvr[_]is%' OR t.name LIKE 'hvr[_]ic%'").fetchall():
                    cols = [x[0].lower() for x in cur.execute(f"SELECT TOP 0 * FROM [{sch}].[{tbl}]").description]
                    if "trailer_cap_begin" in cols:
                        x = cur.execute(f"SELECT MAX(trailer_cap_begin) FROM [{sch}].[{tbl}]").fetchone()[0]
                        if x:
                            cap.append((db, tbl, x))
                    if "integ_blocked" in cols or "ic_blocked" in cols:
                        bc = "integ_blocked" if "integ_blocked" in cols else "ic_blocked"
                        x = cur.execute(f"SELECT MAX(CAST({bc} AS INT)) FROM [{sch}].[{tbl}]").fetchone()[0]
                        blocked.append((db, tbl, x))
            except Exception as e:
                say(f"   {code} {db}: {str(e)[:120]}")
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if cap:
            newest = max(cap, key=lambda z: z[2])
            r["HVR capture latency (min)"] = round((now_utc - newest[2]).total_seconds() / 60, 1)
            r["HVR table"] = f"{newest[0]}.{newest[1]}"
        r["Blocked"] = ", ".join(f"{t}={b}" for _, t, b in blocked) or "n/a"
        cn2 = connect(site["ReplicaServer"], site["ReplicaDatabase"])
        cn2.timeout = 110
        cur = cn2.cursor()
        last, first = cur.execute(f"SELECT MAX(trndte), MIN(trndte) FROM {S}.dlytrn WHERE wh_id = '{W}'").fetchone()
        local_now = now_utc + timedelta(hours=off)
        r["Newest dlytrn (site time)"] = str(last)[:16]
        r["Data latency (min)"] = round((local_now - last).total_seconds() / 60, 1) if last else None
        r["Oldest dlytrn"] = str(first)[:16]
        per_day = cur.execute(f"SELECT CAST(trndte AS DATE), COUNT(*) FROM {S}.dlytrn WHERE wh_id = '{W}' AND trndte >= DATEADD(day, -4, GETDATE()) "
                              "GROUP BY CAST(trndte AS DATE) ORDER BY 1").fetchall()
        r["dlytrn per day (last 4)"] = ", ".join(f"{d:%d-%b} {n:,}" for d, n in per_day)
        others = cur.execute(f"SELECT wh_id, MIN(trndte), MAX(trndte), COUNT(*) FROM {S}.dlytrn WHERE trndte >= DATEADD(day, -4, GETDATE()) "
                             "GROUP BY wh_id ORDER BY 4 DESC").fetchall()
        r["Warehouses (4 d)"] = "; ".join(f"{w}: {n:,} ({str(a)[5:16]} .. {str(b)[5:16]})" for w, a, b, n in others)
        trl = cur.execute(f"SELECT MIN(trndte), MAX(trndte), COUNT(*) FROM {S}.trlract WHERE wh_id = '{W}' AND trndte >= DATEADD(day, -4, GETDATE())").fetchone()
        r["trlract 4 d"] = f"{trl[2]:,} ({str(trl[0])[5:16]} .. {str(trl[1])[5:16]})"
        wko = cur.execute(f"SELECT COUNT(*), MAX(adddte) FROM {S}.wkohdr").fetchone()
        r["wkohdr rows / newest"] = f"{wko[0]:,} / {str(wko[1])[:16]}"
    except Exception as e:
        r["Error"] = str(e)[:200]
    rows.append(r)
    say(f"{code}: " + " | ".join(f"{k}={v}" for k, v in r.items() if k not in ("Site", "Databases")))

cols = ["Site", "Server", "DB", "WH", "HVR capture latency (min)", "Blocked", "Newest dlytrn (site time)", "Data latency (min)", "Oldest dlytrn",
        "dlytrn per day (last 4)", "Warehouses (4 d)", "trlract 4 d", "wkohdr rows / newest", "HVR table", "Error"]
md = ["# Replica health (HVR + data freshness)", "", f"Run {datetime.now():%Y-%m-%d %H:%M} by `py tools/replica_health.py`. HVR capture latency = "
      "UTC now - trailer_cap_begin (how far replication is behind the WMS); data latency = site-local now - newest transaction.", "",
      "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
md += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
(HERE.parent / "docs" / "REPLICA_HEALTH.md").write_text("\n".join(md) + "\n", encoding="utf-8")
say("-> docs/REPLICA_HEALTH.md")
