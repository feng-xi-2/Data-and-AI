# PRD — SQL Remediation (query convertor) for RTCIS, PrIME 2014 and PrIME 2022

Status of every requirement, bug, dependency and test run: [tracker/PRD.md](../tracker/PRD.md) (generated from
`tracker/register.json`; the same ids are the Jira issues of epic WG-144 and appear in commit messages and PR titles).
Design: [ARCHITECTURE.md](ARCHITECTURE.md). How to use it: [USER_GUIDE.md](USER_GUIDE.md). Evidence:
[benchmark/CLOUD_RESULTS.md](../benchmark/CLOUD_RESULTS.md).

## 1. Problem
Warehouse sites are moving from RTCIS (Oracle WMS, replicated to SQL Server) and PrIME 2014 to PrIME 2022 (Blue Yonder).
Each site has dozens of reports and ad-hoc queries written for the old schema. A one-to-one translation does not work:
- Tables split or merge (for example, RTCIS `unitld` maps to PrIME `invlod` / `invsub` / `invdtl`).
- Columns change name and meaning (for example, `pckqty` is the quantity still to pick, while `picked_qty` is what was picked).
- Code values differ (for example, inventory status).
- Every PrIME query must be filtered by warehouse (`wh_id`).

Experts today convert each query by hand and check it against a replica. Business users cannot write SQL at all.

## 2. Users and jobs
| User | Job | Today |
|---|---|---|
| Site analyst / key user | "Convert this RTCIS / PrIME 2014 query for our PrIME 2022 site and tell me it still returns the same columns." | Asks an expert; days |
| Process owner / business user | "How many pallets are stored per area?" in plain language, with the answer from the real database. | Waits for a report |
| WMS expert | Review and approve answers, so that the next answer reuses them. | Rewrites queries by hand |

## 3. Goals and success measures
| Goal | Measure (benchmark round 5, `benchmark/CLOUD_RESULTS.md`) | Target before production |
|---|---|---|
| Every answer runs on a real database | Questions validated on the replica | 100% (now 18/18) |
| The answer is right, not only runnable | Execution accuracy against expert reference queries | ≥ 90% on a held-out set of ≥ 50 questions (now 11/12 on 12 references) |
| Conversions keep the report contract | Converted queries validated with the identical column list | 100% (now 8/8) |
| Grounded, explainable | Every table / column / join taken from the knowledge graph or the live catalog; evidence links shown | 100% (enforced by tools and the final re-validation) |
| Safe | No write, no multi-statement, no linked-server call reaches a replica | 0 (read-only guard in code; tested) |

## 4. Scope
In scope:
- Questions to SQL on all three engines.
- Conversion RTCIS → PrIME 2022, RTCIS → PrIME 2014 and PrIME 2014 → 2022.
- Validation of pasted SQL.
- Batches of up to 25 items.
- Validated templates, approval of answers as examples, and JSON / CSV export.
- The Semantic Layer & Knowledge Graph page: graph views, ontology counts, semantic layer concepts.
- Delivery in the WHS GenAI desktop UI and in iDecide.

Out of scope:
- Writing data.
- Scheduling or report hosting.
- Sites without a replica.
- Power BI model changes, which are covered by the Hypercare / PBI kits.

## 5. Functional requirements
| Id | Requirement | Acceptance |
|---|---|---|
| FR-KG-01 | Live catalogs and validated mappings of the three engines in Cosmos DB (Gremlin) | Every table / column exists in a live catalog; exact load check |
| FR-KG-02 | SDC module / PMC process layer linked to the tables they use | Live catalog check + data presence per link |
| FR-KG-03 | Semantic layer (Timbr concepts) combined with the graph | 37 concepts, 117 `MAPPED_FROM` to validated tables |
| FR-KG-04 | Validated join paths from expert SQL | `JOINS_WITH` only from queries that ran |
| FR-KG-05 | Ontology tab from the Cosmos graph | Live counts confirmed against the load record |
| FR-AG-01 | LangGraph Deep Agent with instructions, skills and narrow tools | Tools scoped to the request database; guard first; run cap; final SQL re-validated in code |
| FR-AG-02 | One box: the service decides between question, validation, conversion and batch | Routing tests; UI E2E |
| FR-AG-03 | Replica access through an endpoint next to the replicas (`KG_REPLICA_ENDPOINT`) | Only guarded SQL is sent |
| FR-AG-04 | Concept-first routing: business theme + Timbr concept → directly linked, catalog-checked tables | Benchmark before / after (round 5) |
| FR-UI-01 / FR-UI-02 | Desktop UI: Knowledge page and SQL Remediation page | UI E2E against the live service |
| FR-IDE-01 | iDecide: Knowledge page, SQL Remediation page, authenticated backend routes | Backend + frontend tests; deployed retest |
| FR-IDE-02 | iDecide hosts the agent in-process (`SQL_REMEDIATION_MODE=inprocess`) | Adapter tests; hosted-mode run with the app's own identity and keys; deployed retest |
| FR-UVA-01 | Alternative host: a uvawh workflow on the Ultimate Platform | On hold (needs platform dependency approval) |

## 6. Non-functional requirements
- **Security:**
  - The agent is read-only.
  - The graph key used by the agent is the read-only key.
  - Secrets stay in the app Key Vault and are never sent to the browser.
  - The approver of an example comes from the verified token.
  - Error messages carry no host names or keys.
- **Truthfulness:** no answer is called validated unless it ran. 0 rows and empty columns are flagged. Benchmark misses are reported with their cause, including wrong reference queries.
- **Performance:** a question takes 30–100 s (the agent plans, looks up and runs SQL). The UI shows progress, and batches run in one request. Graph counts are precomputed, because a full graph count is throttled.
- **Operability:**
  - One runtime bundle (about 1 MB).
  - A clear 503 naming any missing setting.
  - A 502 with only the error type when a dependency is down.
  - A checksum manifest for the vendored copy.

## 7. Release plan
1. **Done:** kit, graph, agent, benchmark rounds 1–5, desktop UI, iDecide pages (PR #3, PR #5, iDecide PR #9).
2. **iDecide DEV with the agent in-process (FR-IDE-02).**
   - Dependencies: `uv.lock` regenerated by someone with access to the private template dependency (DEP-05).
   - Settings from the app Key Vault: the graph key and the app service principal are already there; one secret there is stale (DEP-07).
   - Replica endpoint (DEP-02).
   - Network check from the AI Apps cluster to Cosmos (DEP-06).
   - Then deploy DEV and retest the deployed app.
3. **Held-out benchmark:** ≥ 50 questions over all themes, n ≥ 3, before STG.
4. **STG / PROD** after expert sign-off.

## 8. Risks and open questions
| Risk | Mitigation |
|---|---|
| Agent varies between equivalent-looking columns | Expert reference queries; approval of answers as examples; n ≥ 3 stability runs |
| RTCIS zone grain (sub-site × zone) | BUG-10: grain rule in the query-writing skill |
| AI Apps cluster not allowed by the Cosmos firewall | DEP-06: verify from the deployed app; otherwise add its subnet or a private endpoint |
| Model availability (GPT-6.x tool calls only via the Responses API, which the gateway rejects for multi-turn) | DEP-04; GPT-5.6 Sol on chat completions meanwhile |
