"""build_change_capture — a CHANGE / DELTA view of Config Drift, answering "what is new?"

WHAT THIS IS
------------
Config Drift is scanned on a cadence. Every deviation row in the COE export carries
`First seen on` and `Last seen on`, so the change between scans is native, not guessed:

  * NEW deviation      First seen on >= <since>  and still present in the latest scan
                       -> "what is new in a site, a field and a value"
  * RESOLVED deviation Last seen on  <  the latest scan date
                       -> a deviation that disappeared (fixed or config removed)
  * NEW / updated CRFC a Configuration_RFC.csv row whose Date Cab input / Date TCAB input /
                       Closed Date falls in the window
                       -> "what is new in the CRFC field"

IMPACT ON THE RELATIONSHIP (the graph the change feeds)
-------------------------------------------------------
For every NEW deviation we classify what it does to the governance graph:

  NEW_GOVERNED           a new ACCEPTED exception already backed by a live CFG-RFC.
  NEW_ADOPTABLE          a new OPEN finding whose identity peers already ACCEPT under a
                         live CFG-RFC -> the same CRFC can be adopted here immediately.
  NEW_ADOPTABLE_PEER     a new OPEN/accepted finding whose Section|Element|Type peers govern
                         under a live CFG-RFC -> reuse that governing decision.
  NEW_GAP                a new finding with NO governing CRFC anywhere -> a CFG-RFC should
                         be raised (or the site fixed to the standard).

A NEW CRFC's impact = how many currently-accepted value-identities (and sites) cite it.

IDENTITY (shared with the exception ledger, so the two views line up)
    Section | Element | Attribute | value | Deviation Type

OUTPUTS
    Config report/change_capture.csv     full NEW + RESOLVED list, human-readable.
    UIUX/assets/change-capture.js        window.WHS_CHANGE for the knowledge-graph template
                                         (summary + rows + newCrfc + a delta graph payload).

GROUNDING (Citation Rule — nothing invented)
    [FEED]  First seen / Last seen, site, field, value, severity, notes come from data.xlsx.
    [CRFC]  a cited/new CFG is validated against Configuration_RFC.csv (live/superseded/absent)
            and its dates are read from that register.
    [PEER]  adoptable linkage = the live CFG peers accepted the identical variation under.

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then
raise); fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
from collections import Counter, defaultdict

import pandas as pd

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
COE = os.path.join(ONEDRIVE, "Config report", "data.xlsx")
CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "change_capture.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "change-capture.js")

CFG_RE = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
GROUP_RE = re.compile(r"Group Name <([^>]*)>")
DEAD = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}
OPEN_SEV = ("high", "medium", "low")
MAX_SITES = 40
DEFAULT_DAYS = 30


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def base_site(name: str) -> str:
    return re.sub(r"\s*-\s*(UAT\d*|SITH?|SIT|PROD|TEST)\b.*$", "", str(name or ""), flags=re.IGNORECASE).strip()


def read_text(path: str) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, FileNotFoundError):
            if not os.path.exists(path):
                return ""
            continue
    return ""


def parse_date(s: str):
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s, errors="coerce").date()
    except Exception:
        return None


def load_register(path: str) -> dict:
    """CFG code -> {title, status, decision, valid, date} (date = most recent register date)."""
    reg: dict[str, dict] = {}
    text = read_text(path)
    if not text:
        log(f"note: register missing ({path}); CRFC validity will be 'unknown'")
        return reg
    for row in csv.DictReader(text.splitlines()):
        blob = " ".join(str(row.get(k) or "") for k in ("Code", "Title"))
        m = CFG_RE.search(blob)
        if not m:
            continue
        code = m.group(0).upper()
        status = (row.get("Request Status") or "").strip()
        dates = [parse_date(row.get(c)) for c in ("Date Cab input", "Date TCAB input", "Closed Date")]
        dates = [d for d in dates if d]
        reg[code] = {
            "title": CFG_RE.sub("", (row.get("Title") or "")).strip(" -:·"),
            "status": status,
            "decision": (row.get("Decision Status") or "").strip(),
            "valid": status.lower() not in DEAD,
            "date": max(dates) if dates else None,
        }
    log(f"CFG-RFC register: {len(reg)} codes indexed")
    return reg


def row_cfg(rat: str, notes: str, details: str) -> str:
    for src in (rat, notes):
        m = CFG_RE.search(src or "")
        if m:
            return m.group(0).upper()
    g = GROUP_RE.search(details or "")
    if g:
        m = CFG_RE.search(g.group(1))
        if m:
            return m.group(0).upper()
    return ""


def clip(s: str, n: int) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"look-back window in days for 'new' (default {DEFAULT_DAYS})")
    ap.add_argument("--since", default="", help="explicit YYYY-MM-DD cutoff (overrides --days)")
    args = ap.parse_args()

    if not os.path.exists(COE):
        log(f"ERROR COE reference not found: {COE}")
        raise SystemExit(2)
    reg = load_register(CRFC)

    log(f"reading {COE}")
    try:
        df = pd.read_excel(COE, sheet_name="Export")
    except Exception as e:
        log(f"ERROR failed to read COE xlsx: {type(e).__name__}: {e}")
        raise
    df.columns = [c.strip() for c in df.columns]
    n = len(df)
    log(f"{n:,} rows loaded")

    def col(name, *alts):
        for c in (name, *alts):
            if c in df.columns:
                return df[c].fillna("").astype(str)
        return pd.Series([""] * n)

    site = col("Audited Site")
    section = col("Configuration Section")
    sev = col("Deviation Severity").str.strip().str.lower()
    element = col("Configuration Element")
    attr = col("Element Attribute ID")
    gui = col("Element Attribute Name (GUI)")
    aval = col("Audited Value")
    rval = col("Reference Value")
    typ = col("Deviation Type")
    details = col("Deviation Details")
    notes = col("Deviation Notes").str.strip()
    rat = col("Rationale for Accepted").str.strip()
    first_seen = pd.to_datetime(df.get("First seen on"), errors="coerce")
    last_seen = pd.to_datetime(df.get("Last seen on"), errors="coerce")

    current_scan = last_seen.max()
    if pd.isna(current_scan):
        log("ERROR no valid 'Last seen on' dates — cannot determine the current scan")
        raise SystemExit(2)
    current_scan = current_scan.date()
    if args.since:
        since = parse_date(args.since)
    else:
        since = current_scan - datetime.timedelta(days=args.days)
    log(f"current scan = {current_scan} · 'new' since = {since} ({args.days}d window)")

    cfg = [row_cfg(rat.iloc[i], notes.iloc[i], details.iloc[i]) for i in range(n)]

    # ---- whole-dataset identity model (so 'new' rows can be classified vs the standing state) ----
    def kacc(i):
        return (section.iloc[i].strip(), element.iloc[i].strip(), attr.iloc[i].strip(),
                aval.iloc[i].strip(), typ.iloc[i].strip())

    accepted_live_cfg: dict[tuple, set] = defaultdict(set)   # identity -> live CFGs it is accepted under
    accepted_sites: dict[tuple, set] = defaultdict(set)      # identity -> accepting base sites
    peer_live: dict[tuple, set] = defaultdict(set)           # Section|Element|Type -> live CFGs peers accepted under
    for i in range(n):
        if sev.iloc[i] == "accepted":
            idn = kacc(i)
            accepted_sites[idn].add(base_site(site.iloc[i]))
            c = cfg[i]
            if c and reg.get(c, {}).get("valid", True):
                accepted_live_cfg[idn].add(c)
                peer_live[(section.iloc[i].strip(), element.iloc[i].strip(), typ.iloc[i].strip())].add(c)

    def classify_new(i):
        """Return (impact_state, adopt_cfgs) for a NEW deviation row."""
        idn = kacc(i)
        soft = (section.iloc[i].strip(), element.iloc[i].strip(), typ.iloc[i].strip())
        s = sev.iloc[i]
        if s == "accepted":
            c = cfg[i]
            if c and reg.get(c, {}).get("valid", True):
                return "NEW_GOVERNED", [c]
            pl = sorted(peer_live.get(soft, set()))
            if pl:
                return "NEW_ADOPTABLE_PEER", pl[:3]
            return "NEW_GAP", []
        # open finding
        live = sorted(accepted_live_cfg.get(idn, set()))
        if live:
            return "NEW_ADOPTABLE", live[:3]
        pl = sorted(peer_live.get(soft, set()))
        if pl:
            return "NEW_ADOPTABLE_PEER", pl[:3]
        return "NEW_GAP", []

    # ---- walk rows: new + resolved ----
    new_rows, resolved_rows = [], []
    new_by_site, new_by_section = Counter(), Counter()
    state_tot = Counter()
    for i in range(n):
        fs = first_seen.iloc[i]
        ls = last_seen.iloc[i]
        fs_d = fs.date() if not pd.isna(fs) else None
        ls_d = ls.date() if not pd.isna(ls) else None
        is_present = (ls_d == current_scan)
        is_new = fs_d is not None and fs_d >= since and is_present
        is_resolved = ls_d is not None and ls_d < current_scan
        if is_new:
            state, adopt = classify_new(i)
            bs = base_site(site.iloc[i])
            new_by_site[bs] += 1
            new_by_section[section.iloc[i].strip()] += 1
            state_tot[state] += 1
            new_rows.append({
                "i": i, "site": bs, "state": state, "adopt": adopt,
                "section": section.iloc[i].strip(), "element": element.iloc[i].strip(),
                "attr": attr.iloc[i].strip(), "gui": gui.iloc[i].strip(),
                "a": aval.iloc[i].strip(), "r": rval.iloc[i].strip(),
                "type": typ.iloc[i].strip(), "sev": sev.iloc[i],
                "firstSeen": str(fs_d), "cfg": cfg[i],
                "note": clip(notes.iloc[i], 180),
            })
        elif is_resolved:
            resolved_rows.append({
                "site": base_site(site.iloc[i]), "section": section.iloc[i].strip(),
                "element": element.iloc[i].strip(), "attr": attr.iloc[i].strip(),
                "a": aval.iloc[i].strip(), "type": typ.iloc[i].strip(),
                "sev": sev.iloc[i], "lastSeen": str(ls_d),
            })

    log(f"NEW deviations: {len(new_rows):,} · RESOLVED: {len(resolved_rows):,}")
    for st in ("NEW_GAP", "NEW_ADOPTABLE", "NEW_ADOPTABLE_PEER", "NEW_GOVERNED"):
        log(f"    {st:<20} {state_tot.get(st, 0):,}")

    # ---- new / updated CRFCs in the window ----
    new_crfc = []
    for code, r in reg.items():
        d = r.get("date")
        if d and d >= since:
            # impact: currently-accepted identities citing this code + their sites
            cites = [idn for idn, cs in accepted_live_cfg.items() if code in cs]
            sites = set()
            for idn in cites:
                sites |= accepted_sites.get(idn, set())
            new_crfc.append({
                "code": code, "title": clip(r["title"], 90), "status": r["status"],
                "decision": r["decision"], "date": str(d),
                "governs": len(cites), "sites": len(sites),
            })
    new_crfc.sort(key=lambda x: (x["date"], x["governs"]), reverse=True)
    log(f"NEW/updated CRFCs in window: {len(new_crfc):,}")

    # ---- CSV (new + resolved) ----
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Change", "Impact state", "Site", "Section", "Element", "Attribute",
                        "Setting (GUI)", "Value (A)", "Standard (R)", "Deviation Type",
                        "Severity", "First/Last seen", "CFG", "Adopt CFG", "Note"])
            for r in new_rows:
                w.writerow(["NEW", r["state"], r["site"], r["section"], r["element"], r["attr"],
                            r["gui"], r["a"], r["r"], r["type"], r["sev"], r["firstSeen"],
                            r["cfg"], ", ".join(r["adopt"]), r["note"]])
            for r in resolved_rows:
                w.writerow(["RESOLVED", "", r["site"], r["section"], r["element"], r["attr"],
                            "", r["a"], "", r["type"], r["sev"], r["lastSeen"], "", "", ""])
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV}")

    # ---- delta graph payload (impact on the relationship) ----
    # focus: top new CRFCs, top new gaps, top new adoptables, and the sites/edges they touch.
    nodes, edges, seen_node = [], [], set()

    def add_node(nid, label, **props):
        if nid in seen_node:
            return
        seen_node.add(nid)
        nodes.append({"id": nid, "eid": nid, "labels": [label], "props": props})

    def ident_cap(r):
        return clip((r["element"] or r["section"]) + (" · " + r["attr"] if r["attr"] else ""), 26)

    # new CRFC nodes + what they govern
    for c in new_crfc[:6]:
        cid = "cfg_" + c["code"]
        add_node(cid, "New CRFC", name=c["code"], title=c["title"], status=c["status"],
                 decision=c["decision"], date=c["date"], governs=str(c["governs"]))

    # representative new rows: a MIX of impact types so the graph shows every relationship
    # (Site→gap, Site→adoptable→CRFC, Site→governed→CRFC), not just gap stars.
    order = {"NEW_GAP": 0, "NEW_ADOPTABLE": 1, "NEW_ADOPTABLE_PEER": 2, "NEW_GOVERNED": 3}
    by_state_rows: dict[str, list] = defaultdict(list)
    for r in new_rows:
        by_state_rows[r["state"]].append(r)
    picks = []
    for st, take in (("NEW_ADOPTABLE", 4), ("NEW_ADOPTABLE_PEER", 4),
                     ("NEW_GOVERNED", 3), ("NEW_GAP", 6)):
        picks.extend(by_state_rows.get(st, [])[:take])
    for k, r in enumerate(picks):
        did = "d%d" % k
        lab = {"NEW_GAP": "New gap", "NEW_ADOPTABLE": "New · adoptable",
               "NEW_ADOPTABLE_PEER": "New · peer-governed", "NEW_GOVERNED": "New · governed"}.get(r["state"], "New")
        add_node(did, lab, name=ident_cap(r), section=r["section"], type=r["type"],
                 A=clip(r["a"], 40) or "∅", R=clip(r["r"], 40) or "∅", severity=r["sev"], firstSeen=r["firstSeen"])
        sid = "s_" + re.sub(r"\W+", "_", r["site"])[:24]
        add_node(sid, "Site", name=r["site"])
        edges.append({"src": sid, "dst": did, "type": "NEW"})
        for c in r["adopt"][:1]:
            cid = "cfg_" + c
            add_node(cid, "Governing CRFC", name=c, title=clip(reg.get(c, {}).get("title", ""), 60),
                     status=reg.get(c, {}).get("status", ""))
            edges.append({"src": did, "dst": cid, "type": "ADOPT"})

    graph = {"nodes": nodes, "edges": edges}

    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(COE),
        "currentScan": str(current_scan),
        "since": str(since),
        "windowDays": args.days,
        "stateLegend": {
            "NEW_GAP": "new finding with no governing CRFC anywhere — raise a CFG-RFC or fix",
            "NEW_ADOPTABLE": "new OPEN finding peers already accept under a live CFG — adopt it here",
            "NEW_ADOPTABLE_PEER": "peers govern this Section·Element·Type under a live CFG — reuse it",
            "NEW_GOVERNED": "new accepted exception already backed by a live CFG-RFC",
        },
        "totals": {
            "new": len(new_rows), "resolved": len(resolved_rows),
            "newCrfc": len(new_crfc), "byState": dict(state_tot),
            "newGap": state_tot.get("NEW_GAP", 0),
            "newAdoptable": state_tot.get("NEW_ADOPTABLE", 0) + state_tot.get("NEW_ADOPTABLE_PEER", 0),
        },
        "newBySite": [{"site": s, "n": c} for s, c in new_by_site.most_common(20)],
        "newBySection": [{"section": s, "n": c} for s, c in new_by_section.most_common(15)],
        "newCrfc": new_crfc[:60],
        "rows": [{
            "site": r["site"], "state": r["state"], "section": r["section"],
            "element": clip(r["element"], 80), "attr": r["attr"], "gui": r["gui"],
            "a": clip(r["a"], 80), "r": clip(r["r"], 60), "type": r["type"], "sev": r["sev"],
            "firstSeen": r["firstSeen"], "cfg": r["cfg"], "adopt": r["adopt"], "note": r["note"],
        } for r in sorted(new_rows, key=lambda r: (order.get(r["state"], 9), r["site"]))[:1500]],
        "resolved": resolved_rows[:500],
        "graph": graph,
    }
    header = ("/* AUTO-GENERATED by build_change_capture.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · scan {payload['currentScan']} · since {payload['since']}"
              f" · {payload['generatedAt']} */\n"
              "window.WHS_CHANGE = ")
    try:
        os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
        with open(OUT_JS, "w", encoding="utf-8") as fh:
            fh.write(header)
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write(";\n")
    except Exception as e:
        log(f"ERROR failed to write {OUT_JS}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_JS}")

    log("")
    log("CHANGE SUMMARY:")
    log(f"  window                 {since} → {current_scan} ({args.days}d)")
    log(f"  NEW deviations         {len(new_rows):,}")
    log(f"    new gaps             {state_tot.get('NEW_GAP', 0):,}")
    log(f"    new adoptable        {state_tot.get('NEW_ADOPTABLE', 0) + state_tot.get('NEW_ADOPTABLE_PEER', 0):,}")
    log(f"    new governed         {state_tot.get('NEW_GOVERNED', 0):,}")
    log(f"  RESOLVED deviations    {len(resolved_rows):,}")
    log(f"  NEW/updated CRFCs      {len(new_crfc):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
