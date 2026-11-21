"""cross_site_exceptions — find deviations accepted at one site but NOT accepted at others.

Question: across the whole export (all sites), is there any deviation that one site has
signed off as an ACCEPTED exception, while another site with the SAME deviation leaves it
OPEN (medium/high/low) — i.e. that second site is penalised for something a peer already
governs as an allowed variation?

We define a site-independent deviation IDENTITY from the columns that describe *what* the
deviation is (not which site):

    Configuration Section | Configuration Element | Element Attribute ID |
    A value | R value | Deviation Type

For every identity we split the sites that have it into:
    accepted_sites  = severity == 'accepted'  (governed exception, carries a CFG rationale)
    open_sites      = severity in high/medium/low (open finding, counts against Config Score)

An identity is INCONSISTENT when it has >=1 accepted site AND >=1 open site.
Those are the rows where one site's approved exception is another site's penalty.

Outputs a CSV (one row per inconsistent identity) + a console summary.
Follows workspace rules: timestamped logs; no silent failure (log type+message then raise).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys
from collections import defaultdict

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
DEFAULT_IN = os.path.join(ONEDRIVE, "Config report", "all_sites_deviations.csv")
DEFAULT_OUT = os.path.join(ONEDRIVE, "Config report", "cross_site_exception_inconsistencies.csv")

OPEN_SEVERITIES = {"high", "medium", "low"}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _cfg_from(row: dict) -> str:
    import re
    m = re.search(r"\bCFG\d+\b", (row.get("Rationale") or ""), re.IGNORECASE)
    return m.group(0).upper() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN, help="all-sites deviation CSV")
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT, help="output inconsistencies CSV")
    ap.add_argument("--min-accepted", type=int, default=1,
                    help="min accepted sites for an identity to be reported (default 1)")
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        log(f"ERROR input not found: {args.inp}")
        raise SystemExit(2)

    log(f"reading {args.inp}")
    # identity -> {accepted:set, open:set, sev_by_site, cfg_codes, one row for description}
    idmap: dict[tuple, dict] = defaultdict(lambda: {
        "accepted": set(), "open": set(), "open_sev": defaultdict(set),
        "cfg": set(), "desc": None,
    })
    n = 0
    try:
        with open(args.inp, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                site = (row.get("Audited Instance (A)") or "").strip()
                if not site:
                    continue
                sev = (row.get("Deviation Severity") or "").strip().lower()
                key = (
                    (row.get("Configuration Section") or "").strip(),
                    (row.get("Configuration Element") or "").strip(),
                    (row.get("Configuration Element Attribute ID") or "").strip(),
                    (row.get("A value") or "").strip(),
                    (row.get("R value") or "").strip(),
                    (row.get("Deviation Type") or "").strip(),
                )
                rec = idmap[key]
                if rec["desc"] is None:
                    rec["desc"] = {
                        "section": key[0], "element": key[1], "attr_id": key[2],
                        "attr_gui": (row.get("Configuration Element Attribute Name (GUI)") or "").strip(),
                        "a": key[3], "r": key[4], "type": key[5],
                    }
                if sev == "accepted":
                    rec["accepted"].add(site)
                    c = _cfg_from(row)
                    if c:
                        rec["cfg"].add(c)
                elif sev in OPEN_SEVERITIES:
                    rec["open"].add(site)
                    rec["open_sev"][sev].add(site)
                n += 1
                if n % 20000 == 0:
                    log(f"  scanned {n} rows…")
    except Exception as e:
        log(f"ERROR failed reading input: {type(e).__name__}: {e}")
        raise
    log(f"scanned {n} rows · {len(idmap)} distinct deviation identities")

    # keep identities that are accepted somewhere AND open elsewhere
    incon = []
    for key, rec in idmap.items():
        if len(rec["accepted"]) >= args.min_accepted and rec["open"]:
            incon.append((key, rec))
    # sort by how many sites are penalised (open) desc, then accepted desc
    incon.sort(key=lambda kr: (-len(kr[1]["open"]), -len(kr[1]["accepted"])))
    log(f"found {len(incon)} inconsistent identities "
        f"(accepted at >= {args.min_accepted} site(s) but open at others)")

    total_penalised = sum(len(rec["open"]) for _, rec in incon)

    out_fields = [
        "Configuration Section", "Configuration Element", "Attribute ID", "Attribute Name (GUI)",
        "Deviation Type", "A value", "R value",
        "# Accepted sites", "# Open (penalised) sites",
        "CFG code(s)", "Accepted sites", "Open sites (penalised)", "Open severities",
    ]
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=out_fields)
            w.writeheader()
            for key, rec in incon:
                d = rec["desc"]
                sev_str = "; ".join(
                    f"{s}:{len(rec['open_sev'][s])}" for s in ("high", "medium", "low")
                    if rec["open_sev"].get(s))
                w.writerow({
                    "Configuration Section": d["section"],
                    "Configuration Element": d["element"],
                    "Attribute ID": d["attr_id"],
                    "Attribute Name (GUI)": d["attr_gui"],
                    "Deviation Type": d["type"],
                    "A value": d["a"], "R value": d["r"],
                    "# Accepted sites": len(rec["accepted"]),
                    "# Open (penalised) sites": len(rec["open"]),
                    "CFG code(s)": ", ".join(sorted(rec["cfg"])),
                    "Accepted sites": ", ".join(sorted(rec["accepted"])),
                    "Open sites (penalised)": ", ".join(sorted(rec["open"])),
                    "Open severities": sev_str,
                })
    except Exception as e:
        log(f"ERROR failed writing output: {type(e).__name__}: {e}")
        raise

    log(f"DONE wrote {args.out}")
    log("--- summary ---")
    log(f"  {len(incon)} deviation identities are accepted at some site(s) but OPEN at others")
    log(f"  {total_penalised} site-level open findings could be treated as already-governed exceptions")
    with_cfg = sum(1 for _, r in incon if r["cfg"])
    log(f"  {with_cfg} of those carry a CFG-RFC code on the accepting side (strong precedent)")

    log("--- top 15 by number of penalised sites ---")
    for key, rec in incon[:15]:
        d = rec["desc"]
        cfg = ("/" + ",".join(sorted(rec["cfg"]))) if rec["cfg"] else ""
        val = f"A='{d['a']}' vs R='{d['r']}'" if (d["a"] or d["r"]) else d["type"]
        log(f"  open@{len(rec['open']):>3}  accepted@{len(rec['accepted']):>3}{cfg}  "
            f"| {d['section']} · {d['element']} · {d['attr_gui'] or d['attr_id']} | {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
