# WHS GenAI Platform Technical Design

Audience: product owners, developers, data engineers, AI engineers, citizen developers, and support teams.

Scope: the unified WHS GenAI platform shown in the UIUX mockup, grounded in the M&M workspace. This document defines what already exists, what is in POC or design, and what must be built next.

Status legend:

| Status | Meaning |
|---|---|
| Existing | Evidence exists in the M&M folder and is already represented in the UIUX prototype or reusable workspace assets. |
| POC | Working prototype or pilot path exists, but production governance, deployment, or scale-out is incomplete. |
| Design | A design artifact exists or the target design is defined, but implementation is not complete. |
| To build | Required for the target platform, not yet evidenced as implemented in the folder. |

## 0. Source basis

| Source | What it contributes | Status basis |
|---|---|---|
| `Data Strategy.docx` and extracted text `SQL_Translations/_data_strategy_extract.txt` | PD data strategy, AI-ready data governance, Timbr/data-agent pattern, result-quality scorecard, target Warehouse Orchestration Platform data layer. | Existing strategy source. |
| `.github/agents/ARCHITECTURE-KB.md` | Azure Launchpad, AI Factory, subnets, services, CI/CD, Copilot Studio, Bot Framework Skills, observability, served use cases. | Existing architecture knowledge base. |
| `EU_NPI_Agentic_Flow_Design/EU_NPI_Agentic_Flow_Design.html` | Detailed NPI flow design, 19-site matrix, prompt-flow variants, NPI infrastructure, semantic ontology, agents/tools/skills tabs. | Design artifact for EU NPI. |
| `Presentations/WHS_GenAI_Portfolio.html` and `Presentations/WHS_GenAI_Portfolio_Script.md` | Portfolio status, foundation-first narrative, TACO design, assistant portfolio, human checkpoint principle. | Existing portfolio presentation; TACO design reference. |
| `kb/WH_Data_Replica_Servers.md` | Warehouse Data Replica endpoints by site and region. | Existing data source registry. |
| `SQL_Translations/_neo4j_graph_summary.md` | Neo4j Knowledge Graph node types, relationship types, validation coverage, knowledge hierarchy. | Existing graph source. |
| `SQL_Translations/_mm_audit/_MM_TRANSFER_PACK/README.md` | Transferable Process Discovery and Match & Mapping package, 438 questions, tools, Neo4j graph, query templates, process-mining model. | Existing reusable M&M package. |
| `ALL_LEARNINGS.md`, repo memories, and remediation guides | Query remediation learnings, IRA learnings, timeout RCA, translation patterns, business-intent fixes. | Existing knowledge base. |
| `UIUX/assets/data.js` | Current UIUX registry for assistants, agents, skills, data/knowledge sources, and design-doc cards. | Existing prototype data layer. |
| `ARCHITECTURE.en.md` | Ultimate Platform MCP and Skill capability module architecture: MCP Server (inbound), svc-mcp service (outbound), `skills_core` Skill SDK, pairing with Cosmos `WorkflowConfig`/`attached_services`, OAuth reuse, ADRs, and open questions. | Design artifact for platform runtime and extensibility. |

## 1. Platform intent and operating principle

The platform must not be a set of isolated demos. The product principle is: one shared warehouse data and knowledge foundation, many use-case assistants on top. Each assistant should reuse the same Warehouse Data, Warehouse Knowledge, Semantic Layer, Knowledge Graph, Agent runtime, Skill Platform, governance, and UIUX shell.

The answer path required in the product is:

1. User asks through UIUX, Copilot Studio, Teams, or a citizen-developer tool.
2. Supervisor Agent classifies the request and identifies required skills.
3. Warehouse Knowledge grounds definitions, standards, SOPs, lessons learned, and prior validated decisions.
4. Warehouse Data grounds the answer in replicas, PSDH, WCS, WMS, SAP-approved views, or curated datasets.
5. timbr Semantic Layer and Knowledge Graph run in parallel:
   - timbr Semantic Layer resolves governed business terms, SQL metrics, dimensions, joins, and data access rules.
   - Knowledge Graph resolves lineage, mappings, cross-system relationships, document provenance, transformation rules, and evidence paths.
6. Data Agent executes approved query or graph retrieval.
7. Knowledge Agent retrieves and ranks relevant standards and learnings.
8. Algorithm Agent runs deterministic calculations, validations, or optimizations when correctness cannot be left to text generation.
9. Supervisor Agent returns the query, real database result, explanation, report, citations, quality indicators, and next actions.
10. Human feedback is saved first as the user's personal skill. After steward approval, it is promoted to the shared Skill Platform.

## 2. Current-state and target-state architecture

### 2.1 Current state in the folder

