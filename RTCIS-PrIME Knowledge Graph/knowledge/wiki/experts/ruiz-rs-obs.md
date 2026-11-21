---
title: Site expert RUIZ.RS (Gino) — OBS1–8
type: expert
status: expert
sources: [raw/experts/_EXPERT_RUIZ_RS_0916_AS_SUPPLIED.sql, raw/experts/_EXPERT_RUIZ_RS_0917_ROUND2_AS_SUPPLIED.sql, raw/experts/00_EXPERT_RUIZ_RS_ORIGINAL_vs_SHIPPED.sql, raw/memories/euskirchen_rtcis_prime2022.md]
evidence: [results/expert_rules.json]
updated: 2026-10-20
---
# RUIZ.RS (Gino) — expert rules

Reviews of the Euskirchen label set on 16 and 17 Sep 2026 (`raw/experts/`). Every rule is enforced by
`tools/audit_expert_rules.py` → `results/expert_rules.json` and shown in the HTML report.

| Rule | Ruling | Apply as |
|---|---|---|
| **OBS1** GTIN | GTIN is a row in `alt_prtmst`, chosen by the receiving UOM (`prtftp_dtl RCV_FLG=1`) — configuration, not a CS>IT>SW preference ranking. Also: filter to setup-relevant shipments (`LIST_ID NOT NULL`) = translation of RTCIS `cpord > 0` | [prime-anti-patterns](../learnings/prime-anti-patterns.md) |
| **OBS2** shipment id | RTCIS `shipid` = PrIME **carrier move** `stop.CAR_MOVE_ID` (via `shipment.STOP_ID`), not `shipment.SHIP_ID` (WMD1: 952 ships → 792 moves) | [mappings](../ground-truth/mappings.md) |
| **OBS3** setup | RTCIS setup = PrIME **list pick** `pckwrk_hdr.LIST_ID`; a setup is a pallet; `DENSE_RANK() OVER (PARTITION BY ORDNUM ORDER BY LIST_ID)`, zero-padded like RTCIS (`001/29`) | same |
| **OBS4** inputs | Never invent a runtime input the original did not have | R08–R12 literal windows 3 d / 120 min / 3 d / 33 d / 90 d |
| **OBS5** fields | Keep every original output field, same order (NULL with a reason if no source) | `columns_identical` |
| **OBS6** case qty | `UNTQTY / UNTCAS` with zero fallback, cast to decimal | see deviation below |
| **OBS7** filters | Keep the original's picked-inventory filter and HAVING clause | |
| **OBS8** grain | Keep DISTINCT at the RTCIS grain; PrIME can hold several `invdtl` rows for one RTCIS row | R01/R07/R16 sum per key; R10/R11 no DISTINCT |
| pckwrk_view | Cannot plan at DE08 → `pckwrk_hdr` + `pckwrk_dtl` join; `inventory_view` is fine | rule `VIEW` |

House rules added by the audit tool: **WHT** (`prtmst` with `WH_ID_TMPL` guard), **FAN** (1:n tables via
`OUTER APPLY TOP 1`), **LOC** (`prtdsc` composite key + locale chain, no pinned locale), **VIEW** (no `pckwrk_view`).

## Applied to the RPM set (2026-10-20) `[DB]`
- OBS4: invented `@Days`/`@Minutes` removed; original literal windows restored (R08–R12).
- OBS8: 51 DE08 keys split over 2 `invdtl` rows (RTCIS 0) → aggregate subquery per LODNUM+PRTNUM+PRT_CLIENT_ID+LOTNUM
  in R01/R07/R16; R07 quantity agreement 8,687 → 8,732 of 8,797. DISTINCT removed in R10/R11 (original had none).
- OBS6: decimal division incl. cases-per-layer (R17). WHT guard (R13). LOC `@locale` chain (R06).
- OBS1–3: not applicable to the RPM queries (no GTIN / shipid / setup). Result: **0 FAIL**.

## Declared deviation
**OBS6 quantity** uses the receiving-UOM factor (`UNTQTY / RCV_FLG=1 UNTQTY`) instead of `UNTCAS`, because it reproduces
RTCIS CASQTY on **94% vs 85%** of the same pallets. To revert to Gino's form replace the receiving `UNTQTY` with `d.UNTCAS`.
See [receiving-uom](../concepts/receiving-uom.md).

## Lesson about experts
The setup gap (shipped as constant `'0/0'`) was caught by the site expert, not by tooling — `'0/0'` is also genuine
RTCIS output, so the placeholder was undetectable. Read the platform's own vocabulary (PRFC3957: "non List Pick Works")
and never emit plausible placeholders. [verification-discipline](../learnings/verification-discipline.md).
