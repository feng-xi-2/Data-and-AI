# User guide — SQL Remediation (query convertor)

Where: **WHS GenAI desktop UI → Assistants → SQL Remediation**, or **iDecide → Assistants → SQL Remediation**. The graph
behind it is on **Knowledge → Semantic Layer & Knowledge Graph**.

## What you can type in the one box
| You type | It does | Example |
|---|---|---|
| A question | Writes SQL for the *Run on* database, runs it, returns SQL + rows | `How many pallets are stored per location area?` |
| One SQL, *Convert to* empty | Validates it on *Run on* (dry-run, then execution) | `SELECT equip, equip_desc FROM [EUSKIRCHEN_simp].live3.equip` |
| One SQL, *Convert to* another database | Converts it (RTCIS → PrIME 2022, RTCIS → PrIME 2014, PrIME 2014 → 2022) and runs both sides | an RTCIS report query |
| Several questions (one per line ending with `?`, or a list) or several SQL separated by a line `---` or `GO` | Runs them as a batch (max 25) | a site's report list |

The line under the box shows what will happen (`→ ask on …`, `→ convert RTCIS → PrIME2022`, `→ batch: …`) before you
send it. Ctrl+Enter sends.

**Sites and warehouse:** pick *Run on* (and *Convert to*). PrIME needs a warehouse id. The `wh_id` box is pre-filled per
site (DE08, WMD1, CN74) and passed as `@wh_id`; RTCIS has no warehouse id.

## Reading an answer
- **Status:**
  - `validated`: the SQL ran on the replica.
  - `rejected`: it did not run, or it was refused by the read-only guard; the reason is shown.
- **SQL runs:** how many times the agent ran SQL while working (at most 3), and how long it took.
- **Column contract** (conversions): `identical` means the converted query returns the same columns, in the same order,
  as the source. Otherwise you see the missing and extra columns.
- **Rows:** the first rows from the real database, with the total row count.
  - Columns that are **empty in every row** are flagged in red. Check them: the PrIME source may differ, or the field may
    not be used at the site.
  - 0 rows is not a pass unless the data really has none.
- **Agent steps:** the tools it used, e.g. `concept_context` (business theme + Timbr concept), `describe_tables` (real
  columns), `join_paths` (validated joins), `find_examples` (validated templates), `run_sql`.
- **Evidence in the graph:** links to the tables it used, each shown across RTCIS / PrIME 2014 / PrIME 2022.

## Approving and exporting
- **Approve as example** (validated questions only):
  - The service runs the SQL again on the site before it stores it.
  - Your name is recorded from your sign-in.
  - Approved examples are used for later questions.
- **Download JSON / CSV:** every answer of the session. CSV cells that a spreadsheet would run as a formula are prefixed
  with `'`.

## Good questions
- Name the thing and the grouping: *"inventory quantity per part and inventory status"*,
  *"receiving trucks per receiving status"*.
- Say "picked" / "shipped" / "expected" / "received" explicitly. These are different columns in PrIME.
- For a conversion, paste the full original query, including its filters. Keep the original column names: the converter
  keeps them.

## Limits (see `benchmark/CLOUD_RESULTS.md`)
- Accuracy against expert reference queries is 11/12 on the current benchmark. Always check numbers that matter with
  the site's expert before you use them in a decision.
- **RTCIS "per zone" questions** can come back per sub-site *and* zone (BUG-10). Add "per zone only" if you need one
  row per zone.
- **Time:** an answer takes 30–100 s, and a batch takes about that long per item.
- **Read-only:** nothing is written to any database.
