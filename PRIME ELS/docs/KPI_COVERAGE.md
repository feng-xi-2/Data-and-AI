# KPI coverage - original BD Throughput PBIX + Macro BD Report (Excel) vs the kit

Checked 31-Oct-2026. Every item of the two originals is mapped to where it lives in the kit: **Covered** (same logic), **Changed**
(same question, better definition - why), **Added** (missing before this check, now in the kit), **N/A** (spreadsheet plumbing with no
meaning in Power BI). Accuracy proof: [BD_ORIGINAL_COMPARE.md](BD_ORIGINAL_COMPARE.md) (PBIX), section 4 below (Excel).

## 1. BD Throughput PBIX - 45 measures, 11 pages

* **All 45 original measures are in the model unchanged** (table `_DaxMeasure`), same names, so every original visual works.
* Original pages kept: Landing -> **Home**, Activity Tracking, Pallet Synchronization, Produced Plt/h, TTAT Details, Inv KPIs, Predicted Plt/h,
  Short PO; *Page 1 / Page 2 / Duplicate of Inv Status* were working copies of the RPM readiness and inventory views -> **RPM Material Readiness**
  and **Inv KPIs** (+ the new all-site **Inventory** page).
* Accuracy on the same days (02-05 Oct): produced / planned / shipped pallets, sync %, throughput, line count **identical**; TTAT: every truck of
  the original is in the kit with identical pallets and TTAT, the kit adds the trucks the original query dropped (no TRKNUM, split visits).

## 2. Macro BD Report (Excel) - sheet by sheet

| Excel sheet / item | Kit | Status |
|---|---|---|
| CONFIG - 20 thresholds (Cfg_PPH_*, Cfg_TTAT_*, Cfg_Shift1-3, Cfg_Shift_Warn/Crit, Cfg_Ramp_*, Cfg_Trend_Hours, Cfg_Min_Base, Cfg_Lookback, Cfg_Min_Short/Tall, Cfg_Max_UtilA, Cfg_Max_Hoff, Cfg_Max_Queue, Cfg_Max_Imbal, Cfg_GR_Target, Cfg_Store_A_Target, Cfg_Pick_A_Target, Cfg_Split_Tol, Cfg_Max_Idle_A) | Cfg_Threshold (PPH, TTAT_IN/OUT, SHIFT_ATTAIN, RAMP_ATTAIN + RAMP_DAY_PLAN, TREND_HOURS, MIN_BASE, LOOKBACK, MIN_SHORT, MIN_TALL, LVLA_UTIL, HOFF_IN, LTA_QUEUE, IMBALANCE, GR_TIME, STORE_A_SPLIT, PICK_A_SPLIT, IDLE_A) with the same BD values; shift hours in Cfg_Site | Covered - per site, BD values are the default for every site |
| DAILY_REPORT 1. Data trust | Health Banner (Cockpit, Daily & Hourly, Config & Health) | Covered |
| DAILY_REPORT 2. Headline status | Overall Alert State (Cockpit, Alerts) | Covered |
| DAILY_REPORT 3. Production (pallets today, avg plt/h, rate vs plan, lines in alert) | Cockpit tile 1, Daily report table, Line RCA & Shifts strip | Covered |
| DAILY_REPORT 4. Truck turnaround (in TTAT, trucks, GR time, out loading TAT, loads, pallets shipped) | Cockpit tiles 2-3, Trucks & TTAT, TTAT Details, Daily report | Changed: report day = shift day, trucks counted when completed (dispatch / close) |
| DAILY_REPORT 5. Space & flow (put-away today, % to Level A, % picked from A, LTA queue, HOFF IN, idle A, free SHORT / TALL) | Alerts rules 8-15, Inv KPIs, Process Flow | Covered (Level A / HOFF only where the site has them) |
| DAILY_REPORT data currency line | Banner refresh line + Production data lag health check (15) | Covered |
| DAILY_REPORT 6. Active alerts | Cockpit "What to do now" + Alerts control tower | Covered |
| DAILY_REPORT 7. Hour scan, verdict, outlook, fix order | Daily & Hourly (scan, verdict), Cockpit (verdict, production outlook), Alerts detail panel (fix order) | Covered |
| HOURLY_ALERT (hour x takeaway vs 14-day baseline, consecutive decline, status, in / out trucks per hour, verdict per hour) | Daily & Hourly Report (Hour * measures) | Covered (baseline = LOOKBACK days) |
| ALERTS - 17 rules | Cfg_AlertRule rules 1-17 (same order and logic) + 6 new (18-23: free TALL, location utilisation, outbound TTAT, user productivity, data lag, refresh age) | Covered + extended |
| ALERTS - TTAT diagnostic by shift (trucks, avg GR, avg TTAT, waiting vs unloading) | **Line RCA & Shifts** page, "TTAT by shift" table | **Added 31-Oct** (inbound and outbound, last LOOKBACK days) |
| LTA_RCA - per-line root cause and action | **Line RCA & Shifts** page, production lines table (Line Status / Root Cause / Action, rca_rules.csv LINE_RCA) | **Added 31-Oct** (measures existed, no page showed them) |
| LTA_MONITOR - hour x line grid, latest hour, 14-day average | **Line RCA & Shifts** page, line x hour matrix + strip | **Added 31-Oct** |
| FLOW_ANALYTICS - 80/20 rules (production-to-storage, outbound planning, bin-to-bin) | Alerts 13-15, Inv KPIs (Level A pages) | Covered (sites with Level A) |
| FLOW_ANALYTICS - end-to-end flow balance (produced -> waiting at line -> HOFF -> put away -> picked) | Process Flow (stages and items waiting), Process Mining (measured hand-offs) | Changed: measured from the event logs per stage instead of 5 counters |
| RELATIONSHIPS - correlation line output vs storage | Line RCA root cause (constraint checks: free SHORT + LTA queue, Level A utilisation, HOFF backlog) + Process Mining bottleneck | Changed: rule-based cause per line instead of a correlation table |
| VALIDATION - 39 checks | Health checks 1-20 (Config & Health) + the kit's test chain (field audit, visual replay, reconciliation, report intent) | Covered: data checks in the report; sheet-plumbing checks (text dates, sheet ties, query-row counts) are proven by the test tools; **added 31-Oct: 19 outbound truck feed fresh, 20 inbound / outbound feeds on the same day** |
| REFRESH_LOG, INDEX, Report / Updated / data landing sheets | Banner refresh line, Home page index, Data Health table | Covered / N/A |

