"""change_watch — detect when the inputs change and let the graph + explainer catch up.

WHY THIS EXISTS (Raquel's ask #1 + #2)
--------------------------------------
The Config Drift pipeline is grounded on three moving inputs:

  1. the CFG-RFC register CSV        (the approved changes / exceptions "exceptions file")
  2. the SharePoint knowledge pages  (the Configuration-Change-Process / CoE docs)
  3. the Config Drift output CSV(s)   (the per-site deviation dumps the script compares)

All three are updated periodically (the register whenever a change is approved, SharePoint
whenever the process docs change, the CSVs on every Azure run). If nothing watches them, the
graph and the AI explanations silently go stale. This module takes a content FINGERPRINT of
each input, stores it in a manifest, and on the next scan reports EXACTLY what changed:

  * register CSV changed        -> rebuild the CFG-RFC graph (crfc_register --build --neo4j)
  * SharePoint pages changed    -> the "knowledge version" bumps, so the LLM explain cache
                                   invalidates for affected rows and re-grounds (see
                                   explain_deviations.knowledge_version()).
  * drift CSV changed           -> re-run enrich/explain on the new dump.

It is deliberately dependency-free (hashlib/json/os/glob), fingerprints by content sha1 (not
just mtime, which is unreliable on OneDrive), and never fails silently: every step logs a
timestamped line and any error is logged with type+message then surfaced.

CLI
  python change_watch.py --scan            # report what changed since the last manifest
  python change_watch.py --update          # accept current state as the new baseline
  python change_watch.py --apply           # scan, and if the register changed rebuild the graph
  python change_watch.py --knowledge        # print the current knowledge fingerprint
"""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
MANIFEST = os.path.join(OUT_DIR, "change_manifest.json")

# ---- watched inputs (env-overridable) --------------------------------------
# The register + drift CSVs live in the OneDrive copy's "Config report" folder;
# the SharePoint cache is written next to this script (_sharepoint/).
_ONEDRIVE_MM = os.environ.get(
    "MM_ONEDRIVE_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_REPORT_DIR = os.environ.get(
    "CONFIG_REPORT_DIR", os.path.join(_ONEDRIVE_MM, "Config report"))
REGISTER_CSV = os.environ.get(
    "REGISTER_CSV", os.path.join(CONFIG_REPORT_DIR, "Configuration_RFC.csv"))
SP_PAGES = os.environ.get(
    "SP_PAGES_JSON", os.path.join(BASE, "_sharepoint", "sharepoint_pages.json"))
# derived artefacts the graph is built from (so we can tell if a rebuild is pending)
CRFC_JSON = os.path.join(OUT_DIR, "crfc_register.json")


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] change_watch: {msg}", flush=True)


# --------------------------------------------------------------------------- #
#  fingerprint primitives                                                     #
# --------------------------------------------------------------------------- #
def _sha1_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _fp_file(path: str) -> dict:
    """Content fingerprint of a single file (sha1 + size + mtime)."""
    try:
        if not os.path.exists(path):
            return {"exists": False, "path": path}
        st = os.stat(path)
        return {"exists": True, "path": path, "size": st.st_size,
                "mtime": round(st.st_mtime, 3), "sha1": _sha1_file(path)}
    except Exception as e:
        log(f"ERROR fingerprinting {path}: {type(e).__name__}: {e}")
        return {"exists": False, "path": path, "error": f"{type(e).__name__}: {e}"}


def _fp_sharepoint(sp_json: str) -> dict:
    """Per-page fingerprint of the SharePoint cache: {file: {modified, len, hash}}.

    The page hash is over the extracted text so a real content edit changes it even if the
    Modified timestamp is unreliable; the digest rolls all pages into one short value used
    as the SharePoint half of the knowledge fingerprint.
    """
    try:
        if not os.path.exists(sp_json):
            return {"exists": False, "path": sp_json, "pages": {}, "count": 0, "digest": ""}
        with open(sp_json, encoding="utf-8") as f:
            data = json.load(f)
        pages = data.get("pages", data if isinstance(data, list) else [])
        out = {}
        for p in pages:
            key = p.get("file") or p.get("url") or p.get("title") or ""
            if not key:
                continue
            text = p.get("text") or ""
            out[key] = {
                "modified": p.get("modified", ""),
                "len": int(p.get("textLen", len(text)) or 0),
                "hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
            }
        rolled = "|".join(f"{k}:{v['hash']}" for k, v in sorted(out.items()))
        digest = hashlib.sha1(rolled.encode("utf-8")).hexdigest()
        return {"exists": True, "path": sp_json, "generated": data.get("generated"),
                "pages": out, "count": len(out), "digest": digest}
    except Exception as e:
        log(f"ERROR fingerprinting SharePoint {sp_json}: {type(e).__name__}: {e}")
        return {"exists": False, "path": sp_json, "pages": {}, "count": 0,
                "digest": "", "error": f"{type(e).__name__}: {e}"}


