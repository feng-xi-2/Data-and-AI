"""expert_feedback — let a domain EXPERT train the Config Drift explainer to be more
accurate, without retraining a model. Experts add verified examples; the explainer then
(1) answers identical deviations DETERMINISTICALLY from the expert's own words and
(2) injects the most relevant expert examples as FEW-SHOT guidance for the LLM on the rest.

WHY
---
Layer-2 (explain_deviations.py) is a general prompt. Two things make it drift from what a
CoE expert actually wants: unusual element semantics, and site/policy nuance the model
can't know. This module closes the loop: every expert correction becomes reusable ground
truth. Accuracy compounds as the library grows — and identical future deviations no longer
need the LLM at all (cheaper + 100% consistent with the expert).

STORAGE
-------
_replica_drift/expert_examples.jsonl — one JSON object per line (append-only, git-friendly).
Each record captures the deviation's stable identity + the expert's verdict:
  { id, created, author,
    match: { section, deviation_type, element, exception_code, site },
    verdict: { ai_class, ai_criticality, ai_explanation, ai_suggested_action, ai_citations },
    note }

MATCHING
--------
  match_exact(facts) -> the expert record whose element (or exception_code) matches this
                        deviation exactly -> used as a deterministic answer (no LLM).
  select_fewshot(facts, k) -> up to k most-relevant records (scored by shared exception
                        code / element / section / deviation_type) to steer the LLM.

Follows workspace rules: timestamped logs; no silent failure (log type+message then raise);
atomic append; tolerant JSONL reader that skips (and logs) a corrupt line rather than dying.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "_replica_drift")
STORE = os.path.join(OUT_DIR, "expert_examples.jsonl")
RULES = os.path.join(OUT_DIR, "expert_rules.jsonl")

_VALID_CRIT = {"HIGH", "MEDIUM", "LOW"}
# classes a rule may assign (must match enrich_deviations.classify vocabulary)
_VALID_CLASS = {"FORMATTING_ONLY", "FUNCTIONAL_CHANGE", "KNOWN_EXCEPTION",
                "MISSING_STANDARD", "UNSUPPORTED_RECORD", "STALE_EXCEPTION",
                "ORPHAN_EXCEPTION", "NEEDS_REVIEW"}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] expert: {msg}", flush=True)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def _cfg(s) -> str:
    m = re.search(r"CFG\d+", str(s or ""), re.IGNORECASE)
    return m.group(0).upper() if m else ""


# --------------------------------------------------------------------------- #
#  read / write                                                               #
# --------------------------------------------------------------------------- #
def load_examples() -> list[dict]:
    """Return all expert examples. Skips (and logs) corrupt lines, never dies on one."""
    if not os.path.exists(STORE):
        return []
    out = []
    with open(STORE, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                log(f"WARN skipping corrupt line {n}: {type(e).__name__}: {e}")
    return out


def add_example(*, section="", deviation_type="", element="", exception_code="",
                site="", ai_class="", ai_criticality="MEDIUM", ai_explanation="",
                ai_suggested_action="", ai_citations="", note="", author="expert") -> dict:
    """Append one expert-verified example. Returns the stored record.

    Requires at least an element OR an exception_code to be matchable, and an explanation.
    """
    element = str(element or "").strip()
    exception_code = _cfg(exception_code) or str(exception_code or "").strip().upper()
    if not (element or exception_code):
        raise ValueError("expert example needs an 'element' or an 'exception_code' to match on")
    if not str(ai_explanation or "").strip():
        raise ValueError("expert example needs a non-empty 'ai_explanation'")
    crit = str(ai_criticality or "MEDIUM").strip().upper()
    if crit not in _VALID_CRIT:
        crit = "MEDIUM"
    rec = {
        "id": "exp-" + uuid.uuid4().hex[:10],
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "author": str(author or "expert").strip(),
        "match": {
            "section": str(section or "").strip(),
            "deviation_type": str(deviation_type or "").strip(),
            "element": element,
            "exception_code": exception_code,
            "site": str(site or "").strip(),
        },
        "verdict": {
            "ai_class": str(ai_class or "").strip(),
            "ai_criticality": crit,
            "ai_explanation": str(ai_explanation).strip(),
            "ai_suggested_action": str(ai_suggested_action or "").strip(),
            "ai_citations": str(ai_citations or "").strip(),
        },
        "note": str(note or "").strip(),
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        with open(STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"ERROR writing example: {type(e).__name__}: {e}")
        raise
    log(f"added example {rec['id']} (element={element or exception_code})")
    return rec


# --------------------------------------------------------------------------- #
#  matching                                                                   #
# --------------------------------------------------------------------------- #
def match_exact(facts: dict, examples: list[dict] | None = None) -> dict | None:
    """Deterministic hit: an expert example whose element matches this deviation exactly
    (or, failing that, whose exception_code matches). Returns the verdict dict + provenance,
    or None. This is the highest-accuracy path — it reproduces the expert's own answer."""
    examples = load_examples() if examples is None else examples
    if not examples:
        return None
    el = _norm(facts.get("element"))
    code = _cfg(facts.get("exception_code"))
    by_element = None
    by_code = None
    for ex in examples:
        m = ex.get("match", {})
        if el and _norm(m.get("element")) == el:
            by_element = ex  # element match is the most specific
            break
        if code and _cfg(m.get("exception_code")) == code and by_code is None:
            by_code = ex
    hit = by_element or by_code
    if not hit:
        return None
    v = dict(hit.get("verdict", {}))
    v["_expert_id"] = hit.get("id")
    v["_expert_match"] = "element" if by_element else "exception_code"
    return v


