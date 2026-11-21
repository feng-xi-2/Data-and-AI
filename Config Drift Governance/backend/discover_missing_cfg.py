"""discover_missing_cfg — for every ACCEPTED Config-Drift deviation that carries NO
CFG-RFC code, discover the CFG record that most likely governs it, with SOLID grounding.

THE PROBLEM (from the COE reference, data.xlsx)
-----------------------------------------------
An 'accepted' deviation is a CoE-approved exception and must be justified by a CFG-RFC.
But thousands of accepted rows have NO CFG code on them (UNBACKED) or are justified only by
a free-text Deviation Note. An unbacked acceptance may be masking a real gap, and it cannot
be audited. This module finds the governing CFG for those rows — but only when there is
real evidence, never by guessing.

THE GROUNDING (evidence cascade, strongest first)
-------------------------------------------------
For each accepted-no-CFG row we look for the CFG in this order and record WHICH rule fired:

  1 PEER_PRECEDENT   another site ACCEPTED the IDENTICAL deviation identity
                     (Section | Element | Attribute | A | R | Type) WITH a CFG code.
                     -> that same variation is already governed elsewhere.
                     STRONG when the CFG is in the register; MODERATE otherwise.
  2 NOTE_REFERENCE   the row's own Deviation Note / Rationale text names a CFG code, or a
                     change artefact (EXCPCHG / SSCD / TMPLCHG / P-RFC / repair script).
                     STRONG for a register CFG; MODERATE for a script/ticket reference.
  3 SAME_SITE_SIBLING same site + same policy/element group (element before '#') has a
                     coded acceptance on another row -> the group's CFG most likely applies.
                     MODERATE (>=2 sibling rows) else EMERGING.
  4 REGISTER_TITLE   the element/section tokens match a CFG-RFC register Title.
                     EMERGING — a lead only, must be confirmed by a human.
  (none)            no evidence -> discovered_cfg empty, decision defaults to REVIEW.

Every candidate is a PROPOSAL. Nothing is auto-applied — it enters the human decision layer
(see cfg_decision.py + the config-drift-human-decision skill) for CoE ACCEPT / REJECT /
REASSIGN before it becomes an accepted, governed exception.

OUTPUTS
-------
  Config report/discovered_missing_cfg.csv     human-readable, one row per accepted-no-CFG
                                               deviation, with plain-English grounding.
  UIUX/assets/discovered-cfg.js                window.WHS_CFGD for the HTML review surface.
  _replica_drift/cfg_decisions.jsonl           the decision QUEUE (status=PENDING) that the
                                               human decision layer reads and updates.

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message
then raise); fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
COE = os.path.join(ONEDRIVE, "Config report", "data.xlsx")            # COE reference (has Notes)
CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "discovered_missing_cfg.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "discovered-cfg.js")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
QUEUE = os.path.join(OUT_DIR, "cfg_decisions.jsonl")

CFG_RE = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
GROUP_RE = re.compile(r"Group Name <([^>]*)>")
# change artefacts a note may cite instead of a bare CFG code
ARTEFACT_RE = re.compile(r"\b(?:EXCPCHG|SSCD|TMPLCHG|SCDR|P-?RFC|PR-?Bug)[A-Za-z0-9._-]*", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}")
SAMPLES_PER_SITE = 60
STOP = {"the", "and", "for", "not", "with", "από", "cfg", "new", "site", "config",
        "configuration", "value", "record", "maintenance", "policy", "var", "usr", "uc"}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def base_site(name: str) -> str:
    n = re.sub(r"\s*-\s*(UAT\d*|SITH?|SIT|PROD|TEST)\b.*$", "", str(name or ""), flags=re.IGNORECASE)
    return n.strip()


def elem_base(el: str) -> str:
    return str(el or "").split("#", 1)[0].strip()


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


def load_register(path: str):
    """code -> {title,status,decision,site,valid}; plus a token->codes index over Titles."""
    reg: dict[str, dict] = {}
    tok_index: dict[str, set] = defaultdict(set)
    text = read_text(path)
    if not text:
        log(f"note: CFG-RFC register unreadable/missing ({path}); title matching disabled")
        return reg, tok_index
    dead = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}
    for row in csv.DictReader(text.splitlines()):
        blob = " ".join(str(row.get(k) or "") for k in ("Code", "Title"))
        m = CFG_RE.search(blob)
        if not m:
            continue
        code = m.group(0).upper()
        title = (row.get("Title") or "").strip()
        status = (row.get("Request Status") or "").strip()
        decision = (row.get("Decision Status") or "").strip()
        site = (row.get("Site") or "").strip()
        reg[code] = {
            "title": CFG_RE.sub("", title).strip(" -:·") or title,
            "status": status, "decision": decision, "site": site,
            "valid": status.lower() not in dead,
        }
        for t in TOKEN_RE.findall(title.lower()):
            if t not in STOP:
                tok_index[t].add(code)
    log(f"CFG-RFC register: {len(reg)} codes indexed")
    return reg, tok_index


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


def ident_key(section, element, attr, a, r, typ) -> tuple:
    return (section.strip(), element.strip(), attr.strip(), a.strip(), r.strip(), typ.strip())


def strength_rank(s: str) -> int:
    return {"STRONG": 0, "MODERATE": 1, "EMERGING": 2, "NONE": 3}.get(s, 4)


def main() -> int:
    if not os.path.exists(COE):
        log(f"ERROR COE reference not found: {COE}")
        raise SystemExit(2)
    os.makedirs(OUT_DIR, exist_ok=True)

    reg, tok_index = load_register(CRFC)

    log(f"reading {COE}")
    try:
        df = pd.read_excel(COE, sheet_name="Export")
    except Exception as e:
        log(f"ERROR failed to read COE xlsx: {type(e).__name__}: {e}")
        raise
    df.columns = [c.strip() for c in df.columns]
    n = len(df)
    log(f"{n} rows loaded")

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
    attr_gui = col("Element Attribute Name (GUI)")
    aval = col("Audited Value")
    rval = col("Reference Value")
    typ = col("Deviation Type")
    details = col("Deviation Details")
    notes = col("Deviation Notes").str.strip()
    rat = col("Rationale for Accepted").str.strip()

    log("indexing CFG evidence across all rows…")
    # per-row CFG code
    cfg = [row_cfg(rat.iloc[i], notes.iloc[i], details.iloc[i]) for i in range(n)]

    # Peer precedent is keyed at the VARIATION level, not the exact row: an accepted
    # exception's CFG governs a specific element+attribute+standard-value+type, regardless
    # of the site's own audited value. Two keys, strict first then loose:
    #   strict = Section | Element | Attribute | R value | Type   (the governed variation)
    #   loose  = Section | Element | Type                         (the element/finding)
    peer_strict: dict[tuple, Counter] = defaultdict(Counter)
    peer_strict_sites: dict[tuple, dict] = defaultdict(lambda: defaultdict(set))
    peer_loose: dict[tuple, Counter] = defaultdict(Counter)
    peer_loose_sites: dict[tuple, dict] = defaultdict(lambda: defaultdict(set))
    # same-site element-group -> Counter of CFG codes
    sib_cfg: dict[tuple, Counter] = defaultdict(Counter)

    def ks(i):
        return (section.iloc[i].strip(), element.iloc[i].strip(), attr.iloc[i].strip(),
                rval.iloc[i].strip(), typ.iloc[i].strip())

    def kl(i):
        return (section.iloc[i].strip(), element.iloc[i].strip(), typ.iloc[i].strip())

    for i in range(n):
        c = cfg[i]
        if not c:
            continue
        if sev.iloc[i] == "accepted":
            bs = base_site(site.iloc[i])
            peer_strict[ks(i)][c] += 1
            peer_strict_sites[ks(i)][c].add(bs)
            peer_loose[kl(i)][c] += 1
            peer_loose_sites[kl(i)][c].add(bs)
        sk = (base_site(site.iloc[i]), section.iloc[i].strip(), elem_base(element.iloc[i]))
        sib_cfg[sk][c] += 1

    log("discovering missing CFG for accepted-no-CFG rows…")
    accepted_no_cfg = [(i) for i in range(n) if sev.iloc[i] == "accepted" and not cfg[i]]
    log(f"accepted-no-CFG rows to resolve: {len(accepted_no_cfg)}")

    csv_rows = []
    by_site = defaultdict(list)
    method_tot = Counter()
    strength_tot = Counter()
    queue_lines = []

    for i in accepted_no_cfg:
        s = site.iloc[i]
        sec = section.iloc[i].strip()
        el = element.iloc[i].strip()
        at = (attr_gui.iloc[i] or attr.iloc[i]).strip()
        a, r = aval.iloc[i].strip(), rval.iloc[i].strip()
        tp = typ.iloc[i].strip()
        note = notes.iloc[i].strip()
        k = ident_key(sec, el, attr.iloc[i], a, r, tp)
        ksi = (sec, el, attr.iloc[i].strip(), r, tp)
        kli = (sec, el, tp)

        method = "NONE"
        strength = "NONE"
        cand = []            # candidate CFG codes
        evidence = ""        # short grounding phrase
        peers = []

        # 1 PEER_PRECEDENT — variation-level (strict: same standard value), else element-level
        pc = peer_strict.get(ksi)
        peer_scope = "strict"
        if not pc:
            pc = peer_loose.get(kli)
            peer_scope = "loose"
        if pc:
            cand = [c for c, _ in pc.most_common()]
            top = cand[0]
            sites_map = peer_strict_sites if peer_scope == "strict" else peer_loose_sites
            key_used = ksi if peer_scope == "strict" else kli
            peers = sorted(sites_map[key_used][top] - {base_site(s)})
            in_reg = top in reg
            npeers = len(sites_map[key_used][top] | {base_site(s)}) - (0 if base_site(s) in sites_map[key_used][top] else 1)
            npeers = max(len(peers), 1)
            method = "PEER_PRECEDENT"
            # STRONG needs the code in the register AND a same-standard-value (strict) match;
            # a loose element-level match tops out at MODERATE (human confirms the exact variation).
            if peer_scope == "strict" and in_reg:
                strength = "STRONG"
            elif in_reg or npeers >= 3:
                strength = "MODERATE"
            else:
                strength = "MODERATE" if peer_scope == "strict" else "EMERGING"
            scope_txt = ("the identical variation (same standard value)" if peer_scope == "strict"
                         else "the same element and deviation type")
            evidence = (f"{npeers} peer site(s) accepted {scope_txt} under "
                        f"{', '.join(cand[:3])}" + (f" — register: {reg[top]['title'][:50]}" if in_reg else " (code not in register)"))

        # 2 NOTE_REFERENCE
        if method == "NONE" and (note or rat.iloc[i]):
            blob = note + " || " + rat.iloc[i]
            m = CFG_RE.search(blob)
            if m:
                c = m.group(0).upper()
                cand = [c]
                method = "NOTE_REFERENCE"
                strength = "STRONG" if c in reg else "MODERATE"
                evidence = f"the deviation note names {c}" + (f" ({reg[c]['title'][:50]})" if c in reg else " (not in register)")
            else:
                art = ARTEFACT_RE.search(blob)
                if art:
                    method = "NOTE_REFERENCE"
                    strength = "MODERATE"
                    evidence = f"the note cites change artefact '{art.group(0)}' — trace it to its CFG-RFC"

        # 3 SAME_SITE_SIBLING
        if method == "NONE":
            sk = (base_site(s), sec, elem_base(el))
            sc = sib_cfg.get(sk)
            if sc:
                cand = [c for c, _ in sc.most_common()]
                top = cand[0]
                cnt = sc[top]
                method = "SAME_SITE_SIBLING"
                strength = "MODERATE" if cnt >= 2 else "EMERGING"
                evidence = (f"same site governs {cnt} sibling row(s) of '{elem_base(el)}' under "
                            f"{', '.join(cand[:3])}")

        # 4 REGISTER_TITLE — weak lead only (requires >=3 distinctive token hits)
        if method == "NONE" and tok_index:
            toks = [t for t in TOKEN_RE.findall((el + " " + sec + " " + at).lower()) if t not in STOP]
            score = Counter()
            for t in set(toks):
                codes = tok_index.get(t, ())
                if len(codes) > 40:        # skip common tokens that match too many titles
                    continue
                for c in codes:
                    score[c] += 1
            if score:
                best, hits = score.most_common(1)[0]
                if hits >= 3:
                    cand = [c for c, _ in score.most_common(3)]
                    method = "REGISTER_TITLE"
                    strength = "EMERGING"
                    evidence = (f"element tokens match {hits} distinctive word(s) in the Title of {cand[0]} "
                                f"(\"{reg.get(cand[0],{}).get('title','')[:50]}\") — WEAK lead, confirm manually")

        discovered = cand[0] if cand else ""
        # natural-language explanation + suggested decision
        what = f"{sec} · {el}" + (f" · {at}" if at else "")
        if tp.lower().startswith("missing"):
            finding = "the standard defines this record but the site does not have it"
        elif "mismatch" in tp.lower():
            finding = f"the site value \u201c{a or '(blank)'}\u201d differs from the standard \u201c{r or '(blank)'}\u201d"
        else:
            finding = "the site carries a record that is not in the standard"

        if method == "NONE":
            expl = (f"{s} has accepted this deviation ({finding}) but no CFG-RFC is recorded and no "
                    f"evidence of a governing change could be found on the row, at peer sites, or in "
                    f"the register. This acceptance is UNBACKED — it may be masking a real gap.")
            suggested = "REVIEW"
            action_nl = ("No candidate found. A CoE reviewer must either attach the correct CFG-RFC, "
                         "raise a new one, or re-open the deviation. Do not leave it silently accepted.")
        else:
            pe = (" Peers already governed under this code: " + ", ".join(peers[:6]) + ("…" if len(peers) > 6 else "")) if peers else ""
            expl = (f"{s} accepted this deviation ({finding}) without recording a CFG-RFC. "
                    f"Evidence points to {discovered or 'a change artefact'} as the governing record: {evidence}.{pe} "
                    f"This is a PROPOSAL for a human to confirm before the acceptance is treated as governed.")
            if strength == "STRONG":
                suggested = "ATTACH_CFG"
                action_nl = (f"Attach {discovered} to {s}'s acceptance of this deviation. The identical "
                             f"variation is already governed by {discovered} in the register — this only "
                             f"closes the governance gap, no functional change to the site.")
            elif strength == "MODERATE":
                suggested = "ATTACH_CFG_OR_CONFIRM"
                action_nl = (f"Likely governed by {discovered or 'the cited artefact'}. Confirm it is the "
                             f"correct CFG-RFC (it may be missing from the register), then attach it; "
                             f"otherwise raise a new CFG-RFC.")
            else:
                suggested = "CONFIRM_LEAD"
                action_nl = (f"Weak lead ({discovered}). Verify against the Standard Configuration Library "
                             f"and the register before attaching; do not auto-accept on this evidence alone.")

        cites = (f"[PYTHON] discovery rule {method}. "
                 + (f"[DRIFT] cross-site identity precedent. " if method == "PEER_PRECEDENT" else "")
                 + (f"[CRFC] {discovered} present in register — {reg[discovered]['status']}/{reg[discovered]['decision']}. "
                    if discovered in reg else
                    ("[CRFC] candidate not found in the register (governance gap). " if discovered else "[CRFC] no candidate. "))
                 + "[GENERAL] an accepted deviation must be backed by a CFG-RFC; an unbacked acceptance is a governance gap, not a pass.")

        did = hashlib.sha1(("|".join(k) + "|" + s).encode("utf-8")).hexdigest()[:12]
        row = {
            "Decision ID": did,
            "Site": s,
            "Configuration Section": sec,
            "Configuration Element": el,
            "Attribute": at,
            "Deviation Type": tp,
            "Site value (A)": a,
            "Standard value (R)": r,
            "Existing note": note[:300],
            "Discovered CFG-RFC": discovered,
            "Candidate CFG(s)": ", ".join(cand[:5]),
            "Discovery method": method,
            "Grounding strength": strength,
            "Evidence": evidence,
            "Peer sites (governed)": ", ".join(peers[:12]),
            "Why (plain English)": expl,
            "Suggested decision": suggested,
            "Suggested action": action_nl,
            "Grounding & citations": cites,
            "Human decision": "PENDING",
            "Decided CFG-RFC": "",
            "Decided by": "",
            "Decided on": "",
            "Decision note": "",
        }
        csv_rows.append(row)
        method_tot[method] += 1
        strength_tot[strength] += 1

        if len(by_site[s]) < SAMPLES_PER_SITE:
            by_site[s].append({
                "id": did, "section": sec, "element": el[:80], "attr": at, "type": tp,
                "a": a[:60], "r": r[:60], "note": note[:160],
                "cfg": discovered, "cands": cand[:5], "method": method, "strength": strength,
                "evidence": evidence[:240], "peers": ", ".join(peers[:8]) + ("…" if len(peers) > 8 else ""),
                "explain": expl, "suggested": suggested, "action": action_nl, "cites": cites,
            })

        queue_lines.append(json.dumps({
            "id": did, "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "site": s, "identity": list(k),
            "discovered_cfg": discovered, "candidates": cand[:5],
            "method": method, "strength": strength, "evidence": evidence,
            "suggested": suggested, "status": "PENDING",
            "decided_cfg": "", "decided_by": "", "decided_on": "", "note": "",
        }, ensure_ascii=False))

    # ---- write human CSV (sorted strongest first) ----
    order = {"STRONG": 0, "MODERATE": 1, "EMERGING": 2, "NONE": 3}
    csv_rows.sort(key=lambda x: (order.get(x["Grounding strength"], 9), x["Site"]))
    cols = list(csv_rows[0].keys()) if csv_rows else ["Decision ID"]
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(csv_rows)
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV} ({len(csv_rows)} rows)")

    # ---- write HTML payload ----
    site_blocks = []
    for sname, items in sorted(by_site.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda x: order.get(x["strength"], 9))
        st = Counter(it["strength"] for it in items)
        me = Counter(it["method"] for it in items)
        site_blocks.append({"site": sname, "count": len(items),
                            "strength": dict(st), "method": dict(me), "items": items})
    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(COE),
        "totals": {"rows": len(csv_rows), "sites": len(by_site),
                   "method": dict(method_tot), "strength": dict(strength_tot)},
        "bySite": {b["site"]: b for b in site_blocks},
    }
    header = ("/* AUTO-GENERATED by discover_missing_cfg.py — do not edit by hand.\n"
              f"   Source: {payload['source']} · {payload['generatedAt']} */\n"
              "window.WHS_CFGD = ")
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

    # ---- write decision queue (only if absent, to preserve human decisions) ----
    if os.path.exists(QUEUE):
        log(f"decision queue already exists ({QUEUE}); NOT overwriting to preserve human decisions. "
            f"Use cfg_decision.py to sync new candidates.")
    else:
        try:
            with open(QUEUE, "w", encoding="utf-8") as fh:
                fh.write("\n".join(queue_lines) + ("\n" if queue_lines else ""))
        except Exception as e:
            log(f"ERROR failed to write {QUEUE}: {type(e).__name__}: {e}")
            raise
        log(f"wrote {QUEUE} ({len(queue_lines)} PENDING decisions)")

    log("DONE  method split: " + ", ".join(f"{k} {v}" for k, v in method_tot.most_common()))
    log("      strength split: " + ", ".join(f"{k} {v}" for k, v in strength_tot.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