| Layer | Current evidence | Status |
|---|---|---|
| UIUX shell | `UIUX/index.html`, `assistants.html`, `assistant.html`, `data-knowledge.html`, `dataset.html`, `knowledge-graph.html`, `skills.html`, `skill.html`, `answer.html`. | Existing prototype. |
| Shared data registry | `UIUX/assets/data.js` centralizes assistants, agents, skills, datasets, graph nodes, and design-doc metadata. | Existing prototype. |
| Warehouse Data | Replica endpoint registry in `kb/WH_Data_Replica_Servers.md`; SQL reports and validation scripts under `SQL_Translations/`; M&M transfer pack. | Existing. |
| Warehouse Knowledge | `ALL_LEARNINGS.md`, remediation guides, SDC/PMC knowledge, training modules, repo memories, graph summaries, M&M transfer pack knowledge bases. | Existing. |
| Semantic Layer | Strategy and NPI design describe Timbr as the semantic data access layer; UIUX has a Semantic Layer dataset and NL Query semantic path. | Design to POC. |
| Knowledge Graph | Neo4j graph exports, summary, API scripts, M&M graph exports, validation scripts. | Existing POC. |
| Agent runtime | Architecture KB describes containerized agents and Bot Framework Skills; UIUX models Supervisor, Data, Knowledge, Algorithm agents. | Design to POC. |
| Skill Platform | UIUX skill pages and active SKILL.md files exist; governance flow now defined. | POC. |
| NL Query | UIUX assistant and answer mockup exist; real sample artifacts are linked. | POC. |
| SQL remediation | Real reports, remediation guides, translation scripts, validation reports exist. | Existing to production-ready. |
| Process discovery | M&M transfer pack, graph, query templates, 438 Q&A and validation tooling exist. | POC. |
| EU NPI | Detailed design HTML exists. | Design. |
| iDecide TACO | Portfolio HTML/script describes TACO optimizer design; UIUX marks current product status as POC per latest product direction. | POC. |
| MEGA Assistant | UIUX design-stage assistant entry exists; implementation evidence not yet complete. | Design. |
| Automation KPI Assistant | UIUX design-stage assistant entry exists; implementation evidence not yet complete. | Design. |

### 2.2 Target state

Target architecture is a modular Warehouse Orchestration Platform pattern:

- One PD semantic data model for reusable warehouse concepts.
- Data Twin and warehouse data replicas for structured operational data.
- Warehouse Knowledge for documents, SOPs, standards, learnings, and validated feedback.
- timbr Semantic Layer for business-term-to-data resolution.
- Knowledge Graph for cross-system relationships, lineage, transformation, standards, and evidence.
- Reusable agents: Supervisor, Data, Knowledge, Algorithm.
- Skill Platform with personal-to-shared publication governance.
- Unified UIUX for web, Teams/Copilot Studio, and developer workbench.
- Observability using application logs, LLM traces, source/retrieval trace, quality scorecard, and golden test sets.

## 3. End-to-end modular architecture

### 3.1 Product modules

| Module | Responsibility | Current evidence | Build next |
|---|---|---|---|
| UIUX shell | Navigation, assistant launch, NL Query, data/knowledge registry, design docs, answer trace, bot widget. | `UIUX/` active pages. | Add persistent user state, saved sessions, shared permissions, production routing. |
| Assistant registry | Product catalog for use-case assistants and statuses. | `UIUX/assets/data.js`. | Move from static JS to governed registry API. |
| Agent runtime | Supervisor/Data/Knowledge/Algorithm orchestration. | Architecture KB and UIUX model. | Implement deployment contracts, skill manifests, queueing, retry, and audit. |
| Tool registry | Databricks SQL, Neo4j Cypher, Timbr NLQ, remediation scripts, M&M tools, report writers. | `SQL_Translations/`, M&M transfer pack, UIUX skills. | Register tools with schema, access policy, test evidence, monitoring. |
| Skill Platform | Reusable capability packages, personal skills, steward review, shared publication. | `UIUX/skills/*/SKILL.md`, UI Skill Builder concept. | Production skill store, approval workflow, versioning, rollback. |
| Warehouse Data | Approved structured sources and query paths. | Replica registry, reports, NPI source design. | Source onboarding workflow, DQ checks, timeliness SLAs, SoR/SoRef mapping. |
| Warehouse Knowledge | SOPs, SDC, PMC, WI, learnings, KBs, personal knowledge. | ALL_LEARNINGS, repo memory, training modules, remediation docs. | Knowledge lifecycle: owner, approval, effective date, review, retirement. |
| Semantic Layer | One PD model and per-domain modules. | Data Strategy and NPI ontology design. | Timbr concept buildout, module governance, golden queries. |
| Knowledge Graph | Lineage and relationship graph. | Neo4j export and M&M graph exports. | Formal graph schema, production store, Graph API/Cosmos Graph path, graph tests. |
| Observability | Quality, traceability, RCA, LLM monitoring. | Architecture KB references Arize and Log Analytics; Data Strategy scorecard. | Implement traces and dashboards by assistant, tool, source, and skill. |

### 3.2 Data and retrieval sequence

```
User request
  to Supervisor Agent
  to Warehouse Knowledge grounding
  to Warehouse Data grounding
  to parallel resolution:
       timbr Semantic Layer path
       Knowledge Graph path
  to Data Agent / Knowledge Agent / Algorithm Agent
  to cited answer with query, real database result, explanation, report
  to personal skill capture
  to steward review
  to shared Skill Platform publication
```