def select_fewshot(facts: dict, k: int = 5, examples: list[dict] | None = None) -> list[dict]:
    """Return up to k most-relevant expert examples to inject as few-shot guidance.
    Scored by shared exception code (strong), element token overlap, section, and type."""
    examples = load_examples() if examples is None else examples
    if not examples:
        return []
    f_code = _cfg(facts.get("exception_code"))
    f_sec = _norm(facts.get("section"))
    f_type = _norm(facts.get("deviation_type"))
    f_el = _norm(facts.get("element"))
    f_tokens = set(re.split(r"[#\-_\s]+", f_el)) - {""}

    scored = []
    for ex in examples:
        m = ex.get("match", {})
        score = 0
        if f_code and _cfg(m.get("exception_code")) == f_code:
            score += 5
        if f_sec and _norm(m.get("section")) == f_sec:
            score += 2
        if f_type and _norm(m.get("deviation_type")) == f_type:
            score += 2
        e_tokens = set(re.split(r"[#\-_\s]+", _norm(m.get("element")))) - {""}
        overlap = len(f_tokens & e_tokens)
        score += min(overlap, 3)
        if score > 0:
            scored.append((score, ex))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [ex for _s, ex in scored[:k]]


def fewshot_block(examples: list[dict]) -> str:
    """Render selected expert examples as a compact text block for the LLM prompt."""
    if not examples:
        return ""
    lines = ["EXPERT-VERIFIED EXAMPLES (follow this style and these judgements when the "
             "deviation is similar; do not contradict a matching expert verdict):"]
    for ex in examples:
        m, v = ex.get("match", {}), ex.get("verdict", {})
        ident = m.get("element") or m.get("exception_code") or "(unspecified)"
        lines.append(
            f"- element={ident} | type={m.get('deviation_type','')} | "
            f"section={m.get('section','')} -> criticality={v.get('ai_criticality','')}, "
            f"action={v.get('ai_suggested_action','')}. {v.get('ai_explanation','')}")
    return "\n".join(lines)


def stats() -> dict:
    ex = load_examples()
    from collections import Counter
    crit = Counter(e.get("verdict", {}).get("ai_criticality", "") for e in ex)
    cls = Counter(e.get("verdict", {}).get("ai_class", "") for e in ex)
    return {"count": len(ex), "byCriticality": dict(crit), "byClass": dict(cls),
            "path": STORE.replace("\\", "/")}


