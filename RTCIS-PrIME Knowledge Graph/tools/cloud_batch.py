"""Cloud benchmark through the live API (same path as the UI): NL questions on all three engines + RTCIS -> PrIME 2022
conversions of the real R-query sources, every result validated on the replica. Writes benchmark/cloud_batch_results.json.
    python tools/cloud_batch.py [max_conversions]"""
import json
import os
import sys
import time
import urllib.request

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API = os.environ.get("KG_API", "http://127.0.0.1:8738")
QUESTIONS = [
    ("PrIME2022", "PRIME22_DE08", "How many pallets (loads) are stored per location area?"),
    ("PrIME2022", "PRIME22_DE08", "Which parts have no footprint detail?"),
    ("PrIME2022", "PRIME22_DE08", "Count open pick work per wave / pick batch"),
    ("PrIME2022", "PRIME22_DE08", "List the 20 most recent inventory movements with part, quantity and from / to location"),
    ("PrIME2022", "PRIME22_DE08", "How many locations exist per area, and how many of them are empty?"),
    ("PrIME2022", "PRIME22_DE08", "Inventory quantity per part and inventory status"),
    ("PrIME2022", "PRIME22_WMD1", "How many pallets (loads) are stored per location area?"),
    ("PrIME2014", "PRIME14_XQ", "How many pallets (loads) are stored per location area?"),
    ("PrIME2014", "PRIME14_XQ", "Top 20 parts by number of pallets in stock"),
    ("RTCIS", "RTCIS_EUS", "How many unit loads are in each location zone?"),
    ("RTCIS", "RTCIS_EUS", "Top 20 items by number of unit loads in stock"),
] + [("PrIME2022", "PRIME22_DE08", q) for q in (
    "How many shipments are there in each shipment status?",
    "Total picked and shipped quantity per shipment status",
    "How many receiving trucks are there in each receiving status?",
    "Expected versus received quantity per receiving truck status",
    "How many trailers are there in each trailer status?",
    "How many inventory counts were recorded per count type?",
    "Which WCS (warehouse control system) ids are configured for the warehouse?",
)]
# business theme of each question (graph Domain), for the per-theme comparison
THEME = {
    "How many pallets (loads) are stored per location area?": "inventory", "Which parts have no footprint detail?": "master_data",
    "Count open pick work per wave / pick batch": "picking", "List the 20 most recent inventory movements with part, quantity and from / to location": "inventory",
    "How many locations exist per area, and how many of them are empty?": "location", "Inventory quantity per part and inventory status": "inventory",
    "Top 20 parts by number of pallets in stock": "inventory", "How many unit loads are in each location zone?": "location",
    "Top 20 items by number of unit loads in stock": "inventory",
    "How many shipments are there in each shipment status?": "shipment", "Total picked and shipped quantity per shipment status": "outbound",
    "How many receiving trucks are there in each receiving status?": "receiving", "Expected versus received quantity per receiving truck status": "receiving",
    "How many trailers are there in each trailer status?": "trailer", "How many inventory counts were recorded per count type?": "counting",
    "Which WCS (warehouse control system) ids are configured for the warehouse?": "automation",
}
WH = {"PRIME22_DE08": "DE08", "PRIME22_WMD1": "WMD1", "PRIME14_XQ": "CN74"}
_PAL = ("SELECT m.arecod, COUNT(DISTINCT l.lodnum) FROM {s}.invlod l JOIN {s}.locmst m ON m.stoloc = l.stoloc AND m.wh_id = l.wh_id "
        "WHERE l.wh_id = @wh_id GROUP BY m.arecod")
