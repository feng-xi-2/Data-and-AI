"""build_exception_ledger — a value-level EXCEPTION LEDGER answering, for every configuration
value that at least one site has ACCEPTED:

  * WHAT value in WHAT field is accepted           (Section | Element | Attribute | A value | Type)
  * at WHICH sites                                 (base sites that accepted it)
  * under WHAT CRFC                                 (cited on the row) — or NONE (unbacked)
  * the POTENTIAL CRFC linkage                      (discovered from peer precedent + register)
  * which OTHER sites have the SAME value OPEN       (penalised, not yet accepted) — the adopt list
  * GROUNDED in the sites' own words                (representative Deviation Notes / Rationale)

WHY
---
Config Drift penalises a site for a value another site has already signed off as an allowed
exception. To govern that consistently you need one place that says: "value X of field Y is an
accepted exception at sites A,B,C under CFGnnnn; sites D,E still show it OPEN and should adopt
the same CRFC; here is the justification the accepting sites actually wrote." That is this ledger.

GROUNDING (Citation Rule — every fact is traceable, nothing invented)
--------------------------------------------------------------------
  [FEED]    Section/Element/Attribute/A/R/Type, accepted vs open, and the site's own
            Deviation Notes + Rationale text come straight from the COE export (data.xlsx).
  [CRFC]    a cited CFG code is validated against Configuration_RFC.csv (live / superseded / absent).
  [PEER]    potential CRFC linkage = the CFG that peers accepted the identical variation under.
  No guessing: an accepted value with no cited and no peer CFG is reported UNBACKED, not assigned.

IDENTITY
--------
Accepted value identity (site-independent):  Section | Element | Attribute | A value | Type
The A value is the value the site ACCEPTED. Open peers are matched on the same identity so the
"other sites not accepted" list is the same field carrying the same value left OPEN elsewhere.

OUTPUTS
-------
  Config report/exception_ledger.csv        one row per accepted value-identity, human-readable.
  UIUX/assets/exception-ledger.js           window.WHS_LEDGER for the HTML surface / dialog.
  .github/skills/.../ledger_grounding.json  compact notes/rationale evidence the skill cites.

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then
raise); fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

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
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "exception_ledger.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "exception-ledger.js")
SKILL_DIR = os.path.join(ONEDRIVE, ".github", "skills", "config-drift-human-decision")
SKILL_GROUND = os.path.join(SKILL_DIR, "ledger_grounding.json")

CFG_RE = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
GROUP_RE = re.compile(r"Group Name <([^>]*)>")
DEAD = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}
OPEN_SEV = ("high", "medium", "low")
MAX_NOTES = 4          # representative note/rationale snippets kept per ledger row
MAX_SITES = 40         # cap site lists carried into the JS payload


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


def load_register(path: str) -> dict:
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
        reg[code] = {
            "title": CFG_RE.sub("", (row.get("Title") or "")).strip(" -:·"),
            "status": status,
            "decision": (row.get("Decision Status") or "").strip(),
            "valid": status.lower() not in DEAD,
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


_DETAIL_RE = re.compile(r"([A-Za-z][\w /]*?)\s*<([^>]*)>")
_SKIP_DETAIL = {"modification date", "modification user", "last updated date",
                "last updated user", "warehouse id template", "sort sequence", "group name"}


def is_real_site(name: str) -> bool:
    """Exclude the export's filter-description pseudo-row from the site universe."""
    s = str(name or "")
    return bool(s.strip()) and "applied filters" not in s.lower() and "\n" not in s


def record_hint(details: str) -> str:
    """For a whole-record deviation (Missing/Unexpected record), the A/R value columns are
    blank because the difference is the record's PRESENCE, not one attribute. The record's
    real content lives in Deviation Details as `Field <value>` pairs — surface the meaningful
    ones so the UI can show what the record actually holds instead of an empty value."""
    keep = []
    for k, v in _DETAIL_RE.findall(details or ""):
        v = v.strip()
        kl = k.strip().lower()
        if not v or v.lower() in ("none", "----") or kl in _SKIP_DETAIL:
            continue
        keep.append(f"{k.strip()}={v}")
    return ", ".join(keep[:6])


