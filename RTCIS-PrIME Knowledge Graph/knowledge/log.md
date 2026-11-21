# Log

Append-only. Newest at the bottom. Heading format: `## [YYYY-MM-DD] ingest|convert|query|lint|schema|setup | title`.
Recent entries: `Select-String -Path log.md -Pattern '^## \[' | Select-Object -Last 5`.

## [2026-09-11] convert | Euskirchen label-printing set Q01–Q14
14 Oracle originals converted; validated on Athens (DE08 thin). See wiki/queries/euskirchen-label-set.md.

## [2026-09-16] ingest | RUIZ.RS expert review rounds 1 and 2
OBS1–8 adopted (GTIN by receiving UOM, shipid = carrier move, setup = list pick, no invented inputs, grain).

## [2026-10-08] convert | Euskirchen Q15–Q18 (line supply, conveyor plugins)
All 18 main bodies execute on DE08 and WMD1; Q15–Q18 awaiting review.

## [2026-10-14] ingest | Euskirchen same-pallet evidence
Receiving UOM (711/711), SUP_LOTNUM = VNDCOD+VNDLOT (6,992/6,992), line = LOC_TYP_CAT PROD (43/43).

## [2026-10-20] convert | RPM set R01–R17
51/51 runs (RTCIS EUS, DE08, Athens), columns identical; expert pass 0 FAIL; grades 5 B / 12 C.

## [2026-10-20] setup | LLM wiki created
Restructured the RPM kit + all related knowledge into raw/ (immutable, sealed), wiki/ (50 pages incl. 17 generated
query pages), AGENTS.md schema,
index.md, log.md. Added tools/wiki_lint.py and tools/gen_query_pages.py; tools now read originals from raw/queries/rpm,
template from templates/, write the report to output/.

## [2026-10-20] lint | first full lint after setup
Selftest 6/6 planted defects caught; 54 md files / 50 wiki pages / 125 raw files sealed; all checks PASS, 0 warnings.
Expert audit 0 FAIL; report rebuilt (17 tabs, self-checks passed). Query-page agreement now shown to 0.1%
(0-decimal rounding showed 8767/8797 as 100%).

## [2026-10-20] ingest | CL_LATEST (RTCIS / PrIME 2014 / PrIME 2022) and count-coverage reference queries
raw/queries/cl-ira/. Summary: wiki/sources/cl-ira-references.md.

## [2026-10-20] query | Why is CASQTY not an integer, and where is pallet height? (inventory validation)
RTCIS quantities are numeric(22,0) and truncated; PrIME 1/1000 sub-units gave 4250.400 -> FLOOR in R01, R07-R12, R14-R16
(R01 qty 78% -> 92%, R16 7% -> 100%; 314/315 remaining R01 gaps = RTCIS moves after migration). PrIME dims are cm and
pallet HGT includes the base (earlier 'HGT*100' test was wrong): R01 height mapped, NULL at DE08 because all packaging
footprints are NONE 1x1x1; SAP marm has PAL for 3/1,624 items. R06 dimension check fixed (cm, udepth = WID). R17 item
class + CL rule 95.3% -> 98.8%. Audit OBS8 narrowed to SELECT DISTINCT (COUNT(DISTINCT) false alarm). 0 FAIL.

## [2026-10-21] lint | Field-by-field check RTCIS vs PrIME, empty-field rule E1-E3
New tools/field_check.py + queries/field_notes.json: 212 output fields of R01-R17 with RTCIS/PrIME source, fill % on
RTCIS EUS / DE08 / Athens, agreement on the same keys excluding both-blank pairs, sample-format check. 43 flagged (empty or
<95%), all probed and documented by category; build_report.py refuses to build otherwise. Fixes: R05/R06 door
trlr.STOLOC (= trailer id) -> trlr.YARD_LOC; R16 ctrl_date LSTDTE (303/97,793 set) -> COALESCE(LSTDTE, ADDDTE); R05/R06
PrIME test load like-for-like (packaging receipt at a door). compare.py partial runs now merge into compare.json.
Rule added to wiki/criteria.md item 9-10, method step 9b, AGENTS.md convert workflow; facts 22-28; lessons 25-30.

## [2026-11-21] setup | Knowledge graph of RTCIS / PrIME 2014 / PrIME 2022 in Cosmos DB (Gremlin)
New kit <home>\Desktop\M&M\_kg_cosmos (public copy: github.com/feng-xi-2/Data-and-AI, folder 'RTCIS-PrIME Knowledge Graph', PR #3, issue #2).
Live catalogs of 5 replicas (1,680 tables / 28,585 columns); mappings harvested from this wiki + complete reference + remediation guide +
verified-mappings + data model, validated V1 exists / V2 type / V3 live value lookup: 9,033 pass, 54 rejected (doc errors such as invact->invmov
columns, ord.ship_id, car). Loaded as database whs_kg / graph rtcis_prime (30,806 vertices / 44,840 edges). Benchmark with engine gold
(SHOWPLAN + describe_first_result_set): PrIME entity F1 1.00/0.98, Text2KGBench F1 0.89, conversion lookup 37/59. Lessons: data model lists
1,026 PrIME 2022 tables not in the replica; sample-vs-sample value overlap is misleading for keys (use lookup); bare-name mapping rows
must be limited to mapped table pairs.

## [2026-11-21] tool | Knowledge-graph tab, NL ask / convert / batch, SDC-PMC layer, cloud benchmark
Third tab 'RTCIS <-> PrIME 2014 <-> 2022' in config-drift-governance/UIUX/knowledge-graph.html (same force graph) backed by
_kg_cosmos/tools/kg_api.py (Cosmos graph + GenAI GPT-5.2 + replicas). SDC module / PMC layer validated on live catalogs: 430 links pass,
6 rejected (SDC 03 listed invdtl/invlod/invsub/hold as RTCIS tables; PrIME 'car' does not exist). 91 JOINS_WITH edges mined from the ON
clauses of the validated queries. Cloud benchmark (3 rounds): NL 9/11 -> 11/11 validated, execution accuracy 3/5 strict (4/5 rolled up);
conversions 6/8 -> 8/8 identical contract. Lessons: 'it ran' is not 'it is right' - a Xiqing answer joined invlod.stoloc to
pck_area.pck_arecod and returned 0 rows (reference: 79 areas); giving the model validated join paths fixed it. Xiqing hosts CN66 / CN74 /
CN88 (default CN74). pyodbc cannot fetch datetimeoffset (AT TIME ZONE) without an output converter. sqlglot reads 'SELECT 1 DELETE FROM t'
as an alias - the guard must reject unquoted statement keywords. Public repo: PR #3 updated, Config Drift code PR #5 / issue #4.