## 4. Design area 1: Data Pipeline

### 4.1 Purpose

The Data Pipeline provides approved, traceable access to operational warehouse data for NL Query, SQL remediation, process discovery, Automation KPI, TACO, MEGA, and NPI. It must support multiple latency classes: near-real-time, close-real-time, real-time, and batch/replica modes.

**Data sources:** (1) WCS replica, (2) WMS replica, (3) CDL. **Access:** follows the standard access management of each data source — agent access does not grant data access. A logged-in user with access to an agent but not to a data source must also apply for that data source's access.

### 4.2 Current assets

| Asset | Role | Status |
|---|---|---|
| WH Data Replica registry | Site endpoint catalog for production and non-production SQL DBs across regions. | Existing. |
| SQL_Translations reports/scripts | Validated SQL outputs, remediation reports, IRA reports, latency checks, graph exports. | Existing. |
| M&M transfer pack | Transferable query templates and live answer engine for M&M. | Existing POC. |
| NPI data pipeline design | PSDH, ScrApp, PRIME Replica, RTCIS Replica, SAP, Timbr, Databricks, AI Search. | Design. |
| Data Strategy | Right-sized timeliness, acquisition/integration, data catalog, semantic layer, publication/subscription. | Existing strategy. |

### 4.3 Target interfaces

| Interface | Consumer | Contract |
|---|---|---|
| `query_request` | Data Agent | `business_question`, `site`, `source_preference`, `latency_need`, `access_scope`, `expected_metric`, `request_id`. |
| `semantic_resolution` | Supervisor/Data Agent | governed metric, dimensions, joins, filters, source tables, confidence, fallback use, access policy. |
| `sql_execution_result` | Supervisor/Answer UI | generated SQL, result rows, schema, row count, execution time, source, freshness, validation status. |
| `report_artifact` | UIUX/Skill Platform | report title, path, created time, source query, validation log, owner, status. |

### 4.4 CPS and R&R

CPS means Critical Process Steps. R&R means roles and responsibilities.

| CPS | Owner | Reviewer | Output | Gate |
|---|---|---|---|---|
| Source onboarding | Data Engineering | Data Owner, Security | source record with owner, endpoint, sensitivity, refresh SLA, SoR/SoRef role | Approved source only. |
| Semantic mapping | Semantic Layer Owner | Domain SME | metric/dimension/join mapping | Golden query passes. |
| Query validation | Data Agent Owner | Product Owner | expected result and tolerance | Golden test set pass. |
| Report publication | Use-case owner | Steward | validated report artifact | Report has source and validation trace. |
| Incident RCA | Support Owner | Platform Owner | RCA and prevention action | Failed queries and fallback spikes reviewed. |

### 4.5 Build next

- Data source onboarding form in UIUX.
- Automated source freshness and row-count checks.
- Per-source access policy visible in NL Query trace.
- Query result cache with freshness indicator.
- Production connection abstraction for Timbr, replica SQL, PSDH, WCS/WMS monitoring, and KPI store.

## 5. Design area 2: Semantic Layer

### 5.1 Purpose

The Semantic Layer is the primary governed path from business language to data. It prevents each assistant from inventing private joins, metrics, and filters.

### 5.2 Current assets

| Asset | Role | Status |
|---|---|---|
| Data Strategy | Defines one scalable semantic solution, One PD Data Model, Timbr primary path, reusable data architecture. | Existing strategy. |
| NPI ontology design | Shows how NPI and WMS concepts map to source systems with Timbr. | Design. |
| UIUX Semantic Layer source card | Product view of the semantic path. | Existing prototype. |

### 5.3 Target semantic modules

| Module | Example concepts | Status |
|---|---|---|
| Core warehouse | Site, region, system, location, item, load, inventory, movement, order, shipment. | To build in Timbr from existing graph/source maps. |
| Inventory and IRA | cycle count, post count, pre count, area, countable location, majority plant, item group. | POC through IRA reports. |
| Process discovery | D1-D4, PMC process, SDC module, event log activity, throughput, configuration. | POC through M&M transfer pack. |
| NPI | NPI item, action, disposal order, risk forecast, prevention KPI, accrual. | Design. |
| Automation KPI | equipment, alarm, downtime, fault, root cause, action, SLA. | Design. |
| TACO | trailer, dock, appointment, scheduling parameter, scenario, optimization result. | POC/design. |
| MEGA | portfolio item, capability, owner, milestone, dependency, risk. | Design. |

### 5.4 Governance

- Every semantic object has an owner, definition, source, join logic, refresh expectation, test query, effective date, and retirement rule.
- Every NL Query answer must expose whether it used the semantic path, the graph path, direct data fallback, or a combination.
- Semantic changes are versioned and tested against golden questions before promotion.
- High-risk metrics require business owner sign-off before use in shared assistants.

### 5.5 Build next

- `semantic_objects.json` or registry API as interim catalog.
- Golden query set per module.
- UIUX semantic dictionary page showing terms, definitions, owners, sources, and dependent assistants.
- Timbr concept deployment pipeline.

## 6. Design area 3: Knowledge Graph

### 6.1 Purpose