# reference answers (hand-written from the validated join paths; each one is run on its database before scoring)
GOLD = {
    ("PRIME22_DE08", QUESTIONS[0][2]): _PAL.format(s="dbo"),
    ("PRIME22_WMD1", QUESTIONS[0][2]): _PAL.format(s="dbo"),
    ("PRIME14_XQ", QUESTIONS[0][2]): _PAL.format(s="prodwms"),
    ("PRIME22_DE08", "Inventory quantity per part and inventory status"):
        "SELECT d.prtnum, d.invsts, SUM(CAST(d.untqty AS bigint)) FROM dbo.invdtl d JOIN dbo.invsub s ON s.subnum = d.subnum "
        "JOIN dbo.invlod l ON l.lodnum = s.lodnum WHERE l.wh_id = @wh_id GROUP BY d.prtnum, d.invsts",
    ("RTCIS_EUS", "How many unit loads are in each location zone?"):
        "SELECT lc.zoncod, COUNT(DISTINCT u.ulid) FROM [EUSKIRCHEN_simp].live3.unitld u JOIN [EUSKIRCHEN_simp].live3.locatn lc "
        "ON lc.locatn = u.locatn AND lc.subsit = u.subsit GROUP BY lc.zoncod",
    # theme set (each run on DE08 with real rows on 2026-11-21 before it was added)
    ("PRIME22_DE08", "How many shipments are there in each shipment status?"):
        "SELECT shpsts, COUNT(*) FROM dbo.shipment WHERE wh_id = @wh_id GROUP BY shpsts",
    ("PRIME22_DE08", "Total picked and shipped quantity per shipment status"):
        # picked_qty, not pckqty: on DE08 completed shipments have picked_qty 64,268,802 ~ shpqty 64,268,880 and pckqty 0
        # (pckqty = still to pick); the first reference used pckqty and was corrected on 2026-11-21 after checking the data
        "SELECT s.shpsts, SUM(CAST(sl.picked_qty AS bigint)), SUM(CAST(sl.shpqty AS bigint)) FROM dbo.shipment s JOIN dbo.shipment_line sl "
        "ON sl.ship_id = s.ship_id AND sl.wh_id = s.wh_id WHERE s.wh_id = @wh_id GROUP BY s.shpsts",
    ("PRIME22_DE08", "How many receiving trucks are there in each receiving status?"):
        "SELECT rcvtrk_stat, COUNT(*) FROM dbo.rcvtrk WHERE wh_id = @wh_id GROUP BY rcvtrk_stat",
    ("PRIME22_DE08", "Expected versus received quantity per receiving truck status"):
        "SELECT t.rcvtrk_stat, SUM(CAST(l.expqty AS bigint)), SUM(CAST(l.rcvqty AS bigint)) FROM dbo.rcvtrk t JOIN dbo.rcvlin l "
        "ON l.trknum = t.trknum AND l.wh_id = t.wh_id WHERE t.wh_id = @wh_id GROUP BY t.rcvtrk_stat",
    ("PRIME22_DE08", "How many trailers are there in each trailer status?"):
        "SELECT trlr_stat, COUNT(*) FROM dbo.trlr WHERE stoloc_wh_id = @wh_id GROUP BY trlr_stat",
    ("PRIME22_DE08", "How many inventory counts were recorded per count type?"):
        "SELECT cnttyp, COUNT(*) FROM dbo.cnthst WHERE wh_id = @wh_id GROUP BY cnttyp",
    ("PRIME22_DE08", "Which WCS (warehouse control system) ids are configured for the warehouse?"):
        "SELECT wcs_id FROM dbo.wcsmst WHERE wh_id = @wh_id",
}


def score(site, question, model_sql, params):
    """Execution accuracy vs the reference answer, both executed here with a 5000-row cap."""
    gold = GOLD.get((site, question))
    if not gold or not model_sql:
        return None
    import kg_core
    import kg_services
    db = kg_services.ReplicaDB()
    db.MAX_ROWS = 5000
    g, m = db.validate(gold, site, params), db.validate(model_sql, site, params)
    if not g.get("ok"):
        return {"ex": None, "note": "reference failed: " + str(g.get("error"))}
    if not m.get("ok") or g.get("truncated") or m.get("truncated"):
        return {"ex": False if not m.get("ok") else None, "note": "model failed" if not m.get("ok") else "over 5000 rows - not scored",
                "gold_rows": g.get("row_count")}
    return {"ex": kg_core.exec_match(g["rows"], m["rows"]), "gold_rows": g["row_count"], "model_rows": m["row_count"]}


