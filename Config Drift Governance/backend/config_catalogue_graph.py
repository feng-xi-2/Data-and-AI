"""config_catalogue_graph — build a knowledge graph from the PrIME Standard Configuration
Catalogue ("PrIME config 2022" folder) and capture week-over-week changes.

WHAT THE CATALOGUE IS
---------------------
The "PrIME config 2022" folder is the P&G STANDARD (reference) configuration that the PrIME
Config Drift tool audits every site against. There is one workbook per Configuration Section
(Policy Maintenance, Areas, Job Maintenance, Devices, Web Services, ...). Each workbook has up
to 7 sheets (per Configuration Standards.txt):
    General Rules       - are new records allowed? severity for new/missing records, benchmark
    Column Info         - each column: UI prompt, Audited?/Primary Key, per-column severity
    Optionals           - optional records allowed for some/all sites
    Information         - human notes
    Pre-Loaded Values   - records loaded into the global instance
    Allowing Deviations - (Policies/Areas) per-record nature + whether deviations allowed
    Deviations Allowed  - (Policies/Areas) the allowed value variations
Plus Exceptions_2022.xlsx = the "accepted" deviations list (maps to the report's Rationale col).

WHY A GRAPH
-----------
The alert/validation scripts currently only read a deviation's severity. This catalogue is the
authoritative source for:
  * the ELEMENT-ID structure per section (which columns are Primary Keys -> how the report's
    '#'-concatenated Configuration Element is built). This is what validate_against_replica.py
    had to reverse-engineer.
  * WHY a deviation matters (new-record severity, per-column severity, whether deviations are
    allowed for a record).
  * which deviations are pre-approved (Exceptions -> accepted).
Modelling this as a graph lets the alert script be GROUNDED in the standard, and lets us diff
two snapshots to see exactly what each weekly CFG RFC changed.

OUTPUTS
-------
    graph.json          - nodes + edges (Section, Column, Rule, Exception, Version)
    section_keys.json    - {section: [primary key columns in order]} for the alert/validator
    snapshot_<date>.json - a hashed snapshot used for change capture

USAGE
-----
    python config_catalogue_graph.py --build          # parse folder -> graph.json + keys + snapshot
    python config_catalogue_graph.py --diff A.json B.json   # what changed between two snapshots
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

import openpyxl

CATALOGUE = os.environ.get(
    "PRIME_CATALOGUE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "PrIME config 2022"),
)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_catalogue_graph")

# Sheets we parse (others are human-notes / bulky value dumps we only fingerprint).
GENERAL_RULES = "General Rules"
COLUMN_INFO = "Column Info"


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------
def _rows(ws, limit=None):
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if limit and i >= limit:
            break
        out.append(list(r))
    return out


def parse_general_rules(ws) -> dict:
    """General Rules is a key/value sheet in the first two columns."""
    kv = {}
    for r in ws.iter_rows(values_only=True):
        if not r or r[0] is None:
            continue
        key = str(r[0]).strip()
        val = r[1] if len(r) > 1 else None
        kv[key] = None if val is None else str(val).strip()
    return kv


def parse_column_info(ws) -> list[dict]:
    """Column Info: header row then one row per audited column.

    Columns (observed): Column names, UI Field prompt, Audited?, Allowing deviations,
    Deviations allowed, Validation logic, Severity, info.
    'Audited?' == 'Primary Key' marks the columns that make up the element identifier.
    """
    rows = _rows(ws)
    if not rows:
        return []
    header = [str(c).strip() if c is not None else "" for c in rows[0]]

    def col(name_startswith):
        for i, h in enumerate(header):
            if h.lower().startswith(name_startswith):
                return i
        return None

    ci_name = col("column names") if col("column names") is not None else 0
    ci_prompt = col("ui field")
    ci_aud = col("audited")
    ci_sev = col("severity")

    cols = []
    for r in rows[1:]:
        if not r or (ci_name is not None and (len(r) <= ci_name or r[ci_name] is None)):
            continue
        name = str(r[ci_name]).strip()
        audited = str(r[ci_aud]).strip() if ci_aud is not None and len(r) > ci_aud and r[ci_aud] is not None else ""
        aud_l = audited.lower()
        is_pk = aud_l == "primary key" or aud_l == "pk" or aud_l == "primary_key"
        cols.append({
            "column": name,
            "prompt": str(r[ci_prompt]).strip() if ci_prompt is not None and len(r) > ci_prompt and r[ci_prompt] is not None else None,
            "audited": audited,
            "is_primary_key": is_pk,
            "severity": str(r[ci_sev]).strip() if ci_sev is not None and len(r) > ci_sev and r[ci_sev] is not None else None,
        })
    return cols


def _sheet_fingerprint(ws) -> str:
    """Stable hash of a sheet's values, so we can detect content changes cheaply."""
    h = hashlib.sha256()
    for r in ws.iter_rows(values_only=True):
        h.update(repr(r).encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def section_name_from_file(fn: str) -> tuple[str, str]:
    """'Policy Maintenance_2022.xlsx' -> ('Policy Maintenance', '2022')."""
    stem = fn[:-5]  # drop .xlsx
    ver = "unknown"
    for v in ("2022", "2014"):
        if stem.endswith("_" + v):
            stem = stem[: -(len(v) + 1)]
            ver = v
            break
    return stem, ver


# ---------------------------------------------------------------------------
# graph build
# ---------------------------------------------------------------------------
def build_graph() -> dict:
    if not os.path.isdir(CATALOGUE):
        raise FileNotFoundError(f"catalogue folder not found: {CATALOGUE}")
    files = sorted(f for f in os.listdir(CATALOGUE) if f.endswith(".xlsx"))
    log(f"catalogue: {len(files)} section workbooks in {CATALOGUE}")

    nodes: list[dict] = []
    edges: list[dict] = []
    section_keys: dict[str, list[str]] = {}

    def add_node(nid, ntype, **attrs):
        nodes.append({"id": nid, "type": ntype, **attrs})

    # version nodes
    for v in ("2014", "2022"):
        add_node(f"version:{v}", "Version", label=v)

    exceptions_file = None
    parsed = 0
    for fn in files:
        if fn.lower().startswith("exceptions"):
            exceptions_file = fn
            continue
        section, ver = section_name_from_file(fn)
        path = os.path.join(CATALOGUE, fn)
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as e:
            log(f"  WARN cannot open {fn}: {type(e).__name__}: {e}")
            continue

        sheets = wb.sheetnames
        rules = parse_general_rules(wb[GENERAL_RULES]) if GENERAL_RULES in sheets else {}
        cols = parse_column_info(wb[COLUMN_INFO]) if COLUMN_INFO in sheets else []
        pks = [c["column"] for c in cols if c["is_primary_key"]]
        if pks:
            section_keys[section] = pks

        sec_id = f"section:{section}:{ver}"
        add_node(
            sec_id, "Section",
            label=section, version=ver,
            new_records_allowed=rules.get("Are new records allowed?", rules.get("Are new records allowed? ")),
            severity_new=rules.get("Severity for new records"),
            severity_missing=rules.get("Severity for missing records"),
            sheets=sheets,
            fingerprint={sh: _sheet_fingerprint(wb[sh]) for sh in sheets},
        )
        edges.append({"src": sec_id, "dst": f"version:{ver}", "rel": "OF_VERSION"})

        for c in cols:
            col_id = f"column:{section}:{ver}:{c['column']}"
            add_node(col_id, "Column", label=c["column"], prompt=c["prompt"],
                     audited=c["audited"], is_primary_key=c["is_primary_key"],
                     severity=c["severity"])
            rel = "HAS_KEY" if c["is_primary_key"] else "HAS_COLUMN"
            edges.append({"src": sec_id, "dst": col_id, "rel": rel})
        parsed += 1

    # exceptions (accepted deviations) -> link to sections by GUI Screen
    if exceptions_file:
        try:
            wb = openpyxl.load_workbook(os.path.join(CATALOGUE, exceptions_file),
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
                exc_id = f"exception:{screen}:{entry}:{n_exc}"
                add_node(exc_id, "Exception", screen=screen, entry=entry,
                         deviation_type=str(r[di]).strip() if di is not None and len(r) > di and r[di] is not None else None,
                         where_allowed=str(r[wi]).strip() if wi is not None and len(r) > wi and r[wi] is not None else None,
                         rationale=str(r[ci]).strip() if ci is not None and len(r) > ci and r[ci] is not None else None)
                # link to the 2022 section with the matching GUI screen name
                edges.append({"src": exc_id, "dst": f"section:{screen}:2022", "rel": "ACCEPTED_FOR"})
                n_exc += 1
            log(f"exceptions: {n_exc} accepted deviations from {exceptions_file}")
        except Exception as e:
            log(f"  WARN exceptions parse failed: {type(e).__name__}: {e}")

    graph = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "catalogue": CATALOGUE,
        "counts": {
            "sections_parsed": parsed,
            "nodes": len(nodes),
            "edges": len(edges),
            "sections_with_keys": len(section_keys),
        },
        "section_keys": section_keys,
        "nodes": nodes,
        "edges": edges,
    }
    log(f"graph: {len(nodes)} nodes, {len(edges)} edges, {len(section_keys)} sections with PK definitions")
    return graph


# ---------------------------------------------------------------------------
# snapshot + diff (weekly change capture)
# ---------------------------------------------------------------------------
def snapshot_from_graph(graph: dict) -> dict:
    """Reduce a graph to a comparable fingerprint per section (+ key list)."""
    snap = {}
    for n in graph["nodes"]:
        if n["type"] == "Section":
            snap[n["id"]] = {
                "new_records_allowed": n.get("new_records_allowed"),
                "severity_new": n.get("severity_new"),
                "severity_missing": n.get("severity_missing"),
                "fingerprint": n.get("fingerprint", {}),
            }
    return {"generated": graph["generated"], "section_keys": graph["section_keys"], "sections": snap}


def diff_snapshots(a: dict, b: dict) -> None:
    sa, sb = a["sections"], b["sections"]
    added = sorted(set(sb) - set(sa))
    removed = sorted(set(sa) - set(sb))
    log(f"DIFF  A={a.get('generated')}  ->  B={b.get('generated')}")
    for s in added:
        print(f"  + SECTION ADDED: {s}")
    for s in removed:
        print(f"  - SECTION REMOVED: {s}")
    changed = 0
    for s in sorted(set(sa) & set(sb)):
        ra, rb = sa[s], sb[s]
        difffields = [k for k in ("new_records_allowed", "severity_new", "severity_missing")
                      if ra.get(k) != rb.get(k)]
        # which sheets changed content
        fa, fb = ra.get("fingerprint", {}), rb.get("fingerprint", {})
        sheets_changed = sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))
        if difffields or sheets_changed:
            changed += 1
            print(f"  ~ {s}")
            for k in difffields:
                print(f"       rule {k}: {ra.get(k)!r} -> {rb.get(k)!r}")
            if sheets_changed:
                print(f"       sheets changed: {', '.join(sheets_changed)}")
    # key-structure changes
    ka, kb = a.get("section_keys", {}), b.get("section_keys", {})
    for s in sorted(set(ka) | set(kb)):
        if ka.get(s) != kb.get(s):
            print(f"  ! KEY STRUCTURE {s}: {ka.get(s)} -> {kb.get(s)}")
    log(f"DIFF done: {len(added)} added, {len(removed)} removed, {changed} changed")


