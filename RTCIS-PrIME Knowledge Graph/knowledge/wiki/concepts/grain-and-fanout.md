---
title: Grain and fan-out
type: concept
status: verified
sources: [raw/memories/euskirchen_rtcis_prime2022.md, raw/memories/rtcis_prime_conversion_kit.md]
evidence: [results/compare.json, results/expert_rules.json]
updated: 2026-10-20
---
# Grain and fan-out

PrIME is more normalised than RTCIS; naive joins change the row grain. Rules (`FAN`, `WHT`, `OBS8` in `audit_expert_rules.py`):

| Source of fan-out | Fix |
|---|---|
| `prtmst` dual rows (site + `----` template) | `AND p.WH_ID_TMPL = @wh_id` |
| `prtftp_dtl` (several footprint levels) | `OUTER APPLY (SELECT TOP 1 … ORDER BY …)` |
| `prtdsc` (locale rows) | `OUTER APPLY TOP 1` with locale preference chain |
| pick work (several per pallet) | `OUTER APPLY TOP 1 … ORDER BY` latest |
| `invdtl` split rows (51 DE08 keys) | aggregate per LODNUM+PRTNUM+PRT_CLIENT_ID+LOTNUM first, then join |

OBS8 aggregation pattern (R01/R07/R16):
```sql
JOIN (SELECT s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM,
             MAX(i.FTPCOD) FTPCOD, MAX(i.INVSTS) INVSTS, MIN(i.FIFDTE) FIFDTE,
             MAX(i.SUP_LOTNUM) SUP_LOTNUM, SUM(i.UNTQTY) UNTQTY
      FROM dbo.invsub s JOIN dbo.invdtl i ON i.SUBNUM = s.SUBNUM
      GROUP BY s.LODNUM, i.PRTNUM, i.PRT_CLIENT_ID, i.LOTNUM) d ON d.LODNUM = l.LODNUM
```
Keep DISTINCT only where the original had it. `MAX(FTPCOD)` is arbitrary for mixed footprints — note it.
Check grain with `COUNT(*), COUNT(DISTINCT key)` before and after every new join.
