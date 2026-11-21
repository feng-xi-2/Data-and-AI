# AGENTS.md — schema for the RTCIS → PrIME 2022 LLM wiki

You are maintaining and using a **persistent wiki** about converting warehouse SQL from RTCIS (legacy P&G WMS,
replicated to Azure SQL MI) to PrIME 2022 (Blue Yonder / Puma, SQL Server). The method follows Karpathy's
[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): knowledge is compiled once into
interlinked markdown and kept current — not re-derived from raw documents on every question.

**Start every session by reading [index.md](index.md), then the last 5 entries of [log.md](log.md).**

## 1. Three layers

| Layer | Folder | Who writes it | Rule |
|---|---|---|---|
| **Raw sources** | `raw/` | humans (and `ingest` copies) | **Immutable.** Never edit. `raw/MANIFEST.json` holds a SHA-256 per file; `tools/wiki_lint.py` fails if one changes. |
| **Wiki** | `wiki/` | the agent | Summaries, entities, concepts, ground truth, criteria, learnings, query pages. Every claim cites a source or evidence. |
| **Schema** | `AGENTS.md` (this file) | human + agent together | Conventions and workflows. Change it when a workflow changes, and log it. |

Working assets beside the layers (code and evidence, not prose):

| Folder | What |
|---|---|
| `tools/` | Connect, discover, run, compare, audit, report, lint — see [wiki/tools.md](wiki/tools.md) |
| `queries/` | Derived SQL: `rtcis_tsql/` (RTCIS baseline), `prime/` (deliverables), `params.json` |
| `results/` | **Ground-truth evidence** from the databases (JSON/CSV written by tools). Never hand-edit. |
| `templates/` | `report_template.html` for the tabbed HTML report |
| `output/` | Generated reports (rebuild, never hand-edit) |

## 2. Knowledge hierarchy (what wins when sources disagree)

1. **Ground truth** — measured in the database by a tool in `tools/`, stored in `results/` (or quoted with the query
   and timestamp). Tag `[DB]`.
2. **Expert ruling** — site experts (RUIZ.RS / Gino OBS1-8) and expert-verified corrections. Tag `[EXPERT]`.
3. **Documented reference** — `raw/reference`, `raw/kb`, `raw/schema/verified-mappings.json`. Tag `[DOC]`.
4. **Past learnings** — `raw/memories` (dated session notes). Tag `[LEARNED]`.
5. **Inference** — logically derived, not measured. Tag `[INFERRED]`. **General knowledge** — tag `[GENERAL]`.

If a lower tier contradicts a higher tier, the higher tier wins **and** the wiki page records the contradiction in a
`## Contradictions` section (never silently overwrite). An expert ruling can be overridden only by a *declared
deviation* backed by `[DB]` numbers (example: receiving-UOM factor 94% vs UNTCAS 85%, see
[wiki/experts/ruiz-rs-obs.md](wiki/experts/ruiz-rs-obs.md)).

## 3. Page conventions

Every page in `wiki/` starts with YAML frontmatter:

```yaml
---
title: Receiving-UOM quantity factor
type: concept          # overview | objective | ground-truth | criteria | expert | learning | method | concept | entity | query | source | tool | decision
status: verified       # verified (DB-measured) | expert | documented | inferred | open
sources: [raw/memories/euskirchen_rtcis_prime2022.md]
evidence: [results/map_inventory_fields.json]
updated: 2026-10-20
---
```

- Links are **relative markdown links** (`[text](../concepts/x.md)`) so they work in VS Code preview and GitHub.
- Numbers carry their scope: site, date, grain, tool (`94% of 25,388 matched pallet-items, DE08, 2026-10-20`).
- Mapping tags: `MAPPED`, `[INFERRED]`, `[PARTIAL]`, `[ELIMINATED]` — defined in [wiki/criteria.md](wiki/criteria.md).
- Say "not found with method X", never "does not exist" (see [wiki/learnings/verification-discipline.md](wiki/learnings/verification-discipline.md)).
- One concept per page; prefer linking to repeating. Update `updated:` when you change a page.
- Generated blocks between `<!-- gen:start -->` and `<!-- gen:end -->` are rewritten by tools; write notes outside them.

## 4. Workflows

### Ingest (a new source arrives)
1. Copy the file into the right `raw/` subfolder (do not edit it). Run `python tools/wiki_lint.py --seal` to add its hash.
2. Read it. Discuss key takeaways with the user if they are present.
3. Write/update `wiki/sources/<name>.md` (summary, what it is authoritative for, what is stale).
4. Update every affected entity/concept/ground-truth page (one source often touches 5–15 pages). Record contradictions.
5. Update [index.md](index.md) and append to [log.md](log.md): `## [YYYY-MM-DD] ingest | <title>`.

### Convert a query (the main job)
Follow [wiki/method.md](wiki/method.md): freeze original in `raw/queries/…` → RTCIS baseline in `queries/rtcis_tsql` →
map with [wiki/ground-truth/mappings.md](wiki/ground-truth/mappings.md) → **measure** unknown mappings on the same
physical objects → write `queries/prime` → `run_queries.py` (target + live witness) → `compare.py` →
`field_check.py` (0 undocumented empty/mismatched fields; reasons in `queries/field_notes.json`) →
`audit_expert_rules.py` (0 FAIL) → add `WHAT`/`STATUS` in `tools/build_report.py` → `build_report.py` →
`gen_query_pages.py` → update ground truth / learnings → log `## [date] convert | Rnn`.

### Query (a question is asked)
1. Read [index.md](index.md), open the relevant pages, answer with citations (page + raw source / evidence file).
2. If the answer needs data, run a tool against the database and cite the result file — that is ground truth.
3. **File good answers back** into the wiki (new concept/decision page or a section on an existing page) and log
   `## [date] query | <question>`. Explorations should compound, not vanish into chat history.

### Lint (health check — run before handing over and after every ingest)
`python tools/wiki_lint.py` checks: broken links, orphan pages, pages missing from `index.md`, missing frontmatter,
raw files changed or not yet sealed, malformed `log.md` headings. `python tools/wiki_lint.py --selftest` proves the
checks can fail. Then review by reading: contradictions between pages, stale claims superseded by newer evidence,
concepts mentioned without a page, open decisions that may now be answerable. Log `## [date] lint | <summary>`.

## 5. Safety and honesty rules (non-negotiable)

- **Read-only on databases.** `run_queries.py` refuses DML/EXEC. Never write to a replica.
- **Never print, store or commit tokens.** Caches `tools/.access_token.json`, `tools/.msal_cache.json` are git-ignored.
- **Running is not equivalence.** Grade with [wiki/criteria.md](wiki/criteria.md); report unproven separately.
- **No invented runtime inputs** (OBS4) and **no plausible-looking placeholders** — NULL with `[ELIMINATED]` + reason.
- **Never hand-edit generated artefacts** (`output/*.html`, `results/*`, gen blocks) — fix the builder or data, rebuild.
- **Edit files with editor tools, not terminal string replacement.**
