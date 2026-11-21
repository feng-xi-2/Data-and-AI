"""cfg_decision — the HUMAN DECISION LAYER for discovered missing CFG-RFCs.

WHY THIS EXISTS
---------------
discover_missing_cfg.py PROPOSES the CFG-RFC that most likely governs an accepted-but-unbacked
deviation, with graded grounding (STRONG / MODERATE / EMERGING / NONE). A proposal is NOT a
decision. P&G CoE governance requires a HUMAN to confirm which CFG-RFC actually applies before
an acceptance is treated as governed. This module is that gate: a reviewer reads the grounding
and records ACCEPT / REJECT / REASSIGN. Nothing is auto-applied; every decision is accountable
(who + when + why) and append-only audited.

THE DECISION VOCABULARY
-----------------------
  ACCEPT     the discovered CFG-RFC is correct -> attach it to the acceptance.
             (STRONG/MODERATE candidates. Requires the candidate to exist.)
  REASSIGN   a different CFG-RFC governs it -> supply --cfg CFGxxxx.
  RAISE      no CFG-RFC governs it yet -> a new one must be raised -> supply --cfg (the new id)
             or leave blank to mark 'to be raised'.
  REJECT     this should NOT be an accepted exception -> re-open the deviation (fix to standard).
  DEFER      needs more investigation -> stays actionable, with a note.

GUARDRAILS (governance, enforced here)
--------------------------------------
  * every decision REQUIRES --by (the reviewer id) — no anonymous governance.
  * ACCEPT on a NONE/EMERGING candidate is refused — the evidence is too weak to rubber-stamp;
    the reviewer must REASSIGN/RAISE with an explicit --cfg instead.
  * REASSIGN/RAISE(with id) validate the CFG against the register and WARN if it is missing or
    withdrawn/superseded (a decision may still proceed, but the warning is recorded).
  * decisions are written to an append-only AUDIT log; the queue only ever reflects the latest.

STORAGE
-------
  _replica_drift/cfg_decisions.jsonl        the QUEUE (one line per candidate; status updated)
  _replica_drift/cfg_decision_audit.jsonl   append-only AUDIT trail (one line per decision event)
  Config report/cfg_decisions_applied.csv   (on `export`) the human-approved CFG attachments,
                                            ready to feed back into the drift acceptance data.

USAGE
  python cfg_decision.py stats
  python cfg_decision.py list --strength STRONG --limit 20
  python cfg_decision.py list --site "Ahmedabad" --method PEER_PRECEDENT
  python cfg_decision.py show <id>
  python cfg_decision.py decide <id> --verdict ACCEPT   --by fc7262 --note "confirmed vs library"
  python cfg_decision.py decide <id> --verdict REASSIGN --cfg CFG1601 --by fc7262
  python cfg_decision.py decide <id> --verdict RAISE    --cfg CFG9001 --by fc7262 --note "new RFC drafted"
  python cfg_decision.py decide <id> --verdict REJECT   --by fc7262 --note "typo, fix to standard"
  python cfg_decision.py export      # re-emit CSV/JS reflecting decisions + applied-attachments CSV

Follows workspace rules: timestamped logs; no silent failure (log type+message then raise);
atomic queue write; append-only audit; fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
APPLIED_CSV = os.path.join(ONEDRIVE, "Config report", "cfg_decisions_applied.csv")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
QUEUE = os.path.join(OUT_DIR, "cfg_decisions.jsonl")
AUDIT = os.path.join(OUT_DIR, "cfg_decision_audit.jsonl")

CFG_RE = re.compile(r"^CFG\d+$", re.IGNORECASE)
VERDICTS = {"ACCEPT", "REASSIGN", "RAISE", "REJECT", "DEFER"}
DEAD = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def read_text(path: str) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except FileNotFoundError:
            return ""
        except UnicodeDecodeError:
            continue
    return ""


def load_register() -> dict:
    reg = {}
    text = read_text(CRFC)
    if not text:
        return reg
    code_re = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
    for row in csv.DictReader(text.splitlines()):
        blob = " ".join(str(row.get(k) or "") for k in ("Code", "Title"))
        m = code_re.search(blob)
        if not m:
            continue
        code = m.group(0).upper()
        status = (row.get("Request Status") or "").strip()
        reg[code] = {
            "title": (row.get("Title") or "").strip(),
            "status": status,
            "valid": status.lower() not in DEAD,
        }
    return reg


def load_queue() -> list[dict]:
    if not os.path.exists(QUEUE):
        log(f"ERROR queue not found: {QUEUE}. Run discover_missing_cfg.py first.")
        raise SystemExit(2)
    out = []
    with open(QUEUE, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                log(f"WARN skipping corrupt queue line {ln}: {e}")
    return out


def save_queue(items: list[dict]) -> None:
    tmp = QUEUE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        os.replace(tmp, QUEUE)
    except Exception as e:
        log(f"ERROR failed to save queue: {type(e).__name__}: {e}")
        raise


def append_audit(event: dict) -> None:
    try:
        with open(AUDIT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"ERROR failed to append audit: {type(e).__name__}: {e}")
        raise


# --------------------------------------------------------------------------- #
#  commands                                                                    #
# --------------------------------------------------------------------------- #
def cmd_stats(_args) -> int:
    items = load_queue()
    from collections import Counter
    status = Counter(i.get("status", "PENDING") for i in items)
    strength = Counter(i.get("strength", "NONE") for i in items)
    method = Counter(i.get("method", "NONE") for i in items)
    pend = [i for i in items if i.get("status") == "PENDING"]
    log(f"total candidates      : {len(items)}")
    log(f"status                : " + ", ".join(f"{k} {v}" for k, v in status.most_common()))
    log(f"strength (all)        : " + ", ".join(f"{k} {v}" for k, v in strength.most_common()))
    log(f"method (all)          : " + ", ".join(f"{k} {v}" for k, v in method.most_common()))
    ps = Counter(i.get("strength") for i in pend)
    log(f"PENDING by strength   : " + ", ".join(f"{k} {v}" for k, v in ps.most_common()))
    log("Tip: work STRONG then MODERATE first (highest-confidence, quickest wins).")
    return 0


def _match(it: dict, args) -> bool:
    if args.status and it.get("status", "PENDING").upper() != args.status.upper():
        return False
    if args.strength and it.get("strength", "").upper() != args.strength.upper():
        return False
    if args.method and it.get("method", "").upper() != args.method.upper():
        return False
    if args.site and args.site.lower() not in str(it.get("site", "")).lower():
        return False
    return True


def cmd_list(args) -> int:
    items = load_queue()
    rank = {"STRONG": 0, "MODERATE": 1, "EMERGING": 2, "NONE": 3}
    sel = [i for i in items if _match(i, args)]
    sel.sort(key=lambda x: (rank.get(x.get("strength"), 9), x.get("site", "")))
    if args.limit:
        sel = sel[: args.limit]
    if not sel:
        log("no candidates match.")
        return 0
    log(f"{len(sel)} candidate(s):")
    for it in sel:
        ident = it.get("identity", [])
        el = ident[1] if len(ident) > 1 else ""
        print(f"  {it['id']}  [{it.get('strength'):8}] {it.get('method'):16} "
              f"{str(it.get('site'))[:16]:16} -> {it.get('discovered_cfg') or '(none)':8} "
              f"| {str(el)[:40]}  [{it.get('status','PENDING')}]")
    return 0


def cmd_show(args) -> int:
    items = load_queue()
    it = next((i for i in items if i["id"] == args.id), None)
    if not it:
        log(f"id not found: {args.id}")
        return 1
    ident = it.get("identity", [])
    labels = ["Section", "Element", "Attribute", "A value", "R value", "Type"]
    print("=" * 84)
    print(f"Decision {it['id']}   status={it.get('status','PENDING')}")
    print("=" * 84)
    print(f"  site            : {it.get('site')}")
    for lab, val in zip(labels, ident):
        print(f"  {lab:15} : {val}")
    print(f"  discovered CFG  : {it.get('discovered_cfg') or '(none)'}")
    print(f"  candidates      : {', '.join(it.get('candidates', []))}")
    print(f"  method          : {it.get('method')}")
    print(f"  strength        : {it.get('strength')}")
    print(f"  evidence        : {it.get('evidence')}")
    print(f"  suggested       : {it.get('suggested')}")
    if it.get("status") != "PENDING":
        print(f"  --- decided ---")
        print(f"  verdict         : {it.get('status')}")
        print(f"  decided CFG     : {it.get('decided_cfg')}")
        print(f"  decided by/on   : {it.get('decided_by')} / {it.get('decided_on')}")
        print(f"  note            : {it.get('note')}")
    return 0


def cmd_decide(args) -> int:
    verdict = args.verdict.upper()
    if verdict not in VERDICTS:
        log(f"ERROR verdict must be one of {sorted(VERDICTS)}")
        return 2
    if not args.by:
        log("ERROR --by <reviewer> is required (governance: no anonymous decisions).")
        return 2
    items = load_queue()
    idx = next((n for n, i in enumerate(items) if i["id"] == args.id), None)
    if idx is None:
        log(f"id not found: {args.id}")
        return 1
    it = items[idx]
    reg = load_register()
    cfg = (args.cfg or "").upper().strip()

    if verdict in ("REASSIGN", "RAISE") and not cfg and verdict == "REASSIGN":
        log("ERROR REASSIGN requires --cfg CFGxxxx.")
        return 2
    if cfg and not CFG_RE.match(cfg):
        log(f"ERROR --cfg must look like CFG1234 (got {cfg!r}).")
        return 2

    decided_cfg = ""
    warn = ""
    if verdict == "ACCEPT":
        if it.get("strength") in ("NONE", "EMERGING"):
            log(f"REFUSED: cannot ACCEPT a {it.get('strength')} candidate — evidence too weak to "
                f"rubber-stamp. Use REASSIGN/RAISE with an explicit --cfg, or REJECT.")
            return 3
        decided_cfg = it.get("discovered_cfg", "")
        if not decided_cfg:
            log("REFUSED: no discovered CFG to accept. Use REASSIGN/RAISE.")
            return 3
    elif verdict in ("REASSIGN", "RAISE"):
        decided_cfg = cfg
    elif verdict in ("REJECT", "DEFER"):
        decided_cfg = ""

    if decided_cfg:
        rec = reg.get(decided_cfg)
        if not rec:
            warn = f"CFG {decided_cfg} is NOT in the register (governance gap — ensure it will be added)."
        elif not rec["valid"]:
            warn = f"CFG {decided_cfg} is {rec['status']} in the register (not currently live)."
    if warn:
        log("WARNING: " + warn)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    it["status"] = verdict
    it["decided_cfg"] = decided_cfg
    it["decided_by"] = args.by
    it["decided_on"] = now
    it["note"] = args.note or ""
    items[idx] = it
    save_queue(items)
    append_audit({
        "ts": now, "id": it["id"], "verdict": verdict, "decided_cfg": decided_cfg,
        "by": args.by, "note": args.note or "", "warning": warn,
        "site": it.get("site"), "identity": it.get("identity"),
        "was_discovered": it.get("discovered_cfg"), "strength": it.get("strength"),
        "method": it.get("method"),
    })
    log(f"recorded {verdict} on {it['id']} by {args.by}"
        + (f" -> {decided_cfg}" if decided_cfg else "")
        + (f"  [{warn}]" if warn else ""))
    return 0


def cmd_export(_args) -> int:
    """Write the human-approved attachments to a feed-back CSV."""
    items = load_queue()
    applied = [i for i in items if i.get("status") in ("ACCEPT", "REASSIGN", "RAISE") and i.get("decided_cfg")]
    reopened = [i for i in items if i.get("status") == "REJECT"]
    cols = ["Decision ID", "Site", "Section", "Element", "Attribute", "A value", "R value",
            "Type", "Approved CFG-RFC", "Verdict", "Decided by", "Decided on", "Note",
            "Original discovery", "Strength", "Method"]
    rows = []
    for it in applied:
        ident = (it.get("identity", []) + [""] * 6)[:6]
        rows.append({
            "Decision ID": it["id"], "Site": it.get("site"),
            "Section": ident[0], "Element": ident[1], "Attribute": ident[2],
            "A value": ident[3], "R value": ident[4], "Type": ident[5],
            "Approved CFG-RFC": it.get("decided_cfg"), "Verdict": it.get("status"),
            "Decided by": it.get("decided_by"), "Decided on": it.get("decided_on"),
            "Note": it.get("note"), "Original discovery": it.get("discovered_cfg"),
            "Strength": it.get("strength"), "Method": it.get("method"),
        })
    try:
        with open(APPLIED_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    except Exception as e:
        log(f"ERROR failed to write {APPLIED_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {APPLIED_CSV} ({len(rows)} approved attachments; {len(reopened)} re-opened/REJECT)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="progress dashboard")

    p = sub.add_parser("list", help="list candidates")
    p.add_argument("--status", default="PENDING")
    p.add_argument("--strength", default="")
    p.add_argument("--method", default="")
    p.add_argument("--site", default="")
    p.add_argument("--limit", type=int, default=40)

    p = sub.add_parser("show", help="show one candidate's full grounding")
    p.add_argument("id")

    p = sub.add_parser("decide", help="record a human decision")
    p.add_argument("id")
    p.add_argument("--verdict", required=True, help="ACCEPT | REASSIGN | RAISE | REJECT | DEFER")
    p.add_argument("--cfg", default="", help="CFG-RFC id for REASSIGN/RAISE")
    p.add_argument("--by", required=True, help="reviewer id (accountability)")
    p.add_argument("--note", default="", help="short justification")

    sub.add_parser("export", help="write approved attachments to cfg_decisions_applied.csv")

    args = ap.parse_args()
    return {
        "stats": cmd_stats, "list": cmd_list, "show": cmd_show,
        "decide": cmd_decide, "export": cmd_export,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
