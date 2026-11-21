"""Harvest every documented table/column mapping RTCIS <-> PrIME 2014 <-> PrIME 2022, then validate each one against the REAL
databases before it may enter the graph.

Sources (candidates)                                                   engines
  H1 raw/reference/RTCIS-TO-PRIME-COMPLETE-REFERENCE.md  sec 3 tables, sec 4 columns   RTCIS -> PrIME2022
  H2 raw/schema/verified-mappings.json (tables, columns)                               RTCIS -> PrIME2022
  H3 wiki/entities/tables.md, wiki/ground-truth/mappings.md (Euskirchen, measured)     RTCIS -> PrIME2022
  H4 raw/kb/PRIME-2014-TO-2022-REMEDIATION-GUIDE.md sec 3 (structural changes)         PrIME2014 -> PrIME2022
  H5 raw/schema/prime-datamodel.json transition_map (renamed tables/columns)          PrIME2014 -> PrIME2022
  H6 SQL_Translations/_ontology_kg.json MAPS_TO (older discovery graph)                RTCIS -> PrIME
  H7 catalog identity: same table (+ same columns) present in BOTH PrIME catalogs      PrIME2014 -> PrIME2022
  H8 composition: RTCIS -> PrIME2022 mapping whose target also exists in PrIME2014     RTCIS -> PrIME2014

Validation (benchmark/catalog.json from live INFORMATION_SCHEMA; values sampled live, read-only, TOP n, 60 s timeout)
  V1 EXISTS   both endpoints (table, and column if given) exist in the engine's real catalog      -> else REJECTED
  V2 TYPE     column data-type families match (text / number / date / binary)                     -> TYPE_DIFF flag
  V3 VALUES   same-site value evidence (RTCIS Euskirchen vs PrIME 2022 Euskirchen): share of sampled RTCIS
              values found in the PrIME column, fill rate both sides; code columns across PrIME sites   -> overlap %
Only V1-passing mappings are loaded. Conflicts (one source column -> different targets in different sources) are kept,
each with its own evidence, and flagged CONFLICT so a person decides.

    python mappings.py [--no-values]      -> benchmark/mapping_validation.json
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WIKI = os.environ.get("WIKI_ROOT", os.path.join(KIT, "..", "RTCIS-PrIME-LLM-Wiki"))
OLD_KG = os.environ.get("OLD_KG_JSON", "")
CAT = json.load(open(os.path.join(KIT, "benchmark", "catalog.json"), encoding="utf-8"))
ENG = CAT["engines"]
FAMILY = {"char": "text", "varchar": "text", "nvarchar": "text", "nchar": "text", "text": "text", "ntext": "text",
          "int": "number", "bigint": "number", "smallint": "number", "tinyint": "number", "numeric": "number", "decimal": "number",
          "float": "number", "real": "number", "money": "number", "bit": "number",
          "datetime": "date", "datetime2": "date", "date": "date", "smalldatetime": "date", "datetimeoffset": "date", "time": "date",
          "varbinary": "binary", "binary": "binary", "image": "binary", "uniqueidentifier": "text"}


def rd(*p):
    return open(os.path.join(WIKI, *p), encoding="utf-8").read()


def clean(x):
    return re.sub(r"[`*]", "", x or "").strip()


def cand(out, se, st, sc, de, dt, dc, source, conf="", note="", expr=""):
    st, dt = clean(st).lower(), clean(dt).lower()
    sc, dc = (clean(sc).lower() or None), (clean(dc).lower() or None)
    if not st or not dt or not re.match(r"^[a-z_][\w$]*$", st) or not re.match(r"^[a-z_][\w$]*$", dt):
        return
    out.append({"src": [se, st, sc], "dst": [de, dt, dc], "source": source, "confidence": clean(conf)[:20],
                "note": " ".join((note or "").split())[:300], "expr": expr[:300]})


def md_rows(text, start, stop=None):
    seg = text[text.find(start):] if start in text else ""
    if stop and stop in seg[len(start):]:
        seg = seg[:seg.find(stop, len(start))]
    return [[c.strip() for c in m.group(1).split("|")] for m in re.finditer(r"^\|(.+)\|\s*$", seg, re.M)
            if not re.match(r"^\|\s*-", m.group(0))]


def harvest():
    out = []
    ref = rd("raw", "reference", "RTCIS-TO-PRIME-COMPLETE-REFERENCE.md")
    for conf, (a, b) in (("HIGH", ("### HIGH Confidence", "### MED")), ("MED", ("### MED Confidence", "## 4."))):
        for r in md_rows(ref, a, b)[1:]:
            for dt in re.split(r"[/+,]", clean(r[1]).split(" ")[0]):
                cand(out, "RTCIS", r[0], None, "PrIME2022", dt, None, "H1 complete-reference", conf, r[2] if len(r) > 2 else "")
    for r in md_rows(ref, "### Key RTCIS", "### SYSDTL")[1:]:
        if "." not in r[0]:
            continue
        st, sc = r[0].split(".", 1)
        tgt = clean(r[1])
        if "." in tgt and re.match(r"^[\w.]+$", tgt):
            dt, dc = tgt.split(".", 1)
            cand(out, "RTCIS", st, sc, "PrIME2022", dt, dc, "H1 complete-reference", r[2], r[3] if len(r) > 3 else "")
    for r in md_rows(ref, "### SYSDTL Detail Fields", "### Value Mappings")[1:]:
        for dc in re.split(r"[/,]", clean(r[1])):
            if re.match(r"^\w+$", dc.strip()):
                cand(out, "RTCIS", "sysdtl", r[0], "PrIME2022", "dlytrn", dc.strip(), "H1 complete-reference", "HIGH", r[2] if len(r) > 2 else "")
    vm = json.load(open(os.path.join(WIKI, "raw", "schema", "verified-mappings.json"), encoding="utf-8"))
    for k, v in vm["tables"].items():
        if isinstance(v, dict) and v.get("prime"):
            for dt in re.split(r"[/+,]", clean(str(v["prime"])).split(" ")[0]):
                cand(out, "RTCIS", k, None, "PrIME2022", dt, None, "H2 verified-mappings", v.get("confidence", ""), v.get("notes", ""))
    for k, v in vm["columns"].items():
        if isinstance(v, dict) and "." in k and re.match(r"^[\w]+\.[\w]+$", clean(str(v.get("prime", "")))):
            st, sc = k.split(".", 1)
            dt, dc = clean(v["prime"]).split(".", 1)
            cand(out, "RTCIS", st, sc, "PrIME2022", dt, dc, "H2 verified-mappings", v.get("confidence", ""), v.get("notes", ""))
    for r in md_rows(rd("wiki", "entities", "tables.md"), "| RTCIS")[1:]:
        for st in re.findall(r"`(\w+)`", r[0]):
            for dt in re.findall(r"`(\w+)`|\b([a-z_]{3,})\b", r[1]):
                dt = dt[0] or dt[1]
                if dt in ENG["PrIME2022"]:
                    cand(out, "RTCIS", st, None, "PrIME2022", dt, None, "H3 wiki tables.md [DB]", "MEASURED", r[2] if len(r) > 2 else "")
    gd = rd("raw", "kb", "PRIME-2014-TO-2022-REMEDIATION-GUIDE.md")
    for r in md_rows(gd, "### 3.1 Areas", "### 3.3")[1:]:
        a, b = re.findall(r"`([\w.]+)`", r[0]), re.findall(r"`([\w.]+)`", r[1])
        for x in a:
            for y in b:
                sx, sy = x.split("."), y.split(".")
                cand(out, "PrIME2014", sx[0] if len(sx) > 1 or "_" in x or x in ENG["PrIME2014"] else "prtftp_view", sx[1] if len(sx) > 1 else None,
                     "PrIME2022", sy[0] if len(sy) > 1 or y in ENG["PrIME2022"] else "prtftp_view", sy[1] if len(sy) > 1 else None,
                     "H4 remediation-guide", "DOC", r[2] if len(r) > 2 else "")
    for r in md_rows(gd, "### 3.6 Summary", "---")[1:]:
        t = clean(r[0])
        for x in re.split(r"\s*/\s*", t):
            cand(out, "PrIME2014", x, None, "PrIME2022", x, None, "H4 remediation-guide (safe unchanged)", "DOC", r[2] if len(r) > 2 else "")
    dm = json.load(open(os.path.join(WIKI, "raw", "schema", "prime-datamodel.json"), encoding="utf-8"))
    for a, b in dm["transition_map"].items():
        if "." in a and "." in b:
            (st, sc), (dt, dc) = a.split(".", 1), b.split(".", 1)
            cand(out, "PrIME2014", st, sc, "PrIME2022", dt, dc, "H5 datamodel transition_map", "DOC")
    if OLD_KG and os.path.exists(OLD_KG):
        kg = json.load(open(OLD_KG, encoding="utf-8"))
        n = {x["id"]: x for x in kg["nodes"]}
        for e in kg["edges"]:
            if e["type"] != "MAPS_TO":
                continue
            s, d = n[e["src"]], n[e["dst"]]
            if s["type"] == "Table":
                cand(out, "RTCIS", s["label"], None, "PrIME2022", d["label"], None, "H6 discovery-graph", e.get("confidence", ""), s.get("notes", ""))
            elif "." in s["label"] and "." in d["label"]:
                (st, sc), (dt, dc) = s["label"].split(".", 1), d["label"].split(".", 1)
                cand(out, "RTCIS", st, sc, "PrIME2022", dt, dc, "H6 discovery-graph", e.get("confidence", ""))
    for t in sorted(set(ENG["PrIME2014"]) & set(ENG["PrIME2022"])):
        cand(out, "PrIME2014", t, None, "PrIME2022", t, None, "H7 catalog identity", "CATALOG")
        for c in sorted(set(ENG["PrIME2014"][t]) & set(ENG["PrIME2022"][t])):
            cand(out, "PrIME2014", t, c, "PrIME2022", t, c, "H7 catalog identity", "CATALOG")
    return out


def family(engine, t, c):
    return FAMILY.get(ENG[engine].get(t, {}).get(c, ""), "other")


def v1(engine, t, c):
    if t not in ENG[engine]:
        return f"table {t} not in {engine} catalog"
    if c and c not in ENG[engine][t]:
        return f"column {t}.{c} not in {engine} catalog"
    return ""


def validate(cands, with_values=True):
    seen, rows = {}, []
    for x in cands:
        k = (tuple(x["src"]), tuple(x["dst"]))
        if k in seen:
            seen[k]["sources"].append(x["source"])
            seen[k]["notes"] = (seen[k]["notes"] + " | " + x["note"]).strip(" |")[:500] if x["note"] else seen[k]["notes"]
            continue
        r = {"src": x["src"], "dst": x["dst"], "sources": [x["source"]], "confidence": x["confidence"], "notes": x["note"], "checks": {}}
        e1, e2 = v1(*x["src"]), v1(*x["dst"])
        r["checks"]["V1"] = "PASS" if not (e1 or e2) else "FAIL: " + "; ".join(y for y in (e1, e2) if y)
        if not (e1 or e2) and x["src"][2] and x["dst"][2]:
            fa, fb = family(*x["src"]), family(*x["dst"])
            r["checks"]["V2"] = "PASS" if fa == fb else f"TYPE_DIFF {fa}->{fb}"
        seen[k] = r
        rows.append(r)
    # H8 composition RTCIS -> PrIME2014 (validated against the 2014 catalog)
    for r in list(rows):
        if r["src"][0] == "RTCIS" and r["dst"][0] == "PrIME2022" and r["checks"]["V1"] == "PASS":
            dst14 = ["PrIME2014", r["dst"][1], r["dst"][2]]
            k = (tuple(r["src"]), tuple(dst14))
            if k not in seen:
                e = v1(*dst14)
                nr = {"src": r["src"], "dst": dst14, "sources": ["H8 composition via PrIME2022"], "confidence": r["confidence"],
                      "notes": "same PrIME object exists in the 2014 catalog", "checks": {"V1": "PASS" if not e else "FAIL: " + e}}
                if not e and r["src"][2]:
                    fa, fb = family(*r["src"]), family(*dst14)
                    nr["checks"]["V2"] = "PASS" if fa == fb else f"TYPE_DIFF {fa}->{fb}"
                seen[k] = nr
                rows.append(nr)
    # conflicts: same RTCIS/2014 source -> different target tables in different sources (curated sources only)
    tgt = defaultdict(set)
    for r in rows:
        if r["checks"]["V1"] == "PASS" and not any(s.startswith(("H7", "H8")) for s in r["sources"]):
            tgt[(r["src"][0], r["src"][1], r["src"][2], r["dst"][0])].add((r["dst"][1], r["dst"][2]))
    for r in rows:
        alts = tgt.get((r["src"][0], r["src"][1], r["src"][2], r["dst"][0]), set())
        if len(alts) > 1 and r["src"][2]:
            r["checks"]["CONFLICT"] = sorted(f"{a}.{b}" if b else a for a, b in alts)
    if with_values:
        values(rows)
    return rows


def values(rows):
    """V3: live value evidence for curated column mappings (RTCIS Euskirchen vs PrIME 2022 Euskirchen; PrIME 2014 vs 2022 code sets)."""
    from dbconn import connect
    pref = {"RTCIS": ["RTCIS_EUS"], "PrIME2022": ["PRIME22_DE08"], "PrIME2014": []}
    cache = {}

    def where(engine, t):
        keys = pref.get(engine, []) + [k for k, v in CAT["sites"].items() if v["engine"] == engine]
        for k in keys:
            if k in CAT["sites"] and t in CAT["sites"][k]["tables"]:
                db, sch = CAT["sites"][k]["tables"][t]
                return k, db, sch
        raise KeyError(f"{engine}.{t} at no site")

    def sample(engine, t, c):
        if (engine, t, c) in cache:
            return cache[(engine, t, c)]
        try:
            key, db, sch = where(engine, t)
        except KeyError as e:
            return {"error": str(e)}
        cur = connect(key).cursor()
        try:
            cur.execute(f"SELECT TOP 3000 LTRIM(RTRIM(CAST([{c}] AS nvarchar(200)))) FROM [{db}].[{sch}].[{t}] WITH (NOLOCK)")
            vals = [r[0] for r in cur.fetchall()]
            res = {"n": len(vals), "filled": sum(1 for v in vals if v not in (None, "")), "distinct": {(v or "").upper() for v in vals if v}, "site": key}
        except Exception as e:
            res = {"error": str(e)[:150]}
        cache[(engine, t, c)] = res
        return res

    todo = [r for r in rows if r["checks"]["V1"] == "PASS" and r["src"][2] and r["dst"][2]
            and not any(s.startswith(("H7", "H8")) for s in r["sources"])]
    print("V3 value checks:", len(todo), flush=True)

    def found(engine, t, c, values_):
        """How many of the source values exist in the target column (lookup, not sample-vs-sample)."""
        key, db, sch = where(engine, t)
        fam = family(engine, t, c)
        if fam == "date" or not values_:
            return None
        rhs = "x.v COLLATE DATABASE_DEFAULT" if fam == "text" else "TRY_CAST(x.v AS decimal(38,6))"
        lhs = f"[{c}]" if fam != "text" else f"[{c}] COLLATE DATABASE_DEFAULT"
        cur = connect(key).cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM OPENJSON(?) WITH (v nvarchar(200) '$') x WHERE EXISTS "
                        f"(SELECT 1 FROM [{db}].[{sch}].[{t}] y WITH (NOLOCK) WHERE {lhs.replace('[', 'y.[', 1)} = {rhs})",
                        json.dumps(sorted(values_)[:200]))
            return round(100 * cur.fetchone()[0] / min(len(values_), 200), 1)
        except Exception as e:
            return f"ERROR {str(e)[:100]}"

    for i, r in enumerate(todo):
        a, b = sample(*r["src"]), sample(*r["dst"])
        if "error" in a or "error" in b:
            r["checks"]["V3"] = "ERROR " + (a.get("error") or b.get("error"))
            continue
        fa = round(100 * a["filled"] / a["n"], 1) if a["n"] else None
        fb = round(100 * b["filled"] / b["n"], 1) if b["n"] else None
        ov = round(100 * len(a["distinct"] & b["distinct"]) / len(a["distinct"]), 1) if a["distinct"] else None
        same_site = a["site"] == "RTCIS_EUS" and b["site"] == "PRIME22_DE08"
        r["checks"]["V3"] = {"fill_src": fa, "fill_dst": fb, "value_overlap_pct": ov, "distinct_src": len(a["distinct"]),
                             "distinct_dst": len(b["distinct"]), "same_site": same_site, "sites": [a["site"], b["site"]],
                             "src_values_found_in_dst_pct": found(*r["dst"], a["distinct"])}
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)


def summarise(rows):
    from collections import Counter
    s = Counter()
    for r in rows:
        pair = f"{r['src'][0]}->{r['dst'][0]}"
        lvl = "column" if r["src"][2] else "table"
        s[(pair, lvl, "loaded" if r["checks"]["V1"] == "PASS" else "rejected")] += 1
    return {" ".join(k): v for k, v in sorted(s.items())}


def main():
    rows = validate(harvest(), with_values="--no-values" not in sys.argv)
    summ = summarise(rows)
    json.dump({"summary": summ, "mappings": rows}, open(os.path.join(KIT, "benchmark", "mapping_validation.json"), "w", encoding="utf-8"),
              indent=0, ensure_ascii=False)
    for k, v in summ.items():
        print(f"  {k:55s} {v}")
    rej = [r for r in rows if r["checks"]["V1"] != "PASS"]
    print("rejected examples:", [(r["src"], r["dst"], r["sources"][0], r["checks"]["V1"]) for r in rej[:6]])
    print("conflicts:", sum(1 for r in rows if "CONFLICT" in r["checks"]), "type diffs:", sum(1 for r in rows if str(r["checks"].get("V2", "")).startswith("TYPE")))


if __name__ == "__main__":
    main()
