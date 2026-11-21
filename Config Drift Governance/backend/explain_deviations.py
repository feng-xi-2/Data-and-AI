"""explain_deviations — Layer-2 (LLM) explainer for Config Drift, additive on top of Layer-1.

WHAT THIS IS
------------
The escalation stage of the AI-integration proposal. Layer-1 (enrich_deviations.py) already
resolves the bulk of deviations deterministically and flags the residual with needs_llm=true.
This module takes the *enriched* CSV, selects ONLY the needs_llm rows, grounds each one with
its own facts (deviation type, element key, A/R values, decoded Deviation Comments, and the
matching CFG-RFC register record), asks an LLM for a short structured judgement, and writes a
COPY with four extra columns. It never touches the original file, never re-runs Layer-1, and
never overwrites the deterministic columns.

WHY A SEPARATE PASS
-------------------
  * cost/control : the LLM only sees the ~35-40% Layer-1 could not close, not every row.
  * grounding    : the prompt carries the CFG-RFC record verbatim, so the model explains
                   against the authoritative register instead of guessing.
  * safety       : deterministic output is already on disk; if the LLM is down the run still
                   completes and marks the affected rows LLM_UNAVAILABLE (never silent-drop).

NEW COLUMNS IT ADDS (only populated for needs_llm=true rows)
------------------------------------------------------------
  ai_explanation      one-paragraph plain-English reason the deviation exists / what it means
  ai_criticality      HIGH | MEDIUM | LOW  (business risk of leaving it unresolved)
  ai_suggested_action e.g. "raise CFG-RFC", "align to standard", "accept — cosmetic", "escalate"
  ai_citations        the grounded facts the model used (CFG code + register status, element)

LLM WIRING (pluggable, P&G-ecosystem-friendly, env-driven)
----------------------------------------------------------
Azure OpenAI chat completions over plain HTTPS (no SDK dependency). Set:
  AZURE_OPENAI_ENDPOINT      e.g. https://<resource>.openai.azure.com
  AZURE_OPENAI_DEPLOYMENT    e.g. gpt-4o  (deployment name, not model name)
  AZURE_OPENAI_API_VERSION   e.g. 2024-06-01   (optional; sensible default)
  AZURE_OPENAI_API_KEY       api key            (or use --dry-run to skip calling)
If no endpoint/key is configured, run with --dry-run to build+inspect the prompts and see the
exact per-row grounding without making any network call.

USAGE
  # real run (needs Azure OpenAI env vars), validating against the CFG-RFC register:
  python explain_deviations.py --in _replica_drift\\ahm_enriched.csv \
        --crfc "..\\..\\Config report\\Configuration_RFC.csv" --out _replica_drift\\ahm_explained.csv

  # dry run — no network; writes prompts + a stub so you can eyeball the grounding:
  python explain_deviations.py --in _replica_drift\\ahm_enriched.csv --dry-run

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then
continue-with-marker or raise); every LLM call has a timeout AND bounded retry with backoff; a
disk cache keyed on the grounded facts avoids paying twice for identical rows.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
OUT_DIR = os.path.join(BASE, "_replica_drift")
CACHE_PATH = os.path.join(OUT_DIR, "llm_explain_cache.json")

AI_COLS = ["ai_explanation", "ai_criticality", "ai_suggested_action", "ai_citations"]

# columns Layer-1 wrote that we ground the prompt on
CANON = {
    "type": ["Deviation Type", "Type"],
    "element": ["Configuration Element", "Element"],
    "section": ["Configuration Section", "Section"],
    "severity": ["Deviation Severity", "Severity"],
    "aval": ["A value", "A_value", "Audited Value", "Aval"],
    "rval": ["R value", "R_value", "Reference Value", "Rval"],
    "comments": ["Deviation Comments", "Deviation Details", "Details", "Comments"],
    "audited": ["Audited Instance (A)", "Audited Site", "Audited"],
}

_num_re = re.compile(r"^-?\d+(\.\d+)?$")


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


# --------------------------------------------------------------------------- #
#  grounding: build the fact block the model is allowed to reason over         #
# --------------------------------------------------------------------------- #
def build_facts(row: dict, idx: dict, crfc: dict | None) -> dict:
    """Assemble ONLY grounded facts for one deviation. No invention."""
    exc_code = str(row.get("exception_code") or "").strip().upper()
    facts = {
        "audited_site": g(row, idx, "audited") or str(row.get("crfc_site") or ""),
        "deviation_type": g(row, idx, "type"),
        "section": g(row, idx, "section"),
        "element": g(row, idx, "element"),
        "severity": g(row, idx, "severity"),
        "audited_value": g(row, idx, "aval"),
        "reference_value": g(row, idx, "rval"),
        "change_kind": str(row.get("change_kind") or ""),
        "value_diff": str(row.get("value_diff") or ""),
        "decoded_comments": g(row, idx, "comments")[:600],
        "layer1_class": str(row.get("explanation_class") or ""),
        "layer1_reason": str(row.get("enrich_reason") or ""),
        "layer1_confidence": str(row.get("confidence") or ""),
        "exception_code": exc_code,
        "last_modified_by": str(row.get("last_modified_by") or ""),
        "last_modified_on": str(row.get("last_modified_on") or ""),
    }
    # attach the authoritative CFG-RFC record if we have one
    rec = crfc.get(exc_code) if (crfc and exc_code) else None
    if rec:
        facts["cfg_rfc"] = {
            "code": rec.get("code"),
            "title": rec.get("title"),
            "site": rec.get("site"),
            "request_status": rec.get("requestStatus"),
            "decision_status": rec.get("decisionStatus"),
            "decision_class": rec.get("decisionClass"),
            "code_type": rec.get("codeType"),
            "valid": rec.get("valid"),
            "owner": rec.get("owner"),
        }
    elif exc_code:
        facts["cfg_rfc"] = {"code": exc_code, "note": "NOT FOUND in CFG-RFC register (orphan)"}
    return facts


SYSTEM_PROMPT = (
    "You are a P&G PrIME WMS Configuration governance analyst. You explain warehouse-management-"
    "system CONFIG-DRIFT deviations (a site's configuration record differs from the standard "
    "reference). You are given ONLY grounded facts about ONE deviation plus, when it exists, the "
    "matching CFG-RFC register record (the approved change/exception that would justify the "
    "deviation). Rules:\n"
    "1. Reason ONLY from the supplied facts. Never invent CFG codes, values, dates, or approvals.\n"
    "2. If a CFG-RFC record is present and valid, the deviation is governed -> usually LOW/MEDIUM.\n"
    "3. If the CFG-RFC is invalid (withdrawn/superseded/rejected) or missing (orphan), the "
    "justification is broken -> raise criticality and recommend re-review.\n"
    "4. A pure formatting/case/whitespace difference is LOW and 'accept - cosmetic'.\n"
    "5. A functional value change with no governing CFG-RFC is HIGH and needs a CFG-RFC or "
    "alignment to standard.\n"
    "Return STRICT JSON only, no prose outside it, with keys exactly: "
    '{"ai_explanation": str, "ai_criticality": "HIGH"|"MEDIUM"|"LOW", '
    '"ai_suggested_action": str, "ai_citations": str}. '
    "ai_explanation: one tight paragraph (<=60 words). ai_citations: the specific facts you used "
    "(e.g. 'CFG1608 status=Superseded; element=...; A=... R=...')."
)


def build_prompt(facts: dict, fewshot: str = "") -> list:
    user = (
        "Explain this Config-Drift deviation and judge its business criticality.\n\n"
        "GROUNDED FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=2)
    )
    system = SYSTEM_PROMPT
    if fewshot:
        system = SYSTEM_PROMPT + "\n\n" + fewshot
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
#  LLM transport: Azure OpenAI chat completions, timeout + bounded retry       #
# --------------------------------------------------------------------------- #
def _azure_cfg() -> dict | None:
    ep = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    dep = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    ver = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01")
    if not (ep and dep and key):
        return None
    return {"endpoint": ep, "deployment": dep, "key": key, "version": ver}


def call_llm(messages: list, cfg: dict, timeout: float = 40.0,
             max_retries: int = 3) -> str:
    """POST to Azure OpenAI chat completions with timeout + backoff. Returns raw content.

    Raises RuntimeError after exhausting retries so the caller can mark the row (never silent).
    """
    import urllib.error
    import urllib.request

    url = (f"{cfg['endpoint']}/openai/deployments/{cfg['deployment']}"
           f"/chat/completions?api-version={cfg['version']}")
    body = json.dumps({
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json", "api-key": cfg["key"]}

    last_err = ""
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            last_err = f"HTTP {e.code}: {detail}"
            # 4xx (except 429) won't get better on retry
            if e.code != 429 and 400 <= e.code < 500:
                log(f"LLM HTTPError (no retry) {last_err}")
                raise RuntimeError(last_err)
            log(f"LLM HTTP {e.code} attempt {attempt}/{max_retries}; backing off")
        except Exception as e:  # timeout, conn reset, JSON, key error
            last_err = f"{type(e).__name__}: {e}"
            log(f"LLM error attempt {attempt}/{max_retries}: {last_err}")
        if attempt < max_retries:
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"LLM failed after {max_retries} attempts: {last_err}")


def parse_llm(content: str) -> dict:
    """Coerce model output into the four AI columns; tolerant of stray text around JSON."""
    txt = content.strip()
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if m:
        txt = m.group(0)
    obj = json.loads(txt)  # raise -> caller marks the row
    crit = str(obj.get("ai_criticality", "")).strip().upper()
    if crit not in ("HIGH", "MEDIUM", "LOW"):
        crit = "MEDIUM"
    return {
        "ai_explanation": str(obj.get("ai_explanation", "")).strip(),
        "ai_criticality": crit,
        "ai_suggested_action": str(obj.get("ai_suggested_action", "")).strip(),
        "ai_citations": str(obj.get("ai_citations", "")).strip(),
    }


# --------------------------------------------------------------------------- #
#  cache — keyed on the grounded facts AND the knowledge version               #
# --------------------------------------------------------------------------- #
# The knowledge version is a short fingerprint of the GROUNDING inputs (the CFG-RFC
# register + the SharePoint process pages). When a new CFG-RFC is approved or a
# SharePoint page is edited, this value changes, every cache key changes, and the
# affected explanations are re-grounded instead of served stale. (Raquel's ask #2.)
_KNOWLEDGE_VERSION = None  # set at the start of explain_rows()


def knowledge_version() -> str:
    """Current grounding fingerprint (register + SharePoint). Empty string if unavailable."""
    try:
        import change_watch
        return change_watch.current_knowledge_version()
    except Exception as e:  # never let cache-versioning break the run
        log(f"knowledge_version unavailable ({type(e).__name__}: {e}); cache not knowledge-versioned")
        return ""


def _cache_key(facts: dict) -> str:
    blob = json.dumps({"kv": _KNOWLEDGE_VERSION, "facts": facts},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"cache unreadable ({type(e).__name__}: {e}); starting fresh")
    return {}


def save_cache(cache: dict) -> None:
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


# --------------------------------------------------------------------------- #
#  IO                                                                          #
# --------------------------------------------------------------------------- #
def read_rows(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
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


def load_crfc(path: str) -> dict:
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        log(f"loaded CFG-RFC register (json): {len(data)} codes")
        return data
    import crfc_register as cr
    return cr.load_register(path)


# --------------------------------------------------------------------------- #
#  core: explain the needs_llm rows in place (reusable by the CLI and by             #
#  enrich_deviations.py --llm)                                                       #
# --------------------------------------------------------------------------- #
def explain_rows(rows, idx, crfc=None, cfg=None, *, dry_run=False, limit=0,
                 timeout=40.0, max_retries=3, use_expert=True, prompts_dump=None):
    """Fill the four AI_COLS on every needs_llm=true row, in place. Returns a stats dict.

    Order of resolution for each row (highest accuracy first):
      1. expert exact match  -> deterministic answer from the expert library (no LLM).
      2. cache hit           -> previously computed answer.
      3. LLM                 -> grounded call, steered by relevant expert few-shot examples.
    Never silent-drops: a failed LLM row is marked LLM_UNAVAILABLE and the run continues.
    """
    # knowledge version: stamps the cache so explanations refresh when the register or
    # SharePoint grounding changes (see change_watch.current_knowledge_version()).
    global _KNOWLEDGE_VERSION
    _KNOWLEDGE_VERSION = knowledge_version()
    if _KNOWLEDGE_VERSION:
        log(f"knowledge version: {_KNOWLEDGE_VERSION} (cache re-grounds when register/SharePoint change)")

    # expert training library (optional; degrades gracefully if unavailable)
    ef = None
    expert_lib = []
    if use_expert:
        try:
            import expert_feedback as ef
            expert_lib = ef.load_examples()
            if expert_lib:
                log(f"expert library: {len(expert_lib)} verified example(s) loaded")
        except Exception as e:
            log(f"expert library unavailable ({type(e).__name__}: {e}); continuing without it")
            ef = None

    cache = load_cache()

    # default AI cols empty for every row; only needs_llm rows get filled
    for r in rows:
        for c in AI_COLS:
            r.setdefault(c, "")

    targets = [i for i, r in enumerate(rows) if str(r.get("needs_llm")).lower() == "true"]
    if limit and len(targets) > limit:
        log(f"limiting to first {limit} of {len(targets)} needs_llm rows")
        targets = targets[:limit]
    log(f"{len(rows)} rows total; {len(targets)} flagged needs_llm -> Layer-2")

    done = cached = failed = expert = 0
    crit_counter = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    t0 = time.time()

    def _tally(ai):
        c = ai.get("ai_criticality", "MEDIUM")
        crit_counter[c] = crit_counter.get(c, 0) + 1

    for n, i in enumerate(targets, 1):
        row = rows[i]
        facts = build_facts(row, idx, crfc)

        # 1) expert exact match -> deterministic, no LLM
        if ef and expert_lib:
            hit = ef.match_exact(facts, expert_lib)
            if hit:
                row["ai_explanation"] = hit.get("ai_explanation", "")
                row["ai_criticality"] = hit.get("ai_criticality", "MEDIUM")
                row["ai_suggested_action"] = hit.get("ai_suggested_action", "")
                row["ai_citations"] = (hit.get("ai_citations", "")
                                       + f" [expert:{hit.get('_expert_id','')}"
                                         f"/{hit.get('_expert_match','')}]").strip()
                expert += 1
                _tally(hit)
                continue

        # relevant expert few-shot to steer the LLM on non-exact rows
        fewshot = ""
        if ef and expert_lib:
            fewshot = ef.fewshot_block(ef.select_fewshot(facts, k=5, examples=expert_lib))

        messages = build_prompt(facts, fewshot)

        if dry_run:
            if prompts_dump is not None:
                prompts_dump.append({"row_index": i, "facts": facts, "messages": messages})
            if n <= 3:
                log(f"[dry-run] sample prompt {n} facts: "
                    f"{json.dumps(facts, ensure_ascii=False)[:200]}...")
            continue

        key = _cache_key(facts)
        if key in cache:
            row.update(cache[key])
            cached += 1
            _tally(cache[key])
            continue

        try:
            content = call_llm(messages, cfg, timeout=timeout, max_retries=max_retries)
            ai = parse_llm(content)
            row.update(ai)
            cache[key] = ai
            done += 1
            _tally(ai)
            if done % 10 == 0:
                save_cache(cache)  # checkpoint
                log(f"progress {n}/{len(targets)} (new={done} cached={cached} "
                    f"expert={expert} failed={failed}) elapsed={time.time()-t0:.0f}s")
        except Exception as e:
            # NEVER silent-drop: mark the row, log, keep going
            msg = f"LLM_UNAVAILABLE: {type(e).__name__}: {e}"
            row["ai_explanation"] = msg
            row["ai_criticality"] = "MEDIUM"
            row["ai_suggested_action"] = "manual review (LLM failed)"
            row["ai_citations"] = ""
            failed += 1
            log(f"row {i} -> {msg}")

    if not dry_run:
        save_cache(cache)

    return {"targets": len(targets), "expert": expert, "new": done, "cached": cached,
            "failed": failed, "criticality": crit_counter}


# --------------------------------------------------------------------------- #
#  main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Layer-2 LLM explainer for Config Drift deviations")
    ap.add_argument("--in", dest="inp", required=True,
                    help="enriched deviations CSV/XLSX (output of enrich_deviations.py)")
    ap.add_argument("--out", dest="out", help="output explained CSV")
    ap.add_argument("--crfc", dest="crfc",
                    help="Configuration_RFC.csv or crfc_register.json to ground the CFG-RFC facts")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + save prompts, DO NOT call the LLM (no network)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap number of needs_llm rows to explain (0 = all)")
    ap.add_argument("--no-expert", action="store_true",
                    help="ignore the expert training library (expert_examples.jsonl)")
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--max-retries", type=int, default=3)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    crfc = load_crfc(args.crfc) if args.crfc else None
    if args.crfc and crfc is None:
        log("WARNING: --crfc supplied but register empty")

    log(f"reading enriched file: {args.inp}")
    header, rows = read_rows(args.inp)
    if "needs_llm" not in header:
        log("ERROR: input is not a Layer-1 enriched file (no 'needs_llm' column). "
            "Run enrich_deviations.py first.")
        raise SystemExit(2)

    idx = build_index(header)
    out = args.out or (os.path.splitext(args.inp)[0] + "_explained.csv")
    out_header = list(header) + [c for c in AI_COLS if c not in header]

    cfg = _azure_cfg()
    if not args.dry_run and cfg is None:
        log("ERROR: no Azure OpenAI env config (AZURE_OPENAI_ENDPOINT/DEPLOYMENT/API_KEY). "
            "Re-run with --dry-run to inspect prompts, or set the env vars.")
        raise SystemExit(3)
    if cfg:
        log(f"LLM endpoint: {cfg['endpoint']} deployment={cfg['deployment']} "
            f"api-version={cfg['version']}")

    prompts_dump = [] if args.dry_run else None
    st = explain_rows(rows, idx, crfc, cfg, dry_run=args.dry_run, limit=args.limit,
                      timeout=args.timeout, max_retries=args.max_retries,
                      use_expert=not args.no_expert, prompts_dump=prompts_dump)

    # write output (always — deterministic + whatever AI we got)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_header, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    cc = st["criticality"]
    log("=" * 64)
    if args.dry_run:
        dump_path = os.path.join(OUT_DIR, "llm_explain_prompts.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(prompts_dump, f, ensure_ascii=False, indent=2)
        log(f"DRY-RUN: built {len(prompts_dump)} prompts -> {dump_path}")
        log(f"wrote pass-through copy (AI cols empty) -> {out}")
    else:
        log(f"explained {st['targets']} needs_llm rows -> {out}")
        log(f"  from expert lib : {st['expert']}")
        log(f"  new LLM calls   : {st['new']}")
        log(f"  from cache      : {st['cached']}")
        log(f"  failed(marked)  : {st['failed']}")
        log(f"criticality: HIGH={cc.get('HIGH',0)} "
            f"MEDIUM={cc.get('MEDIUM',0)} LOW={cc.get('LOW',0)}")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