The Knowledge Graph complements the Semantic Layer. It explains how concepts, tables, columns, values, documents, standards, transformation rules, and lessons learned connect.

### 6.2 Current assets

| Asset | Role | Status |
|---|---|---|
| `SQL_Translations/_neo4j_graph_summary.md` | Node/relationship catalog and validation coverage. | Existing. |
| `SQL_Translations/_neo4j_export*.json/cypher` | Exportable graph data. | Existing POC. |
| `SQL_Translations/neo4j_kb_api.py` | Graph API support. | Existing POC. |
| M&M transfer pack graph | Dedicated M&M graph layer and process-mining graph. | Existing POC. |
| NPI ontology relationship design | NPI to WMS cross-domain relationships. | Design. |

### 6.3 Target graph schema

| Node category | Examples | Purpose |
|---|---|---|
| Source systems | RTCIS, PrIME 2014, PrIME 2022, WCS, SAP, PSDH, ScrApp, Data Replica. | System lineage. |
| Data objects | Table, view, column, value, metric, report, query. | Query and translation trace. |
| Knowledge objects | SDC document, PMC process, Work Instruction, learning, KB rule. | Retrieval and evidence. |
| Semantic objects | concept, dimension, metric, relationship, business term. | Semantic-to-data bridge. |
| Use-case objects | assistant, agent, skill, tool, workflow, report output. | Product traceability. |
| Governance objects | owner, approval, source status, test result, incident, RCA. | Audit and lifecycle. |

### 6.4 CPS and R&R

| CPS | Owner | Reviewer | Output | Gate |
|---|---|---|---|---|
| Graph schema update | Knowledge Graph Owner | Semantic Owner | versioned schema | Backward-compatible or migration approved. |
| Source ingestion | Knowledge/Data Agent Owner | Source Owner | nodes, relationships, source metadata | Source approved and traceable. |
| Validation | QA/AI Evaluation | Domain SME | graph completeness/accuracy report | Golden graph questions pass. |
| Publication | Platform Owner | Steward | graph version promoted | Rollback path exists. |

### 6.5 Build next

- Production graph store decision: Neo4j for current POC or Cosmos Graph if following AI Factory target.
- Graph ingestion jobs for SharePoint/Graph API, M&M transfer pack, remediation KB, NPI ontology, and source registry.
- Graph retrieval evaluation dashboard.
- UIUX graph trace panel in answer page and assistant pages.

## 7. Design area 4: Agents, Tools, Skills, Workflows

### 7.1 Agent model

| Agent | Responsibility | Tools/skills | Status |
|---|---|---|---|
| Supervisor Agent | Plan, route, critique, verify, return. | all tools by policy. | Design/POC. |
| Data Agent | Resolve schema, generate SQL/Cypher, execute, shape result. | timbr, Databricks SQL, replica SQL, Neo4j/Cosmos Graph. | Design/POC. |
| Knowledge Agent | Retrieve standards, SOPs, learnings, graph evidence; reason and cite. | AI Search, Graph API, Knowledge Graph, SDC/PMC/RAG. | Design/POC. |
| Algorithm Agent | Run deterministic computations, validations, optimization, reconciliation. | Python tools, SQL validation scripts, optimizers, M&M engines. | Existing tools, agent wrapper to build. |

### 7.2 Skill categories

| Category | Examples | Governance |
|---|---|---|
| Query skills | NL Query, IRA query, report query writing, Automation KPI query. | Needs golden test set and result validation. |
| Remediation skills | RTCIS to PrIME, PrIME 2014 to 2022, field/value/filter remediation. | Needs parity check and business intent review. |
| Knowledge skills | Architecture Q&A, SDC search, training RAG, query remediation KB. | Needs document lifecycle metadata. |
| Process skills | M&M D1-D4 autofill, process discovery, process mining. | Needs conformance evidence and source trace. |
| Optimization skills | TACO, slotting, capacity, disposal optimization. | Needs human approval, rollback, safety limits. |
| Design skills | EU NPI design, MEGA design, Automation KPI design. | Needs design-to-build backlog and acceptance criteria. |

### 7.3 Workflow lifecycle

1. Intake: user question, report request, source onboarding, skill proposal, or assistant launch.
2. Planning: Supervisor Agent determines flow, skills, tools, and data/knowledge sources.
3. Resolution: semantic and graph paths run in parallel where applicable.
4. Execution: tools run under policy, with inputs and outputs logged.
5. Validation: deterministic checks, source citations, answer quality scorecard, human review if needed.
6. Feedback: corrections saved as personal skill first.
7. Steward review: evidence checked against Warehouse Knowledge, Warehouse Data, Semantic Layer, and Knowledge Graph.
8. Publication: approved changes promoted to shared Skill Platform.
9. Monitoring: usage, failures, fallback events, drift, quality score, and incidents reviewed.

### 7.4 Build next

- Tool manifest schema: name, owner, input schema, output schema, allowed sources, secrets, logging, tests.
- Skill manifest schema: frontmatter plus body evidence; owner, use cases, sources, tools, tests, status.
- Workflow execution log in PostgreSQL/Cosmos DB.
- Human approval UI for skill publication and high-risk actions.

