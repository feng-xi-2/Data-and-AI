---
name: Config Drift Grounded Explainability (columns I & J)
description: "Turn a P&G PrIME WMS Config Drift (PCD) deviation into a plain-English explanation where EVERY claim is tagged with the rule that justifies it — [MOCA] data model, [PRIME] product behaviour, [CRFC] governance register, [PYTHON] how the code classified it, [GENERAL] domain knowledge. Built around columns I (A value = audited site) and J (R value = reference standard) and the three deviation types (Missing record, Unexpected record, Unexpected mismatching value). The same tagged-grounding method also explains MOCA/txplan code diffs (e.g. two versions of a job). USE WHEN explaining what a deviation means and WHY, sourcing each part of the answer, comparing an audited value to the standard, distinguishing formatting vs functional change, or explaining the difference between two versions of a MOCA command/job. Trigger phrases: 'explain the deviation and ground it', 'which rule grounds this', 'MOCA CRFC python explanation', 'explain columns I and J', 'A value vs R value', 'formatting or functional', 'explain the difference between the two codes', 'ground by general knowledge', 'cite the source of each claim'."
---

# Config Drift Grounded Explainability

Explain a **Config Drift (PCD)** deviation — or a **MOCA/txplan code diff** — in plain
English where **each sentence carries the rule/source that justifies it**. This is the
explainability method the CoE asked for: not just *what* deviated, but *which authority*
tells us that, so the answer is auditable and never a black box.

The companion enrichment pipeline is the `config-drift-deviation-explainer` skill (Layer-1
+ LLM). This skill is the **grounding-and-citation layer**: how to read columns I/J and
attach a tagged source to every claim.

## The two columns everything hangs on

| Col | Header | Meaning |
| --- | --- | --- |
| **I** | **A value** | the value at the **audited** site being checked (e.g. `AHM_PRODWMS`) |
| **J** | **R value** | the value in the **reference** golden standard (e.g. `mnt-wms`) |

A deviation is always "I differs from J" (or one side is absent). Explaining it = say what
I and J are, why they differ, and what rule backs each statement.

## The five grounding tags (the whole method)

Every claim in an explanation is tagged with exactly one source:

| Tag | Owns | Example |
| --- | --- | --- |
| `[MOCA]` | **What deviated / where it physically lives** — Blue Yonder/RedPrairie data model + MOCA-DSL verbs. Objective. | Policy element = `polcod#polvar#polval` in `poldat_view`; "Return String 2" = `poldat.rtstr2`; Area = `aremst`; `set savepoint`/`catch(@?)`/`@!` are MOCA txn verbs. |
| `[PRIME]` | **What the deviation TYPE means + why it matters** — PrIME 2022 Config Drift product behaviour. | "Unexpected mismatching value" = both sides define the record, one attribute differs; "accepted" severity = governed exception; HOST-MU = host unit-of-measure default. |
| `[CRFC]` | **Whether the change is sanctioned** — the authoritative CFG-RFC register (`Configuration_RFC.csv`). | `CFG1635` found → "Productization PRFC4767… status Delivered, type Job"; code not found → **orphan exception, re-review**. |
| `[PYTHON]` | **How THIS row was classified** — the enrichment code's own decision. | formatting-vs-functional diff result (`COSMETIC`/`REORDER`/`VALUE_DELTA`); modification user/date parsed by regex from Deviation Comments. |
| `[GENERAL]` | **General WMS/engineering knowledge** — only when no workspace file backs the claim. | "an unscoped auto-logout is a real defect"; atomicity / no-partial-commit. |

Grounding hierarchy in one glance:

```
WHAT deviated / where it lives     -> [MOCA]    poldat_view, rtstr2, aremst   (data model, objective)
WHAT the deviation type means      -> [PRIME]   mismatch vs missing vs unexpected (product semantics)
WHY it matters (business meaning)  -> [PRIME]   HOST-MU = host UOM default
HOW it was classified              -> [PYTHON]  formatting vs functional, provenance parse (code's call)
WHETHER it's a sanctioned change   -> [CRFC]    CFG code verified in the register (governance)
fallback interpretation            -> [GENERAL] general knowledge, only when no file backs it
```

## The three deviation types (explained differently)

| Type | I / J | How to explain it |
| --- | --- | --- |
| **Missing record** | both blank | Standard (J-side) defines the record, site (A) does not have it. I/J blank because an ENTIRE record is absent — expected content is in Deviation Comments. `[PRIME]` = present in golden standard, absent at site. |
| **Unexpected record** | both blank | Site (A) has the record, standard (R) does not. I/J blank because the whole record is extra site config. `[PRIME]` = normally needs a CFG-RFC to be productised, or removal. |
| **Unexpected mismatching value** | both populated | Both sides define the element; one attribute differs. Name I vs J, then run the formatting-vs-functional diff (`[PYTHON]`). |

