"""tag_potential_exceptions — flag OPEN config-drift findings that are very likely
legitimate, governable EXCEPTIONS (not defects), grounded on peer-site precedent.

WHY THIS EXISTS
---------------
Config Drift today tells a site "Fix or raise CFG-RFC" for every open functional mismatch.
But many of those open findings are not defects at all: a *peer site* has already signed the
IDENTICAL deviation off as an ACCEPTED exception (often under a CFG-RFC). When that is true,
the honest recommendation is not "fix" — it is "raise a CFG-RFC and accept it, exactly like
the peers did." This module surfaces those cases as POTENTIAL EXCEPTIONS with solid grounding.

THE GROUNDING (no guessing — every tag cites real precedent)
------------------------------------------------------------
We reuse the already-computed cross-site table
    Config report/cross_site_exception_inconsistencies.csv
which, for each site-independent deviation IDENTITY
    Section | Element | Attribute | A value | R value | Deviation Type
lists the sites that ACCEPTED it (governed variation, may carry CFG code[s]) and the sites
that leave it OPEN (penalised). Every OPEN site on such an identity is a potential exception:
its finding is something >=1 peer already governs as allowed.

STRENGTH (how confident the precedent is)
-----------------------------------------
  STRONG    a CFG-RFC code backs the peer acceptance  -> cite CFGxxxx, propose adopting it
  MODERATE  no code, but >=3 peers accept it          -> propose CFG-RFC, name the peers
  EMERGING  no code and 1-2 peers accept it           -> review; precedent is thin

OUTPUTS
-------
  Config report/potential_exceptions.csv
        one row per (open site x identity) with a plain-English explanation, the grounding,
        the suggested action and the strength — the human-readable deliverable.
  UIUX/assets/potential-exceptions.js
        window.WHS_PXC = { generatedAt, source, bySite:{site:[...]}, totals } for the HTML
        Config-Drift Site-Action dialog (no build step, mirrors assets/data.js).

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message
then raise); fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
import sys
from collections import defaultdict

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
IN_XSITE = os.path.join(ONEDRIVE, "Config report", "cross_site_exception_inconsistencies.csv")
IN_CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "potential_exceptions.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "potential-exceptions.js")

CFG_RE = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
SAMPLES_PER_SITE = 40  # cap rows carried into the HTML payload per site (CSV keeps them all)


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def split_sites(blob: str) -> list[str]:
    return [s.strip() for s in (blob or "").split(",") if s.strip()]


def base_site(name: str) -> str:
    """Collapse an environment suffix so 'Amiens KH- UAT' == 'Amiens KH' for precedent counts."""
    n = re.sub(r"\s*-\s*(UAT\d*|SITH?|SIT|PROD|TEST)\b.*$", "", name, flags=re.IGNORECASE)
    return n.strip()


def load_crfc(path: str) -> dict:
    """code -> short human label 'CFG1531 · Ready for CoE · APPROVED'. Best-effort, never fatal."""
    out: dict[str, str] = {}
    if not os.path.exists(path):
        log(f"note: CFG-RFC register not found ({path}); CFG codes will be shown bare")
        return out
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc, newline="") as fh:
                text = fh.read()
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        log("note: could not decode CFG-RFC register in any known encoding; continuing bare")
        return out
    try:
        for row in csv.DictReader(text.splitlines()):
            blob = " ".join(str(row.get(k) or "") for k in ("Code", "Title"))
            m = CFG_RE.search(blob)
            if not m:
                continue
            code = m.group(0).upper()
            title = (row.get("Title") or "").strip()
            title = CFG_RE.sub("", title).strip(" -:·")  # drop the code prefix from the title
            status = (row.get("Request Status") or "").strip()
            decision = (row.get("Decision Status") or "").strip()
            bits = [b for b in (title[:60], status, decision) if b]
            out[code] = " · ".join(bits)
    except Exception as e:
        log(f"note: failed to parse CFG-RFC register ({type(e).__name__}: {e}); continuing bare")
    log(f"CFG-RFC register: {len(out)} codes indexed")
    return out


def strength_of(cfgs: list[str], n_accept: int) -> str:
    if cfgs:
        return "STRONG"
    if n_accept >= 3:
        return "MODERATE"
    return "EMERGING"


def humanize(site, desc, accepted_peers, cfgs, n_accept, n_open, strength, crfc) -> tuple[str, str, str]:
    """Return (explanation_nl, suggested_action_nl, grounding_citations)."""
    sec = desc["section"]
    el = desc["element"]
    attr = desc["attr_gui"] or desc["attr_id"]
    typ = (desc["type"] or "").lower()
    a, r = desc["a"], desc["r"]
    what = f"{sec} · {el}" + (f" · {attr}" if attr else "")

    # describe the deviation in words
    if "missing" in typ:
        finding = f"the standard defines this record but {site} does not have it"
    elif "unexpected" in typ and "mismatch" in typ:
        finding = (f"{site} carries the value \u201c{a or '(blank)'}\u201d where the standard "
                   f"reference is \u201c{r or '(blank)'}\u201d")
    elif "unexpected" in typ:
        finding = f"{site} has an extra record that is not in the standard"
    else:
        finding = f"{site}'s value \u201c{a or '(blank)'}\u201d differs from the standard \u201c{r or '(blank)'}\u201d"

    peer_show = ", ".join(accepted_peers[:6]) + ("…" if len(accepted_peers) > 6 else "")
    peer_word = "peer site" if n_accept == 1 else "peer sites"

    # explanation
    if cfgs:
        codes = ", ".join(cfgs)
        cfg_desc = "; ".join(f"{c} ({crfc[c]})" for c in cfgs if c in crfc) or codes
        expl = (f"This is flagged because {finding}. It is almost certainly a legitimate, "
                f"site-specific configuration rather than a defect: {n_accept} {peer_word} "
                f"({peer_show}) already run the identical setting and have it signed off as an "
                f"ACCEPTED exception under {codes}. In other words, the change was already reviewed "
                f"and governed elsewhere — {site} simply has not raised its own exception yet, so the "
                f"drift engine still counts it against the Config Score.")
        action = (f"Adopt the existing precedent: raise a CFG-RFC for {site} citing {codes} "
                  f"({cfg_desc}) and mark this deviation as an accepted exception. No functional "
                  f"change to the site is needed — this only closes the governance gap.")
    else:
        expl = (f"This is flagged because {finding}. It looks like an allowed site variation rather "
                f"than a defect: {n_accept} {peer_word} ({peer_show}) already run the identical "
                f"setting and have accepted it as an exception — but with no CFG-RFC code recorded "
                f"against that acceptance. {site} is one of {n_open} sites still penalised for it.")
        if strength == "MODERATE":
            action = (f"Strong peer precedent ({n_accept} sites) but no governing CFG-RFC exists. "
                      f"Raise one CFG-RFC to formally accept this variation and back-fill the peer "
                      f"acceptances, then mark {site} as an accepted exception.")
        else:
            action = (f"Thin precedent ({n_accept} {peer_word}) and no CFG-RFC on record. Review "
                      f"whether this should be standardised (fix everywhere) or governed as an "
                      f"exception (raise a CFG-RFC); do not auto-accept on {n_accept}-site precedent alone.")

    cites = (f"[PYTHON] cross-site identity match on Section|Element|Attribute|A|R|Type. "
             f"[DRIFT] {n_accept} accepted vs {n_open} open sites for this identity. "
             + (f"[CRFC] peer acceptance governed by {', '.join(cfgs)}. " if cfgs
                else "[CRFC] no CFG-RFC code on the peer acceptance (governance gap). ")
             + "[GENERAL] a deviation a peer already governs as an allowed variation is a candidate "
               "exception, not automatically a defect.")
    return expl, action, cites


def main() -> int:
    if not os.path.exists(IN_XSITE):
        log(f"ERROR cross-site input not found: {IN_XSITE}")
        log("Run cross_site_exceptions.py first to produce it.")
        raise SystemExit(2)

    crfc = load_crfc(IN_CRFC)

    log(f"reading {IN_XSITE}")
    try:
        with open(IN_XSITE, encoding="utf-8-sig", newline="") as fh:
            identities = list(csv.DictReader(fh))
    except Exception as e:
        log(f"ERROR failed to read cross-site CSV: {type(e).__name__}: {e}")
        raise
    log(f"{len(identities)} inconsistent identities")

    csv_rows: list[dict] = []
    by_site: dict[str, list[dict]] = defaultdict(list)
    strength_tot: dict[str, int] = defaultdict(int)

    for idn in identities:
        desc = {
            "section": (idn.get("Configuration Section") or "").strip(),
            "element": (idn.get("Configuration Element") or "").strip(),
            "attr_id": (idn.get("Attribute ID") or "").strip(),
            "attr_gui": (idn.get("Attribute Name (GUI)") or "").strip(),
            "a": (idn.get("A value") or "").strip(),
            "r": (idn.get("R value") or "").strip(),
            "type": (idn.get("Deviation Type") or "").strip(),
        }
        accepted_peers = split_sites(idn.get("Accepted sites"))
        open_sites = split_sites(idn.get("Open sites (penalised)"))
        cfgs = sorted({c.upper() for c in CFG_RE.findall(idn.get("CFG code(s)") or "")})
        # de-dup peers by base name for an honest precedent count
        acc_base = sorted({base_site(p) for p in accepted_peers})
        n_accept = len(acc_base)
        n_open = len(open_sites)
        if n_accept < 1 or not open_sites:
            continue
        strength = strength_of(cfgs, n_accept)

        for site in open_sites:
            expl, action, cites = humanize(site, desc, acc_base, cfgs, n_accept, n_open, strength, crfc)
            strength_tot[strength] += 1
            row = {
                "Site": site,
                "Configuration Section": desc["section"],
                "Configuration Element": desc["element"],
                "Attribute": desc["attr_gui"] or desc["attr_id"],
                "Deviation Type": desc["type"],
                "Site value (A)": desc["a"],
                "Standard value (R)": desc["r"],
                "Potential exception": "YES",
                "Grounding strength": strength,
                "# Peer sites accepting": n_accept,
                "Peer sites accepting": ", ".join(acc_base),
                "Governing CFG-RFC": ", ".join(cfgs),
                "# Sites still open": n_open,
                "Why it's a potential exception": expl,
                "Suggested action": action,
                "Grounding & citations": cites,
            }
            csv_rows.append(row)
            if len(by_site[site]) < SAMPLES_PER_SITE:
                by_site[site].append({
                    "section": desc["section"],
                    "element": desc["element"][:70],
                    "attr": desc["attr_gui"] or desc["attr_id"],
                    "type": desc["type"],
                    "a": desc["a"][:60],
                    "r": desc["r"][:60],
                    "cfg": ", ".join(cfgs),
                    "strength": strength,
                    "nAccept": n_accept,
                    "peers": ", ".join(acc_base[:8]) + ("…" if len(acc_base) > 8 else ""),
                    "nOpen": n_open,
                    "explain": expl,
                    "action": action,
                    "cites": cites,
                })

    # ---- write the human CSV ----
    cols = ["Site", "Configuration Section", "Configuration Element", "Attribute",
            "Deviation Type", "Site value (A)", "Standard value (R)", "Potential exception",
            "Grounding strength", "# Peer sites accepting", "Peer sites accepting",
            "Governing CFG-RFC", "# Sites still open", "Why it's a potential exception",
            "Suggested action", "Grounding & citations"]
    # sort: strongest grounding first, then most peer precedent
    order = {"STRONG": 0, "MODERATE": 1, "EMERGING": 2}
    csv_rows.sort(key=lambda x: (order.get(x["Grounding strength"], 9),
                                 -int(x["# Peer sites accepting"]), x["Site"]))
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(csv_rows)
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV} ({len(csv_rows)} potential-exception rows)")

    # ---- write the HTML payload ----
    site_blocks = []
    for site, items in sorted(by_site.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda x: (order.get(x["strength"], 9), -x["nAccept"]))
        st = defaultdict(int)
        for it in items:
            st[it["strength"]] += 1
        site_blocks.append({"site": site, "count": len(items),
                            "strength": dict(st), "items": items})
    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(IN_XSITE),
        "totals": {"rows": len(csv_rows), "sites": len(by_site),
                   "strength": dict(strength_tot)},
        "bySite": {b["site"]: b for b in site_blocks},
    }
    header = ("/* AUTO-GENERATED by tag_potential_exceptions.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · {payload['generatedAt']} */\n"
              "window.WHS_PXC = ")
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
    log(f"DONE strength split: STRONG {strength_tot.get('STRONG',0)} · "
        f"MODERATE {strength_tot.get('MODERATE',0)} · EMERGING {strength_tot.get('EMERGING',0)} "
        f"across {len(by_site)} sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
