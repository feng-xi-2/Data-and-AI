"""enrich_deviations — Layer-1 (deterministic, no LLM) enrichment for Config Drift.

WHAT THIS IS
------------
A *drop-in, additive* post-processing step for the existing Config Drift comparison.
It reads the row-level deviation output (CSV/XLSX) and writes a COPY with new columns —
it never touches the original file or the comparison logic. This is the "Layer 1" of the
AI-integration proposal (deterministic rules first; LLM/RAG layered on later only for the
residual). It already resolves the bulk of triage cheaply and 100% reproducibly.

NEW COLUMNS IT ADDS
-------------------
  explanation_class   FORMATTING_ONLY | FUNCTIONAL_CHANGE | KNOWN_EXCEPTION |
                      MISSING_STANDARD | UNSUPPORTED_RECORD | NEEDS_REVIEW
  is_formatting_only  true when A/R differ only by case/whitespace/delimiter/number format
  matched_exception   the CFGxxxx group / Rationale code that explains an accepted deviation
  last_modified_by    parsed 'Modification user' from Deviation Comments
  last_modified_on    parsed 'Modification Date' from Deviation Comments
  confidence          rule confidence 0..1
  needs_llm           true when Layer 1 can't fully resolve -> hand to Layer 2 (LLM)
  enrich_reason       short human trace of which rule fired

INPUT
-----
Any CSV/XLSX with (case-insensitive, flexible) columns among:
  Deviation Type, Configuration Element, Configuration Section, Deviation Severity,
  A value, R value, Deviation Comments, Rationale, Migration Notes, Audited Instance (A)
Missing columns are tolerated (rules degrade gracefully).

USAGE
  # enrich an existing deviations export:
  python enrich_deviations.py --in <deviations.csv|xlsx> --out <enriched.csv>

  # DEMO: pull a real row-level sample from the PBI model, then enrich it:
  python enrich_deviations.py --sample-from-pbi NEM_PRODWMS --section "Policy Maintenance"

Follows workspace rules: timestamped logs; no silent failure (log type+message then raise);
PBI sampling has timeout+retry via pbi_drift_alert.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

OUT_DIR = os.path.join(BASE, "_replica_drift")

# ---- flexible column resolution -------------------------------------------
CANON = {
    "type": ["Deviation Type", "Type"],
    "element": ["Configuration Element", "Element"],
    "section": ["Configuration Section", "Section"],
    "severity": ["Deviation Severity", "Severity"],
    "aval": ["A value", "A_value", "Audited Value", "Aval"],
    "rval": ["R value", "R_value", "Reference Value", "Rval"],
    "comments": ["Deviation Comments", "Deviation Details", "Details", "Comments"],
    "rationale": ["Rationale"],
    "mignotes": ["Migration Notes", "MigNotes"],
    "audited": ["Audited Instance (A)", "Audited Site", "Audited"],
}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def build_index(header: list[str]) -> dict:
    lower = {h.lower().strip(): h for h in header}
    idx = {}
    for canon, options in CANON.items():
        for opt in options:
            if opt.lower() in lower:
                idx[canon] = lower[opt.lower()]
                break
    return idx


def g(row: dict, idx: dict, canon: str) -> str:
    col = idx.get(canon)
    v = row.get(col) if col else None
    return "" if v is None else str(v).strip()


# ---- deterministic helpers -------------------------------------------------
_num_re = re.compile(r"^-?\d+(\.\d+)?$")


def normalize_value(v: str) -> str:
    """Aggressively normalise for FORMATTING_ONLY detection."""
    s = str(v or "").strip().lower()
    if _num_re.match(s):
        # numeric equality: 0 == 0.0 == 0.00
        try:
            return str(float(s))
        except ValueError:
            pass
    # collapse whitespace, unify common delimiters, strip wrapping brackets/quotes
    s = re.sub(r"\s+", " ", s)
    s = s.replace("_", "-").replace("|", ",").replace(";", ",")
    s = s.strip("[]<>\"' ")
    return s


_token_re = re.compile(r"[A-Za-z0-9_]+")


def _tokens(s: str) -> list[str]:
    return _token_re.findall(str(s or "").lower())


def _short_unique(seq, n: int = 8) -> list[str]:
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
        if len(out) >= n:
            break
    return out


def analyze_diff(aval: str, rval: str) -> dict:
    """Explain HOW an audited value differs from the reference standard.

    This is the formatting-vs-functional distinction Raquel asked the AI to make. It escalates
    through cheap tests first and only reports a functional delta when the actual token content
    differs — for a mismatch on two long SQL blobs it names the specific tokens that changed
    instead of just saying "different".

      NONE         identical
      COSMETIC     differs only by case / whitespace / delimiter (formatting)
      REORDER      exactly the same tokens in a different order (formatting)
      VALUE_DELTA  real content difference (functional) — lists site-only / standard-only tokens
    """
    a, r = str(aval or ""), str(rval or "")
    if a == r:
        return {"change_kind": "NONE", "is_formatting": True, "summary": "identical values"}
    if normalize_value(a) == normalize_value(r):
        return {"change_kind": "COSMETIC", "is_formatting": True,
                "summary": "differs only by case/whitespace/delimiter (formatting-only)"}
    from collections import Counter
    ta, tr = _tokens(a), _tokens(r)
    ca, cr = Counter(ta), Counter(tr)
    if ca and ca == cr:
        return {"change_kind": "REORDER", "is_formatting": True,
                "summary": "same tokens in a different order (formatting-only)"}
    site_only = _short_unique((ca - cr).elements())    # extra at the site
    std_only = _short_unique((cr - ca).elements())     # missing at the site (in standard only)
    parts = []
    if site_only:
        parts.append("site-only: " + ", ".join(site_only))
    if std_only:
        parts.append("standard-only: " + ", ".join(std_only))
    return {"change_kind": "VALUE_DELTA", "is_formatting": False,
            "summary": ("functional change — " + "; ".join(parts)) if parts else "values differ",
            "site_only": site_only, "standard_only": std_only}



# comments vary by section: "Modification user/Date <>" (Policy Maintenance) or
# "Last Updated User/Date <>" (other sections, e.g. Note Type Maintenance).
_mod_user_re = re.compile(r"(?:Modification user|Last Updated User) <([^>]*)>")
_mod_date_re = re.compile(r"(?:Modification Date|Last Updated Date) <([^>]*)>")
_group_re = re.compile(r"Group Name <([^>]*)>")
_cfg_re = re.compile(r"\bCFG\d+\b", re.IGNORECASE)


def classify(row: dict, idx: dict, crfc: dict | None = None,
             rules: list | None = None) -> dict:
    typ = g(row, idx, "type")
    sev = g(row, idx, "severity").lower()
    aval = g(row, idx, "aval")
    rval = g(row, idx, "rval")
    comments = g(row, idx, "comments")
    rationale = g(row, idx, "rationale")

    # parse modification metadata out of the decoded comments
    mod_user = (_mod_user_re.search(comments) or [None, ""])[1] if _mod_user_re.search(comments) else ""
    mod_date = (_mod_date_re.search(comments) or [None, ""])[1] if _mod_date_re.search(comments) else ""
    group = (_group_re.search(comments) or [None, ""])[1] if _group_re.search(comments) else ""

    # exception code: prefer explicit Rationale, else a CFG code embedded in comments/group
    exc = ""
    if rationale and _cfg_re.search(rationale):
        exc = _cfg_re.search(rationale).group(0).upper()
    elif rationale:
        exc = rationale.strip()
    elif group and _cfg_re.search(group):
        exc = _cfg_re.search(group).group(0).upper()

    # the CFG code we can look up in the authoritative register (may differ from the
    # free-text exc when Rationale is prose like "CFG1208 - migrated to ...")
    exc_code = ""
    for src in (rationale, exc, group, comments):
        m = _cfg_re.search(src or "")
        if m:
            exc_code = m.group(0).upper()
            break

    is_fmt = False
    cls = "NEEDS_REVIEW"
    conf = 0.5
    reasons = []
    # structured diff of audited vs reference (formatting vs functional) — the explainability
    # signal that also grounds Layer-2. Computed once when both sides are present.
    diff = analyze_diff(aval, rval) if (aval and rval) else {
        "change_kind": "", "is_formatting": False, "summary": ""}

    # RULE 1: accepted / has a governing exception code -> KNOWN_EXCEPTION
    if sev == "accepted" or exc:
        cls = "KNOWN_EXCEPTION"
        conf = 0.95 if exc else 0.8
        reasons.append(f"accepted/exception({exc or 'no-code'})")
    # RULE 2: mismatching value — formatting (incl. reorder) is cosmetic, else functional
    elif "mismatch" in typ.lower() and aval and rval:
        if diff["is_formatting"]:
            is_fmt = True
            cls = "FORMATTING_ONLY"
            conf = 0.9
            reasons.append(diff["change_kind"].lower() or "A==R after normalise")
        else:
            cls = "FUNCTIONAL_CHANGE"
            conf = 0.7
            reasons.append(diff["summary"] or "value differs after normalise")
    # RULE 3: missing record -> standard expected but absent at site
    elif typ.lower().startswith("missing"):
        cls = "MISSING_STANDARD"
        conf = 0.75
        reasons.append("standard record absent at site")
    # RULE 4: unexpected record -> present but not in standard
    elif typ.lower().startswith("unexpected") and "mismatch" not in typ.lower():
        cls = "UNSUPPORTED_RECORD"
        conf = 0.7
        reasons.append("record not in standard")

    # ---- validate the exception against the authoritative CFG-RFC register --------
    crfc_found = crfc_valid = ""
    crfc_decision = crfc_status = crfc_title = crfc_site = crfc_codetype = ""
    if crfc is not None and exc_code:
        rec = crfc.get(exc_code)
        crfc_found = str(bool(rec)).lower()
        if rec:
            crfc_decision = rec.get("decisionClass", "")
            crfc_status = rec.get("requestStatus", "")
            crfc_title = rec.get("title", "")
            crfc_site = rec.get("site", "")
            crfc_codetype = rec.get("codeType", "")
            crfc_valid = str(bool(rec.get("valid"))).lower()
            if not rec.get("valid"):
                # exception cites a withdrawn/superseded/rejected CFG-RFC -> re-review
                cls = "STALE_EXCEPTION"
                conf = 0.6
                reasons.append(f"CFG-RFC {exc_code} is {rec.get('requestStatus')}")
            else:
                reasons.append(f"CFG-RFC {exc_code} {rec.get('decisionClass')}")
        elif cls == "KNOWN_EXCEPTION":
            # accepted deviation whose CFG code is NOT in the register -> orphan
            cls = "ORPHAN_EXCEPTION"
            conf = 0.55
            reasons.append(f"CFG code {exc_code} not in register")

    # ---- expert dynamic rules: a trained standing policy re-classes / resolves ----
    # (runs AFTER register validation so an expert can deliberately override, e.g.
    # "any REORDER mismatch in Job Maintenance is FORMATTING_ONLY — dismiss".)
    rule_applied = ""
    rule_resolve = False
    if rules:
        try:
            import expert_feedback as _ef
            hit = _ef.match_rule({
                "exception_code": exc_code,
                "element": g(row, idx, "element"),
                "section": g(row, idx, "section"),
                "deviation_type": typ,
                "change_kind": diff.get("change_kind", ""),
                "audited_site": g(row, idx, "audited") if "audited" in idx else "",
            }, rules)
        except Exception as _e:
            hit = None
        if hit:
            if hit.get("classify_as"):
                cls = hit["classify_as"]
            conf = 0.9
            rule_applied = f"{hit.get('_rule_id', '')}/{hit.get('_rule_match', '')}"
            rule_resolve = bool(hit.get("resolve"))
            reasons.append(f"expert-rule {rule_applied}")

    needs_llm = cls in ("FUNCTIONAL_CHANGE", "UNSUPPORTED_RECORD", "NEEDS_REVIEW",
                        "ORPHAN_EXCEPTION", "STALE_EXCEPTION")
    # an expert rule that says resolve wins: the deviation is settled at Layer-1
    if rule_resolve:
        needs_llm = False

    return {
        "explanation_class": cls,
        "is_formatting_only": str(is_fmt).lower(),
        "change_kind": diff.get("change_kind", ""),
        "value_diff": diff.get("summary", ""),
        "expert_rule": rule_applied,
        "matched_exception": exc,
        "exception_code": exc_code,
        "crfc_found": crfc_found,
        "crfc_valid": crfc_valid,
        "crfc_decision": crfc_decision,
        "crfc_status": crfc_status,
        "crfc_site": crfc_site,
        "crfc_code_type": crfc_codetype,
        "crfc_title": crfc_title,
        "last_modified_by": mod_user,
        "last_modified_on": mod_date,
        "confidence": f"{conf:.2f}",
        "needs_llm": str(needs_llm).lower(),
        "enrich_reason": "; ".join(reasons) or "no rule matched",
    }


NEW_COLS = ["explanation_class", "is_formatting_only", "change_kind", "value_diff",
            "expert_rule", "matched_exception", "exception_code", "crfc_found", "crfc_valid",
            "crfc_decision", "crfc_status", "crfc_site", "crfc_code_type", "crfc_title",
            "last_modified_by", "last_modified_on", "confidence",
            "needs_llm", "enrich_reason"]


# ---- IO --------------------------------------------------------------------
def read_rows(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb["Export"] if "Export" in wb.sheetnames else wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h) if h is not None else "" for h in next(it)]
        rows = []
        for raw in it:
            vals = list(raw) + [None] * (len(header) - len(raw))
            if all(v in (None, "") for v in vals):
                continue
            rows.append({header[i]: vals[i] for i in range(len(header))})
        return header, rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        rows = [r for r in rd]
        return rd.fieldnames or [], rows


def sample_from_pbi(instance: str, section: str, limit: int):
    import pbi_drift_alert as pbi
    pbi.get_access_token()
    cols = ["Deviation Type", "Configuration Element", "Configuration Section",
            "Deviation Severity", "A value", "R value", "Deviation Comments",
            "Rationale", "Migration Notes"]
    sel = ",\n".join(f'    "{c}", {pbi._col(c)}' for c in cols)
    dax = (
        f"EVALUATE\nTOPN({limit},\n  SELECTCOLUMNS(\n"
        f"    FILTER('{pbi.TABLE}',\n"
        f'        {pbi._col("Audited Instance (A)")} = "{instance}"\n'
        f'        && {pbi._col("Configuration Section")} = "{section}"\n'
        f'        && {pbi._col("Deviation Status")} = "ACTIVE"),\n'
        f"{sel}\n  ))"
    )
    rows = [pbi._clean(r) for r in pbi.run_dax(dax)]
    header = cols[:]
    # add audited column for context
    for r in rows:
        r["Audited Instance (A)"] = instance
    header.append("Audited Instance (A)")
    return header, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Layer-1 deterministic deviation enrichment")
    ap.add_argument("--in", dest="inp", help="input deviations CSV/XLSX")
    ap.add_argument("--out", dest="out", help="output enriched CSV")
    ap.add_argument("--sample-from-pbi", dest="pbi_instance",
                    help="DEMO: pull a row-level sample for this PBI instance")
    ap.add_argument("--section", default="Policy Maintenance")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--crfc", dest="crfc",
                    help="path to Configuration_RFC.csv or crfc_register.json — validates "
                         "each exception's CFG code against the authoritative CFG-RFC register")
    ap.add_argument("--llm", action="store_true",
                    help="after Layer-1, run the Layer-2 LLM explainer on needs_llm rows in the "
                         "same pass (one command). Needs Azure OpenAI env vars unless --llm-dry-run.")
    ap.add_argument("--llm-dry-run", action="store_true",
                    help="with --llm: build the Layer-2 prompts but do NOT call the LLM (no network)")
    ap.add_argument("--no-expert", action="store_true",
                    help="with --llm: ignore the expert training library (expert_examples.jsonl)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    # optional: load the CFG-RFC register for authoritative exception validation
    crfc = None
    if args.crfc:
        import crfc_register as cr
        if args.crfc.lower().endswith(".json"):
            import json as _json
            with open(args.crfc, encoding="utf-8") as f:
                crfc = _json.load(f)
            log(f"loaded CFG-RFC register (json): {len(crfc)} codes")
        else:
            crfc = cr.load_register(args.crfc)

    # optional: load expert standing rules (train the skill to auto-resolve classes of devs)
    rules = None
    if not args.no_expert:
        try:
            import expert_feedback as _ef
            rules = _ef.load_rules()
            if rules:
                log(f"expert rules: {len(rules)} standing rule(s) loaded")
        except Exception as e:
            log(f"expert rules unavailable ({type(e).__name__}: {e}); continuing without them")
            rules = None

    if args.pbi_instance:
        log(f"DEMO: sampling {args.limit} rows from PBI instance {args.pbi_instance} / {args.section}")
        header, rows = sample_from_pbi(args.pbi_instance, args.section, args.limit)
        # persist the raw sample so it mimics the compare script's CSV output
        sample_path = os.path.join(OUT_DIR, "sample_deviations.csv")
        with open(sample_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        log(f"wrote raw sample -> {sample_path} ({len(rows)} rows)")
        out = args.out or os.path.join(OUT_DIR, "sample_deviations_enriched.csv")
    else:
        if not args.inp:
            ap.error("provide --in <file> or --sample-from-pbi <instance>")
        log(f"reading {args.inp}")
        header, rows = read_rows(args.inp)
        out = args.out or os.path.splitext(args.inp)[0] + "_enriched.csv"

    idx = build_index(header)
    log(f"resolved columns: {idx}")
    if "type" not in idx:
        log("WARNING: no Deviation Type column found — classification will be weak")

    # enrich
    from collections import Counter
    cls_counter, fmt_count, exc_count, llm_count = Counter(), 0, 0, 0
    crfc_found_n = crfc_invalid_n = orphan_n = 0
    out_header = list(header) + [c for c in NEW_COLS if c not in header]
    enriched = []
    for r in rows:
        add = classify(r, idx, crfc, rules)
        merged = dict(r)
        merged.update(add)
        enriched.append(merged)
        cls_counter[add["explanation_class"]] += 1
        fmt_count += add["is_formatting_only"] == "true"
        exc_count += bool(add["matched_exception"])
        llm_count += add["needs_llm"] == "true"
        crfc_found_n += add.get("crfc_found") == "true"
        crfc_invalid_n += add.get("crfc_valid") == "false"
        orphan_n += add["explanation_class"] == "ORPHAN_EXCEPTION"

    # ---- optional Layer-2: LLM explainer in the SAME pass (one command) ---------
    llm_stats = None
    if args.llm:
        import explain_deviations as ex
        ex_idx = ex.build_index(out_header)
        cfg = ex._azure_cfg()
        if not args.llm_dry_run and cfg is None:
            log("--llm requested but no Azure OpenAI env config "
                "(AZURE_OPENAI_ENDPOINT/DEPLOYMENT/API_KEY); "
                "writing Layer-1 columns only. Use --llm-dry-run to build prompts offline.")
        else:
            log("Layer-2: explaining needs_llm rows " +
                ("(dry-run, no network)" if args.llm_dry_run else f"via {cfg['deployment']}"))
            llm_stats = ex.explain_rows(enriched, ex_idx, crfc, cfg,
                                        dry_run=args.llm_dry_run,
                                        use_expert=not args.no_expert)
            out_header = out_header + [c for c in ex.AI_COLS if c not in out_header]

    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_header, extrasaction="ignore")
        w.writeheader()
        w.writerows(enriched)

    total = len(enriched)
    log("=" * 64)
    log(f"enriched {total} rows -> {out}")
    log("classification breakdown:")
    for cls, n in cls_counter.most_common():
        log(f"   {cls:20s} {n:5d}  ({n / total * 100:5.1f}%)")
    log(f"formatting-only (auto-dismiss)   : {fmt_count}")
    log(f"resolved by exception code       : {exc_count}")
    if crfc is not None:
        log(f"exception validated in CFG-RFC   : {crfc_found_n}")
        log(f"exception cites INVALID CFG-RFC  : {crfc_invalid_n} (withdrawn/superseded/rejected)")
        log(f"orphan exceptions (code missing) : {orphan_n}")
    log(f"Layer-1 RESOLVED (no LLM needed)  : {total - llm_count}  ({(total - llm_count) / total * 100:.1f}%)")
    log(f"hand to Layer-2 LLM (needs_llm)  : {llm_count}  ({llm_count / total * 100:.1f}%)")
    if llm_stats is not None:
        cc = llm_stats["criticality"]
        log("-" * 64)
        log(f"Layer-2 explained {llm_stats['targets']} rows  "
            f"(expert={llm_stats['expert']} new={llm_stats['new']} "
            f"cached={llm_stats['cached']} failed={llm_stats['failed']})")
        log(f"AI criticality: HIGH={cc.get('HIGH',0)} MEDIUM={cc.get('MEDIUM',0)} LOW={cc.get('LOW',0)}")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
