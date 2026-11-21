"""site_exception_report — per-AUDITED-INSTANCE statistics that MIRROR the Config-Drift
report (PROD / SIT / UAT counted separately, never summed into a base site), then MARK
two governance facts on top of the report's own numbers:

  1  ACCEPTED-BY-OTHERS-WITH-GROUNDING-CRFC
     This site's finding is already ACCEPTED as an exception at >=1 OTHER site under a
     CFG-RFC that is live in the register. That registered code is the grounding CRFC.

  2  POTENTIAL-ACCEPT
     This site leaves the finding OPEN, but a peer already accepted the identical variation.
     -> it is a candidate to be accepted the same way (raise / adopt the CFG-RFC), not a defect.

WHY PER-INSTANCE
----------------
The report audits one physical warehouse once per environment (e.g. 'Ahmedabad TEVA',
'Ahmedabad TEVA- SIT', 'Ahmedabad TEVA- UAT'). Collapsing the '- UAT/SIT/SITH/PROD/TEST'
suffix and summing them TRIPLES a site's count (413+977+352 -> 1742). This report keeps the
report's own granularity so the totals reconcile line-for-line with all_sites_deviations.csv.
Peer precedent is still de-duplicated to the BASE site, so a site is never its own peer.

IDENTITY (site-independent, what a CFG-RFC governs)
---------------------------------------------------
  strict = Section | Element | Attribute | R value | Type   (identical standard variation)
  loose  = Section | Element | Type                         (same element/finding)

SEVERITY BUCKETS (mirrors the report)
-------------------------------------
  accepted            CoE-approved exception
  high / medium / low OPEN, penalised against the Config Score
  open = high+medium+low

OUTPUTS
-------
  Config report/site_exception_report.csv     one row per audited instance, report-native
                                              severity columns + the two governance marks.
  UIUX/assets/site-exception-report.js        window.WHS_SXR for the HTML surface.

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message
then raise); fixed absolute paths under the M&M workspace; no network.
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
COE = os.path.join(ONEDRIVE, "Config report", "data.xlsx")            # per-instance, has Notes
CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "site_exception_report.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "site-exception-report.js")

CFG_RE = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
GROUP_RE = re.compile(r"Group Name <([^>]*)>")
DEAD = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}
OPEN_SEV = ("high", "medium", "low")


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def base_site(name: str) -> str:
    """Collapse an environment suffix so PROD/SIT/UAT of one warehouse share a base identity."""
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
        log(f"note: register unreadable/missing ({path}); grounding falls back to code-present only")
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
    aval = col("Audited Value")
    rval = col("Reference Value")
    typ = col("Deviation Type")
    details = col("Deviation Details")
    notes = col("Deviation Notes").str.strip()
    rat = col("Rationale for Accepted").str.strip()

    log("indexing per-row CFG codes…")
    cfg = [row_cfg(rat.iloc[i], notes.iloc[i], details.iloc[i]) for i in range(n)]

    def ks(i):  # strict identity
        return (section.iloc[i].strip(), element.iloc[i].strip(), attr.iloc[i].strip(),
                rval.iloc[i].strip(), typ.iloc[i].strip())

    def kl(i):  # loose identity
        return (section.iloc[i].strip(), element.iloc[i].strip(), typ.iloc[i].strip())

    # Peer precedent: for each identity, which BASE sites ACCEPTED it, and which live
    # register CFG codes back that acceptance.
    log("building peer-acceptance precedent (strict + loose, base-site de-duped)…")
    acc_sites_strict: dict[tuple, set] = defaultdict(set)
    acc_sites_loose: dict[tuple, set] = defaultdict(set)
    acc_crfc_strict: dict[tuple, set] = defaultdict(set)   # live register codes only
    acc_crfc_loose: dict[tuple, set] = defaultdict(set)
    for i in range(n):
        if sev.iloc[i] != "accepted":
            continue
        bs = base_site(site.iloc[i])
        acc_sites_strict[ks(i)].add(bs)
        acc_sites_loose[kl(i)].add(bs)
        c = cfg[i]
        if c and reg.get(c, {}).get("valid", bool(c)):
            # a code is "grounding" if it is live in the register (or, if the register is
            # unavailable, any code counts — load_register logs that fallback)
            if not reg or reg.get(c, {}).get("valid"):
                acc_crfc_strict[ks(i)].add(c)
                acc_crfc_loose[kl(i)].add(c)

    log("rolling up per audited instance…")
    rows: dict[str, dict] = {}
    for i in range(n):
        s = site.iloc[i]
        bs = base_site(s)
        st = rows.get(s)
        if st is None:
            st = rows[s] = {
                "site": s, "base": bs, "total": 0,
                "accepted": 0, "high": 0, "medium": 0, "low": 0, "open": 0, "other": 0,
                "accepted_cfg_backed": 0, "accepted_unbacked": 0,
                "accepted_unbacked_peer_crfc": 0,          # unbacked here, peer governs under live CRFC
                "open_potential_accept": 0,                 # peer accepted identical variation
                "open_potential_accept_crfc": 0,            # peer acceptance carries a live CRFC (STRONG)
                "_ground_crfcs": set(),                     # the grounding codes seen for this site
                "_peer_sites": set(),                       # peer sites providing precedent
            }
        st["total"] += 1
        sv = sev.iloc[i]

        # peer precedent for this row's identity, excluding this warehouse's own base site
        peers_s = acc_sites_strict.get(ks(i), set()) - {bs}
        peers_l = acc_sites_loose.get(kl(i), set()) - {bs}
        peers = peers_s or peers_l
        crfcs = acc_crfc_strict.get(ks(i), set()) or acc_crfc_loose.get(kl(i), set())

        if sv == "accepted":
            st["accepted"] += 1
            if cfg[i]:
                st["accepted_cfg_backed"] += 1
            else:
                st["accepted_unbacked"] += 1
                if crfcs:
                    st["accepted_unbacked_peer_crfc"] += 1
                    st["_ground_crfcs"].update(crfcs)
                    st["_peer_sites"].update(peers)
        elif sv in OPEN_SEV:
            st[sv] += 1
            st["open"] += 1
            if peers:
                st["open_potential_accept"] += 1
                st["_peer_sites"].update(peers)
                if crfcs:
                    st["open_potential_accept_crfc"] += 1
                    st["_ground_crfcs"].update(crfcs)
        else:
            st["other"] += 1

    # ---- assemble output rows ----
    out = []
    for s, st in rows.items():
        gcodes = sorted(st["_ground_crfcs"])
        peers = sorted(st["_peer_sites"])
        governed = st["open_potential_accept_crfc"] + st["accepted_unbacked_peer_crfc"]
        out.append({
            "Audited Site": s,
            "Base Site": st["base"],
            "Total deviations": st["total"],
            "Accepted": st["accepted"],
            "High": st["high"],
            "Medium": st["medium"],
            "Low": st["low"],
            "Open (H+M+L)": st["open"],
            "Accepted — CFG-backed": st["accepted_cfg_backed"],
            "Accepted — unbacked (no CFG)": st["accepted_unbacked"],
            "Accepted-elsewhere w/ grounding CRFC": governed,
            "  · open → potential accept (CRFC-grounded)": st["open_potential_accept_crfc"],
            "  · accepted-unbacked → peer CRFC": st["accepted_unbacked_peer_crfc"],
            "Open → potential accept (any peer)": st["open_potential_accept"],
            "Grounding CRFCs": ", ".join(gcodes[:20]) + ("…" if len(gcodes) > 20 else ""),
            "Precedent peer sites": ", ".join(peers[:20]) + ("…" if len(peers) > 20 else ""),
        })
    out.sort(key=lambda r: -r["Total deviations"])

    cols = list(out[0].keys()) if out else ["Audited Site"]
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(out)
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV} ({len(out)} instances)")

    # ---- JS payload for the UIUX ----
    grand = Counter()
    for st in rows.values():
        for k in ("total", "accepted", "open", "accepted_cfg_backed", "accepted_unbacked",
                  "accepted_unbacked_peer_crfc", "open_potential_accept", "open_potential_accept_crfc"):
            grand[k] += st[k]
    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(COE),
        "granularity": "audited instance (report-native; environments NOT summed)",
        "totals": dict(grand),
        "sites": out,
    }
    header = ("/* AUTO-GENERATED by site_exception_report.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · {payload['generatedAt']} · per audited instance */\n"
              "window.WHS_SXR = ")
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
    log("GRAND TOTALS (per-instance, report-native):")
    log(f"  instances                          {len(out)}")
    log(f"  total deviations                   {grand['total']:,}")
    log(f"  accepted                           {grand['accepted']:,}  "
        f"(CFG-backed {grand['accepted_cfg_backed']:,} · unbacked {grand['accepted_unbacked']:,})")
    log(f"  open (H+M+L)                       {grand['open']:,}")
    log(f"  open → potential accept            {grand['open_potential_accept']:,}  "
        f"(CRFC-grounded {grand['open_potential_accept_crfc']:,})")
    log(f"  accepted-unbacked → peer CRFC      {grand['accepted_unbacked_peer_crfc']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