# --------------------------------------------------------------------------- #
#  DYNAMIC EXCEPTION RULES                                                     #
#  --------------------------------------------------------------------------- #
#  Examples correct ONE deviation. A RULE generalises: it lets an expert teach a
#  standing policy that resolves whole classes of future deviations at Layer-1,
#  deterministically, with no LLM — the automated version of the manual
#  "exceptions file updated whenever a change is approved" (Raquel's ask #3).
#
#  A rule matches on the most specific signal present and re-classifies (and can
#  auto-resolve) the deviation:
#    { id, created, author,
#      match:  { exception_code, element, section, deviation_type, change_kind, site },
#      action: { classify_as, criticality, resolve, explanation, suggested_action, note } }
# --------------------------------------------------------------------------- #
def load_rules() -> list[dict]:
    """Return all expert rules. Skips (and logs) corrupt lines, never dies on one."""
    if not os.path.exists(RULES):
        return []
    out = []
    with open(RULES, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                log(f"WARN skipping corrupt rule line {n}: {type(e).__name__}: {e}")
    return out


def add_rule(*, exception_code="", element="", section="", deviation_type="",
             change_kind="", site="", classify_as="", criticality="MEDIUM",
             resolve=True, explanation="", suggested_action="", note="",
             author="expert") -> dict:
    """Append one standing rule. Needs at least one match signal and a target class."""
    exception_code = _cfg(exception_code) or str(exception_code or "").strip().upper()
    element = str(element or "").strip()
    section = str(section or "").strip()
    deviation_type = str(deviation_type or "").strip()
    change_kind = str(change_kind or "").strip().upper()
    if not (exception_code or element or (section and deviation_type) or change_kind):
        raise ValueError("a rule needs a match signal: exception_code, element, "
                         "section+deviation_type, or change_kind")
    classify_as = str(classify_as or "").strip().upper()
    if classify_as and classify_as not in _VALID_CLASS:
        raise ValueError(f"classify_as must be one of {sorted(_VALID_CLASS)}")
    crit = str(criticality or "MEDIUM").strip().upper()
    if crit not in _VALID_CRIT:
        crit = "MEDIUM"
    rec = {
        "id": "rule-" + uuid.uuid4().hex[:10],
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "author": str(author or "expert").strip(),
        "match": {
            "exception_code": exception_code, "element": element,
            "section": section, "deviation_type": deviation_type,
            "change_kind": change_kind, "site": str(site or "").strip(),
        },
        "action": {
            "classify_as": classify_as, "criticality": crit,
            "resolve": bool(resolve),
            "explanation": str(explanation or "").strip(),
            "suggested_action": str(suggested_action or "").strip(),
            "note": str(note or "").strip(),
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        with open(RULES, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"ERROR writing rule: {type(e).__name__}: {e}")
        raise
    log(f"added rule {rec['id']} (match on "
        f"{exception_code or element or (section + '/' + deviation_type) or change_kind})")
    return rec


def match_rule(facts: dict, rules: list[dict] | None = None) -> dict | None:
    """Return the most specific matching rule's action, or None.

    Precedence (most specific first): exception_code, element, section+deviation_type
    (optionally narrowed by change_kind), then change_kind alone. Optional 'site' on a
    rule must match when present.
    """
    if rules is None:
        rules = load_rules()
    if not rules:
        return None
    f_code = _cfg(facts.get("exception_code")) or str(facts.get("exception_code") or "").strip().upper()
    f_elem = _norm(facts.get("element"))
    f_sec = _norm(facts.get("section"))
    f_type = _norm(facts.get("deviation_type"))
    f_kind = str(facts.get("change_kind") or "").strip().upper()
    f_site = _norm(facts.get("audited_site") or facts.get("site"))

    def _site_ok(m):
        ms = _norm(m.get("site"))
        return (not ms) or ms == f_site

    scored = []  # (specificity, matched_on, rule)
    for r in rules:
        m = r.get("match", {})
        if not _site_ok(m):
            continue
        m_code = str(m.get("exception_code") or "").strip().upper()
        m_elem = _norm(m.get("element"))
        m_sec = _norm(m.get("section"))
        m_type = _norm(m.get("deviation_type"))
        m_kind = str(m.get("change_kind") or "").strip().upper()
        if m_code and f_code and m_code == f_code:
            spec, mon = 5, "exception_code"
        elif m_elem and f_elem and m_elem == f_elem:
            spec, mon = 4, "element"
        elif m_sec and m_type and m_sec == f_sec and m_type == f_type:
            if m_kind and m_kind == f_kind:
                spec, mon = 3, "section+type+kind"
            elif m_kind:
                continue  # rule wants a specific change_kind that didn't match
            else:
                spec, mon = 2, "section+type"
        elif m_kind and f_kind and m_kind == f_kind and not (m_code or m_elem or m_sec):
            spec, mon = 1, "change_kind"
        else:
            continue
        scored.append((spec, mon, r))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    spec, mon, r = scored[0]
    act = dict(r.get("action", {}))
    act["_rule_id"] = r.get("id", "")
    act["_rule_match"] = mon
    return act


def rules_stats() -> dict:
    rl = load_rules()
    from collections import Counter
    cls = Counter(r.get("action", {}).get("classify_as", "") for r in rl)
    return {"count": len(rl), "byClass": dict(cls), "path": RULES.replace("\\", "/")}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Manage expert training examples for the "
                                             "Config Drift explainer")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add", help="add one expert example")
    a.add_argument("--element", default="")
    a.add_argument("--exception-code", dest="exception_code", default="")
    a.add_argument("--section", default="")
    a.add_argument("--type", dest="deviation_type", default="")
    a.add_argument("--site", default="")
    a.add_argument("--class", dest="ai_class", default="")
    a.add_argument("--criticality", dest="ai_criticality", default="MEDIUM")
    a.add_argument("--explanation", dest="ai_explanation", required=True)
    a.add_argument("--action", dest="ai_suggested_action", default="")
    a.add_argument("--citations", dest="ai_citations", default="")
    a.add_argument("--note", default="")
    a.add_argument("--author", default="expert")
    sub.add_parser("list", help="list examples")
    sub.add_parser("stats", help="show stats")
    r = sub.add_parser("add-rule", help="add one standing exception rule")
    r.add_argument("--exception-code", dest="exception_code", default="")
    r.add_argument("--element", default="")
    r.add_argument("--section", default="")
    r.add_argument("--type", dest="deviation_type", default="")
    r.add_argument("--change-kind", dest="change_kind", default="")
    r.add_argument("--site", default="")
    r.add_argument("--classify-as", dest="classify_as", default="")
    r.add_argument("--criticality", dest="criticality", default="MEDIUM")
    r.add_argument("--resolve", dest="resolve", action="store_true", default=True)
    r.add_argument("--no-resolve", dest="resolve", action="store_false")
    r.add_argument("--explanation", dest="explanation", default="")
    r.add_argument("--action", dest="suggested_action", default="")
    r.add_argument("--note", default="")
    r.add_argument("--author", default="expert")
    sub.add_parser("list-rules", help="list rules")
    sub.add_parser("rules-stats", help="show rule stats")
    args = ap.parse_args()

    if args.cmd == "add":
        rec = add_example(
            element=args.element, exception_code=args.exception_code, section=args.section,
            deviation_type=args.deviation_type, site=args.site, ai_class=args.ai_class,
            ai_criticality=args.ai_criticality, ai_explanation=args.ai_explanation,
            ai_suggested_action=args.ai_suggested_action, ai_citations=args.ai_citations,
            note=args.note, author=args.author)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    elif args.cmd == "add-rule":
        rec = add_rule(
            exception_code=args.exception_code, element=args.element, section=args.section,
            deviation_type=args.deviation_type, change_kind=args.change_kind, site=args.site,
            classify_as=args.classify_as, criticality=args.criticality, resolve=args.resolve,
            explanation=args.explanation, suggested_action=args.suggested_action,
            note=args.note, author=args.author)
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    elif args.cmd == "list-rules":
        for r in load_rules():
            print(json.dumps(r, ensure_ascii=False))
    elif args.cmd == "rules-stats":
        print(json.dumps(rules_stats(), ensure_ascii=False, indent=2))
    elif args.cmd == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    else:
        for e in load_examples():
            print(json.dumps(e, ensure_ascii=False))
