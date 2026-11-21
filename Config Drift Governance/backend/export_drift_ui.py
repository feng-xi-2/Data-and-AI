"""export_drift_ui — build a no-build JS data file for the UIUX Config Drift Actions page.

Reads the *_explained.csv (produced by explain_ij.py) and writes
UIUX/assets/drift-actions.js which sets window.WHS_DRIFT for the static page.

Per site it rolls up:
  - severity / deviation-type / exception-trail / recommended-action counts
  - a priority-bucketed action summary (P1 fix, P2 governance, P3 migration, monitor)
  - a capped set of representative rows per action (element, I/J, AI Info, explanation, grounding)

No network, no build step — mirrors the assets/data.js pattern.
Follows workspace rules: timestamped logs; no silent failure (log type+message then raise).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
from collections import Counter, defaultdict

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
DEFAULT_IN = os.path.join(ONEDRIVE, "Config report", "20260817_0038_ahm_output_explained.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "drift-actions.js")

# recommended-action verb -> (label, priority bucket, one-line meaning)
ACTION_META = {
    "FIX_NOW_HIGH":                 ("Fix now (HIGH)",            "P1", "High-severity open deviation — significant WMS impact."),
    "FIX_OR_RAISE_CFG_RFC":         ("Fix or raise CFG-RFC",      "P1", "Open functional mismatch — site value differs from the standard."),
    "ADD_STANDARD_OR_RAISE_CFG_RFC":("Add standard / CFG-RFC",    "P1", "Missing record — standard defines it, site lacks it."),
    "REMOVE_OR_RAISE_CFG_RFC":      ("Remove / productise",       "P1", "Unexpected record — extra site config not in the standard."),
    "REVIEW_STALE_EXCEPTION":       ("Review stale exception",    "P2", "Accepted, but the backing CFG-RFC is superseded/withdrawn."),
    "FIND_ORPHAN_TICKET":           ("Find orphan ticket",        "P2", "Accepted, cites a CFG not in the register."),
    "JUSTIFY_OR_REOPEN":            ("Justify or re-open",        "P2", "Accepted with no CFG-RFC recorded."),
    "FIX_BEFORE_MIGRATION":         ("Fix before migration",      "P3", "2014→2022 migration-only deviation."),
    "IGNORE_FORMATTING":            ("Ignore (formatting)",       "IGNORE", "Open, but formatting-only — no functional change."),
    "HEALTH_CHECK":                 ("Health check",              "MONITOR", "Health Score only, not Config Score."),
    "MONITOR":                      ("Monitor",                   "MONITOR", "Healthy governed exception — no action."),
    "REVIEW":                       ("Review",                    "P2", "Open deviation — review against the standard."),
}
PRIORITY_ORDER = ["P1", "P2", "P3", "IGNORE", "MONITOR"]


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def clip(s: str, n: int = 320) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN, help="*_explained.csv to roll up")
    ap.add_argument("--samples", dest="samples", type=int, default=6,
                    help="representative rows kept per action per site (default 6)")
    args = ap.parse_args()

    inp = args.inp
    cap = max(1, args.samples)
    if not os.path.exists(inp):
        log(f"ERROR input not found: {inp}")
        raise SystemExit(2)
    log(f"reading {inp}")
    try:
        with open(inp, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception as e:
        log(f"ERROR failed to read: {type(e).__name__}: {e}")
        raise
    log(f"{len(rows)} rows")

    # group by audited site (this export is single-site AHM but the model is multi-site)
    by_site: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_site[(r.get("Audited Instance (A)") or "UNKNOWN").strip()].append(r)

    sites_out = []
    for site, rs in sorted(by_site.items()):
        sev = Counter((r.get("Deviation Severity") or "").strip().lower() or "(blank)" for r in rs)
        typ = Counter((r.get("Deviation Type") or "").strip() for r in rs)
        trail = Counter((r.get("Exception Trail Status") or "").split(" ")[0] for r in rs if r.get("Exception Trail Status"))
        act = Counter((r.get("Recommended Action") or "REVIEW").strip() for r in rs)

        # priority rollup
        prio = Counter()
        for a, c in act.items():
            prio[ACTION_META.get(a, ("", "P2", ""))[1]] += c

        # representative rows per action (cap 6 each) — the real alert detail
        samples: dict[str, list] = defaultdict(list)
        for r in rs:
            a = (r.get("Recommended Action") or "REVIEW").strip()
            if len(samples[a]) >= cap:
                continue
            samples[a].append({
                "section": r.get("Configuration Section", ""),
                "element": clip(r.get("Configuration Element", ""), 70),
                "attr": r.get("Configuration Element Attribute Name (GUI)", ""),
                "level": r.get("Configuration Level", ""),
                "sev": r.get("Deviation Severity", ""),
                "type": r.get("Deviation Type", ""),
                "a": clip(r.get("A value", ""), 60),
                "r": clip(r.get("R value", ""), 60),
                "trail": r.get("Exception Trail Status", ""),
                "cfg": (r.get("Rationale", "") or "").strip(),
                "ai": clip(r.get("AI Info", ""), 340),
                "explain": clip(r.get("Deviation Explanation (NL)", ""), 500),
                "cites": clip(r.get("Grounding & Citations", ""), 400),
            })

        # ordered action list for the UI
        actions_list = []
        for a, c in act.most_common():
            label, pr, meaning = ACTION_META.get(a, (a, "P2", ""))
            actions_list.append({
                "id": a, "label": label, "priority": pr, "meaning": meaning,
                "count": c, "samples": samples.get(a, []),
            })
        actions_list.sort(key=lambda x: (PRIORITY_ORDER.index(x["priority"]) if x["priority"] in PRIORITY_ORDER else 9,
                                         -x["count"]))

        open_ct = sum(c for s, c in sev.items() if s not in ("accepted", "(blank)", "") and not s.startswith("health"))
        sites_out.append({
            "site": site,
            "total": len(rs),
            "open": open_ct,
            "accepted": sev.get("accepted", 0),
            "priority": dict(prio),
            "severity": dict(sev),
            "type": dict(typ),
            "trail": dict(trail),
            "actions": actions_list,
        })

    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(inp),
        "priorityOrder": PRIORITY_ORDER,
        "priorityLabel": {
            "P1": "Fix / govern open findings", "P2": "Clean up exception trail",
            "P3": "Migration blockers", "IGNORE": "Formatting — ignore", "MONITOR": "No action — monitor",
        },
        "sites": sites_out,
    }

    header = ("/* AUTO-GENERATED by export_drift_ui.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · {payload['generatedAt']} */\n"
              "window.WHS_DRIFT = ")
    try:
        os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
        with open(OUT_JS, "w", encoding="utf-8") as fh:
            fh.write(header)
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write(";\n")
    except Exception as e:
        log(f"ERROR failed to write {OUT_JS}: {type(e).__name__}: {e}")
        raise
    log(f"DONE wrote {OUT_JS}")
    for s in sites_out:
        log(f"  {s['site']}: {s['total']} rows · open {s['open']} · P1 {s['priority'].get('P1',0)} "
            f"· P2 {s['priority'].get('P2',0)} · monitor {s['priority'].get('MONITOR',0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