## 8. Design area 5: Citizen developer integration

### 8.1 Product intent

Citizen developers should be able to contribute knowledge, tools, skills, prompts, and UI views without bypassing governance. The platform must separate personal/private learning from shared production learning.

### 8.2 Capability model

| Capability | Existing | To build |
|---|---|---|
| Personal knowledge | UIUX dataset card for `feng.xi.2 My KB`; feedback flow concept. | Personal KB store, privacy policy, export/delete, trace view. |
| Personal skill | UIUX Skill Builder concept; NL Query feedback wording. | Save correction as personal skill; apply only to that user until approved. |
| Shared skill publication | UIUX workflow concept. | Steward review queue, approvals, version promotion, rollback. |
| Low-code agent extension | Copilot Studio and Bot Framework Skills described in architecture KB. | Skill templates and connector templates for citizen developers. |
| Tool contribution | Python and SQL tools exist in workspace. | Tool packaging, validation harness, sandbox, access boundaries. |
| UI contribution | Static UIUX prototype. | Component templates and governed configuration registry. |

### 8.3 FY26/FY27 scope proposal

| Horizon | Scope |
|---|---|
| FY26 | Ship unified UIUX prototype, Design Documents tab, skill normalization, NL Query trace, personal skill capture POC, SQL remediation live path, Process Discovery POC, NPI and TACO design pages. |
| FY27 | Productionize Skill Platform, semantic registry, graph governance, Copilot Studio integration, citizen developer templates, automated quality scorecard, regional scale-out, WOP modules. |

## 9. Design area 6: Skill Platform

### 9.1 Skill lifecycle

| Stage | Description | Status |
|---|---|---|
| Draft | User or developer creates a skill from feedback, file, prompt, tool, or design artifact. | POC in UIUX. |
| Personal | Skill improves only the creator's answers. | To build. |
| Candidate | Skill is submitted for steward review. | To build. |
| Approved | Steward validates evidence, access scope, source status, tests, and downstream impact. | To build. |
| Published | Skill is available to shared platform users. | To build. |
| Monitored | Usage, errors, drift, fallback events, and user corrections are tracked. | To build. |
| Retired | Obsolete skill is hidden or removed with rollback evidence. | To build. |

### 9.2 Minimum skill metadata

| Field | Required | Purpose |
|---|---|---|
| Name and description | Yes | Human discovery. |
| Trigger | Yes | When the skill should be used. |
| Owner | Yes | Support accountability. |
| Status | Yes | Existing, POC, Design, To build, Retired. |
| Sources | Yes | Approved data/knowledge references. |
| Tools | Conditional | Tool names, versions, input/output schemas. |
| Tests | Yes | Golden questions, expected outputs, or validation scripts. |
| Access policy | Yes | What data it can read/write; whether operational writeback is allowed. |
| Publication history | Yes | Version, approver, date, rollback path. |

### 9.3 UIUX requirements

- Skill list with status, owner, source, output artifact, and dependent assistants.
- Skill detail with readable SKILL.md, artifacts, test evidence, and edit/draft state.
- Skill Builder to save personal skills from answer feedback.
- Approval workflow to promote personal skill to shared Skill Platform.
- Obsolete/retired label rather than silent deletion.

## 10. Design area 7: Unified UIUX

### 10.1 Current UIUX

The active prototype already includes:

- Home page with `feng.xi.2 How can I help you today?`.
- Assistants catalog and assistant detail pages.
- NL Query dialog detail with query/result/explanation/report example.
- Agents catalog and agent detail pages.
- Skills catalog and editable SKILL.md detail pages.
- Data & Knowledge tabs: Platform Stack, Sources, Design Documents, Document Intake.
- Knowledge Graph page.
- Answer page with sources and trace.
- Bot widget.

### 10.2 Required UIUX product pattern

| UI area | Required behavior |
|---|---|
| Home | Command entry, quick-launch assistants, resolver chain showing Warehouse Knowledge, Warehouse Data, timbr Semantic Layer, Knowledge Graph, cited answer, Skill Builder. |
| NL Query | Show business query, generated SQL/query intent, result from real database, explanation, and real report link. |
| Data & Knowledge | Put Semantic Layer and Knowledge Graph before raw Warehouse Data and Warehouse Knowledge. Include personal KB registered by `feng.xi.2`. |
| Design Documents | Separate tab with MD and HTML design documents; mark existing vs new/to-build; include developer/product technical detail. |
| Skills | Normalize SKILL.md, show sources, tools, outputs, test evidence, and status. |
| Answer | Display source citations, retrieval path, generated query, result, report, quality score, and feedback capture. |
| Skill Builder | Save correction into personal skill first, then approval workflow to publish shared skill. |
| Admin | Source onboarding, semantic object review, graph ingestion status, skill approval, obsolete reference review. |

### 10.3 Integration targets

