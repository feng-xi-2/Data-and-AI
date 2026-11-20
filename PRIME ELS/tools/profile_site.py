"""Auto-profile the technical settings of a PrIME 2014 / 2022 site from its data replica (read-only).

    py tools/profile_site.py SITE                      # site already in config/site_config.csv (server / db / wh from there)
    py tools/profile_site.py SITE --server S --db D [--wh WH] [--version "PrIME 2022"]
    py tools/profile_site.py SITE --compare            # regression: proposal vs the confirmed config row
    py tools/profile_site.py SITE --write              # fill the config row (only cells that are blank / NEW, --force = all)

Every proposal carries a confidence (HIGH / MED / LOW) and the evidence it is based on.
Weak evidence switches a feature OFF (~NA~) - a missing feature shows 'not configured', never a wrong number.
Rules are generic (no site names); production-model token templates come from config/production_models.csv.
"""
import sys, os, csv, json, argparse, datetime, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CFG = os.path.join(ROOT, "config")
NA = "~NA~"
DAYS = 14
MIN_PROD_PALLETS = 10          # presence of a production flow (low-volume / ramp-up sites count too)
MIN_LEVELA_PICKS = 20
MIN_LEVELA_SHARE = 0.05
MIN_HISTORY_H = 72             # less operational history than this = site not live yet: absent features are 'confirm', not OFF
MIN_MOVES = 5                  # a location feature is 'in use' from this many moves
ROBOT_TXN_PER_HOUR = 600
BASE_USR_EXCLUDE = ["SUPER", "NOUSER"]