def _fp_drift_csvs(folder: str) -> dict:
    """Fingerprint every Config Drift CSV/XLSX in the report folder (excludes the register)."""
    files = {}
    try:
        cand = glob.glob(os.path.join(folder, "*.csv")) + glob.glob(os.path.join(folder, "*.xlsx"))
        for path in sorted(cand):
            name = os.path.basename(path)
            if os.path.abspath(path) == os.path.abspath(REGISTER_CSV):
                continue  # the register is watched separately
            files[name] = _fp_file(path)
    except Exception as e:
        log(f"ERROR scanning drift folder {folder}: {type(e).__name__}: {e}")
    return {"folder": folder, "files": files, "count": len(files)}


# --------------------------------------------------------------------------- #
#  fingerprint bundle + knowledge version                                     #
# --------------------------------------------------------------------------- #
def build_fingerprint() -> dict:
    """Take a full fingerprint of every watched input right now."""
    fp = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "register": _fp_file(REGISTER_CSV),
        "sharepoint": _fp_sharepoint(SP_PAGES),
        "drift": _fp_drift_csvs(CONFIG_REPORT_DIR),
        "crfc_json": _fp_file(CRFC_JSON),
    }
    fp["knowledge"] = knowledge_digest(fp)
    return fp


def knowledge_digest(fp: dict) -> str:
    """Short stable hash of the GROUNDING knowledge = register content + SharePoint content.

    This is the value the explainer stamps into its LLM cache key: when a new CFG-RFC is
    approved (register changes) or a process page is edited (SharePoint changes), the digest
    changes and stale explanations are re-grounded instead of served from cache.
    """
    reg = (fp.get("register") or {}).get("sha1", "")
    sp = (fp.get("sharepoint") or {}).get("digest", "")
    return hashlib.sha1(f"reg:{reg}|sp:{sp}".encode("utf-8")).hexdigest()[:16]


def current_knowledge_version() -> str:
    """Compute the knowledge fingerprint from the live inputs (no manifest needed)."""
    return knowledge_digest({
        "register": _fp_file(REGISTER_CSV),
        "sharepoint": _fp_sharepoint(SP_PAGES),
    })


# --------------------------------------------------------------------------- #
#  manifest IO                                                                 #
# --------------------------------------------------------------------------- #
def load_manifest() -> dict | None:
    if not os.path.exists(MANIFEST):
        return None
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"manifest unreadable ({type(e).__name__}: {e}); treating as first run")
        return None


def save_manifest(fp: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fp, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANIFEST)
    log(f"manifest updated -> {MANIFEST} (knowledge={fp.get('knowledge')})")


# --------------------------------------------------------------------------- #
#  diff                                                                        #
# --------------------------------------------------------------------------- #
def _file_changed(old: dict | None, new: dict | None) -> bool:
    o = (old or {}).get("sha1"), (old or {}).get("exists")
    n = (new or {}).get("sha1"), (new or {}).get("exists")
    return o != n


def _sp_delta(old: dict, new: dict) -> dict:
    op = (old or {}).get("pages", {}) or {}
    np_ = (new or {}).get("pages", {}) or {}
    added = sorted(set(np_) - set(op))
    removed = sorted(set(op) - set(np_))
    changed = sorted(k for k in set(op) & set(np_) if op[k].get("hash") != np_[k].get("hash"))
    return {"added": added, "removed": removed, "changed": changed,
            "digestChanged": (old or {}).get("digest") != (new or {}).get("digest")}


def scan() -> dict:
    """Compare the live inputs to the stored manifest and report the deltas."""
    new = build_fingerprint()
    old = load_manifest()
    if old is None:
        return {
            "firstRun": True, "anyChange": True,
            "knowledge": {"old": None, "new": new["knowledge"], "changed": True},
            "register": {"changed": True, "reason": "no baseline"},
            "sharepoint": {"changed": True, "added": list((new["sharepoint"].get("pages") or {}).keys()),
                           "removed": [], "changed_pages": []},
            "drift": {"changed": True,
                      "added": list((new["drift"].get("files") or {}).keys()),
                      "removed": [], "changed_files": []},
            "graphRebuildNeeded": True,
            "current": new,
        }

    reg_changed = _file_changed(old.get("register"), new.get("register"))
    sp = _sp_delta(old.get("sharepoint", {}), new.get("sharepoint", {}))
    sp_changed = bool(sp["added"] or sp["removed"] or sp["changed"] or sp["digestChanged"])

    old_df = (old.get("drift") or {}).get("files", {}) or {}
    new_df = (new.get("drift") or {}).get("files", {}) or {}
    df_added = sorted(set(new_df) - set(old_df))
    df_removed = sorted(set(old_df) - set(new_df))
    df_changed = sorted(k for k in set(old_df) & set(new_df)
                        if _file_changed(old_df[k], new_df[k]))
    drift_changed = bool(df_added or df_removed or df_changed)

    know_changed = old.get("knowledge") != new.get("knowledge")

    return {
        "firstRun": False,
        "anyChange": reg_changed or sp_changed or drift_changed,
        "knowledge": {"old": old.get("knowledge"), "new": new.get("knowledge"),
                      "changed": know_changed},
        "register": {"changed": reg_changed,
                     "oldSha1": (old.get("register") or {}).get("sha1"),
                     "newSha1": (new.get("register") or {}).get("sha1")},
        "sharepoint": {"changed": sp_changed, "added": sp["added"],
                       "removed": sp["removed"], "changed_pages": sp["changed"]},
        "drift": {"changed": drift_changed, "added": df_added,
                  "removed": df_removed, "changed_files": df_changed},
        # a register change (approved CFG-RFC) means the CFG-RFC graph must be rebuilt
        "graphRebuildNeeded": reg_changed,
        "current": new,
    }