| Target | Purpose | Status |
|---|---|---|
| Copilot Studio | Teams/root bot and bot skill consumer. | Architecture design. |
| iDecide / Orchestrions | Product UI integration for operational AI and scheduling/optimization. | TACO POC/design. |
| Grafana / KPI monitoring | Automation KPI and WCS/WMS monitoring dashboards. | Design. |
| Scheduler / KPI store | Time-based jobs, KPI snapshots, result cache. | Design. |
| Data product catalog | Source discovery and approved data products. | Strategy/design. |
| Developer workbench | Skill/tool creation, tests, logs, traces, release notes. | To build. |

## 11. Design area 8: Use-case delivery

### 11.1 Status matrix

| Use case | UI name | Status in UIUX | Source evidence | Next build |
|---|---|---|---|---|
| SQL remediation | SQL Remediation | Live | Remediation reports, guides, scripts, validation outputs. | Productionize as governed skill with CI tests. |
| NL Query | NL Query | Live/POC | UIUX dialog, IRA report, replica/semantic/graph sources. | Real backend execution, query trace, result cache, golden tests. |
| Process discovery | Process Discovery (M&M) | POC | M&M transfer pack, 438 Q&A, graph, query templates, conformance engine. | Package into assistant workflow and Skill Platform. |
| iDecide TACO | iDecide TACO | POC | Portfolio TACO design says 30+ settings and narrows huge search space to about 125 options; UIUX status set to POC. | Create dedicated TACO design HTML page, optimizer contract, rollback safety gate. |
| EU NPI | EU NPI Disposal Assistant | In design | NPI detailed design HTML with 19 sites, 3 WMS systems, 4 agents, prompt-flow variants, infrastructure. | Turn design into build backlog and pilot implementation. |
| MEGA | MEGA Assistant | In design | UIUX design entry; needs source artifacts and product backlog. | Define MEGA data model, skills, UI views, R&R. |
| Automation KPI | Automation KPI Assistant | In design | UIUX design entry; Data Strategy mentions WCS/WMS and Automation KPI semantic grounding. | Define WCS/WMS KPI store, Grafana integration, RCA tools. |
| Automation troubleshooting | Automation Troubleshooting | Live/design | Architecture and portfolio references; UIUX assistant entry. | Bind to logs, SDC/WI, RCA memory, and incident workflow. |

### 11.2 EU NPI implementation package

Required product slices:

1. Site configuration service: stores site, WMS, cadence, DO type, sloc strategy, data sources, automation, communication, approvals, thresholds.
2. NPI data pipeline: PSDH/NPI portal, ScrApp, PrIME replica, RTCIS replica, SAP-approved checks, SharePoint/DC files.
3. NPI semantic layer: NPI item, material, batch, plant, action, disposal order, risk forecast, safety stock, prevention KPI, accrual.
4. NPI workflow: input gathering, decision, DO creation, communication, execution/booking.
5. Agent workflow: Orchestration, Data, Knowledge, Algorithm with site-specific prompt-flow variants.
6. Human approval: WOC SpOC/DC line manager/site owner review depending on site rule.
7. Output: decision summary, DO draft, email draft, report, audit trail, feedback capture.

### 11.3 TACO implementation package

Required product slices:

1. Data sources: current performance, weather/time context if approved, recent operational issues, TACO parameter state, historical outcomes.
2. Knowledge sources: manuals, past tuning decisions, scheduling constraints, safety/rollback rules.
3. Semantic objects: trailer, dock, appointment, queue, load, capacity, parameter, scenario, optimization result.
4. Algorithm path: narrow candidate settings from large search space to approximately 125 candidates, then delegate evaluation to optimization engine.
5. Safety gate: compare against baseline, rollback if not better, log every parameter change.
6. Human checkpoint: show recommendation, confidence, expected impact, risk, and rollback plan.
7. Output: scenario comparison, selected setting, reason, test result, rollback status, personal/shared learning candidate.

## 12. Quality, governance, and audit

### 12.1 AI result quality scorecard

Every production assistant should report or log:

| Dimension | Required evidence |
|---|---|
| Accuracy | Match against trusted data, expected result, or SME-approved answer. |
| Completeness | Includes all required business context, assumptions, exclusions, and limits. |
| Traceability | Shows data source, knowledge source, semantic path, graph path, tool, and report. |
| Consistency | Stable answer for same source state and same user access. |
| Freshness | Data timestamp, document effective date, and ingestion timestamp. |
| Business usability | Clear wording, actionability, and next step. |
| Policy alignment | Respects access boundaries, approved sources, no unauthorized writeback. |

### 12.2 Golden test sets

Each assistant must maintain:

- Standard business questions.
- Expected answer or tolerance.
- Source-of-truth references.
- Access policy.
- Regression test command.
- Product-owner sign-off.

### 12.3 Operational controls

- Log every tool call, source used, generated query, validation result, and answer version.
- Track direct-data fallback and semantic/graph disagreement as operational events.
- Route platform incidents to RCA workflow with affected assistants and downstream reports.
- Maintain deprecation registry for obsolete skills, references, reports, and source paths.

## 13. Developer work packages

