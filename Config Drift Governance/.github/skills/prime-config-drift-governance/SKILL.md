---
name: prime-config-drift-governance
description: "Reason about the P&G PrIME WMS CONFIGURATION domain — Config Drift (PCD) deviations & scoring, the Standard Configuration Library, the CFG-RFC change process, Design Review / CAR / CHR governance gates, 2014→2022 deployment (SCDR vs DxC RO) and Migration Readiness. USE WHEN: interpreting a Config Drift deviation (type/severity/element/rationale); deciding if a new site configuration meets the standard or what its impact is; explaining how a config change is approved (CFG-RFC) and deployed; mapping a PrIME 2014 configuration section to its PrIME 2022 navigation path; questions about Config Score vs Health Score, accepted exceptions, migration categories, CoE Features / config-with-code, or the config knowledge graph. Trigger phrases: 'what is this drift deviation', 'config drift', 'does this config meet the standard', 'new config impact', 'CFG-RFC', 'CAR / CHR / Design Review', 'Configuration Library', 'SCDR vs RO', 'migration readiness 2014 to 2022', 'Config Score', 'accepted exception rationale', 'configuration section 2014 2022'."
---

# PrIME Configuration — Drift & Governance

Domain skill for the **P&G PrIME WMS Configuration** area, owned by **PrIME CoE**
(Center of Excellence). It grounds two operating questions:

1. **Running Config Drift → what is a deviation?** (Objective 1)
2. **A new site configuration → does it meet the standard, and what is the impact?** (Objective 2)

