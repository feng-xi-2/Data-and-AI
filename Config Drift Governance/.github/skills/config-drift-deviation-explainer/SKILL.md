---
name: Config Drift Deviation Explainer (Layer-1 + LLM)
description: "Two-layer, additive AI explanation and triage for P&G PrIME WMS Config Drift (PCD) deviations. Layer-1 deterministically classifies every deviation and validates each accepted exception's CFGxxxx code against the authoritative CFG-RFC register (found? valid? withdrawn/superseded? orphan?). Layer-2 escalates ONLY the unresolved rows to a grounded LLM that returns a plain-English explanation, a business criticality (HIGH/MEDIUM/LOW), a suggested action, and citations. USE WHEN triaging a Config Drift export, explaining why a deviation exists, deciding if a deviation is critical, or judging whether an accepted exception is still governed. DO NOT USE to change the compare logic itself. Trigger phrases: 'explain this deviation', 'is this drift critical', 'why is this accepted', 'enrich the drift output', 'stale exception', 'orphan exception', 'triage config drift', 'what should I do about this deviation'."
---

# Config Drift Deviation Explainer (Layer-1 + LLM)

Explain and triage PrIME **Config Drift (PCD)** deviations **without touching the compare
logic**. The skill is *additive*: it reads the row-level deviation export (CSV/XLSX) and
writes a COPY with new columns. Two layers, run in order.

## Layer 1 — deterministic enrichment (always run first)

`enrich_deviations.py --in <deviations.csv> --crfc <Configuration_RFC.csv|crfc_register.json>`

- Classifies each deviation into `explanation_class`:
  `FORMATTING_ONLY` · `FUNCTIONAL_CHANGE` · `KNOWN_EXCEPTION` · `MISSING_STANDARD` ·
  `UNSUPPORTED_RECORD` · `STALE_EXCEPTION` · `ORPHAN_EXCEPTION` · `NEEDS_REVIEW`.
- Extracts the `CFGxxxx` exception code from Rationale / Group Name / decoded Deviation
  Comments and **validates it against the CFG-RFC register**:
  - found + valid → `KNOWN_EXCEPTION` (governed).
  - found + invalid (withdrawn / superseded / rejected / disused) → `STALE_EXCEPTION`.
  - accepted but code **not** in register → `ORPHAN_EXCEPTION`.
- **Formatting vs functional** — for a mismatch it runs a structured diff and records
  `change_kind` (`COSMETIC` / `REORDER` / `VALUE_DELTA`) plus a `value_diff` that NAMES the
  tokens that differ (e.g. `site-only: 0; standard-only: 1`). Cosmetic and reorder diffs are
  `FORMATTING_ONLY`; a real content delta is `FUNCTIONAL_CHANGE`. This is the formatting-vs-
  functional distinction the CoE asked the AI to make, and it also grounds Layer-2.
- **Expert standing rules** — a trained rule (`expert_rules.jsonl`) can re-classify and
  auto-resolve whole classes of deviation at Layer-1 with no LLM: the automated version of
  the manual "exceptions file updated whenever a change is approved". Match on exception
  code / element / section+type / change kind; most specific wins; provenance in
  `expert_rule`.
- Flags `needs_llm=true` for the residual it cannot fully close.

This alone resolves the bulk of triage cheaply and 100% reproducibly.

### One command (Layer-1 + Layer-2 in a single pass)

`enrich_deviations.py --in <deviations.csv> --crfc <register> --out <out.csv> --llm`
(add `--llm-dry-run` to build prompts with no network). Runs Layer-1, then hands the
`needs_llm` rows straight to Layer-2 in the same process.

## Layer 2 — LLM explainer (escalation only)

`explain_deviations.py --in <enriched.csv> --crfc <...> --out <explained.csv>`

- Selects **only** the `needs_llm=true` rows (never the whole file).
- Grounds each prompt on that row's own facts — deviation type, section, element key
  (`polcod#polvar#polval`), A value vs R value, decoded comments, Layer-1 class/reason —
  **plus the matching CFG-RFC register record verbatim** (or an explicit "NOT FOUND /
  orphan" note). The model reasons only from supplied facts; it never invents CFG codes,
  values, dates, or approvals.
- Writes four columns: `ai_explanation`, `ai_criticality` (HIGH/MEDIUM/LOW),
  `ai_suggested_action`, `ai_citations`.

### LLM wiring (pluggable, P&G-ecosystem)

Azure OpenAI chat completions over plain HTTPS (no SDK). Env-driven:
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_API_VERSION` (default `2024-06-01`). Run with `--dry-run` to build and
inspect prompts with no network call.

## Guardrails (non-negotiable)

- Deterministic columns always populate even if the LLM is unavailable.
- Every LLM call has a **timeout + bounded retry with backoff**; 4xx (except 429) is not
  retried.
- **No silent failure**: a failed row is marked `ai_explanation="LLM_UNAVAILABLE: ..."`,
  logged, and the run still completes — rows are never dropped.
- A sha1 disk cache keyed on the grounded facts **and a knowledge version** avoids paying
  twice for identical rows — and automatically **re-grounds** an explanation when the
  register or the SharePoint process pages change (see change-watch below).

## Grounding sources

- **CFG-RFC register** — `crfc_register.py` loads `Configuration_RFC.csv` into
  `{CFGxxxx → record}` (status, decision class, site, validity) and into Neo4j
  (`:CRFC`, `:Site`, `FOR_SITE`).
- **PrIME Config Drift** definitions (deviation types, severities, Config Score vs Health
  Score) — see the `prime-config-drift-governance` skill.

## Staying fresh (change-watch)

`change_watch.py` fingerprints the three moving inputs — the CFG-RFC register CSV, the
SharePoint process pages, and the Config Drift CSVs — and reports exactly what changed:

- register changed → rebuild the CFG-RFC graph (`--apply`).
- SharePoint changed → the **knowledge version** bumps, so cached explanations re-ground.
- drift CSV changed → re-run enrich/explain on the new dump.

`--scan` reports, `--update` sets the baseline, `--apply` rebuilds the graph on a register
change. The knowledge version is `reg-sha1 + sharepoint-digest`.

## Train the skill (expert loop)

`expert_feedback.py` lets a CoE expert improve accuracy without retraining a model:

- **Examples** (`expert_examples.jsonl`) — an exact-match example answers identical future
  deviations deterministically and steers the LLM (few-shot) on the rest.
- **Rules** (`expert_rules.jsonl`) — a standing policy that resolves whole classes at
  Layer-1 (see above).

Both are editable from the Knowledge Graph page (Config, CRFC & Drift tab).

## Files

- `enrich_deviations.py` — Layer-1 enricher (+ `--crfc` validation, formatting/functional
  diff, expert rules, one-command `--llm`).
- `explain_deviations.py` — Layer-2 LLM explainer (grounded, knowledge-versioned cache,
  guard-railed, expert few-shot).
- `crfc_register.py` — CFG-RFC register loader (exceptions source + graph).
- `expert_feedback.py` — expert examples + standing rules.
- `change_watch.py` — input change detection + knowledge version.