| Work package | Files/areas | Acceptance criteria |
|---|---|---|
| UIUX polish | `UIUX/assets/design-system.css`, active HTML pages | No emojis in active UI, no stale fallback resolver wording, responsive layout, clear status chips. |
| Design docs | `UIUX/docs/WHS_GenAI_Platform_Technical_Design.md/html` | Separate MD/HTML design docs linked from Design Documents tab. |
| Skill normalization | `UIUX/skills/*/SKILL.md` | Valid frontmatter, body includes owner/status/sources/tools/tests/artifacts. |
| Skill registry refresh | `UIUX/assets/data.js` | Registry points to real artifacts and design docs; statuses match product direction. |
| Source validation | Data/knowledge pages | Links resolve or are clearly marked external/unavailable. |
| NL Query trace | `assistant.html`, `answer.html` | Query, real database result, explanation, real report, semantic path, graph path, and feedback flow visible. |
| Obsolete cleanup | `UIUX/_archive`, references | Copied reference captures remain archived; active pages do not depend on obsolete captures. |
| Backend integration plan | new API spec | Define endpoints for registry, query execution, skill publication, graph lookup, semantic lookup, source ingestion. |

## 14. Product roadmap

| Phase | Outcome |
|---|---|
| Phase 0: Prototype cleanup | UIUX active pages are coherent, no stale language, skill files valid, design docs created. |
| Phase 1: Governed POC | Static registries become JSON/API; NL Query executes against approved test data; skill approval POC works. |
| Phase 2: Production foundation | Semantic registry, graph store, source onboarding, golden tests, observability, Copilot Studio integration. |
| Phase 3: Use-case scale | SQL remediation, Process Discovery, NL Query, EU NPI, TACO, MEGA, Automation KPI run on shared platform. |
| Phase 4: Warehouse Orchestration Platform | WOP modules use One PD semantic layer, data twin, skills layer, and unified UIUX. |

## 15. Decisions and open questions

| Topic | Current decision | Open question |
|---|---|---|
| Primary data path | timbr Semantic Layer should be primary where available; direct replica is controlled fallback. | When is fallback allowed and who reviews repeated fallback? |
| Graph runtime | Neo4j exists in workspace; target architecture also mentions Cosmos Graph in AI Factory. | Which graph platform is production target? |
| Writeback | GenAI should support inquiry, assistance, summarization, and admin tasks; operational writeback remains deterministic and governed. | Which assistants will ever be allowed to submit writeback requests? |
| Skill publication | Personal skill first, shared skill after approval. | Who are default stewards by domain? |
| TACO status | UIUX marks POC per current product direction; portfolio artifact says design ready. | What is pilot deployment date and owner? |
| NPI status | In design with detailed HTML artifact. | Which pilot site and which data sources first? |
| MEGA/Automation KPI | In design in UIUX. | Which source documents and owners define MVP scope? |

## 16. Immediate build sequence

1. Finish active UIUX cleanup and validation.
2. Link this design document into the Design Documents tab.
3. Normalize all active SKILL.md files.
4. Add design skills for EU NPI, iDecide TACO, MEGA, and Automation KPI.
5. Create backend API specification for registry, query execution, graph lookup, semantic lookup, and skill publication.
6. Create golden test set template and apply it to NL Query, SQL remediation, and Process Discovery.
7. Convert existing source artifacts into a governed source registry with owner, status, and refresh expectation.
8. Add admin views for skill approval and obsolete reference review.

## 17. Platform runtime architecture: MCP and Skill capability module

Source: `ARCHITECTURE.en.md` (Ultimate Platform MCP and Skill capability module, V1.0.0, draft for review). This section maps that platform-engineering design onto the WHS GenAI platform so developers and the product team can see the runtime that hosts the agents, tools, and skills described in sections 7 and 9.

### 17.1 Why this layer exists

The agents, tools, and skills in this design need a concrete runtime to be hosted, orchestrated, exposed, and extended. The Ultimate Platform (`pyrogai + pygentic + LangGraph`, IPA on AKS) provides that runtime. The MCP and Skill capability module adds three things on top of it:

| Sub-module | Direction | Responsibility | Status |
|---|---|---|---|
| MCP Server | Inbound | Expose enabled, RBAC-filtered platform flows/agents as MCP tools to external clients (Claude Desktop, Copilot Studio, IDEs). Thin wrapper that forwards to the existing `FlowController`. | To build (OAuth callback infra exists; server not yet hosted). |
| svc-mcp service | Outbound | New tenant service (`type_of_service: "mcp"`, BUILDER kind) that lets platform flows consume tools from external MCP servers, injected through `attached_services`. | To build (service provider pattern exists). |
| `skills_core` | Orchestration | Skill SDK that implements the `SkillFactory` protocol and provides an MCP Skill, registered alongside existing skills in `create_pydantic_supervisor`. | Design exists in `universal-skills-based-agent-plan.md`; not yet implemented. |

### 17.2 Module data flow

