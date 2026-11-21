---
name: config-drift-human-decision
description: "The HUMAN-IN-THE-LOOP decision layer for P&G PrIME Config Drift — govern ACCEPTED deviations that carry NO CFG-RFC code. USE WHEN: an accepted deviation is unbacked (no CFG record) and you need to discover the governing CFG-RFC with solid grounding; reviewing / approving AI-proposed CFG attachments; deciding ACCEPT / REASSIGN / RAISE / REJECT / DEFER on a discovered CFG; explaining why an acceptance is a governance gap; asking what value in what field is accepted at what site, under which CRFC, and which other sites still have the same value open; explaining what a configuration value MEANS; capturing what CHANGED since the last scan — new deviations, new sites/fields/values, new CRFCs and their impact on the governance graph; grounding a decision in the sites' own Deviation Notes / Rationale; running or interpreting discover_missing_cfg.py, cfg_decision.py, build_exception_ledger.py, build_change_capture.py or explain_config_values.py; the discovered_missing_cfg.csv, exception_ledger.csv, change_capture.csv, config_value_dictionary.json, config_value_meanings.csv, cfg_decisions.jsonl queue, cfg_decision_audit.jsonl, ledger_grounding.json, or cfg_decisions_applied.csv. Trigger phrases: 'accepted but no CFG', 'discover the missing CFG', 'unbacked exception', 'which CFG governs this', 'human decision layer', 'approve the discovered CFG', 'CFG decision queue', 'attach a CFG-RFC', 'is this acceptance governed', 'exception ledger', 'what value is accepted at what site', 'which sites accept this value', 'potential CRFC linkage', 'who has not accepted', 'what does this value mean', 'value meaning dictionary', 'what changed', 'what is new', 'new deviations', 'new CRFC', 'change capture', 'delta since last scan', 'newly accepted', 'resolved deviations'."
---

# Config Drift — Human Decision Layer (missing CFG-RFC)

Governs the residual that pure automation must **not** decide on its own: an **Accepted**
Config-Drift deviation that has **no CFG-RFC** recorded. An accepted deviation is a
CoE-approved exception and *must* be backed by a CFG-RFC; an unbacked acceptance is a
**governance gap**, not a pass — it may be masking a real gap and it cannot be audited.

This skill pairs a **grounded discovery** step (AI proposes) with a **human decision** gate
(CoE disposes). Nothing is auto-applied. Every decision is accountable and append-only audited.

> Reference domain: see the [prime-config-drift-governance](../prime-config-drift-governance/SKILL.md)
> skill for deviation types, severities, Config vs Health Score, and the CFG-RFC lifecycle.
> **Source of truth for the data:** the COE export `Config report/data.xlsx` (has *Deviation
> Notes* and *Rationale for Accepted*) and the register `Config report/Configuration_RFC.csv`.

---

## 1. The problem, quantified (from data.xlsx, 97,481 rows)

| Bucket | Count | Meaning |
|---|---|---|
| Accepted, **no CFG + no note** (UNBACKED) | 10,543 | acceptance with zero governance evidence |
| Accepted, **note only, no CFG** | 5,115 | justified by free text, not a ticket |
| **Accepted-no-CFG total to resolve** | **15,658** | the decision queue |
| Accepted citing a CFG **not in the register** (ORPHAN) | 4,806 | cites a code that does not exist |

