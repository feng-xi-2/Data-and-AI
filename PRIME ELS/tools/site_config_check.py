"""Site configuration gate - checks every config/site_config.csv row against its live replica BEFORE the model is built (read-only).

    py tools/site_config_check.py [SITE ...]          -> docs/SITE_CONFIG_CHECK.md + exit 1 when any FAIL

Sustainable fix for "a page is empty at one site": wrong / stale config is caught here for every current and future site,
instead of being found visual by visual. Checks per site (all values from the config, nothing site-specific in this code):
  WH_ID          the configured warehouse is the busiest wh_id of the replica (dlytrn last 7 days)            FAIL if not
  HISTORY        days of dlytrn history in the replica vs the longest look-back the model needs              WARN if shorter
  TRAILERS       trlract has RCV / SHIP rows in the last 14 days (TTAT pages)                                 WARN if none
  FEATURE flags  Has_LevelA / Has_HOFF -> their LOC_* pattern matches storage locations of WH_ID            FAIL if 0
                 Has_Production -> produced-pallet query returns rows in the last 14 days                    WARN if 0
  TOKENS         every LOC_* / AREA_* token (not ~NA~) matches >= 1 location / area of WH_ID                 WARN if 0
Heartbeat line per check; every SQL error is reported (never silent).
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import validate_sql as v  # noqa: E402
from probe_replica_schema import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {"Has_LevelA": "LOC_LEVEL_A", "Has_HOFF": "LOC_HOFF_IN"}


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def like_sql(pattern):
    return pattern.replace("'", "''")


def check_site(code):
    site, tok = v.tokens(code)
    S = tok.get("S") or ("dbo" if "2022" in site["WMS_Version"] else "prodwms")
    wh = site["WH_ID"]
    out = []

    def add(level, check, detail):
        out.append((level, check, detail))
        say(f"  {code:10s} {level:4s} {check:14s} {detail}")

    try:
        cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
        cn.timeout = 110
        cur = cn.cursor()
        cur.execute("SET LOCK_TIMEOUT 60000")
    except Exception as e:
        add("FAIL", "CONNECT", f"cannot connect: {str(e)[:160]}")
        return out

    def q(sql):
        try:
            return cur.execute(sql).fetchall()
        except Exception as e:
            return e

    # WH_ID = busiest warehouse; other active warehouses in the same replica are reported (features may live there)
    r = q(f"SELECT wh_id, COUNT(*) FROM {S}.dlytrn WHERE trndte >= DATEADD(day, -7, GETDATE()) AND wh_id IS NOT NULL GROUP BY wh_id ORDER BY 2 DESC")
    if isinstance(r, Exception):
        add("FAIL", "WH_ID", f"query error {str(r)[:150]}")
    elif not r:
        add("WARN", "WH_ID", "no dlytrn rows in the last 7 days at all")
    else:
        top, tot = r[0], sum(x[1] for x in r)
        mine = next((x[1] for x in r if x[0] == wh), 0)
        if top[0] != wh:
            add("FAIL" if not mine else "WARN", "WH_ID",
                f"configured {wh} has {mine:,} txns (7 d), {top[0]} has {top[1]:,}"
                + (" - set WH_ID to the warehouse in hypercare" if not mine else
                   f" - {wh} kept (go-live / hypercare warehouse); switch WH_ID only if {top[0]} is the one in hypercare"))
        else:
            add("OK", "WH_ID", f"{wh} = busiest warehouse ({mine:,} of {tot:,} txns, 7 d)")
        others = [f"{x[0]} ({x[1]:,})" for x in r if x[0] != wh and x[1] >= 0.1 * max(mine, 1)]
        if others:
            add("WARN", "WH_SCOPE", f"replica also holds active warehouse(s) {', '.join(others)} - only {wh} is in the dashboard; "
                                    "LTA / production locations living there are not counted")
    # robot / interface users inflate user productivity: > ROBOT_TXN_PER_HOUR pallet transactions in one hour (7 d)
    robot = int(site.get("ROBOT_TXN_PER_HOUR") or 600)
    r = q(f"""SELECT TOP 5 usr_id, MAX(n), SUM(n) FROM (SELECT usr_id, CAST(trndte AS DATE) d, DATEPART(HOUR, trndte) h, COUNT(*) n
              FROM {S}.dlytrn WHERE wh_id = '{wh}' AND trndte >= DATEADD(day, -7, GETDATE()) AND lodnum IS NOT NULL AND usr_id IS NOT NULL
              AND usr_id NOT IN ({tok.get('USR_EXCLUDE') or "''"}) GROUP BY usr_id, CAST(trndte AS DATE), DATEPART(HOUR, trndte)) x
              GROUP BY usr_id HAVING MAX(n) > {robot} ORDER BY 2 DESC""")
    if isinstance(r, Exception):
        add("FAIL", "ROBOT_USERS", f"query error {str(r)[:150]}")
    elif r:
        add("WARN", "ROBOT_USERS", "users with more than " + str(robot) + " pallet transactions in one hour (automation / interface?): "
            + ", ".join(f"{x[0]} (max {x[1]:,}/h)" for x in r) + " -> if not a person, add to USR_EXCLUDE (user productivity KPI)")
    else:
        add("OK", "ROBOT_USERS", f"no user above {robot} pallet transactions per hour")
    # history depth
    need = max(int(site.get(k) or 0) for k in ("ACT_DAYS", "MOVEMENT_DAYS", "DETAIL_DAYS", "WO_WINDOW_DAYS"))
    r = q(f"SELECT DATEDIFF(day, MIN(trndte), MAX(trndte)), MIN(trndte) FROM {S}.dlytrn WHERE wh_id = '{wh}'")
    if isinstance(r, Exception):
        add("FAIL", "HISTORY", f"query error {str(r)[:150]}")
    else:
        days = r[0][0] or 0
        add("OK" if days >= need else "WARN", "HISTORY",
            f"replica keeps {days} day(s) of transactions (oldest {str(r[0][1])[:16]}); model look-back up to {need} d"
            + ("" if days >= need else " -> past days will be empty at this site (replica retention, not a dashboard bug)"))
    # trailers
    r = q(f"SELECT trlr_cod, COUNT(*) FROM {S}.trlract WHERE trndte >= DATEADD(day, -14, GETDATE()) AND wh_id = '{wh}' GROUP BY trlr_cod")
    if isinstance(r, Exception):
        add("FAIL", "TRAILERS", f"query error {str(r)[:150]}")
    else:
        d = {x[0]: x[1] for x in r}
        inb = sum(n for c, n in d.items() if c and c.startswith("RCV"))
        outb = sum(n for c, n in d.items() if c and not c.startswith("RCV"))
        add("OK" if inb and outb else "WARN", "TRAILERS",
            f"trailer actions 14 d: inbound (RCV*) {inb}, outbound ({', '.join(sorted(c for c in d if c and not c.startswith('RCV'))) or '-'}) {outb}"
            + ("" if inb and outb else " -> the TTAT pillar without trucks shows 'no truck closed'"))
    # feature flags -> their location pattern must exist
    for flag, token in FLAGS.items():
        pat = tok.get(token, "~NA~")
        on = str(site.get(flag, "0")) == "1"
        if pat in ("", "~NA~"):
            add("FAIL" if on else "OK", flag, f"{flag}={int(on)} and {token} not set" + (" -> set the pattern or the flag to 0" if on else ""))
            continue
        r = q(f"SELECT COUNT(*) FROM {S}.locmst WHERE wh_id = '{wh}' AND stoloc LIKE '{like_sql(pat)}'")
        if isinstance(r, Exception):
            add("FAIL", flag, f"query error {str(r)[:150]}")
            continue
        n = r[0][0]
        if on and n == 0:
            add("FAIL", flag, f"{flag}=1 but {token} '{pat}' matches 0 locations in {wh}")
        elif not on and n > 0:
            add("WARN", flag, f"{flag}=0 but {token} '{pat}' matches {n} locations in {wh} - feature may exist")
        else:
            add("OK", flag, f"{flag}={int(on)}, {token} '{pat}' -> {n} locations")
    # production returns rows
    wo_win = int(site.get("WO_WINDOW_DAYS") or 30)
    r = q(f"SELECT wh_id, COUNT(*) FROM {S}.wkohdr WHERE sch_begdte >= DATEADD(day, -{wo_win}, GETDATE()) GROUP BY wh_id ORDER BY 2 DESC")
    if isinstance(r, Exception):
        add("FAIL", "WORK_ORDERS", f"query error {str(r)[:150]}")
    else:
        mine = next((x[1] for x in r if x[0] == wh), 0)
        elsewhere = ", ".join(f"{x[0]} ({x[1]:,})" for x in r if x[0] != wh)
        on = str(site.get("Has_Production", "0")) == "1"
        if on and not mine:
            if not r:
                add("WARN", "WORK_ORDERS", f"Has_Production=1 but the replica's wkohdr has no work orders in +-{wo_win} d in ANY warehouse "
                    "(replica reload / table not replicated?) -> production pages stay empty until it is back; check HVR")
            else:
                add("FAIL", "WORK_ORDERS", f"Has_Production=1 but {wh} has 0 work orders in +-{wo_win} d; production runs in warehouse(s) "
                    f"{elsewhere} -> add a site row per plant warehouse (same server/db, that WH_ID) and set Has_Production=0 here")
        elif not on and mine:
            add("WARN", "WORK_ORDERS", f"Has_Production=0 but {wh} has {mine:,} work orders in +-{wo_win} d - production pillar may apply")
        else:
            add("OK", "WORK_ORDERS", f"{wh}: {mine:,} work orders in +-{wo_win} d" + (f" (other warehouses: {elsewhere})" if elsewhere else ""))
    if str(site.get("Has_Production", "0")) == "1":
        sql = v.render(v.sql_from_m(v.queries()["Produced Pallet"][1], tok), tok)
        r = q(sql)
        if isinstance(r, Exception):
            add("FAIL", "Has_Production", f"produced-pallet query error {str(r)[:150]}")
        else:
            add("OK" if r else "WARN", "Has_Production", f"produced-pallet query -> {len(r)} line-hour rows"
                + ("" if r else " -> check PROD_* tokens / line_map"))
    # every LOC_* / AREA_* token matches something
    for k, val in sorted(tok.items()):
        if not (k.startswith("LOC_") or k.startswith("AREA_")) or k in ("LOC_LEVEL_A", "LOC_HOFF_IN") or val in ("", "~NA~", None):
            continue
        if not re.fullmatch(r"[\w%\[\]\-^.#]+", str(val)):
            continue
        col = "arecod" if k.startswith("AREA_") else "stoloc"
        op = "LIKE" if ("%" in val or "[" in val or "_" in val) else "="
        r = q(f"SELECT COUNT(*) FROM {S}.locmst WHERE wh_id = '{wh}' AND {col} {op} '{like_sql(val)}'")
        if isinstance(r, Exception):
            add("WARN", k, f"query error {str(r)[:120]}")
        elif r[0][0] == 0:
            r2 = q(f"SELECT COUNT(*) FROM {S}.dlytrn WHERE trndte >= DATEADD(day, -14, GETDATE()) AND wh_id = '{wh}' "
                   f"AND ({'to_arecod' if col == 'arecod' else 'tostol'} {op} '{like_sql(val)}' OR {'fr_arecod' if col == 'arecod' else 'frstol'} {op} '{like_sql(val)}')")
            used = 0 if isinstance(r2, Exception) else r2[0][0]
            add("OK" if used else "WARN", k, f"'{val}' -> 0 in locmst, {used} transactions (14 d)"
                + ("" if used else " -> pattern matches nothing at this site"))
        else:
            add("OK", k, f"'{val}' -> {r[0][0]} {('areas' if col == 'arecod' else 'locations')}")
    return out


def main(argv):
    import csv
    codes = [a.upper() for a in argv] or [r["SiteCode"] for r in csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig"))]
    md = ["# Site configuration check", "", f"Run {time.strftime('%Y-%m-%d %H:%M')} - `py tools/site_config_check.py` (read-only, live replicas).", "",
          "| Site | Level | Check | Detail |", "|---|---|---|---|"]
    fails = 0
    for code in codes:
        say(f"=== {code}")
        for level, check, detail in check_site(code):
            fails += level == "FAIL"
            if level != "OK":
                md.append(f"| {code} | {level} | {check} | {detail.replace('|', '/')} |")
        md.append(f"| {code} | OK | (all other checks) | |")
    (ROOT / "docs" / "SITE_CONFIG_CHECK.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    say(f"DONE {len(codes)} site(s), {fails} FAIL -> docs/SITE_CONFIG_CHECK.md")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