# ---------------------------------------------------------------------------
# Neo4j export (CSV + LOAD CSV cypher) for Neo4j Desktop
# ---------------------------------------------------------------------------
# Scalar property columns kept per node label (complex props like fingerprint dict are
# dropped from the CSV; sheets list is pipe-joined). id is the unique key used for MATCHes.
NEO4J_NODE_SPECS = {
    "Version":   ["id", "label"],
    "Section":   ["id", "label", "version", "new_records_allowed", "severity_new",
                  "severity_missing", "sheets"],
    "Column":    ["id", "label", "prompt", "audited", "is_primary_key", "severity"],
    "Exception": ["id", "screen", "entry", "deviation_type", "where_allowed", "rationale"],
}


def _neo4j_scalar(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    s = str(v)
    return "" if s == "None" else s


def export_neo4j(graph: dict) -> str:
    import csv

    out = os.path.join(OUT_DIR, "neo4j_import")
    os.makedirs(out, exist_ok=True)

    # one CSV per node label
    by_label: dict[str, list[dict]] = {lbl: [] for lbl in NEO4J_NODE_SPECS}
    for n in graph["nodes"]:
        if n["type"] in by_label:
            by_label[n["type"]].append(n)

    for label, spec in NEO4J_NODE_SPECS.items():
        fn = os.path.join(out, f"{label.lower()}.csv")
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(spec)
            for n in by_label[label]:
                w.writerow([_neo4j_scalar(n.get(c)) for c in spec])
        log(f"neo4j: wrote {label.lower()}.csv ({len(by_label[label])} rows)")

    # relationships CSV (typed by rel)
    rel_fn = os.path.join(out, "rels.csv")
    with open(rel_fn, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["src", "dst", "rel"])
        for e in graph["edges"]:
            w.writerow([e["src"], e["dst"], e["rel"]])
    log(f"neo4j: wrote rels.csv ({len(graph['edges'])} rows)")

    # load.cypher — paste into Neo4j Browser (files must be in the DBMS import folder)
    cypher = f"""// PrIME Config Drift catalogue — Neo4j load script
// Generated {graph['generated']}
//
// HOW TO RUN (Neo4j Desktop):
// 1. In Neo4j Desktop, open your DBMS -> "..." -> Open folder -> Import.
//    Copy ALL *.csv from this neo4j_import folder into that DBMS 'import' folder.
// 2. Start the DBMS, open Neo4j Browser.
// 3. Paste this whole script and run (or use  :source load.cypher ).

// --- clean slate (optional; comment out to keep existing data) ---
MATCH (n) DETACH DELETE n;

// --- uniqueness constraints (also speeds up the MATCHes below) ---
CREATE CONSTRAINT version_id  IF NOT EXISTS FOR (v:Version)   REQUIRE v.id IS UNIQUE;
CREATE CONSTRAINT section_id  IF NOT EXISTS FOR (s:Section)   REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT column_id   IF NOT EXISTS FOR (c:Column)    REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT exception_id IF NOT EXISTS FOR (e:Exception) REQUIRE e.id IS UNIQUE;

// --- nodes ---
LOAD CSV WITH HEADERS FROM 'file:///version.csv' AS row
CREATE (:Version {{id: row.id, label: row.label}});

LOAD CSV WITH HEADERS FROM 'file:///section.csv' AS row
CREATE (:Section {{
  id: row.id, label: row.label, version: row.version,
  new_records_allowed: row.new_records_allowed,
  severity_new: row.severity_new, severity_missing: row.severity_missing,
  sheets: row.sheets
}});

LOAD CSV WITH HEADERS FROM 'file:///column.csv' AS row
CREATE (:Column {{
  id: row.id, label: row.label, prompt: row.prompt,
  audited: row.audited,
  is_primary_key: (row.is_primary_key = 'true'),
  severity: row.severity
}});

LOAD CSV WITH HEADERS FROM 'file:///exception.csv' AS row
CREATE (:Exception {{
  id: row.id, screen: row.screen, entry: row.entry,
  deviation_type: row.deviation_type, where_allowed: row.where_allowed,
  rationale: row.rationale
}});

// --- relationships (typed by the 'rel' column) ---
LOAD CSV WITH HEADERS FROM 'file:///rels.csv' AS row
CALL {{
  WITH row
  MATCH (a {{id: row.src}})
  MATCH (b {{id: row.dst}})
  CALL apoc.create.relationship(a, row.rel, {{}}, b) YIELD rel
  RETURN rel
}} IN TRANSACTIONS OF 500 ROWS;

// If you do NOT have the APOC plugin, replace the block above with these 4 statements:
// LOAD CSV WITH HEADERS FROM 'file:///rels.csv' AS row WITH row WHERE row.rel='OF_VERSION'
//   MATCH (a {{id:row.src}}),(b {{id:row.dst}}) CREATE (a)-[:OF_VERSION]->(b);
// LOAD CSV WITH HEADERS FROM 'file:///rels.csv' AS row WITH row WHERE row.rel='HAS_KEY'
//   MATCH (a {{id:row.src}}),(b {{id:row.dst}}) CREATE (a)-[:HAS_KEY]->(b);
// LOAD CSV WITH HEADERS FROM 'file:///rels.csv' AS row WITH row WHERE row.rel='HAS_COLUMN'
//   MATCH (a {{id:row.src}}),(b {{id:row.dst}}) CREATE (a)-[:HAS_COLUMN]->(b);
// LOAD CSV WITH HEADERS FROM 'file:///rels.csv' AS row WITH row WHERE row.rel='ACCEPTED_FOR'
//   MATCH (a {{id:row.src}}),(b {{id:row.dst}}) CREATE (a)-[:ACCEPTED_FOR]->(b);

// --- handy views to try after loading ---
// Policy Maintenance and its primary-key columns:
//   MATCH (s:Section {{label:'Policy Maintenance', version:'2022'}})-[:HAS_KEY]->(c) RETURN s,c;
// Sections that do NOT allow new records (high-risk if a new record appears):
//   MATCH (s:Section) WHERE s.new_records_allowed = 'no' RETURN s.label, s.severity_new;
// Accepted exceptions per section:
//   MATCH (e:Exception)-[:ACCEPTED_FOR]->(s:Section) RETURN s.label, count(e) ORDER BY count(e) DESC;
"""
    with open(os.path.join(out, "load.cypher"), "w", encoding="utf-8") as f:
        f.write(cypher)
    log(f"neo4j: wrote load.cypher in {out}")
    return out


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="PrIME config catalogue -> knowledge graph")
    ap.add_argument("--build", action="store_true", help="parse folder -> graph.json + keys + snapshot")
    ap.add_argument("--neo4j", action="store_true", help="also export Neo4j CSVs + load.cypher")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"), help="diff two snapshot json files")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    if args.diff:
        a = json.load(open(args.diff[0], encoding="utf-8"))
        b = json.load(open(args.diff[1], encoding="utf-8"))
        # accept either full graph or snapshot
        a = a if "sections" in a else snapshot_from_graph(a)
        b = b if "sections" in b else snapshot_from_graph(b)
        diff_snapshots(a, b)
        return 0

    # default: build
    log("=== catalogue graph BUILD ===")
    graph = build_graph()
    with open(os.path.join(OUT_DIR, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, default=str)
    with open(os.path.join(OUT_DIR, "section_keys.json"), "w", encoding="utf-8") as f:
        json.dump(graph["section_keys"], f, indent=2)
    snap = snapshot_from_graph(graph)
    snap_name = f"snapshot_{datetime.date.today():%Y%m%d}.json"
    with open(os.path.join(OUT_DIR, snap_name), "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, default=str)
    log(f"wrote graph.json, section_keys.json, {snap_name} in {OUT_DIR}")

    if args.neo4j:
        export_neo4j(graph)

    log("=== DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