> **Authoritative source:** the SharePoint "Configuration" tab of *WMS PrIME Service*
> — root [Configuration.aspx](https://<sharepoint-host>/sites/WMSPrIMEService/SitePages/Configuration.aspx),
> 92 configuration pages captured live via `sharepoint_reader.py --pages-only`.
> **Machine-readable mirror:** `window.WHS.configModel` in `UIUX/assets/data.js`.
> **Graph:** `config_governance.py` + `crfc_semantic.py` load it into Neo4j; ask it in
> English via the local bridge `graph_api.py` (`POST /nl`).

---

## 0. The knowledge graph is organized in TWO categories

| Category | What it answers | Nodes (labels) |
|---|---|---|
| **1 · PrIME ↔ RTCIS ↔ SDC Relationship** | how to translate/validate a query across systems | RTCISTable/Column/Value, PrIMETable/Column/Value, ConfigSection, SDCDocument, PMCProcess, WorkInstruction |
| **2 · PrIME 2014 → 2022 Configuration → CRFC** | the two objectives below | Version, Section, Column, Field, Exception, Change · Process/Stage/Role/Decision/Deployment/Output/Tool (CRFC) · DriftTool/DeviationType/Severity/Score/Gate/MigrationCategory/DeploymentPath/ConfigBucket (governance) |

UIUX: [UIUX/knowledge-graph.html](../../../UIUX/knowledge-graph.html) has a **category switcher**;
[UIUX/knowledge-graph.html](../../../UIUX/knowledge-graph.html) is the live Neo4j knowledge-graph page (ontology + Config/CRFC/Drift tabs).

---

## 1. OBJECTIVE 1 — Config Drift: what is a deviation?

**PrIME Config Drift (PCD)** — CoE application, **v3.0 (June 2026)**. Runs **twice a week**
on the Decision Automation Platform, publishes to Power BI. Compares each PrIME instance
against the **standard configuration** (reference instance **MNTWMS**) plus allowed
variations. Audit scope **132 instances (62 PROD · 35 UAT · 34 SIT)** as of Jan 2026.
[Configuration-Drift.aspx]

### Two independent scores (split in v3.0)
- **Config Score** — adherence to configuration standards.
- **Health Score** — the "Configuration and Health Checks" section (retention, time since
  last security refresh, job execution times…). Split out so checks no longer move Config Score.

### Deviation TYPES (what the report can flag)
| Type | Meaning |
|---|---|
| **Missing record** | record is absent in the audited instance |
| **Unexpected record** | record present but not allowed (may be allowed for other sites) |
| **Mismatching value** | record present but has an unsupported setting (fills **A Value** vs **R Value**) |

### Deviation SEVERITIES (drive scoring, higher = bigger penalty)
| Severity | Meaning | Scoring |
|---|---|---|
| **High** | significant WMS impact — must be addressed | largest penalty (Config Score) |
| **Medium** | should be reviewed; function may be lost/differ | penalty |
| **Low** | information only — cosmetic / new base config | small penalty |
| **Accepted** | CoE-approved exception / temporary variance (2014) | **no Config-Score impact**; carries a **Rationale** |
| **2022** | only affects the 2014→2022 migration — fix **before** migrating | migration screen only |
| **health_high/medium/low** | checks only (June 2026) | **Health Score only**, never Config Score |

### The Configuration Element (how a deviation is identified)
A **single value** OR a **`#`-concatenation of the section's primary keys**:
- `MANPKGOPR#DEFAULT#MINIMUM-WEIGHT` = policy code # variable # value
- `delv_flg#trlrmgtopr#trlrmgtopr#WM,SEAMLES` = Variable Name # Application ID # Form ID # Addon ID

**Sections using `#`-concatenated elements** include: Workflow Actions, Code Maintenance,
Database Archive Details, Bar Code Template, Variable Validation, Variable Lookup, Lookup ID,
Custom Parameter, **Policy Maintenance**, Workflow Instructions, Pick Pre-Validation Scheme,
Custom Permission, Variable Catalog, Tables Columns, Profile Maintenance, Hold Definition,
Variable Configuration, Warehouse Workflow, Variable Default, Compliant Configuration,
Inventory Status Progression. [CAR page]

### Full Deviation Report columns (16)
Audited Instance · Configuration Section · Deviation Severity · Configuration Element ·
Element Attribute ID · Element Attribute Name (GUI) · **A Value** (audited) · **R Value**
(reference/MNTWMS) · Deviation Type · Deviation Comments · Deviation Notes · **Rationale** ·
First Seen On · Last Seen On · **Migration Category** · Migration Notes.

### How rules are set & a deviation is resolved
- Each **Configuration Section** is defined by CoE: whether **new records** are allowed,
  whether **missing records** are allowed, how it's audited, the severity per deviation type,
  and disallowed values. (e.g. **Jobs** allows no new records; **Devices** does.)
- Auditing rules are **refreshed weekly via approved CFG-RFCs**.
- The **Exceptions file** = every deviation shown as **Accepted** (2014 temporary/allowed
  deviations + outdated-but-valid config awaiting the next RO).
- **Resolve** by either fixing at the instance (set to the standard value) **or** CoE
  accepting it as a new allowed variation via **CFG-RFC**. Resolved deviations are purged
  after the retention period.
- **CAR** (Configuration Audit Report) is now built from the Drift report; **CHR** merged
  into Drift as "Configuration and Health Checks" (completed Mar 2026).

> **Reading a deviation, in order:** Section → Deviation Type → Severity → Configuration
> Element (split on `#` into the section's primary keys) → A Value vs R Value → check
> Rationale/Notes to see if it's an accepted exception or a real gap to fix.

---

## 2. OBJECTIVE 2 — new site config: does it meet the standard? what impact?

### First, which bucket is it?
- **Central configuration** — owned by **Product Team**, shared by all sites, **preloaded,
  must NOT be modified** (inventory statuses, lot formats, jobs…). A change here is almost
  always a deviation.
- **Site configuration** — owned by **SE (projects) / site KU / BPO**; legitimate
  business-process + site-preference settings (storage strategy, allocation strategy…).

### Governance gates (how it is checked & approved)
| Gate | Role |
|---|---|
| **Design Review (DR)** | project gate; GBS PM raises **2 weeks prior**, 5 sessions; global experts review Work Process + PrIME Configuration vs standards; needs **CoE signoff**. Gaps → CFG-RFC or CoE Features. [Design-Review.aspx] |
| **CAR** (Configuration Audit Report) | shows not-allowed config vs the global standard (now from Drift). Fix to standard **or** raise a CFG-RFC. |
| **CHR** (Config & Health Report) | **NOK** = must fix for CoE signoff · **NOK-CC** = approve the CC in SCDT · **CHECK** = review & address · **INFO** = informative. Merged into Drift Mar 2026. |
| **CFG-RFC** | the change request that turns a new/changed config into a standard, allowed deviation, or exception (see §3). |
| **CoE Features** (config-with-code) | must be **productized** via a **P-RFC in iCM**; deployed via SCDT (2014) or Roll-out (2022). Un-productized code is overwritten by the DxC RO. [Configuration-with-Code page] |

### The impact answer
> Any config that is **not in the standard** surfaces in Config Drift as an **Unexpected
> record** or **Mismatching value** → reduces the site's **Config Score** → must be **fixed**
> or **accepted by CoE (with Rationale)**. Configuration-with-code that isn't productized
> risks being **overwritten by the next DxC Roll-out**.

### If it's a decision for CoE, the outcomes are (CFG-RFC)
Approved as **new standard** · Approved as **allowed deviation** · **Exception temporary
approved** (needs a "Till" link to a P-RFC / PR-Bug) · **Exception approved for site/region**.

---

## 3. Supporting facts

### Standard Configuration Library — the source of truth
Repository for the P&G PrIME Standard Configuration, structured by **Configuration Section**
(usually one configuration **GUI screen**). Per section: overview · best practices w/ pros&cons ·
**defaulted config** (Global Template) · **allowed deviations** w/ guidance · **optional records**
(re-applicable) · **exceptions** · (2022) changes vs 2014 + P&G customization. Two catalogues:
**Configuration Catalogue 2014 (166 workbooks)** and **202x (151 workbooks)**. The Library also
publishes the **2014 screen name ↔ 2022 navigation path** crosswalk for every section. Updated
via CFG-RFC. [Standard-Configuration-Library.aspx]

### Deployment paths
- **v2014 — SCDR**: catalogue = **SCD Portfolio** (TMPLCHG packages), tracked in QuickBase/SCDT.
  Mandatory install sequence: **Rollout → SCDR package → Hard Bounce → Security Refresh**.
  Lead time 3 wd (specific) / 2 wk (assessment). Self-Service SCDRs are on-the-shelf packages.
- **v2022 — DxC Roll-out (push)**: no SCDR; the RO carries most config (default/dummy values) +
  all CoE-Feature code (**disabled**). **SSCD** self-service packages for urgent/special cases.
  Features **enabled via Role Base Policy Maintenance**. Watch-out: RO overrides local coding
  with the productized version. [Standard-Configuration-Deployment-Process(-2022).aspx]

### Migration Readiness 2014 → 2022 (a Drift function) — categories
- **Action Required - PrIME 2014 Cleanup** — MUST fix before migration.
- **Action Required - Site Awareness** — resolved/migrated per case; site must know behavior; may raise CFG-RFC.
- **No Action for Migration** — no impact, no review.
- **Undefined - CoE to Review** — temporary; CoE will triage.
- **Not Possible as Per Drift Rules** — internal; should not occur in 2022.
> **2022-severity** deviations and **High** deviations must be addressed **before** migration.

### CFG-RFC lifecycle (change process) — ordered
Submitted → Ready for CoE meeting → Waiting for requestor action → Waiting for OPL/TPL approval
→ Integration in progress → Waiting for requestor to accept integration → Delivered.
Off-ramps: Rejected · Withdrawn · Disused. Tracked in **QuickBase**. Outputs bridge to the
**Configuration Library / Audit tool / Deployment packages / Global Template**.
[Configuration-Change-Process.aspx] — full model in `crfc_semantic.py`.

---

## 4. How to use the graph to answer

Start the local bridge (once):
```
cd SQL_Translations/PBI_Config_Drift_Alert
set NEO4J_USER=neo4j & set NEO4J_PASSWORD=***
python graph_api.py --port 8737
```
Then `POST http://127.0.0.1:8737/nl {"q": "..."}` — grounded, read-only Cypher. Working NL:
- *"What is a deviation in Config Drift?"* → DeviationType
- *"Show deviation severities and scoring"* → Severity → Score
- *"What governance gates check a new site config?"* → Gate
- *"Show the migration 2014 to 2022 categories"* → MigrationCategory
- *"How is config deployed in 2014 vs 2022?"* → DeploymentPath → Version
- *"Show the CRFC lifecycle in order"* / *"What are the decision outcomes?"* → CRFC

Rebuild the governance layer after editing the facts:
```
python config_governance.py --build --neo4j     # DriftTool/DeviationType/Severity/Gate/...
python crfc_semantic.py     --build --neo4j     # CFG-RFC process
```
Edit the UIUX facts in `UIUX/assets/data.js` → `window.WHS.configModel` (drift, newConfig,
deployment, migration, library). The knowledge-graph page renders them under **Category 2**.

---

## 5. Rules of engagement (do / don't)

- **Don't** treat a name-match as a standard-match: a config being *present* is not the same
  as *meeting the standard* — always check the section's allowed/optional/exception rules.
- **Don't** invent severities or categories — the enumerations above are the complete sets.
- **Do** split a Configuration Element on `#` using the **section's primary keys** (from the
  P&G Standards of that section) before interpreting it.
- **Do** distinguish **Config Score** vs **Health Score** — `health_*` and check sections
  never affect Config Score.
- **Do** treat an **Accepted** deviation as intentional (has a Rationale) — not a gap to fix.
- **Do** cite the SharePoint page and, where relevant, `window.WHS.configModel` / the graph.
