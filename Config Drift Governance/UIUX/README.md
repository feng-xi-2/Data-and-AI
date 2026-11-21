# WHS GenAI — UIUX Prototype

A **real, clickable** prototype of the WHS GenAI platform — industrial-standard
(Perplexity-style) layout with P&G-blue, clip-chart / PPT-style components and no emoji dependency. Plain HTML + CSS + a
few tiny scripts, no build step. Open any `.html` directly in a browser.

## Information architecture

| Layer | Definition | List page | Detail page |
|-------|-----------|-----------|-------------|
| **Assistants** | Agentic workflows — one per business use case | [assistants.html](assistants.html) | [assistant.html?id=…](assistant.html) |
| **Agents** | Reusable specialist agents (Supervisor · Data · Knowledge · Algorithm) | [agents.html](agents.html) | [agent.html?id=…](agent.html) |
| **Skills** | Capability packages (SKILL.md + scripts/resources/tools), per the open **Agent Skills** model | [skills.html](skills.html) | [skill.html?id=…](skill.html) |
| **Data & Knowledge** | Semantic Layer, Knowledge Graph, Warehouse Data, Warehouse Knowledge, personal KB and Design Documents | [data-knowledge.html](data-knowledge.html) | [dataset.html?id=…](dataset.html) |
| **Knowledge Graph** | The validated Neo4j graph (RTCIS ↔ PrIME) | [knowledge-graph.html](knowledge-graph.html) | — |
| **Design Documents** | Developer/product technical design in MD and HTML | [data-knowledge.html#design](data-knowledge.html#design) | [docs/WHS_GenAI_Platform_Technical_Design.html](docs/WHS_GenAI_Platform_Technical_Design.html) |

Everything is **clickable**: the sidebar lists every Agent and Workflow; list
rows, cards, chips and graph nodes all link to detail pages.

## Q&A bot on every page

A floating **WHS Assistant** (bottom-right) answers questions grounded in this
M&M workspace — NL Query, SQL Remediation, Process Discovery, IRA queries, validated
sites (Luogang, Pomezia, Athens, Urlati, Lima, Skelmersdale), the 4 agents,
SDC deviations, and the Neo4j ontology. Knowledge base lives in
[assets/data.js](assets/data.js) (`botKB` + `answer()`); widget in
[assets/bot.js](assets/bot.js).

## Skill definition (Agent Skills model)

A **Skill** is a self-contained capability package: a folder with a
`SKILL.md` (name + description + instructions) plus optional bundled
`scripts/`, `resources/` and tools. An agent discovers a skill by its
description and **loads it progressively** only when relevant — keeping context
lean. Three kinds: **Knowledge**, **Flow**, **Tool**.

## Files

```
UIUX/
├─ index.html              ← Home (Perplexity prompt)
├─ assistants.html / assistant.html
├─ agents.html / agent.html
├─ skills.html / skill.html
├─ data-knowledge.html / dataset.html
├─ docs/                   ← technical design MD + HTML
├─ knowledge-graph.html    ← Knowledge Graph
├─ skills/                 ← active SKILL.md packages
├─ _template.html
└─ assets/
    ├─ design-system.css   ← tokens + components + app shell + bot
    ├─ data.js             ← single source of truth (entities + bot KB)
    ├─ shell.js            ← injects sidebar (nested agent/workflow lists)
    ├─ bot.js              ← floating Q&A widget
    └─ logo.png
```

## Add a new page

1. Copy `_template.html`, rename it.
2. Set `<body data-active="…">` (and optional `data-active-id`).
3. Fill `.content__body`.
4. Add data in [assets/data.js](assets/data.js); the sidebar + bot pick it up automatically.

## Design tokens

| Token | Value |
|-------|-------|
| `--color-primary` | `#003DA5` |
| `--color-primary-dark` | `#003899` |
| `--color-bg-alt` | `#F3F4F9` |
| `--font-sans` | `Geist`, Arial fallback |
| `--sidebar-w` | `256px` |
| `--radius-pill` | `999px` |

> Note: the bot answers are prototype/canned (no network). Wire `WHS.answer()` to a
> real retrieval endpoint to make it live. Obsolete copied reference captures have been removed from the active UIUX tree.