# --------------------------------------------------------------------------- #
#  apply: rebuild the graph when the register changed                          #
# --------------------------------------------------------------------------- #
def rebuild_graph() -> dict:
    """Rebuild the CFG-RFC register + graph JSON and (best-effort) load Neo4j."""
    log("rebuilding CFG-RFC graph from the changed register…")
    try:
        import crfc_register as cr
    except Exception as e:
        log(f"ERROR importing crfc_register: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        reg = cr.load_register(REGISTER_CSV)
        graph = cr.build_nodes(reg)
        # persist register + graph JSON (mirrors crfc_register --build)
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(CRFC_JSON, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        with open(os.path.join(OUT_DIR, "crfc_graph.json"), "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        counts = graph.get("counts", {})
        log(f"graph JSON rebuilt: {counts}")
        neo = {"loaded": False}
        try:
            cr.load_neo4j(graph)
            neo = {"loaded": True}
        except Exception as e:
            log(f"Neo4j load skipped/failed ({type(e).__name__}: {e})")
            neo = {"loaded": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": True, "codes": len(reg), "counts": counts, "neo4j": neo}
    except Exception as e:
        log(f"ERROR rebuilding graph: {type(e).__name__}: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def apply_changes(auto_update: bool = True) -> dict:
    """Scan, rebuild the graph if the register changed, and refresh the baseline."""
    result = scan()
    actions = []
    if result.get("graphRebuildNeeded"):
        rb = rebuild_graph()
        actions.append({"action": "rebuild_graph", "result": rb})
    if result.get("knowledge", {}).get("changed"):
        actions.append({"action": "knowledge_bumped",
                        "note": "LLM explain cache will re-ground affected rows on next run",
                        "knowledge": result["knowledge"]["new"]})
    if auto_update:
        save_manifest(result["current"])
        actions.append({"action": "manifest_updated"})
    result["actions"] = actions
    return result


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #
def _print_scan(r: dict) -> None:
    log(f"first run: {r['firstRun']}   any change: {r['anyChange']}")
    log(f"knowledge version: {r['knowledge']['old']} -> {r['knowledge']['new']} "
        f"(changed={r['knowledge']['changed']})")
    reg = r["register"]
    log(f"register CSV changed: {reg['changed']}")
    sp = r["sharepoint"]
    log(f"SharePoint changed: {sp['changed']} "
        f"(+{len(sp['added'])} pages / -{len(sp['removed'])} / ~{len(sp['changed_pages'])})")
    if sp["changed_pages"][:8]:
        log(f"  changed pages: {', '.join(sp['changed_pages'][:8])}"
            + (" …" if len(sp["changed_pages"]) > 8 else ""))
    df = r["drift"]
    log(f"drift CSVs changed: {df['changed']} "
        f"(+{len(df['added'])} / -{len(df['removed'])} / ~{len(df['changed_files'])})")
    log(f"graph rebuild needed: {r['graphRebuildNeeded']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect input changes for the Config Drift graph/explainer")
    ap.add_argument("--scan", action="store_true", help="report what changed since the baseline")
    ap.add_argument("--update", action="store_true", help="accept current state as the new baseline")
    ap.add_argument("--apply", action="store_true",
                    help="scan + rebuild graph if the register changed + refresh baseline")
    ap.add_argument("--knowledge", action="store_true", help="print the current knowledge fingerprint")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    if args.knowledge:
        print(current_knowledge_version())
        return 0
    if args.apply:
        r = apply_changes(auto_update=True)
        _print_scan(r)
        for a in r.get("actions", []):
            log(f"action: {a.get('action')} -> {json.dumps(a.get('result', a), ensure_ascii=False)[:200]}")
        return 0
    if args.update:
        fp = build_fingerprint()
        save_manifest(fp)
        log("baseline set.")
        return 0
    # default: scan (read-only)
    r = scan()
    _print_scan(r)
    if not (args.scan):
        log("(read-only scan; use --update to set baseline, --apply to rebuild on change)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
