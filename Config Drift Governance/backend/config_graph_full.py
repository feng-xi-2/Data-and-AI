"""
config_graph_full.py — build a FULL-GRANULARITY knowledge graph of the PrIME
Standard Configuration Catalogue for BOTH 2014 and 2022, from the real files
downloaded off SharePoint (sharepoint_reader.py --download), and CAPTURE THE
2014 -> 2022 CHANGE.

Richness (vs the earlier config_catalogue_graph.py which only did 2022 Section/
Column/Exception):
  * BOTH versions (2014 + 2022), one Section per workbook per version.
  * Full Column Info granularity per column: UI prompt, Audited?/Primary Key,
    Allowing deviations, Deviations allowed, Validation logic, Severity, info.
  * The REAL underlying data schema of each section = the header columns of its
    'Pre-Loaded Values' sheet -> Field nodes (shared Field per version reveals
    columns reused across sections, e.g. wh_id / client_id).
  * Pre-loaded record COUNT per section (content volume) + all General Rules.
  * Exceptions (accepted deviations) -> ACCEPTED_FOR the 2022 section.
  * CHANGE CAPTURE: same-named sections linked 2014 -[:EVOLVES_TO]-> 2022 with
    added/removed/kept column deltas + PK-structure change; sections only in one
    version flagged ADDED_IN_2022 / REMOVED_IN_2022; per-section Change node.

Grounded only in the actual workbook contents — no invented table names.

Outputs (in _catalogue_graph_full/):
    graph_full.json         nodes + edges (Version, Section, Column, Field,
                            Exception, Change)
    change_2014_2022.json    the human-readable diff
Loads straight into Neo4j (bolt://localhost:7687) with --neo4j.

USAGE
    python config_graph_full.py --build
    python config_graph_full.py --build --neo4j
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os

import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DIR_2014 = os.path.join(BASE, "_sharepoint", "_config_2014")
DIR_2022 = os.path.join(BASE, "_sharepoint", "_config_2022")
OUT_DIR = os.path.join(BASE, "_catalogue_graph_full")

GENERAL_RULES = "General Rules"
COLUMN_INFO = "Column Info"
PRELOADED = "Pre-Loaded Values"
INFORMATION = "Information"


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


# --- parsing helpers --------------------------------------------------------
def _rows(ws, limit=None):
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if limit and i >= limit:
            break
        out.append(list(r))
    return out


def parse_general_rules(ws) -> dict:
    kv = {}
    for r in ws.iter_rows(values_only=True):
        if not r or r[0] is None:
            continue
        key = str(r[0]).strip()
        val = r[1] if len(r) > 1 and r[1] is not None else None
        kv[key] = None if val is None else str(val).strip()
    return kv


def _find_col(header: list[str], *starts: str):
    for i, h in enumerate(header):
        hl = h.lower().strip()
        for s in starts:
            if hl.startswith(s):
                return i
    return None


def parse_column_info(ws) -> list[dict]:
    rows = _rows(ws)
    if not rows:
        return []
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    ci_name = _find_col(header, "column name") or 0
    ci_prompt = _find_col(header, "ui field", "ui prompt")
    ci_aud = _find_col(header, "audited")
    ci_allow = _find_col(header, "allowing deviation")
    ci_dev = _find_col(header, "deviations allow")
    ci_val = _find_col(header, "validation")
    ci_sev = _find_col(header, "severity")
    ci_info = _find_col(header, "info")

    def cell(r, i):
        if i is None or i >= len(r) or r[i] is None:
            return None
        s = str(r[i]).strip()
        return s or None

    cols = []
    for r in rows[1:]:
        if not r or ci_name >= len(r) or r[ci_name] is None:
            continue
        name = str(r[ci_name]).strip()
        if not name:
            continue
        audited = cell(r, ci_aud) or ""
        aud_l = audited.lower()
        is_pk = aud_l in ("primary key", "pk", "primary_key")
        cols.append({
            "column": name,
            "prompt": cell(r, ci_prompt),
            "audited": audited,
            "is_primary_key": is_pk,
            "allowing_deviations": cell(r, ci_allow),
            "deviations_allowed": cell(r, ci_dev),
            "validation_logic": cell(r, ci_val),
            "severity": cell(r, ci_sev),
            "info": cell(r, ci_info),
        })
    return cols


def parse_preloaded(ws) -> tuple[list[str], int]:
    """Return (data field names from header row, record count)."""
    fields: list[str] = []
    count = 0
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            fields = [str(c).strip() for c in r if c is not None and str(c).strip()]
        else:
            if r and any(c is not None for c in r):
                count += 1
    return fields, count


def parse_information(ws) -> dict:
    """Pull a short description + primary-key note if present."""
    out = {"description": None, "primary_keys_note": None}
    rows = _rows(ws, limit=40)
    for r in rows:
        if not r or r[0] is None:
            continue
        label = str(r[0]).strip().lower()
        val = None
        for c in r[1:]:
            if c is not None and str(c).strip():
                val = str(c).strip()
                break
        if val is None:
            continue
        if out["description"] is None and label.startswith("description"):
            out["description"] = val[:400]
        if label.startswith("primary key"):
            out["primary_keys_note"] = val[:200]
    return out


def _fingerprint(ws) -> str:
    h = hashlib.sha256()
    for r in ws.iter_rows(values_only=True):
        h.update(repr(r).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def section_from_filename(fn: str) -> str:
    stem = fn[:-5]
    for v in ("_2014", "_2022", "_202x"):
        if stem.endswith(v):
            return stem[: -len(v)]
    return stem


# --- build one version ------------------------------------------------------
def build_version(folder: str, version: str, nodes, edges, section_keys):
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"folder not found: {folder}")
    files = sorted(f for f in os.listdir(folder) if f.endswith(".xlsx"))
    log(f"[{version}] {len(files)} workbooks in {folder}")

    def add_node(nid, ntype, **attrs):
        nodes.append({"id": nid, "type": ntype, **attrs})

    add_node(f"version:{version}", "Version", label=version)

    sections_seen: dict[str, dict] = {}
    exceptions_file = None
    parsed = 0

    for fn in files:
        low = fn.lower()
        if low.startswith("exceptions"):
            exceptions_file = fn
            continue
        section = section_from_filename(fn)
        path = os.path.join(folder, fn)
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            log(f"  WARN cannot open {fn}: {type(e).__name__}: {e}")
            continue

        sheets = wb.sheetnames
        rules = parse_general_rules(wb[GENERAL_RULES]) if GENERAL_RULES in sheets else {}
        cols = parse_column_info(wb[COLUMN_INFO]) if COLUMN_INFO in sheets else []
        fields, rec_count = ([], 0)
        if PRELOADED in sheets:
            fields, rec_count = parse_preloaded(wb[PRELOADED])
        info = parse_information(wb[INFORMATION]) if INFORMATION in sheets else {}

        pks = [c["column"] for c in cols if c["is_primary_key"]]
        if pks:
            section_keys.setdefault(version, {})[section] = pks

        sec_id = f"section:{section}:{version}"
        add_node(
            sec_id, "Section",
            label=section, version=version,
            new_records_allowed=rules.get("Are new records allowed?",
                                          rules.get("Are new records allowed? ")),
            severity_new=rules.get("Severity for new records"),
            severity_missing=rules.get("Severity for missing records"),
            benchmark=rules.get("Benchmark"),
            description=info.get("description"),
            primary_keys_note=info.get("primary_keys_note"),
            n_columns=len(cols),
            n_fields=len(fields),
            preloaded_count=rec_count,
            sheets=sheets,
            source_file=fn,
            fingerprint={sh: _fingerprint(wb[sh]) for sh in sheets},
        )
        edges.append({"src": sec_id, "dst": f"version:{version}", "rel": "OF_VERSION"})

        for c in cols:
            col_id = f"column:{section}:{version}:{c['column']}"
            add_node(col_id, "Column", label=c["column"], section=section, version=version,
                     prompt=c["prompt"], audited=c["audited"], is_primary_key=c["is_primary_key"],
                     allowing_deviations=c["allowing_deviations"],
                     deviations_allowed=c["deviations_allowed"],
                     validation_logic=c["validation_logic"],
                     severity=c["severity"], info=c["info"])
            edges.append({"src": sec_id, "dst": col_id,
                          "rel": "HAS_KEY" if c["is_primary_key"] else "HAS_COLUMN"})

        # physical data fields (shared Field per version reveals reuse across sections)
        for fld in fields:
            fid = f"field:{version}:{fld}"
            if fid not in sections_seen:
                add_node(fid, "Field", label=fld, version=version)
                sections_seen[fid] = {}
            edges.append({"src": sec_id, "dst": fid, "rel": "HAS_FIELD"})

        wb.close()
        parsed += 1

    # exceptions -> ACCEPTED_FOR section (this version)
    if exceptions_file:
        try:
            wb = openpyxl.load_workbook(os.path.join(folder, exceptions_file),
                                        read_only=True, data_only=True)
            ws = wb[wb.sheetnames[0]]
            rows = _rows(ws)
            header = [str(c).strip() if c is not None else "" for c in rows[0]]
            hi = {h.lower(): i for i, h in enumerate(header)}
            gi = hi.get("gui screen", 0)
            ei = hi.get("entry")
            di = hi.get("deviation type")
            ci = hi.get("comments")
            wi = hi.get("where allowed?")
            n_exc = 0
            for r in rows[1:]:
                if not r or gi >= len(r) or r[gi] is None:
                    continue
                screen = str(r[gi]).strip()
                entry = str(r[ei]).strip() if ei is not None and len(r) > ei and r[ei] is not None else None
                exc_id = f"exception:{version}:{screen}:{entry}:{n_exc}"
                add_node(exc_id, "Exception", version=version, screen=screen, entry=entry,
                         deviation_type=str(r[di]).strip() if di is not None and len(r) > di and r[di] is not None else None,
                         where_allowed=str(r[wi]).strip() if wi is not None and len(r) > wi and r[wi] is not None else None,
                         rationale=str(r[ci]).strip() if ci is not None and len(r) > ci and r[ci] is not None else None)
                edges.append({"src": exc_id, "dst": f"section:{screen}:{version}", "rel": "ACCEPTED_FOR"})
                n_exc += 1
            log(f"[{version}] exceptions: {n_exc} accepted deviations from {exceptions_file}")
            wb.close()
        except Exception as e:
            log(f"  WARN exceptions parse failed: {type(e).__name__}: {e}")

    log(f"[{version}] parsed {parsed} sections")
    return parsed


# --- change capture 2014 -> 2022 --------------------------------------------
def capture_change(nodes, edges) -> dict:
    secs = {}
    cols_by_sec = {}
    fields_by_sec = {}
    for n in nodes:
        if n["type"] == "Section":
            secs[(n["label"], n["version"])] = n
        elif n["type"] == "Column":
            cols_by_sec.setdefault((n["section"], n["version"]), {})[n["label"]] = n
    for e in edges:
        if e["rel"] == "HAS_FIELD":
            # src is section id "section:<label>:<ver>", dst "field:<ver>:<name>"
            sid = e["src"]
            fid = e["dst"]
            fields_by_sec.setdefault(sid, set()).add(fid.split(":", 2)[2])

    labels_2014 = {lbl for (lbl, v) in secs if v == "2014"}
    labels_2022 = {lbl for (lbl, v) in secs if v == "2022"}
    only_2022 = sorted(labels_2022 - labels_2014)
    only_2014 = sorted(labels_2014 - labels_2022)
    common = sorted(labels_2014 & labels_2022)

    # --- rename detection: a section that exists only in 2014 and one only in 2022
    #     with a highly similar underlying field set is almost certainly a rename
    #     (e.g. "Area Maintenance" -> "Areas"). We use IDF-WEIGHTED field similarity
    #     so ubiquitous audit columns (is_purged, wh_id, ins_dt, last_upd_dt, ...
    #     present in dozens of sections) count near-zero, and RARE business keys
    #     (polcod, arecod, carcod, ...) drive the match. This kills false positives
    #     where two unrelated screens share only generic audit fields. Conservative:
    #     weighted-Jaccard >= 0.6 AND mutually-best match.
    import math

    def fset(lbl, ver):
        return fields_by_sec.get(f"section:{lbl}:{ver}", set())

    # document frequency of each field across ALL sections (both versions)
    df: dict[str, int] = {}
    n_docs = 0
    for sid, fs in fields_by_sec.items():
        n_docs += 1
        for f in fs:
            df[f] = df.get(f, 0) + 1
    def idf(f: str) -> float:
        return math.log((n_docs + 1) / (df.get(f, 0) + 1)) + 1.0

    def wjaccard(fa: set, fb: set) -> float:
        if not fa or not fb:
            return 0.0
        inter = fa & fb
        union = fa | fb
        wi = sum(idf(f) for f in inter)
        wu = sum(idf(f) for f in union)
        return wi / wu if wu else 0.0

    renames = []
    used_2022 = set()
    sim = {}
    for a in only_2014:
        fa = fset(a, "2014")
        if not fa:
            continue
        for b in only_2022:
            fb = fset(b, "2022")
            if not fb:
                continue
            j = wjaccard(fa, fb)
            if j >= 0.6:
                sim[(a, b)] = j
    # greedy mutually-best assignment
    for (a, b) in sorted(sim, key=lambda k: -sim[k]):
        if a in {r["from"] for r in renames} or b in used_2022:
            continue
        # ensure b is a's best and a is b's best
        best_b = max((bb for (aa, bb) in sim if aa == a), key=lambda bb: sim[(a, bb)])
        best_a = max((aa for (aa, bb) in sim if bb == b), key=lambda aa: sim[(aa, b)])
        if best_b == b and best_a == a:
            renames.append({"from": a, "to": b, "similarity": round(sim[(a, b)], 3)})
            used_2022.add(b)

    renamed_from = {r["from"] for r in renames}
    renamed_to = {r["to"] for r in renames}
    added = [b for b in only_2022 if b not in renamed_to]
    removed = [a for a in only_2014 if a not in renamed_from]

    change = {"added_sections": added, "removed_sections": removed,
              "renamed_sections": renames,
              "changed_sections": [], "unchanged_sections": []}

    for lbl in added:
        edges.append({"src": f"section:{lbl}:2022", "dst": "version:2022", "rel": "ADDED_IN_2022"})
    for lbl in removed:
        edges.append({"src": f"section:{lbl}:2014", "dst": "version:2014", "rel": "REMOVED_IN_2022"})
    for r in renames:
        edges.append({"src": f"section:{r['from']}:2014", "dst": f"section:{r['to']}:2022",
                      "rel": "RENAMED_TO", "similarity": r["similarity"]})

    # section pairs to compare at column level = exact-name commons + detected renames
    pairs = [(lbl, lbl) for lbl in common] + [(r["from"], r["to"]) for r in renames]
    for lbl14, lbl22 in pairs:
        c14 = cols_by_sec.get((lbl14, "2014"), {})
        c22 = cols_by_sec.get((lbl22, "2022"), {})
        cadded = sorted(set(c22) - set(c14))
        cremoved = sorted(set(c14) - set(c22))
        pk14 = sorted(k for k, v in c14.items() if v.get("is_primary_key"))
        pk22 = sorted(k for k, v in c22.items() if v.get("is_primary_key"))
        pk_changed = pk14 != pk22
        sev_changes = []
        for k in sorted(set(c14) & set(c22)):
            if (c14[k].get("severity") or "") != (c22[k].get("severity") or ""):
                sev_changes.append({"column": k, "from": c14[k].get("severity"),
                                    "to": c22[k].get("severity")})
        s14, s22 = secs[(lbl14, "2014")], secs[(lbl22, "2022")]
        rule_changes = {k: [s14.get(k), s22.get(k)]
                        for k in ("new_records_allowed", "severity_new", "severity_missing")
                        if (s14.get(k) or "") != (s22.get(k) or "")}
        renamed = lbl14 != lbl22
        is_changed = bool(cadded or cremoved or pk_changed or sev_changes or rule_changes or renamed)

        edges.append({
            "src": f"section:{lbl14}:2014", "dst": f"section:{lbl22}:2022", "rel": "EVOLVES_TO",
            "columns_added": len(cadded), "columns_removed": len(cremoved),
            "pk_changed": pk_changed, "severity_changes": len(sev_changes),
            "renamed": renamed,
        })

        if is_changed:
            ch_id = f"change:{lbl22}"
            nodes.append({
                "id": ch_id, "type": "Change", "label": lbl22,
                "renamed_from": lbl14 if renamed else "",
                "columns_added": "|".join(cadded), "columns_removed": "|".join(cremoved),
                "pk_2014": "|".join(pk14), "pk_2022": "|".join(pk22),
                "pk_changed": pk_changed,
                "severity_changes": json.dumps(sev_changes, ensure_ascii=False),
                "rule_changes": json.dumps(rule_changes, ensure_ascii=False),
            })
            edges.append({"src": ch_id, "dst": f"section:{lbl14}:2014", "rel": "CHANGE_FROM"})
            edges.append({"src": ch_id, "dst": f"section:{lbl22}:2022", "rel": "CHANGE_TO"})
            change["changed_sections"].append({
                "section": lbl22, "renamed_from": lbl14 if renamed else None,
                "columns_added": cadded, "columns_removed": cremoved,
                "pk_2014": pk14, "pk_2022": pk22, "pk_changed": pk_changed,
                "severity_changes": sev_changes, "rule_changes": rule_changes,
            })
        else:
            change["unchanged_sections"].append(lbl22)

    log(f"CHANGE: +{len(added)} added, -{len(removed)} removed, "
        f"~{len(renames)} renamed, {len(change['changed_sections'])} changed, "
        f"={len(change['unchanged_sections'])} unchanged")
    return change


# --- Neo4j load -------------------------------------------------------------
def load_neo4j(nodes, edges):
    from neo4j import GraphDatabase

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER")
    pw = os.environ.get("NEO4J_PASSWORD")
    if not user or not pw:
        raise RuntimeError("set NEO4J_USER / NEO4J_PASSWORD to load Neo4j")

    log(f"Neo4j: connecting {uri} as {user}")
    driver = GraphDatabase.driver(uri, auth=(user, pw), connection_timeout=10)
    try:
        driver.verify_connectivity()
        with driver.session() as s:
            # Replace the ENTIRE config graph (any prior Version/Section/Column/
            # Exception/Field/Change nodes — including ones loaded earlier WITHOUT
            # the :FullConfig label), but leave the WHS graph (RTCISTable/PrIMETable
            # /Learning/... — disjoint labels) untouched.
            log("Neo4j: clearing previous config nodes (keeping WHS graph)")
            s.run(
                "MATCH (n) WHERE n:Version OR n:Section OR n:Column OR n:Exception "
                "OR n:Field OR n:Change DETACH DELETE n"
            )
            for label in ("Version", "Section", "Column", "Field", "Exception", "Change"):
                s.run(f"CREATE CONSTRAINT fc_{label.lower()} IF NOT EXISTS "
                      f"FOR (n:{label}) REQUIRE n.id IS UNIQUE")

            by_type: dict[str, list] = {}
            for n in nodes:
                by_type.setdefault(n["type"], []).append(n)
            for ntype, rows in by_type.items():
                clean = []
                for r in rows:
                    props = {}
                    for k, v in r.items():
                        if k == "type":
                            continue
                        props[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                    clean.append(props)
                # tag with :FullConfig too so we can wipe just this graph next time
                s.run(f"UNWIND $rows AS row MERGE (n:{ntype}:FullConfig {{id: row.id}}) SET n += row",
                      rows=clean)
                log(f"  loaded {len(clean)} :{ntype}")

            by_rel: dict[str, list] = {}
            for e in edges:
                props = {k: v for k, v in e.items() if k not in ("src", "dst", "rel")}
                by_rel.setdefault(e["rel"], []).append({"src": e["src"], "dst": e["dst"], "p": props})
            for rel, rows in by_rel.items():
                s.run(f"UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
                      f"MERGE (a)-[r:{rel}]->(b) SET r += row.p", rows=rows)
                log(f"  loaded {len(rows)} [:{rel}]")

            log("Neo4j: === labels ===")
            for r in s.run("MATCH (n:FullConfig) RETURN labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"):
                print(f"    {r['l']}: {r['c']}")
    finally:
        driver.close()


# --- main -------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Full 2014+2022 config graph + change capture")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--neo4j", action="store_true", help="also load into Neo4j")
    args = ap.parse_args()
    if not args.build:
        ap.print_help()
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    nodes: list[dict] = []
    edges: list[dict] = []
    section_keys: dict[str, dict] = {}

    n14 = build_version(DIR_2014, "2014", nodes, edges, section_keys)
    n22 = build_version(DIR_2022, "2022", nodes, edges, section_keys)
    change = capture_change(nodes, edges)

    graph = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": "SharePoint WMS PrIME Service — ConfigurationCatalogue2014 + 202x",
        "counts": {
            "sections_2014": n14, "sections_2022": n22,
            "nodes": len(nodes), "edges": len(edges),
        },
        "section_keys": section_keys,
        "nodes": nodes,
        "edges": edges,
    }
    with open(os.path.join(OUT_DIR, "graph_full.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "change_2014_2022.json"), "w", encoding="utf-8") as f:
        json.dump(change, f, indent=2, ensure_ascii=False)
    log(f"wrote graph_full.json ({len(nodes)} nodes, {len(edges)} edges) and change_2014_2022.json")

    if args.neo4j:
        load_neo4j(nodes, edges)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