> The pipeline that builds the drift actions only reads *Rationale*/*Comments*, **not the
> manual *Deviation Notes* column** — 12.3% of rows carry a note the automation never sees.
> That is a primary source of action inaccuracy; the decision layer restores that signal.

---

## 2. Discovery — how the missing CFG is proposed (AI, grounded)

`discover_missing_cfg.py` resolves each accepted-no-CFG row by an **evidence cascade**
(strongest first) and records **which rule fired** and **how strong** it is. It never guesses.

| # | Rule | Evidence | Strength |
|---|---|---|---|
| 1 | **PEER_PRECEDENT** | another site accepted the **same variation** (Section·Element·Attribute·**R value**·Type) under a CFG. Falls back to element-level (Section·Element·Type). | **STRONG** if strict match **and** the CFG is live in the register; else **MODERATE** |
| 2 | **NOTE_REFERENCE** | the row's own *Deviation Note* names a CFG, or a change artefact (EXCPCHG / SSCD / TMPLCHG / SCDR / P-RFC / repair script) | STRONG for a register CFG; **MODERATE** for an artefact to trace |
| 3 | **SAME_SITE_SIBLING** | the same site governs a **sibling** row of the same policy/element group (element before `#`) under a CFG | MODERATE (≥2 siblings) else EMERGING |
| 4 | **REGISTER_TITLE** | the element/section tokens match ≥3 distinctive words in a CFG-RFC **Title** | **EMERGING** — a *weak lead*, confirm manually |
| — | **NONE** | no evidence anywhere | **NONE** — UNBACKED, must be reviewed |

Typical yield on the current export: **PEER_PRECEDENT ≈ 906 · NOTE_REFERENCE ≈ 3,451 ·
SAME_SITE_SIBLING ≈ 40 · REGISTER_TITLE ≈ 4,221 (weak) · NONE ≈ 7,040**.

**Only STRONG and MODERATE are "solid".** EMERGING is a lead; NONE is an explicit "no evidence —
human must decide". Being honest about the weak tail is the point — do not treat a title
token-match as governance.

Run it:
```
cd SQL_Translations/PBI_Config_Drift_Alert
python discover_missing_cfg.py
# -> Config report/discovered_missing_cfg.csv      (human-readable, plain-English grounding)
# -> UIUX/assets/discovered-cfg.js                 (window.WHS_CFGD for the HTML review surface)
# -> _replica_drift/cfg_decisions.jsonl            (the PENDING decision queue)
```

---

## 3. The decision — how a human disposes (CoE, accountable)

`cfg_decision.py` is the gate. A reviewer reads the grounding and records one verdict.

| Verdict | When | Requires |
|---|---|---|
| **ACCEPT** | the discovered CFG is correct → attach it | candidate must be **STRONG/MODERATE** and non-empty |
| **REASSIGN** | a *different* CFG governs it | `--cfg CFGxxxx` |
| **RAISE** | no CFG governs it yet → a new one is needed | `--cfg` (new id) or blank = "to be raised" |
| **REJECT** | should **not** be accepted → re-open & fix to standard | — |
| **DEFER** | needs more investigation | a `--note` |

### Guardrails (enforced by the tool)
- **No anonymous decisions** — `--by <reviewer>` is mandatory.
- **No rubber-stamping weak evidence** — `ACCEPT` is **refused** on `NONE`/`EMERGING`
  candidates; the reviewer must `REASSIGN`/`RAISE` with an explicit `--cfg`, or `REJECT`.
- **Register validity check** — attaching a CFG that is missing, `Superseded`, `Withdrawn`
  or `Rejected` in the register is allowed but **WARNs** and records the warning.
- **Append-only audit** — every decision writes to `cfg_decision_audit.jsonl` (ts, id,
  verdict, cfg, by, note, warning, identity). The queue only ever reflects the latest state.

Workflow:
```
python cfg_decision.py stats                                  # dashboard; work STRONG then MODERATE
python cfg_decision.py list --strength STRONG --limit 20
python cfg_decision.py list --site "Ahmedabad" --method PEER_PRECEDENT
python cfg_decision.py show <id>                              # full grounding for one row
python cfg_decision.py decide <id> --verdict ACCEPT   --by fc7262 --note "confirmed vs library"
python cfg_decision.py decide <id> --verdict REASSIGN --cfg CFG1601 --by fc7262
python cfg_decision.py decide <id> --verdict REJECT   --by fc7262 --note "typo, fix to standard"
python cfg_decision.py export        # -> Config report/cfg_decisions_applied.csv (approved attachments)
```

`cfg_decisions_applied.csv` is the feed-back artefact: the human-approved CFG attachments,
ready to write back into the acceptance data (closing the governance gap) or to seed
[expert_feedback.py](../../../SQL_Translations/PBI_Config_Drift_Alert/expert_feedback.py) so
identical future deviations resolve deterministically.

---

## 4. Rules of engagement (do / don't)

- **Do** work top-down: STRONG → MODERATE first (highest confidence, fastest governance wins).
- **Do** open `show <id>` and read the **A vs R** values and the **peer sites** before ACCEPTing —
  a peer precedent proves the *variation* is governed, but the reviewer confirms it is the
  *same* variation.
- **Do** treat a **register WARNING** (Superseded/missing) as a real finding: the acceptance
  may be pointing at a dead ticket — REASSIGN to the current CFG or RAISE a new one.
- **Don't** ACCEPT a `REGISTER_TITLE` (EMERGING) lead — it is a starting point, not evidence.
- **Don't** silently leave an UNBACKED acceptance: every `NONE` row must end as REASSIGN,
  RAISE, or REJECT — an acceptance with no governing CFG is a gap, not a pass.
- **Don't** invent a CFG id — REASSIGN/RAISE must cite a real (or newly-raised) CFG-RFC.

---

## 5. Exception ledger — what value, in what field, is accepted at what site

> **Terminology: an ACCEPTED deviation *is* an exception.** The two words are the same thing —
> a CoE-signed-off allowed variation. The ledger counts *accepted exceptions*, not two categories.

`build_exception_ledger.py` is the **cross-site reference** the decision layer grounds on. For
every configuration **value** at least one site has ACCEPTED it answers, in one row:

- **what value in what field** — identity `Section | Element | Attribute | Accepted value | Type`;
- **at which sites** — the base sites that accepted it (PROD/SIT/UAT de-duped);
- **coverage** — how many of the **77 sites in scope** accept it (`nAcc / totalSites`);
- **breadth** — is it **site-specific** (accepted at ONE site, peers don't share it), shared by a
  **few** (2–5), or **widespread** (6+, a de-facto standard candidate);
- **consistency** — **consistent** (every site that has it has accepted it) vs **partial** (some
  sites still have it OPEN → adoptable now);
- **under what CRFC** — the cited CFG-RFC, validated live/stale/orphan against the register;
- **the potential CRFC linkage** — when unbacked, the CFG a **peer** accepted the same variation under;
- **which OTHER sites carry the same value OPEN** — the *adopt list* (should raise/adopt the same CRFC);
- **the sites' own words** — representative *Deviation Notes* + *Rationale* that justify the acceptance.

> **Whole-record deviations (Missing / Unexpected record) have blank A and R values.** That is
> *not* "A equals R" — the difference is the record being **present or absent**, not one attribute
> value, so the attribute-level A/R columns are empty by design. The record's real content lives in
> *Deviation Details* (`Field <value>` pairs); the ledger surfaces it as the `detail` field (e.g.
> `UC-BATCH-DELIVERY#PURGE-RULES#RETENTION-HOURS` → `Return Number 1=8` = an 8-hour retention rule).

### Governance state (per accepted value)
| State | Meaning | Decision cue |
|---|---|---|
| **GOVERNED** | accepted under a **live** CFG-RFC | consistent — propagate to the OPEN adopt list |
| **STALE** | cited CFG-RFC is superseded/withdrawn | REASSIGN to the current CFG |
| **ORPHAN** | cited a CFG-RFC not in the register | FIND_ORPHAN_TICKET → REASSIGN/RAISE |
| **UNBACKED_PEER** | no CFG here, but **peers govern it** under one | ATTACH the peer's CFG (STRONG lead) |
| **UNBACKED** | accepted with **no CFG-RFC anywhere** | real gap — RAISE or REJECT |

Typical yield on the current export: **1,873 accepted exceptions across 77 sites** — GOVERNED ≈
847 · UNBACKED ≈ 926 · UNBACKED_PEER ≈ 45 · STALE ≈ 55. By **breadth**: ~384 are **site-specific**
(accepted at a single site — the local exceptions peers don't share, the ones to scrutinise), ~706
few, ~783 widespread. By **consistency**: ~1,852 consistent, **~21 partial** (a peer still has the
identical value OPEN and should take the same CRFC — the directly adoptable set).

> **Site-specific is the interesting cut.** A value accepted at *one* site but left OPEN at others
> is either a genuine local need (→ its own CFG-RFC) or an inconsistency (peers should adopt or the
> site should re-open). A value accepted at *many* sites is a de-facto standard (→ productise). Use
> the **Breadth** filter on the ledger tab to isolate the site-specific exceptions.

Run it:
```
cd SQL_Translations/PBI_Config_Drift_Alert
python build_exception_ledger.py
# -> Config report/exception_ledger.csv     (the human-readable ledger; adds Coverage / Breadth / Consistency)
# -> UIUX/assets/exception-ledger.js        (window.WHS_LEDGER — surfaced inline in the deviation dialog + graph tab)
# -> .github/skills/config-drift-human-decision/ledger_grounding.json  (notes/rationale evidence)
```

### Learning from the notes/rationale (grounding the decision)
`ledger_grounding.json` distils, per accepted value-identity, the sites' **actual** *Deviation
Notes* and *Rationale for Accepted* text (deduped across environments) plus the cited/potential
CFG. Use it to answer *"why did the accepting sites sign this off?"* in the site's own words —
never invent a justification. When the note itself names a CFG or a change artefact, that is a
`NOTE_REFERENCE` lead the discovery step already promotes.

> **Read the note, not just the flag.** The most common accepted values (e.g. `seqnum=1`
> Workflow Instruction sequence gaps, `cnzcodeandamt` count-near-zero settings) are justified in
> the notes as "no functional impact"; a value the note calls "temporary / pending PRFC" is a
> STALE/RAISE candidate, not a permanent exception. The grounding text is the deciding evidence.

## 5b. Value meaning — what a value *means* in configuration

`explain_config_values.py` produces the plain-English **meaning** of each setting/value, so a
reviewer who is not a Blue Yonder config expert can read a deviation. It is grounded three ways:
**[FEED]** the GUI label + record context; **[GENERAL]** BY flag convention (1/Y = enabled,
0/N = disabled) for the 100 boolean flags; **[DICT]** an **editable dictionary you own**,
`Config report/config_value_dictionary.json`, where the authoritative **SharePoint** definitions
for coded values are pasted. The dictionary is **create-once, never clobbered** — re-runs only
add newly-seen attributes/values and preserve every `means` you fill in. CODE attributes with no
definition are reported `needs_definition=true` — a task, never a fabricated meaning.

```
python explain_config_values.py
# -> Config report/config_value_dictionary.json  (EDIT this: paste SharePoint definitions)
# -> Config report/config_value_meanings.csv      (one row per value-context, plain English)
# -> UIUX/assets/config-meanings.js               (window.WHS_MEAN — inline in the deviation dialog)
```

The deviation dialog in `UIUX/index.html` consumes both: **window.WHS_MEAN** decodes the A/R
values inline (e.g. *"0 = disabled / no"*) and **window.WHS_LEDGER** shows, under each finding,
which peers accept the same value, under which CRFC, and who still has it open.

---

## 5c. Change capture — what is *new* since the last scan

`build_change_capture.py` turns the export's own **`First seen on`** / **`Last seen on`** columns
into a delta view — no second snapshot needed, nothing guessed. It answers *"what is new in a
site, a field, a value, and in the CRFC register, and what does it do to the governance graph?"*

| Change | How it is detected (grounded) |
|---|---|
| **NEW deviation** | `First seen on ≥ since` **and** still present in the latest scan (`Last seen on = max`) |
| **RESOLVED deviation** | `Last seen on < max` — the finding disappeared (fixed or config removed) |
| **NEW / updated CRFC** | a `Configuration_RFC.csv` row whose *Date Cab input* / *Date TCAB input* / *Closed Date* falls in the window |

Each NEW deviation is classified by its **impact on the relationship** (same identity model as the
ledger — Section·Element·Attribute·value·Type):

| Impact state | Meaning → decision |
|---|---|
| `NEW_GOVERNED` | a new **accepted** exception already backed by a **live** CFG-RFC — no action |
| `NEW_ADOPTABLE` | a new **open** finding peers already accept under a live CFG → **adopt that CRFC here** |
| `NEW_ADOPTABLE_PEER` | peers govern this Section·Element·Type under a live CFG → **reuse that decision** |
| `NEW_GAP` | a new finding with **no** governing CRFC anywhere → **raise a CFG-RFC** or fix to standard |

A new CRFC's impact = how many currently-accepted value-identities (and sites) cite it.

```
python build_change_capture.py            # default: new = last 30 days up to the current scan
python build_change_capture.py --days 60  # widen the window
python build_change_capture.py --since 2026-08-01
# -> Config report/change_capture.csv   (full NEW + RESOLVED list, human-readable)
# -> UIUX/assets/change-capture.js       (window.WHS_CHANGE — summary + rows + newCrfc + delta graph)
```

It is surfaced as the **"What changed"** query template on `UIUX/knowledge-graph.html`
(Config, CRFC & Drift tab): a delta subgraph (**Site → new finding → the CRFC it can adopt**)
plus tables of new/updated CRFCs and the newest findings with their impact chips. The
**"Exception ledger"** template on the same tab renders the decision table (field · accepted-in
sites · open-in sites · CRFC status · **Accept / Re-open / Suggest CRFC**, saved per browser).

> Typical current window (30d to scan 2026-08-12): ~11,158 new · ~5,909 new **gaps** ·
> ~998 **adoptable** · ~4,251 **governed** · 68 resolved · 1 new/updated CRFC. The new **gaps**
> are the queue that feeds §2 discovery and §3 human decision.

---

## 6. Files

| File | Role |
|---|---|
| [discover_missing_cfg.py](../../../SQL_Translations/PBI_Config_Drift_Alert/discover_missing_cfg.py) | grounded discovery → CSV + JS + queue |
| [cfg_decision.py](../../../SQL_Translations/PBI_Config_Drift_Alert/cfg_decision.py) | human decision CLI + guardrails + audit |
| [build_exception_ledger.py](../../../SQL_Translations/PBI_Config_Drift_Alert/build_exception_ledger.py) | value-level accepted-per-site ledger + peers + notes grounding |
| [build_change_capture.py](../../../SQL_Translations/PBI_Config_Drift_Alert/build_change_capture.py) | delta view: new/resolved deviations, new CRFCs, impact states + graph |
| [explain_config_values.py](../../../SQL_Translations/PBI_Config_Drift_Alert/explain_config_values.py) | plain-English value meanings + editable SharePoint dictionary |
| [site_exception_report.py](../../../SQL_Translations/PBI_Config_Drift_Alert/site_exception_report.py) | per-instance report-native stats + governance marks |
| Config report/discovered_missing_cfg.csv | human-readable proposals (plain-English grounding) |
| Config report/exception_ledger.csv | the cross-site accepted-value ledger |
| Config report/change_capture.csv | new / resolved deviations + new CRFCs since the last scan |
| Config report/config_value_dictionary.json | **editable** meaning dictionary (paste SharePoint here) |
| Config report/config_value_meanings.csv | plain-English meaning per value-context |
| ledger_grounding.json | notes/rationale evidence the decisions cite |
| _replica_drift/cfg_decisions.jsonl | the decision queue (status per candidate) |
| _replica_drift/cfg_decision_audit.jsonl | append-only decision audit trail |
| Config report/cfg_decisions_applied.csv | approved CFG attachments (feed-back) |
| UIUX/assets/discovered-cfg.js | `window.WHS_CFGD` for the HTML review surface |
| UIUX/assets/exception-ledger.js | `window.WHS_LEDGER` — inline ledger in the deviation dialog |
| UIUX/assets/change-capture.js | `window.WHS_CHANGE` — the "What changed" graph template (new/resolved/new-CRFC + impact) |
| UIUX/assets/config-meanings.js | `window.WHS_MEAN` — inline value meanings in the deviation dialog |