## 3. Not carried over (on purpose)

| Item | Why |
|---|---|
| Excel "AUTOMATION REALITY CHECK" / manual refresh notes | The kit refreshes itself every 30 min (Desktop) and in the Service |
| Excel hard-coded site values (wh_id VN07, date windows from 2026-07-01, LTA line list) | Replaced by Cfg_Site tokens / Hypercare_Start / Cfg_LineMap - works for every site |

## 4. Excel vs kit on the same data (BD, 29-Oct up to 12:00, Excel saved at 12:00)

| Item | Excel | Kit | Result |
|---|---|---|---|
| Takeaway pallets per hour 00-12 (LTA_DATA vs Produced Pallet) | 434 | 434 | **13 / 13 hours identical** |
| Takeaway lines with output | 11 | 11 (+1 line that started after 12:00) | same lines, kit later hours included |
| Inbound trucks dispatched 28-29 Oct (Query12 vs TTAT) | 13 | 30 | all 13 in both; +17 in the kit = trailers without TRKNUM (same cause as the PBIX comparison) |

## 5. GCFC Timbr warehouse KPIs (semantic layer `dtimbr`, 21-Nov-2026)

Source: `timbr_warehouse_kpis_view.txt` / `_gcfc_measure_defs.txt` (Timbr ontology one_supply_warehousing, GCFC). Copied only where
the replica data of every PRIME ELS site supports it - a KPI that stays empty at the hypercare sites is not added (it would show
empty visuals).

| GCFC / Timbr KPI | Definition | In this report | Status |
|---|---|---|---|
| Outbounds completed (trucks), day / night shift, op day | distinct carrier moves with shift_date = op day | `Outbound Trucks` (closed trucks of the window), Trucks & TTAT; per shift via the Shift slicer and the TTAT-by-shift rows | Covered |
| Pallets out | `SUM(pallets_loaded)` | `Outbound Pallets Shipped`, `Flow Out Pallets Day` | Covered |
| Avg loading duration (h) | loading_start -> loading_end | `KPI Out Load Time` (min), Outbound TTA `Load Time (Minutes)` | Covered (minutes) |
| Avg staging lane dwell (h), all trucks | first allocation -> trailer closed | **`Staging Lane Dwell h`** (first pallet staged in the lane -> trailer closed, outbound trucks of the window), Trucks & TTAT > Dock & staging | **Added** - starts at the first staged pallet: the replica keeps no allocation time per trailer |
| FP / LTFP staging dwell (full vs less-than-full pallet) | same, split by `full_pallet_only_flag` | - | Not added: needs the pick-work full-pallet flag per carrier move (`pckwrk`), not loaded today |
| HZM (horizontal-move lane) outbounds and dwell | `horizontal_move_lane_flag = 'Yes'` | - | N/A: GCFC lane type, no HZM lanes at the PRIME ELS sites |
| Avg AGV allocation -> AGV staged last (h) | AGV timestamps | - | N/A: no AGV at the PRIME ELS sites |
| Staging lanes out of service | count of unusable staging lanes | - | Candidate: `locmst` usable flag of the staging-lane locations (needs the site's staging-lane pattern) |
| Total S2 cuts in cases | order-line cuts with reason S2 (`ordact` HOST_ORDQTY - ORDQTY) | - | Candidate for Orders & Shipments once the sites ship customer orders (Jakarta: 1 order in the rehearsal data) |
| Doors out of service, yard utilisation, rack utilisation per cell (A/B/C) | `doors` / `yard` / `racking` concepts | Location utilisation KPI (storage), Inventory page | Partly covered: doors / yard need the door and yard location patterns (Jakarta LOC_DOOR_PATTERN not profiled yet) |