```
External MCP clients (Claude Desktop / Copilot Studio / IDE)
  to (inbound, OAuth2.1 PKCE over Streamable-HTTP)
MCP Server module  src/ultimate_platform/mcp/server/
  maps enabled flows/agents to MCP tools by RBAC, forwards to FlowController
  to
Platform core (existing, not rewritten):
  CosmosFlowRegistry, WorkflowConfig, CompileConfig.services, Supervisor
  injected via services["svc-mcp"]
  to (outbound)
svc-mcp service  services/agent_services/mcp.py  (BUILDER kind)
  connects to external MCP servers, loads their tools as langchain BaseTool
  provides tools to
Skill layer  skills_core/  plus MCP Skill
  wraps MCP tools as a SkillFactory subgraph, registered into the supervisor
```

### 17.3 Pairing with the WHS GenAI platform

| WHS GenAI element (this design) | Pairing with the MCP and Skill module |
|---|---|
| Supervisor, Data, Knowledge, Algorithm Agents (section 7.1) | Each agent's tool set can include external MCP tools injected via svc-mcp; high-value external capabilities are wrapped as MCP Skills routed by the supervisor. |
| Skill categories and Skill Platform (sections 7.2, 9) | `skills_core` is the production SDK behind the Skill Platform; the personal-to-shared publication governance maps to Cosmos config plus `update_registry` hot-reload. |
| Tool registry (section 3.1) | Tool manifests become MCP tool exposures (inbound) and svc-mcp allowlist entries (outbound), each with RBAC and audit. |
| NL Query, SQL remediation, Process Discovery, NPI, TACO assistants | Inbound: mark a flow `mcp_exposed=true` to offer it as an external tool. Outbound: add svc-mcp plus an MCP Skill to gain external tools, with zero business-code change. |
| Observability (section 12) | MCP tool calls and skill routing reuse Arize/Phoenix traces and the `outputs.results` output-standardization. |

### 17.4 Authentication and isolation (MUST)

- Inbound OAuth reuses the existing `GET /v1/auth/callback` (pygentic MCP PKCE flow, state `mcp:<thread_id>:<token>`). No parallel callback endpoint.
- Access tokens are bound to `tenant_namespace`; the exposed tool list is filtered by tenant and by `access_business_users` / `access_technical_users`. Unauthorized calls return 403 and are audited.
- Outbound credentials use two-stage tenant auth (Master SP to Tenant Key Vault to Tenant SP, then `await self.get_secret(...)`). No hardcoded or cross-tenant credentials.
- External MCP endpoints must be on an explicit tenant allowlist; runtime URL injection is forbidden.

### 17.5 Key constraints and ADRs (from ARCHITECTURE.en.md)

| ADR | Decision | Consequence for build |
|---|---|---|
| ADR-001 | Pin `fastmcp` to `>=2.9.2,<3.0.0`. | `langchain-timbr` requires `uvicorn~=0.34`, incompatible with fastmcp v3. CI must enforce the lock; v3 features are deferred as tech debt. |
| ADR-002 | Streamable-HTTP transport (plus SSE), no stdio. | Only HTTP-transport MCP servers integrate directly; pure-stdio tools need a gateway. |
| ADR-003 | Prefer the fastmcp client for outbound; use `langchain-mcp-adapters` only when needed. | Minimize dependency surface; pin versions if adapters are added. |
| ADR-004 | Build `skills_core` to implement the existing Skill plan, not an ad-hoc wrapper. | Scope includes the SDK infrastructure (contracts, config_bridge, supervisor_builder), larger than MCP alone. |
| ADR-005 | svc-mcp as a `BaseTenantService` (BUILDER kind). | Reuses two-stage auth, lazy init, alias injection, health checks; register in both service registries. |
| ADR-006 | Reuse `/v1/auth/callback` for MCP OAuth. | MCP OAuth couples to the pygentic version; pygentic upgrades require regression of this path. |
| ADR-007 | Mount the MCP Server on the IPA FastAPI app, not standalone. | Shares the IPA lifecycle and scaling; split out later only if load characteristics diverge. |

### 17.6 Open questions to resolve before build

| # | Question | Tentative assumption |
|---|---|---|
| Q1 | Is the goal inbound exposure, outbound consumption, or Skill orchestration, or all three? | All three, phased: outbound svc-mcp plus MCP Skill first, then the inbound server. |
| Q2 | Bring `skills_core` infrastructure into scope now? | Yes, as `skills_core` Phase 0. |
| Q3 | Which flows does the inbound server expose, and at what granularity? | Not exposed by default; explicit `mcp_exposed=true`; whole-flow granularity. |
| Q4 | Trust boundary of consumable external MCP servers? | P&G internal or security-reviewed servers only, with a URL allowlist. |
| Q5 | Lift the `langchain-timbr` uvicorn constraint to unlock fastmcp v3? | No in the short term; lock fastmcp 2.x. |

### 17.7 Build next for WHS GenAI

- Decide the first WHS flow to expose inbound (candidate: NL Query or Architecture Q&A) and the first external MCP server to consume outbound.
- Stand up `skills_core` Phase 0 and migrate one existing skill (for example Architecture Q&A) to the `SkillFactory` protocol as a reference.
- Add svc-mcp declarations and `mcp_exposed` markers to the relevant `WorkflowConfig` / `tenant-*.json`, gated by platform-team review.
- Add CI dependency checks for the fastmcp and uvicorn version locks (ADR-001).