def hb(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def read_csv(name):
    with open(os.path.join(CFG, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Profiler:
    def __init__(self, cur, sch, wh):
        self.cur, self.S, self.wh = cur, sch, wh
        self.out = {}

    def q(self, title, sql):
        hb(f"  query: {title}")
        try:
            return [tuple(r) for r in self.cur.execute(sql).fetchall()]
        except Exception as e:                                   # report, never hide
            hb(f"  ERROR in '{title}': {repr(e)[:200]}")
            return None

    def put(self, col, val, conf, ev):
        self.out[col] = {"value": val, "confidence": conf, "evidence": ev}

    def since(self, days=DAYS):
        return f"DATEADD(day, -{days}, (SELECT MAX(trndte) FROM {self.S}.dlytrn))"

    # ---- rules -------------------------------------------------------------------------------------------------
    def r_production(self):
        S, wh = self.S, self.wh
        wo = self.q("work-order receipts", f"SELECT COUNT(DISTINCT d.lodnum) FROM {S}.dlytrn d WHERE d.trndte >= {self.since()} AND d.wh_id = '{wh}' "
                    f"AND d.actcod = 'RCV' AND d.oprcod = 'UID' AND EXISTS (SELECT 1 FROM {S}.wkohdr w WHERE w.wkonum = d.frstol AND w.wh_id = d.wh_id)")
        lt = self.q("LT locations", f"SELECT CASE WHEN stoloc LIKE 'LTA%' THEN 'LTA%' ELSE 'LT%' END p, COUNT(*) FROM {S}.locmst WHERE wh_id = '{wh}' AND stoloc LIKE 'LT%' GROUP BY CASE WHEN stoloc LIKE 'LTA%' THEN 'LTA%' ELSE 'LT%' END")
        lt = dict(lt or [])
        lta_pat = "LTA%" if lt.get("LTA%") and not lt.get("LT%") else ("LT%" if lt else None)
        lta_n = 0
        if lta_pat:
            r = self.q("pallets leaving LT locations", f"SELECT COUNT(DISTINCT d.lodnum) FROM {S}.dlytrn d WHERE d.trndte >= {self.since()} AND d.wh_id = '{wh}' AND d.frstol LIKE '{lta_pat}'")
            lta_n = r[0][0] if r else 0
        wo_n = wo[0][0] if wo else 0
        models = {m["Model"]: m for m in read_csv("production_models.csv")}
        ev = f"{DAYS} d: {wo_n:,} pallets received from work orders; {lta_n:,} pallets left {lta_pat or 'no LT'} locations"
        if max(wo_n, lta_n) < MIN_PROD_PALLETS:
            self.put("Has_Production", "0", "MED", ev + f" (< {MIN_PROD_PALLETS}: no production in PrIME)")
            model = models["LTA"]
            conf = "LOW"
        else:
            self.put("Has_Production", "1", "HIGH", ev)
            model = models["WO"] if wo_n >= lta_n else models["LTA"]
            conf = "HIGH" if min(wo_n, lta_n) < 0.2 * max(wo_n, lta_n) else "MED"
        for c in ("PROD_TXN_FILTER", "PROD_SRC_EXPR", "PROD_SCOPE", "PROD_ARRIVED_COND", "PROD_LEFT_COND", "OPR_LTA_STORE", "Prod_Model"):
            self.put(c, model[c], conf, f"model {model['Model']} (template = {model['Template_Site']}); " + ev)
        self.put("LOC_LTA", lta_pat if lta_n >= MIN_PROD_PALLETS else NA, "HIGH" if lta_n >= MIN_PROD_PALLETS or not lt else "MED",
                 f"locmst LT locations {lt or 'none'}; {lta_n:,} pallets moved out in {DAYS} d")
        sup = self.q("PL supply locations", f"SELECT COUNT(DISTINCT d.lodnum) FROM {S}.dlytrn d WHERE d.trndte >= {self.since()} AND d.wh_id = '{wh}' AND d.tostol LIKE 'PL%'")
        n = sup[0][0] if sup else 0
        m = self.in_master("PL%")
        self.put("LOC_PROD_SUPPLY", "PL%" if n >= MIN_MOVES or (m and self.out["Has_Production"]["value"] == "1") else NA, "HIGH" if n >= MIN_MOVES else "MED",
                 f"{n:,} pallets moved to PL% (line supply) in {DAYS} d; {m:,} PL% locations in locmst")

    def r_level_a(self):
        S, wh = self.S, self.wh
        rows = self.q("pick areas x level A", f"SELECT TOP 5 srcare, COUNT(*) n, SUM(CASE WHEN RIGHT(srcloc, 1) = 'A' THEN 1 ELSE 0 END) a FROM {S}.pckwrk_view "
                      f"WHERE wh_id = '{wh}' AND last_upd_dt >= DATEADD(day, -{DAYS}, GETDATE()) GROUP BY srcare ORDER BY a DESC")
        if not rows or rows[0][2] < MIN_LEVELA_PICKS or rows[0][2] < MIN_LEVELA_SHARE * rows[0][1]:
            ev = f"best area {rows[0] if rows else 'none'}: picks from locations ending 'A' below {MIN_LEVELA_PICKS} / {MIN_LEVELA_SHARE:.0%}"
            self.put("Has_LevelA", "0", "MED", ev); self.put("LOC_LEVEL_A", NA, "MED", ev); self.put("AREA_LEVEL_A_PICK", NA, "MED", ev)
            return
        area, n, a = rows[0]
        ch = self.q("level A location prefix", f"SELECT LEFT(srcloc, 1), SUBSTRING(srcloc, 2, 1), COUNT(*) FROM {S}.pckwrk_view WHERE wh_id = '{wh}' AND srcare = '{area}' "
                    f"AND RIGHT(srcloc, 1) = 'A' AND last_upd_dt >= DATEADD(day, -{DAYS}, GETDATE()) GROUP BY LEFT(srcloc, 1), SUBSTRING(srcloc, 2, 1)") or []
        tot = sum(r[2] for r in ch) or 1
        def dom(i):
            agg = {}
            for r in ch: agg[r[i]] = agg.get(r[i], 0) + r[2]
            k, v = max(agg.items(), key=lambda kv: kv[1]) if agg else ("_", 0)
            return k if v >= 0.8 * tot else "_"
        c1, c2 = dom(0), dom(1)
        pat = (c1 + c2 + "%A") if c2 != "_" else (c1 + "%A" if c1 != "_" else "%A")
        ev = f"area {area}: {a:,} of {n:,} picks ({a / n:.0%}) from locations ending 'A' in {DAYS} d; first 2 chars {sorted(ch, key=lambda x: -x[2])[:4]}"
        self.put("Has_LevelA", "1", "HIGH", ev); self.put("AREA_LEVEL_A_PICK", area, "HIGH", ev); self.put("LOC_LEVEL_A", pat, "MED", ev)

    def moved(self, like, col="tostol"):
        r = self.q(f"moves {col} LIKE {like}", f"SELECT COUNT(*) FROM {self.S}.dlytrn WHERE trndte >= {self.since()} AND wh_id = '{self.wh}' AND {col} LIKE '{like}'")
        return r[0][0] if r else 0

    def r_hoff(self):
        S, wh = self.S, self.wh
        n_in, n_out = self.moved("HO%IN"), self.moved("HO%OUT", "frstol")
        if n_in >= MIN_MOVES and n_out >= MIN_MOVES:
            ev = f"{n_in:,} moves into HO%IN, {n_out:,} out of HO%OUT in {DAYS} d"
            self.put("Has_HOFF", "1", "HIGH", ev); self.put("LOC_HOFF_IN", "HO%IN", "HIGH", ev); self.put("LOC_HOFF_OUT", "HO%OUT", "HIGH", ev)
            return
        pairs = self.q("-IN / -OUT location pairs", f"SELECT TOP 5 LEFT(i.stoloc, LEN(i.stoloc) - 3) p, COUNT(*) FROM {S}.dlytrn d JOIN {S}.locmst i ON i.stoloc = d.tostol AND i.wh_id = d.wh_id "
                       f"WHERE d.trndte >= {self.since()} AND d.wh_id = '{wh}' AND i.stoloc LIKE '%-IN' AND EXISTS (SELECT 1 FROM {S}.locmst o WHERE o.wh_id = i.wh_id AND o.stoloc = LEFT(i.stoloc, LEN(i.stoloc) - 3) + '-OUT') "
                       f"GROUP BY LEFT(i.stoloc, LEN(i.stoloc) - 3) ORDER BY 2 DESC") or []
        if pairs and pairs[0][1] >= MIN_MOVES:
            p, k = pairs[0]
            ev = f"{k:,} moves into {p}-IN (paired {p}-OUT exists) in {DAYS} d; HO%IN {n_in:,}"
            self.put("Has_HOFF", "1", "MED", ev); self.put("LOC_HOFF_IN", p + "-IN", "MED", ev); self.put("LOC_HOFF_OUT", p + "-OUT", "MED", ev)
            return
        ev = f"no hand-off lane with >= {MIN_MOVES} moves (HO%IN {n_in:,}, -IN pairs {pairs[:2]})"
        self.put("Has_HOFF", "0", "MED", ev); self.put("LOC_HOFF_IN", NA, "MED", ev); self.put("LOC_HOFF_OUT", NA, "MED", ev)

    def in_master(self, like):
        r = self.q(f"locmst LIKE {like}", f"SELECT COUNT(*) FROM {self.S}.locmst WHERE wh_id = '{self.wh}' AND stoloc LIKE '{like}'")
        return r[0][0] if r else 0

    def best_pattern(self, col, cands, title, min_n=1):
        best, bn, seen = NA, 0, {}
        for p in cands:
            n = self.moved(p, col); seen[p] = n
            if n > bn: best, bn = p, n
        return (best if bn >= min_n else NA), bn, seen

    def r_locations(self):
        p, n, seen = self.best_pattern("tostol", ["PROB%", "PRBL%"], "problem")
        master = {c: self.in_master(c) for c in ("PROB%", "PRBL%")}
        if p == NA and max(master.values()):
            p = max(master, key=master.get)
        self.put("LOC_PROBLEM", p, "HIGH" if n >= MIN_MOVES else "MED", f"moves into problem locations in {DAYS} d: {seen}; locations in locmst: {master}")
        p, n, seen = self.best_pattern("tostol", ["RTN%", "RER%", "%RET%"], "return")
        self.put("LOC_RETURN", p, "MED", f"moves into return locations in {DAYS} d: {seen}")
        r = self.q("RDT areas", f"SELECT TOP 3 to_arecod, COUNT(*) FROM {self.S}.dlytrn WHERE trndte >= {self.since()} AND wh_id = '{self.wh}' AND to_arecod LIKE 'RDT%' GROUP BY to_arecod ORDER BY 2 DESC") or []
        r = self.q("RDT areas", f"SELECT TOP 8 fr_arecod, COUNT(*) FROM {self.S}.dlytrn WHERE trndte >= {self.since()} AND wh_id = '{self.wh}' AND fr_arecod LIKE 'RDT%' GROUP BY fr_arecod ORDER BY 2 DESC") or r
        used = [x[0] for x in r if x[0] and x[1] >= 0.01 * r[0][1]]
        if len(used) > 1:                                        # several RF areas carry pallets -> LIKE pattern on their common prefix
            pre = os.path.commonprefix(used).rstrip("0123456789")
            val, conf = (pre + "%", "HIGH") if len(pre) >= 3 else (r[0][0], "MED")
        else:
            val, conf = (r[0][0], "HIGH") if r else (NA, "MED")
        self.put("AREA_RDTS", val, conf, f"pallet moves out of RDT (RF device) areas in {DAYS} d: {r}")
        r = self.q("receiving areas", f"SELECT TOP 5 to_arecod, COUNT(*) FROM {self.S}.dlytrn WHERE trndte >= {self.since()} AND wh_id = '{self.wh}' AND actcod IN ('RCV','ASN_TRUST','ASN_NONTRUST') GROUP BY to_arecod ORDER BY 2 DESC") or []
        rc = [x for x in r if (x[0] or "").startswith("RCST")]
        other = [x for x in r if x[0] and not x[0].startswith("RDT")]           # RDT = forklift / RF device area, not a stage
        stage = "RCST%" if rc else (other[0][0] if other else NA)
        self.put("AREA_RCV_STAGE", stage, "HIGH" if rc else "LOW", f"areas receiving pallets in {DAYS} d: {r}")
        self.put("AREA_RCV_DOCK", "RCST%" if rc else NA, "MED", f"RCST areas used: {[x[0] for x in rc]}")
        # door locations that pallets are moved (UTR) onto before loading - used by Shipped Pallet (LOAD step)
        seen = {c: self.moved(c) for c in ("C[0-9][0-9][0-9]", "DOOR%")}
        master = {c: self.in_master(c) for c in seen}
        best = max(seen, key=seen.get)
        if seen[best] >= MIN_MOVES:
            pat, conf = best, "HIGH"
        elif max(master.values()):
            pat, conf = max(master, key=master.get), "MED"
        else:
            pat, conf = NA, "MED"
        self.put("LOC_DOOR_PATTERN", pat, conf, f"moves onto door locations in {DAYS} d: {seen}; door locations in locmst: {master}")

    def r_fg_prtnum(self):
        S, wh = self.S, self.wh
        src = [(f"parts loaded on trailers ({DAYS} d)", f"SELECT LEFT(prtnum, 1), COUNT(*) FROM {S}.dlytrn WHERE trndte >= {self.since()} AND wh_id = '{wh}' AND tostol LIKE 'TRL%' AND prtnum IS NOT NULL GROUP BY LEFT(prtnum, 1) ORDER BY 2 DESC", "HIGH"),
               ("parts made on work orders (wkohdr, 90 d)", f"SELECT LEFT(prtnum, 1), COUNT(*) FROM {S}.wkohdr WHERE wh_id = '{wh}' AND sch_begdte >= DATEADD(day, -90, GETDATE()) AND prtnum IS NOT NULL GROUP BY LEFT(prtnum, 1) ORDER BY 2 DESC", "MED"),
               ("parts in inventory (includes materials)", f"SELECT LEFT(prtnum, 1), COUNT(*) FROM {S}.inventory_view GROUP BY LEFT(prtnum, 1) ORDER BY 2 DESC", "LOW")]
        r, title, base = [], "none", "LOW"
        for title, sql, base in src:
            r = self.q(title, sql) or []
            if sum(x[1] for x in r) >= MIN_PROD_PALLETS:
                break
        tot = sum(x[1] for x in r)
        keep = sorted(x[0] for x in r if tot and x[1] >= 0.05 * tot and x[0])
        pat = (keep[0] + "%" if len(keep) == 1 else "[" + "".join(keep) + "]%") if keep else NA
        conf = base if keep and sum(x[1] for x in r if x[0] in keep) >= 0.95 * tot else ("MED" if base == "HIGH" else "LOW")
        self.put("FG_PRTNUM_LIKE", pat, conf, f"first character of {title}: {r[:6]}")

    def r_locale(self):
        r = self.q("part description locales", f"SELECT TOP 3 locale_id, COUNT(*) FROM {self.S}.prtdsc GROUP BY locale_id ORDER BY 2 DESC") or []
        en = dict(r).get("US_ENGLISH", 0)
        pick = "US_ENGLISH" if r and en >= 0.9 * r[0][1] else (r[0][0] if r else "US_ENGLISH")
        tie = len(r) > 1 and r[1][1] >= 0.9 * r[0][1] and pick != "US_ENGLISH"
        self.put("PRTDSC_LOCALE", pick, "LOW" if not r or tie else "HIGH", f"prtdsc rows by locale (US_ENGLISH preferred when it covers >= 90%): {r}")

    def r_users(self):
        r = self.q("robot-speed users", f"SELECT TOP 10 usr_id, MAX(n) FROM (SELECT usr_id, CONVERT(date, trndte) dd, DATEPART(hour, trndte) hh, COUNT(*) n FROM {self.S}.dlytrn "
                   f"WHERE trndte >= {self.since(7)} AND wh_id = '{self.wh}' AND lodnum IS NOT NULL AND usr_id IS NOT NULL GROUP BY usr_id, CONVERT(date, trndte), DATEPART(hour, trndte)) x GROUP BY usr_id HAVING MAX(n) > {ROBOT_TXN_PER_HOUR} ORDER BY 2 DESC") or []
        bots = [u for u, n in r if u and n > 5 * ROBOT_TXN_PER_HOUR and u not in BASE_USR_EXCLUDE]   # no person scans > 50 per minute
        self.put("USR_EXCLUDE", ",".join(f"'{u}'" for u in BASE_USR_EXCLUDE + bots), "MED",
                 f"system users + interfaces above {5 * ROBOT_TXN_PER_HOUR}/h {bots}; ask the site about users above {ROBOT_TXN_PER_HOUR} pallet transactions/h in 7 d: {r}")

    def run(self):
        for rule in (self.r_production, self.r_level_a, self.r_hoff, self.r_locations, self.r_fg_prtnum, self.r_locale, self.r_users):
            hb(f"rule {rule.__name__[2:]}")
            try:
                rule()
            except Exception as e:
                hb(f"  RULE FAILED {rule.__name__}: {repr(e)[:200]}")
        return self.out


def static_defaults(site, peer):
    """Settings that are the same for every site (taken from the default site row) or follow a naming rule."""
    out = {}
    for c in ("TALL_HEIGHT_CM", "LOC_TRAILER", "ROBOT_TXN_PER_HOUR", "WO_WINDOW_DAYS", "MOVEMENT_DAYS", "DETAIL_DAYS", "ACT_DAYS", "CAL_FUTURE_DAYS",
              "Databricks_Host", "Databricks_HttpPath", "RPM_VendorList_Sheet"):
        out[c] = {"value": peer[c], "confidence": "HIGH", "evidence": "same for all sites (default site row)"}
    for c in ("LOC_PROD_CHECKIN", "CTMZ_LINE", "LOC_EOL", "LOC_EOL_EXACT"):
        out[c] = {"value": NA, "confidence": "LOW", "evidence": "site-specific line feature - OFF until the site confirms"}
    for c in ("ZONES_EXCL_PICK", "ZONES_EXCL_BIN"):
        out[c] = {"value": f"'{NA}'", "confidence": "LOW", "evidence": "zones to exclude need site knowledge - none excluded until confirmed"}
    out["Has_SAP_Plan"] = {"value": "0", "confidence": "LOW", "evidence": "SAP plan feed is per-site - OFF until confirmed"}
    out["Has_RPM_Master"] = {"value": "0", "confidence": "LOW", "evidence": "RPM master files are per-site - OFF until provided"}
    out["SAP_PALLET_UOM"] = {"value": "A1" if site.get("SAP_Plant") else "", "confidence": "LOW", "evidence": "most sites use A1 - confirm in SAP"}
    out["Has_SAP_Prod"] = {"value": "1" if site.get("SAP_Plant") else "0", "confidence": "HIGH", "evidence": "SAP_Plant given in the inputs file" if site.get("SAP_Plant") else "no SAP_Plant"}
    out["Gateway_Connection"] = {"value": f"MI-{site['ReplicaDatabase']}-PROD-FULL-PaaS-ADHOC", "confidence": "MED", "evidence": "gateway naming rule MI-<database>-PROD-FULL-PaaS-ADHOC"}
    try:
        out["ShiftDay_Start_Min"] = {"value": str(int(float(site["Shift1_Start"])) * 60), "confidence": "LOW", "evidence": "Shift1_Start x 60 min - confirm the exact minute the report day starts"}
    except (KeyError, ValueError):
        pass
    return out


def profile(code, server=None, db=None, wh=None, version=None):
    from probe_replica_schema import connect
    rows = {r["SiteCode"]: r for r in read_csv("site_config.csv")}
    site = dict(rows.get(code) or {})
    server = server or site.get("ReplicaServer"); db = db or site.get("ReplicaDatabase")
    if not server or not db:
        raise SystemExit(f"{code}: no ReplicaServer / ReplicaDatabase (add the site to the inputs file or pass --server / --db)")
    site.update({"ReplicaServer": server, "ReplicaDatabase": db})
    hb(f"{code}: connecting {server} / {db}")
    cn = connect(server, db); cn.timeout = 110; cur = cn.cursor()
    sch = cur.execute("SELECT TOP 1 s.name FROM sys.objects o JOIN sys.schemas s ON s.schema_id = o.schema_id WHERE o.name = 'dlytrn' ORDER BY CASE s.name WHEN 'prodwms' THEN 0 ELSE 1 END").fetchone()
    if not sch:
        raise SystemExit(f"{code}: dlytrn not found - not a PrIME replica")
    sch = sch[0]
    eng = "PrIME 2014" if sch.lower() == "prodwms" else "PrIME 2022"
    out = {"WMS_Version": {"value": eng, "confidence": "HIGH", "evidence": f"dlytrn is in schema {sch}"}}
    if version and version != eng:
        out["WMS_Version"]["confidence"] = "CHECK"; out["WMS_Version"]["evidence"] += f" but the inputs file says {version}"
    whs = cur.execute(f"SELECT TOP 3 wh_id, COUNT(*) FROM {sch}.dlytrn WHERE trndte >= DATEADD(day, -{DAYS}, (SELECT MAX(trndte) FROM {sch}.dlytrn)) GROUP BY wh_id ORDER BY 2 DESC").fetchall()
    best = whs[0][0] if whs else None
    wh = wh or site.get("WH_ID") or best
    out["WH_ID"] = {"value": wh, "confidence": "HIGH" if wh == best else "CHECK", "evidence": f"most active warehouses in dlytrn: {[tuple(x) for x in whs]}"}
    last = cur.execute(f"SELECT MAX(trndte), GETUTCDATE() FROM {sch}.dlytrn WHERE wh_id = '{wh}'").fetchone()
    if last and last[0]:
        off = round((last[0] - last[1]).total_seconds() / 3600)
        out["UTC_Offset_h (hint)"] = {"value": str(off), "confidence": "LOW", "evidence": f"newest transaction {last[0]} vs UTC {last[1]:%Y-%m-%d %H:%M} (replica lag lowers it)"}
    peer = next((r for r in rows.values() if r.get("Is_Default") == "1"), next(iter(rows.values())))
    out.update(static_defaults(site, peer))
    span = cur.execute(f"SELECT MIN(trndte), MAX(trndte) FROM {sch}.dlytrn WHERE wh_id = '{wh}' AND trndte >= DATEADD(day, -{DAYS}, (SELECT MAX(trndte) FROM {sch}.dlytrn))").fetchone()
    hours = round((span[1] - span[0]).total_seconds() / 3600, 1) if span and span[0] else 0
    out["History_h (info)"] = {"value": str(hours), "confidence": "HIGH" if hours >= MIN_HISTORY_H else "CHECK", "evidence": f"dlytrn activity {span[0]} -> {span[1]} in the last {DAYS} d window"}
    prof = Profiler(cur, sch, wh).run()
    if hours < MIN_HISTORY_H:                                    # site not live: absence of evidence is not evidence of absence
        for k, v in prof.items():
            if v["value"] in (NA, "0") or str(v["value"]).startswith("~"):
                v["confidence"] = "LOW"
                v["evidence"] += f" | only {hours} h of history - keep the peer default and re-profile after go-live"
    out.update(prof)
    return site, out


COMPARE_SKIP = {"UTC_Offset_h (hint)", "History_h (info)"}


def norm(v):
    return re.sub(r"\s+", " ", (v or "").strip().replace("'", "")).upper()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("site"); ap.add_argument("--server"); ap.add_argument("--db"); ap.add_argument("--wh"); ap.add_argument("--version")
    ap.add_argument("--compare", action="store_true"); ap.add_argument("--write", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    site, out = profile(a.site, a.server, a.db, a.wh, a.version)
    print(f"\n=== {a.site} proposal ({len(out)} settings) ===")
    for k, v in out.items():
        print(f"  {k:22s} {v['confidence']:5s} {str(v['value'])[:60]:60s} | {v['evidence'][:150]}")
    js = a.json or os.path.join(ROOT, "docs", f"profile_{a.site}.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"site": a.site, "generated": datetime.datetime.now().isoformat(timespec="seconds"), "proposal": out}, f, indent=1, default=str)
    hb(f"proposal saved: {js}")
    if a.compare:
        same = diff = 0
        confirm = []
        print(f"\n=== {a.site} proposal vs confirmed config ===")
        for k, v in out.items():
            if k in COMPARE_SKIP or k not in site:
                continue
            ok = norm(str(v["value"])) == norm(site[k])
            if v["confidence"] == "LOW":
                if not ok:
                    confirm.append(k)
                continue
            same += ok; diff += not ok
            if not ok:
                print(f"  DIFF {k:22s} {v['confidence']:4s} proposed={str(v['value'])[:50]!r:53s} config={site[k][:50]!r}")
                print(f"       evidence: {v['evidence'][:170]}")
        print(f"  {a.site}: {same} same, {diff} different on evidence-based settings ({same / max(1, same + diff):.0%} agreement); "
              f"site-input settings differing (LOW, expected): {confirm}")
    if a.write:
        rows = read_csv("site_config.csv"); cols = list(rows[0].keys())
        row = next((r for r in rows if r["SiteCode"] == a.site), None)
        if row is None:
            raise SystemExit(f"{a.site} is not in config/site_config.csv - run py tools/apply_inputs.py --apply first")
        new = (row.get("Config_Status") or "").startswith("NEW") or a.force
        n = 0
        for k, v in out.items():
            if k in cols and v["value"] is not None and (not row.get(k) or (new and v["confidence"] != "LOW") or (a.force and v["confidence"] != "LOW")):
                row[k] = str(v["value"]); n += 1
        low = sorted(k for k, v in out.items() if v["confidence"] in ("LOW", "CHECK"))
        row["Config_Status"] = "AUTO-PROFILED - confirm with site"
        row["Notes"] = (f"{row.get('WMS_Version')} ({'prodwms' if row.get('WMS_Version') == 'PrIME 2014' else 'dbo'}), wh {row.get('WH_ID')}. "
                        f"Auto-profiled {datetime.date.today()} by tools/profile_site.py (docs/profile_{a.site}.json). Confirm: {', '.join(low)}")
        with open(os.path.join(CFG, "site_config.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(rows)
        hb(f"{a.site}: {n} settings written to config/site_config.csv (Config_Status = AUTO-PROFILED)")


if __name__ == "__main__":
    main(sys.argv[1:])