def main() -> int:
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

    # the site universe (denominator for coverage) — every real audited site in the export
    all_sites = sorted({base_site(site.iloc[i]) for i in range(n) if is_real_site(site.iloc[i])})
    n_sites = len(all_sites)
    log(f"{n_sites} distinct sites in scope (coverage denominator)")

    log("indexing per-row CFG codes…")
    cfg = [row_cfg(rat.iloc[i], notes.iloc[i], details.iloc[i]) for i in range(n)]

    # accepted value identity: Section | Element | Attribute | A value | Type
    def kacc(i):
        return (section.iloc[i].strip(), element.iloc[i].strip(), attr.iloc[i].strip(),
                aval.iloc[i].strip(), typ.iloc[i].strip())

    # peer precedent (for potential CRFC linkage): the variation another site accepted UNDER a
    # code, keyed loosely on Section | Element | Type (independent of the exact site value).
    peer_cfg: dict[tuple, Counter] = defaultdict(Counter)
    for i in range(n):
        if sev.iloc[i] == "accepted" and cfg[i]:
            peer_cfg[(section.iloc[i].strip(), element.iloc[i].strip(), typ.iloc[i].strip())][cfg[i]] += 1

    log("aggregating accepted value-identities…")
    led: dict[tuple, dict] = {}
    # also index OPEN rows by the same accepted-identity so we can list "other sites, same value, open"
    open_by_ident: dict[tuple, dict] = defaultdict(lambda: {"sites": set(), "sev": Counter()})
    for i in range(n):
        idn = kacc(i)
        if sev.iloc[i] in OPEN_SEV:
            open_by_ident[idn]["sites"].add(base_site(site.iloc[i]))
            open_by_ident[idn]["sev"][sev.iloc[i]] += 1
        if sev.iloc[i] != "accepted":
            continue
        e = led.get(idn)
        if e is None:
            e = led[idn] = {
                "section": idn[0], "element": idn[1], "attr": idn[2], "a": idn[3], "type": idn[4],
                "gui": gui.iloc[i].strip(), "r": rval.iloc[i].strip(),
                "acc_sites": set(), "acc_instances": Counter(),
                "cited_cfg": Counter(), "unbacked": 0, "notes": [], "rationale": [], "detail": "",
            }
        bs = base_site(site.iloc[i])
        e["acc_sites"].add(bs)
        e["acc_instances"][site.iloc[i].strip()] += 1
        if not e["gui"]:
            e["gui"] = gui.iloc[i].strip()
        # whole-record deviation: keep the record's real content (from Deviation Details)
        if not e["detail"] and idn[4].lower().endswith("record"):
            e["detail"] = record_hint(details.iloc[i])
        if cfg[i]:
            e["cited_cfg"][cfg[i]] += 1
        else:
            e["unbacked"] += 1
        # grounding — the site's own words (dedup on the site+text so PROD/SIT don't repeat)
        nt = notes.iloc[i].strip()
        if nt and len(e["notes"]) < MAX_NOTES:
            item = f"{bs}: {clip(nt, 200)}"
            if item not in e["notes"]:
                e["notes"].append(item)
        rt = rat.iloc[i].strip()
        if rt and not CFG_RE.fullmatch(rt) and len(e["rationale"]) < MAX_NOTES:
            item = f"{bs}: {clip(rt, 160)}"
            if item not in e["rationale"]:
                e["rationale"].append(item)

    log(f"{len(led):,} accepted value-identities")

    # ---- assemble rows ----
    out = []
    ground = {}     # compact evidence for the skill
    js_rows = []
    tot_unbacked_but_peer = 0
    for idn, e in led.items():
        cited = [c for c, _ in e["cited_cfg"].most_common()]
        cited_live = [c for c in cited if reg.get(c, {}).get("valid", True)]
        cited_stale = [c for c in cited if c in reg and not reg[c]["valid"]]
        cited_absent = [c for c in cited if c not in reg]
        # potential linkage when the accepting sites did NOT all cite a live code
        peers = peer_cfg.get((idn[0], idn[1], idn[4]), Counter())
        peer_live = [c for c, _ in peers.most_common() if reg.get(c, {}).get("valid", True) and c not in cited]
        open_info = open_by_ident.get(idn, {"sites": set(), "sev": Counter()})
        open_sites = sorted(open_info["sites"] - e["acc_sites"])

        # governance state for this accepted value
        if cited_live:
            state = "GOVERNED"          # backed by a live CRFC
        elif cited_stale:
            state = "STALE"             # cited code is superseded/withdrawn
        elif cited_absent:
            state = "ORPHAN"            # cited a code not in the register
        elif peer_live:
            state = "UNBACKED_PEER"     # no code here, but peers govern it under one
            tot_unbacked_but_peer += 1
        else:
            state = "UNBACKED"          # no code anywhere — real governance gap

        potential = peer_live[:3] if state in ("UNBACKED_PEER", "STALE", "ORPHAN", "UNBACKED") else []
        acc_sites = sorted(e["acc_sites"])
        grounds = e["notes"] + [f"[rationale] {r}" for r in e["rationale"]]

        # ---- site-coverage relationship ----------------------------------------
        n_acc = len(acc_sites)
        n_open = len(open_sites)
        n_scope = len(set(acc_sites) | set(open_sites))   # sites that have this deviation at all
        # breadth = how many sites ACCEPT this exception (independent of open peers)
        if n_acc <= 1:
            breadth = "SITE_SPECIFIC"     # accepted at ONE site only — not shared by peers
        elif n_acc <= 5:
            breadth = "FEW"               # a handful of sites
        else:
            breadth = "MANY"             # broadly accepted — de-facto standard candidate
        # consistency = is every site that has it in agreement (all accepted, none left open)?
        consistency = "PARTIAL" if n_open else "CONSISTENT"
        record_level = idn[4].lower().endswith("record")

        row = {
            "Configuration Section": idn[0],
            "Configuration Element": idn[1],
            "Attribute ID": idn[2],
            "Setting (GUI)": e["gui"],
            "Deviation Type": idn[4],
            "Accepted value": (f"[whole record] {e['detail']}" if record_level else idn[3]),
            "Standard value (R)": e["r"],
            "Governance state": state,
            "Breadth": breadth,
            "Consistency": consistency,
            "# Accepting sites": n_acc,
            "# Sites with this deviation": n_scope,
            "Site coverage": f"{n_acc}/{n_sites}",
            "Accepting sites": ", ".join(acc_sites[:MAX_SITES]) + ("…" if len(acc_sites) > MAX_SITES else ""),
            "Cited CRFC (live)": ", ".join(cited_live),
            "Cited CRFC (stale)": ", ".join(cited_stale),
            "Cited CRFC (not in register)": ", ".join(cited_absent),
            "Potential CRFC linkage (peer)": ", ".join(potential),
            "# Other sites same value OPEN": n_open,
            "Other sites same value OPEN (should adopt)": ", ".join(open_sites[:MAX_SITES]) + ("…" if len(open_sites) > MAX_SITES else ""),
            "Grounding (sites' own words)": " || ".join(grounds[:MAX_NOTES]) if grounds else "(no note or rationale recorded)",
        }
        out.append(row)

        key = "|".join(idn)
        js_rows.append({
            "section": idn[0], "element": clip(idn[1], 80), "attr": idn[2], "gui": e["gui"],
            "type": idn[4], "a": clip(idn[3], 80), "r": clip(e["r"], 60), "state": state,
            "breadth": breadth, "consistency": consistency, "recordLevel": record_level,
            "detail": clip(e["detail"], 90),
            "accSites": acc_sites[:MAX_SITES], "nAcc": n_acc, "nScope": n_scope, "totalSites": n_sites,
            "citedLive": cited_live, "citedStale": cited_stale, "citedAbsent": cited_absent,
            "potential": potential, "openSites": open_sites[:MAX_SITES], "nOpen": n_open,
            "grounds": grounds[:MAX_NOTES],
        })
        if grounds:
            ground[key] = {"state": state, "cited": cited_live + cited_stale + cited_absent,
                           "potential": potential, "evidence": grounds[:MAX_NOTES]}

    # sort: adoptable first (has open peers), then unbacked, then by acceptance breadth
    state_rank = {"UNBACKED": 0, "UNBACKED_PEER": 1, "ORPHAN": 2, "STALE": 3, "GOVERNED": 4}
    out.sort(key=lambda r: (-(r["# Other sites same value OPEN"] > 0),
                            state_rank.get(r["Governance state"], 9),
                            -r["# Accepting sites"]))
    js_rows.sort(key=lambda r: (-(r["nOpen"] > 0), state_rank.get(r["state"], 9), -r["nAcc"]))

    cols = list(out[0].keys()) if out else ["Attribute ID"]
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(out)
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV} ({len(out)} value-identities)")

    state_tot = Counter(r["Governance state"] for r in out)
    breadth_tot = Counter(r["Breadth"] for r in out)
    consistency_tot = Counter(r["Consistency"] for r in out)
    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(COE),
        "identity": "Section | Element | Attribute | Accepted value | Deviation Type",
        "term": "An ACCEPTED deviation IS an exception — the two words mean the same thing here. "
                "Every row below is one accepted exception (a signed-off allowed variation).",
        "totalSites": n_sites,
        "stateLegend": {
            "GOVERNED": "accepted under a live CFG-RFC",
            "STALE": "cited CFG-RFC is superseded/withdrawn",
            "ORPHAN": "cited a CFG-RFC not in the register",
            "UNBACKED_PEER": "no CFG-RFC here, but peers govern the same variation under one",
            "UNBACKED": "accepted with no CFG-RFC anywhere — governance gap",
        },
        "breadthLegend": {
            "SITE_SPECIFIC": f"accepted at ONE site only — a local exception peers don't share",
            "FEW": "accepted at 2–5 sites",
            "MANY": "accepted at 6+ sites — a de-facto standard candidate",
        },
        "consistencyLegend": {
            "CONSISTENT": "every site that has this deviation has accepted it (no open peers)",
            "PARTIAL": "accepted at some sites but still OPEN/penalised at others — adoptable now",
        },
        "totals": {"identities": len(out), "byState": dict(state_tot),
                   "byBreadth": dict(breadth_tot), "byConsistency": dict(consistency_tot),
                   "siteSpecific": breadth_tot.get("SITE_SPECIFIC", 0),
                   "adoptable": sum(1 for r in out if r["# Other sites same value OPEN"] > 0),
                   "unbacked_but_peer_governed": tot_unbacked_but_peer},
        "rows": js_rows[:4000],
    }
    header = ("/* AUTO-GENERATED by build_exception_ledger.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · {payload['generatedAt']} */\n"
              "window.WHS_LEDGER = ")
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

    # compact grounding evidence for the skill (notes/rationale the decisions cite)
    try:
        os.makedirs(SKILL_DIR, exist_ok=True)
        with open(SKILL_GROUND, "w", encoding="utf-8") as fh:
            json.dump({"generatedAt": payload["generatedAt"], "source": os.path.basename(COE),
                       "count": len(ground), "evidence": ground}, fh, ensure_ascii=False, indent=1)
        log(f"wrote {SKILL_GROUND} ({len(ground)} grounded identities)")
    except Exception as e:
        log(f"ERROR failed to write {SKILL_GROUND}: {type(e).__name__}: {e}")
        raise

    log("")
    log("LEDGER SUMMARY:")
    log(f"  accepted exceptions (identities)    {len(out):,}   across {n_sites} sites")
    for st in ("GOVERNED", "UNBACKED_PEER", "UNBACKED", "ORPHAN", "STALE"):
        log(f"    {st:<16} {state_tot.get(st, 0):,}")
    log(f"  breadth  SITE_SPECIFIC (1 site)     {breadth_tot.get('SITE_SPECIFIC', 0):,}")
    log(f"           FEW (2-5 sites)            {breadth_tot.get('FEW', 0):,}")
    log(f"           MANY (6+ sites)            {breadth_tot.get('MANY', 0):,}")
    log(f"  consistency  CONSISTENT             {consistency_tot.get('CONSISTENT', 0):,}")
    log(f"               PARTIAL (adoptable)    {consistency_tot.get('PARTIAL', 0):,}")
    log(f"  adoptable (peers still OPEN)         {payload['totals']['adoptable']:,}")
    log(f"  unbacked here but peer-governed      {tot_unbacked_but_peer:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
