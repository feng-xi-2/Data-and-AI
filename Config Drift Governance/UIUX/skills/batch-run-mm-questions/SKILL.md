---
name: batch-run-mm-questions
description: 'Use to answer the full Process Discovery / M&M question set across one or more sites in a single sweep. Trigger phrases: "answer all MM questions for <site>", "run the MM batch", "regenerate the MM answer book".'
---

# Batch Run MM Questions

## Metadata

- Display name: Batch Run MM Questions
- Kind: tool
- Owner: WHS GenAI / Process Discovery
- Sources:
  - `SQL_Translations/_mm_audit/STANDARD_WORKFLOW.md`
  - `SQL_Translations/_mm_audit/answer_all_questions.py`

## Purpose

Tool skill that answers the full **MM question master** (361 questions) across the
selected sites in one governed sweep, picking the most-specific evidence rule per
question and running it live.

> Production-tested: 361 MM questions × 3 sites (Athens / Xiqing / London),
> 0 errors, 659 site-answers in ~85 seconds.

## End-to-end

```powershell
cd SQL_Translations/_mm_audit
python build_neo4j_mm_layer.py   # rebuild :MMQuestion + :EvidenceRule graph (~30s)
python answer_all_questions.py   # answer all 361 Qs x sites (~85s)
```

## Rule-specificity tiers (most specific wins)

| Tier | Specificity | Rule kind |
|---|---:|---|
| A | 8 | topic-specific interface check / site-profile derivation |
| B | 7 | work-process catalogue |
| C | 6 | external-system probe |
| D | 5 | SAT artefact (catch-all) |
| E | 2 | generic submodule |
| F | 1 | last-resort artefact |

## CLI flags

`--qid Q-0048` · `--submodule 05.02` · `--sites ATHENS,XIQING` · `--limit 20`

## Outputs

- `_mm_all_answers.json` — structured answers
- `_mm_all_answers.md` / `_mm_all_answers_full.md` — human-readable answer book
- `_mm_combined_answer_report.xlsx` — combined report