## Formatting vs functional (the `[PYTHON]` decision)

For a mismatch, escalate through cheap tests — this is what makes "cosmetic vs real change"
explainable:

1. `I == J`? → identical.
2. `normalize(I) == normalize(J)`? (case/whitespace/delimiter/number) → **COSMETIC** = formatting only.
3. same tokens, different order? → **REORDER** = formatting only.
4. else → **VALUE_DELTA** = functional; name the site-only and standard-only tokens.
   - single short value each → plain phrasing: *"the site uses 'millimeter' where the standard expects 'centimeter'"*.

Only VALUE_DELTA is a real functional finding; COSMETIC/REORDER are dismissible.

## Worked example (the canonical one)

Row: `HOST-MU#DEFAULT#LINEAR`, attr "Return String 2", **I = `millimeter`**, **J = `centimeter`**, type "Unexpected mismatching value".

- `[PRIME]` "Unexpected mismatching value" → both sites define it, one attribute differs (so I and J are populated).
- `[PYTHON]` diff → not equal, not equal after normalise, tokens differ → **VALUE_DELTA (functional)**: the site uses `millimeter` where the standard expects `centimeter`.
- `[MOCA]` `HOST-MU#DEFAULT#LINEAR` is a policy key (`polcod=HOST-MU / polvar=DEFAULT / polval=LINEAR`) in `poldat_view` — the same table a job reads at runtime; "Return String 2" = `poldat.rtstr2`. So it's literally `rtstr2='millimeter'` at AHM vs `'centimeter'` in the standard.
- `[PRIME]` HOST-MU/LINEAR = the host **length** unit-of-measure default → why it matters (host integration reports lengths in mm vs cm).
- `[CRFC]` no CFG on this row → open functional finding; if it cited a CFG, look it up (found → cite title/status; missing → orphan).
- `[PYTHON]` last changed by `CW0835` on `2019-02-10` — parsed from Deviation Comments.

## Same method on a MOCA/txplan code diff

The tags also explain the difference between two versions of a job (e.g. `USR-AUTO-LOGOUT`
5125 vs 7718):

- `+ rftmst.wh_id = @wh_id` → `[MOCA]` `wh_id` is the warehouse partition key on `rftmst/devmst/dlytrn`; scoping fix = **functional**.
- `try { set savepoint … } catch(@?) { rollback … }` → `[MOCA]` txn verbs (`@?`=status, `@!`=error text), `[PRIME]` makes the logout atomic.
- `{ }>>res` → `;` inside `try` → `[PYTHON]`-style token diff shows same inner tokens reordered = **cosmetic**.
- new coupled-trailer decouple block (`trlr`, `vc_couple_devcod`) → `[MOCA]` trailer master; new functional scope that per `[CRFC]` should be backed by a **Job**-type CFG-RFC (else orphan).
- `publish data` + `FAILED …` audit log → `[MOCA]` verbs, `[PRIME]` observability.

Net: functional changes get `[MOCA]/[PRIME]` grounding; restructures that keep the same
tokens are `[PYTHON]` cosmetic; any added behaviour is checked for a `[CRFC]` sanction.

## How to run it

`explain_ij.py --in <deviations.csv> --out <explained.csv> --crfc <Configuration_RFC.csv>`

- Defaults resolve to the AHM report and a sibling `*_explained.csv`.
- Reads columns I (A value) and J (R value) plus section/element/attr/type/comments/rationale.
- Writes **two additive columns** into a COPY (never mutates the source):
  - **Deviation Explanation (NL)** — the plain-English account.
  - **Grounding & Citations** — the tagged sources for every claim.
- Cross-checks any `CFGxxxx` against the register: found → cite title/site/status; missing → `orphan exception`.

## Guardrails (workspace rules)

- Additive only: writes a copy, never edits the original report or the compare logic.
- Timestamped heartbeat logs; **no silent failure** — a row that fails logs `type: message`
  then raises; rows are never dropped.
- `[MOCA]`/`[PRIME]`/`[GENERAL]` claims that are domain knowledge (not read from a file that
  run) are labelled as such — never presented as if quoted from a workspace document.
- Register is `cp1252`; pass `--crfc` with the OneDrive path explicitly.

## Files

- `explain_ij.py` — the grounded I/J explainer (this skill).
- `enrich_deviations.py` / `explain_deviations.py` — the Layer-1 + LLM pipeline
  (`config-drift-deviation-explainer` skill) that this grounding method feeds.
- `Configuration_RFC.csv` — the CFG-RFC register (the `[CRFC]` source).
