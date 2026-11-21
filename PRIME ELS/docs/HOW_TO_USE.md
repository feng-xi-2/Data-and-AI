# How to use the PRIME ELS Hypercare KPI report

**For:** site leads, shift leads, hypercare team · **What it is:** one Power BI report for the PrIME 2014 / 2022 sites in hypercare -
throughput, trucks, production, storage, orders, people, alerts with targets, and data health - loaded from the sites' data replicas.

**New here? Read `START HERE - how to open the Hypercare report.pdf` in the SharePoint folder - one page, two minutes.**

---

## Step 1 – Open the one file (no zip, no refresh, no sign-in)

SharePoint › OSS warehousing data and GenAI › Documents › Data Projects › **PRIME ELS › Hypercare KPI** ›
**`WH Hypercare KPI - ALL_SITES.pbix`** - the report **with the data of every site inside**.

* **A. In the browser (fastest):** click the file - it opens in the browser, nothing to install (needs a Power BI Pro / E5 licence;
  if SharePoint only offers *Download*, use B).
* **B. In Power BI Desktop (free):** Download → double-click → it opens **with data** in about 1 minute.
* **Do not press Refresh** - you don't need to. The data is inside the file.
* The zips in *For report builders (optional)* are for people who change the report - not needed to view it.

**How fresh:** a new copy of the file is put in the folder twice a day (about 07:30 and 19:30 Singapore time - the banner shows the
times in your site's time). The banner on every page says **data as of** &lt;time&gt;; *⚠ this copy is N h old* = open the file in
SharePoint again. (The copies are made on the hypercare team's PC: when it is locked or off, the copy comes after its next unlock.)

## Step 2 – Live data (optional, needs replica access)

1. Read access to your site's data replica: AD group **`<ad-group>-<SITE>-READONLY`** (ask the replica owner), on the **P&G network or ZPA**.
2. Power BI Desktop: **File → Options and settings → Options → Security** → untick *Require user approval for new native database queries* (once).
3. **Home › Refresh**. Choose **Microsoft account** (Organizational account) → **Sign in** with your `@<company>` account → **Connect**.
   Do **not** choose *Windows* - Azure SQL refuses it ("untrusted domain").

The all-sites file refreshes every site (about 10 minutes; you need access to every replica). For one site only: unzip
`WH Hypercare KPI - <SITE>.zip` from *For report builders (optional)* and open the `.pbip` - it opens empty and needs one Refresh
(measured 3-Nov: Akashi 113 s, Minhang 133 s, Binh Duong 146 s, Jakarta 229 s). The file reads **only the data replica** - no Excel,
SharePoint or SAP / Databricks connection. Pages open with the KPI values computed at refresh (fast); picking another day or shift
recalculates them live, which takes a few seconds longer on the Daily report and Alerts pages.

## Step 3 – Pick what you look at (the filter bar, same on every page)

| Filter | What it does | Blank means |
|---|---|---|
| **Site** | which site (all-sites file only) | the default site |
| **Day** | the shift day | today's shift day (or the last day with activity) |
| **Shift** | one shift of that day: every KPI, hourly chart, truck list and productivity uses only that shift's hours | the whole shift day |

The text on the right of the bar says exactly which window every page shows (site time).

## Step 4 – Read it from top to bottom

Tabs follow the site process: **Overview → Inbound & Trucks → Production & Lines → Storage & Inventory → Outbound & Orders → People → Admin.**

1. **Hypercare Cockpit** - the 6 KPIs vs target, previous day and prediction; *What to do now* lists the open alerts, critical first.
2. **Alerts** - every alert rule: actual vs target and why; click a rule to see the numbers behind it, the diagnosis and the action.
3. Open the **section that is red** - every page reads: KPIs → where it is stuck → why → the detail list.
   * Trucks late? **Trucks & TTAT**: where the truck time goes, dock and staging lane per truck, the truck Gantt.
   * Pallets stuck? **Process Flow** (stage board) and **Pallet Flow**.
   * Production behind? **Line RCA & Shifts**, **Produced Pallets**. A site without planned production says
     *"No production planned"* in the banner. SAP data (SAP production receipts, SAP production plan) is not in this report:
     it needs a Databricks (CDL) connection, so its pages were removed from the shared file (20-Nov).
   * People? **User Productivity** - by hour vs target, per user, user x hour.
4. **Config & Health** - is the data fresh and complete? Read this first if the banner says checks failed.

Buttons: **Ctrl + click** in Power BI Desktop, a normal click in the Service. Every page has a **⌂ Home** button top left.

## Step 5 – Change an alert target

Open **Hypercare_KPI_Inputs.xlsx** in the PRIME ELS SharePoint folder (*Data Projects → PRIME ELS → Hypercare KPI*), tab **Alert targets**:
Site = `All sites` for everyone or your site code for your site → Target / Warning at / Critical at → save → tell the hypercare team.
The targets are **copied into the report file when it is built**, so the file never needs the workbook; the team rebuilds and re-shares
the file (`py tools/build_pbip.py <SITE>`). Only want to try a value? Config & Health → *Alert threshold inputs* (only for you, not saved).

## Step 6 – Ask Copilot about the KPIs and the action plan

The report carries **AI instructions** for Copilot (Home → *Prep data for AI* shows them) and two **answer tables** built at every
refresh: **KPI Scorecard** (one row per site × KPI: value, target, limits, status, forecast, explanation, action, owner) and
**Site Summary** (one row per site: state, main constraint, action plan, production outlook, data as of). Copilot only sees these
tables plus site, date and a few history measures - the ~600 helper fields of the pages are hidden from it, so it answers from
the same numbers as the pages without guessing.

* **Power BI Desktop:** sign in (top right) → **Home → Copilot**. The first time it asks for a workspace with Copilot: pick
  **<workspace>** (Fabric capacity). In the Copilot pane choose the skill *Answers questions about the data*.
* **Power BI Service:** open the report in **<workspace>** → **Copilot** (top right).
* **Always name the site** (BINHDUONG / BD, MINHANG / MH, JAKARTA / JKT, AKASHI) - otherwise Copilot answers per site.
  XIQING and ATHENS are not in the shared report since 19-Nov (left out to make it lighter - `config/build_options.csv`
  AllSites_Exclude); their single-site files still exist for the hypercare team.

**Question templates** - replace `<SITE>`, `<KPI>`, `<OWNER>`. Copilot also offers the examples as starter questions when it
opens, and its instructions tell it exactly how to answer each one (source: `config/copilot_questions.csv`).

| Template | Example | Answer comes from |
|---|---|---|
| How is `<SITE>` doing today? | How is BINHDUONG doing today? | Site Summary state + KPI Scorecard red / amber rows |
| Which KPIs are critical at `<SITE>`? | Which KPIs are critical at JAKARTA? | KPI Scorecard, Status = CRITICAL |
| What should we do first at `<SITE>`? Give issue - evidence - action - owner. | ... at MINHANG ... | KPI Scorecard actions, critical first, + main constraint |
| What are the open actions for the `<OWNER>` at `<SITE>`? | ... for the Warehouse lead at BINHDUONG? | KPI Scorecard rows of that owner |
| What is the `<KPI>` at `<SITE>` vs target? | ... inbound truck turnaround at JAKARTA ... | KPI Scorecard row: actual, target, status, forecast |
| Why is `<KPI>` at `<SITE>` off target and how is it calculated? | ... goods receipt time at BINHDUONG ... | KPI Scorecard: how calculated, numbers behind, what to check |
| Will `<SITE>` reach its targets by the end of the day? | ... BINHDUONG ... | KPI Scorecard forecasts + production outlook |
| Compare all sites: critical and warning KPIs and main constraint. | (as is) | Site Summary, one row per site |
| Compare `<KPI>` across all sites. | ... outbound truck turnaround ... | KPI Scorecard, one row per site |
| Show `<KPI>` at `<SITE>` for each of the last 7 days. | ... inbound truck turnaround at AKASHI ... | history measure by day |
| How fresh is the data for `<SITE>` and can I trust it? | ... MINHANG ... | Site Summary: data as of, failed checks, settings status |

Owners: Inbound lead, Outbound lead, Warehouse lead, Production supervisor, Shift leader, Hypercare lead, Report owner.
The same templates are on the report page **Ask Copilot** (Admin section of Home), so users can copy them while working.

Copilot can still be wrong: check important numbers on the page it points to (the Hypercare Cockpit and Alerts pages show the same values).
Production-line root causes are on the *Line RCA & Shifts* page (not in Copilot's view).

---

## If something looks wrong

| You see | Meaning | Do |
|---|---|---|
| "Working on it" box in Desktop | someone pressed Refresh (or, on the hypercare team's PC, the automatic refresh runs) | wait until it closes; on a downloaded copy: close without saving and reopen |
| SharePoint only offers *Download* | no Power BI Pro licence, or the browser view is off in the tenant | Download and open in Power BI Desktop (Step 1 B) |
| ⚠ this copy is N h old | an old download | open the file in SharePoint again |
| Empty tables after opening a `.pbip` | project files store no data | open the `.pbix` instead (Step 1), or **Refresh** (Step 2) |
| Refresh error naming SAP Plan PO / Shipping Market / Databricks | an old file from before 3-Nov | open the current `.pbix` from the PRIME ELS folder |
| "Login failed … untrusted domain" | a Windows sign-in is stored | File → Options and settings → Data source settings → the `<replica-server>` entry → **Clear permissions** → Refresh → Microsoft account |
| A page says "NOT USED AT <site>" / "No production planned" | the site does not run that process (e.g. no production, no Level A) | nothing - the page explains it |
| A number looks wrong | data timing (late postings) or a site setting | Config & Health first, then send a screenshot + page + site + day to the hypercare team |
| Copilot button greyed out / "select a workspace" | not signed in, or no Copilot workspace chosen yet | sign in; pick **<workspace>** when asked (needs access to that workspace - ask the hypercare team) |
| Copilot adds up all sites or answers for the wrong site | no site in the question | name the site in the question (e.g. "at JAKARTA") |
