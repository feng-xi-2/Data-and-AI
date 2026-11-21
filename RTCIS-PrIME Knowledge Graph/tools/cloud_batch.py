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
]
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
    out = {"ask": [], "convert": []}
    for eng, site, q in QUESTIONS:
        t = time.time()
        r = post("/rp/ask", {"question": q, "engine": eng, "site": site, "params": {"wh_id": WH[site]} if site in WH else None})
        v = r.get("validation") or {}
        row = {"engine": eng, "site": site, "question": q, "status": r["status"], "attempts": r["attempts"], "rows": v.get("row_count"),
               "error": v.get("error"), "empty_fields": v.get("empty_fields"), "warnings": r.get("warnings"), "seconds": round(time.time() - t, 1), "sql": r["sql"]}
        row["accuracy"] = score(site, q, r["sql"] if r["status"] == "validated" else "", {"wh_id": WH[site]} if site in WH else None)
        out["ask"].append(row)
        print("ASK", eng, site, row["status"], row["attempts"], row["rows"], row["error"] or "", row["seconds"], "s |", q, "| EX:", row["accuracy"], flush=True)
    templates = json.load(urllib.request.urlopen(API + "/rp/templates", timeout=60))
    src = [t for t in templates if t["engine"] == "RTCIS" and "@" not in t["sql"]][:max_conv]
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
                      "execution_accuracy": {f"{x['site']} | {x['question']}": (x["accuracy"] or {}).get("ex") for x in out["ask"] if x.get("accuracy")}}
    json.dump(out, open(os.path.join(KIT, "benchmark", "cloud_batch_results.json"), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