def post(path, body, timeout=900):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main():
    max_conv = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    only = os.environ.get("KG_BATCH_ONLY", "")   # e.g. "theme" = only the theme set (no conversions)
    # stability check: only questions containing one of these '|' separated texts, each REPEAT times, no conversions
    match = [m for m in os.environ.get("KG_BATCH_MATCH", "").split("|") if m]
    repeat = int(os.environ.get("KG_BATCH_REPEAT", "1"))
    out = {"ask": [], "convert": []}
    todo = [(e, s_, q) for e, s_, q in QUESTIONS if not match or any(m in q for m in match)]
    for eng, site, q in [x for x in todo for _ in range(repeat)]:
        if only == "theme" and THEME.get(q) in ("inventory", "location", "picking", "master_data"):
            continue
        t = time.time()
        r = post("/rp/ask", {"question": q, "engine": eng, "site": site, "params": {"wh_id": WH[site]} if site in WH else None})
        v = r.get("validation") or {}
        row = {"engine": eng, "site": site, "theme": THEME.get(q, "other"), "question": q, "status": r["status"], "attempts": r["attempts"], "rows": v.get("row_count"),
               "error": v.get("error"), "empty_fields": v.get("empty_fields"), "warnings": r.get("warnings"), "seconds": round(time.time() - t, 1), "sql": r["sql"]}
        row["accuracy"] = score(site, q, r["sql"] if r["status"] == "validated" else "", {"wh_id": WH[site]} if site in WH else None)
        out["ask"].append(row)
        print("ASK", eng, site, row["status"], row["attempts"], row["rows"], row["error"] or "", row["seconds"], "s |", q, "| EX:", row["accuracy"], flush=True)
    templates = json.load(urllib.request.urlopen(API + "/rp/templates", timeout=60))
    src = [] if match else [t for t in templates if t["engine"] == "RTCIS" and "@" not in t["sql"]][:max_conv]
    for t0 in src:
        t = time.time()
        r = post("/rp/convert", {"sql": t0["sql"], "source_engine": "RTCIS", "target_engine": "PrIME2022", "source_site": "RTCIS_EUS",
                                 "target_site": "PRIME22_DE08", "params": {"wh_id": "DE08"}})
        v, c = r.get("validation") or {}, r.get("contract") or {}
        row = {"qid": t0["qid"], "title": t0["title"], "status": r["status"], "attempts": r["attempts"], "source_ok": (r.get("source_validation") or {}).get("ok"),
               "rows": v.get("row_count"), "error": v.get("error"), "contract_identical": c.get("identical"), "missing": c.get("missing"),
               "extra": c.get("extra"), "empty_fields": v.get("empty_fields"), "seconds": round(time.time() - t, 1), "sql": r["sql"]}
        out["convert"].append(row)
        print("CONVERT", row["qid"], row["status"], row["attempts"], "src_ok", row["source_ok"], "rows", row["rows"], "contract", row["contract_identical"],
              row["error"] or "", row["seconds"], "s", flush=True)
    from collections import Counter
    out["summary"] = {"ask": dict(Counter(x["status"] for x in out["ask"])), "convert": dict(Counter(x["status"] for x in out["convert"])),
                      "ask_by_engine": {e: dict(Counter(x["status"] for x in out["ask"] if x["engine"] == e)) for e in ("RTCIS", "PrIME2014", "PrIME2022")},
                      "by_theme": {th: {"n": sum(1 for x in out["ask"] if x["theme"] == th),
                                         "validated": sum(1 for x in out["ask"] if x["theme"] == th and x["status"] == "validated"),
                                         "ex_true": sum(1 for x in out["ask"] if x["theme"] == th and (x["accuracy"] or {}).get("ex") is True),
                                         "ex_scored": sum(1 for x in out["ask"] if x["theme"] == th and (x["accuracy"] or {}).get("ex") is not None)}
                                    for th in sorted({x["theme"] for x in out["ask"]})},
                      "execution_accuracy": {}}
    for x in out["ask"]:   # a list per question: repeated runs (stability mode) must all be kept
        if x.get("accuracy"):
            out["summary"]["execution_accuracy"].setdefault(f"{x['site']} | {x['question']}", []).append(x["accuracy"].get("ex"))
    json.dump(out, open(os.path.join(KIT, "benchmark", os.environ.get("KG_BATCH_OUT", "cloud_batch_results_stability.json" if match or repeat > 1 else "cloud_batch_results.json")), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
