"""Data-gap report from the OPEN model: per site, today vs the previous shift day (trucks, TTAT, pallet moves, PrIME and SAP
production), the live waiting snapshot and the data-driven explanations - plus the rule 'every site shows truck / TTAT / pallet
movement / production activity on the previous day'. Re-runnable for any site set (no hard-coded site facts).

    py tools/data_gaps.py [--pid <PBIDesktop pid>]        -> docs/DATA_GAPS.md, exit 1 when a site has no previous-day activity

Uses tools/run_dax_batch.ps1 (heartbeat every 30 s, never silent).
"""
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "docs" / "DATA_GAPS.md"
TMP = ROOT.parent / "_uitest"
sys.path.insert(0, str(HERE))
from pbi_common import read_csv, sap_included  # noqa: E402

_SAP = sap_included()   # Include_SAP_CDL = 0: the SAP measures are not in the model
DAY_MEASURES = [("in_trucks", "[Inbound Trucks]"), ("out_trucks", "[Outbound Trucks]"), ("ttat_in", "[KPI TTAT In]"), ("ttat_out", "[KPI TTAT Out]"),
                ("moves", "[User Pallets Moved]"), ("users", "[KPI Active Users]"), ("wms_prod", "[Prod Pallets Day]")] + \
               ([("sap_prod", "[SAP Pallets Day]")] if _SAP else [])
NOW_MEASURES = [("waiting", "[Flow Items Waiting]"), ("warn", "[Flow Items Warning]"), ("crit", "[Flow Items Critical]"), ("trucks_on_site", "[Trucks On Site]"),
                ("pallets_flow", "[Pallets In Flow Now]"), ("ship_open", "[Shipments Open]"), ("orders_used", "IF([Orders Flow Used], 1, 0)"),
                ("first_txn", "[Replica First Txn]"), ("last_txn", "[Data Last Txn]"), ("lag_min", "[KPI Data Lag Min]"),
                ("verdict", "[Flow Verdict]"), ("last_text", "[Last Activity Text]"),
                ("snapshot", "[Flow Snapshot]"), ("today", "[Site Shift Today]")] + \
               ([("prod_text", "[Production Explanation]"), ("sap_window", "[SAP Pallets Window]"), ("wms_window", "[WMS Pallets Window]")] if _SAP else [])


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def desktop_pid():
    if "--pid" in sys.argv:
        return int(sys.argv[sys.argv.index("--pid") + 1])
    ps = [p for p in psutil.process_iter(["name", "pid"]) if (p.info["name"] or "").lower() == "pbidesktop.exe"]
    if not ps:
        raise SystemExit("FAILED: no Power BI Desktop running - open dist/ALL_SITES (py tools/open_model.py ...) first")
    return ps[0].info["pid"]


def dax_for(site, offset):
    """offset None = snapshot measures; 0 = today; -1 = previous shift day (site-local shift day)."""
    if offset is None:
        cols = ", ".join(f'"{k}", CALCULATE({m}, Cfg_Site[SiteCode] = s)' for k, m in NOW_MEASURES)
        return f'EVALUATE\nVAR s = "{site}"\nRETURN ROW({cols})'
    cols = ", ".join(f'"{k}", CALCULATE({m}, Cfg_Site[SiteCode] = s, TREATAS({{t + ({offset})}}, DimDate[Date]))' for k, m in DAY_MEASURES)
    return f'EVALUATE\nVAR s = "{site}"\nVAR t = CALCULATE([Site Shift Today], Cfg_Site[SiteCode] = s)\nRETURN ROW({cols})'


def run_batch(pid, qs):
    TMP.mkdir(exist_ok=True)
    qin, qout = TMP / "_gaps_in.json", TMP / "_gaps_out.json"
    qin.write_text(json.dumps([{"id": i, "dax": d} for i, d in qs]), encoding="utf-8")
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "run_dax_batch.ps1"), "-ProcId", str(pid),
           "-InJson", str(qin), "-OutJson", str(qout), "-TimeoutSec", "120"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        print("   " + line.rstrip(), flush=True)
    p.wait()
    res = json.loads(qout.read_text(encoding="utf-8-sig"))
    res = res if isinstance(res, list) else [res]
    return {r["id"]: r for r in res}


def val(r, k):
    f = (r or {}).get("first") or {}
    return f.get(f"[{k}]")


def num(x, fmt="{:,.0f}"):
    if x in (None, ""):
        return "-"
    try:
        return fmt.format(float(x))
    except (TypeError, ValueError):
        return str(x)


def main():
    pid = desktop_pid()
    sites = [r for r in read_csv("site_config.csv")]
    qs = []
    for s in sites:
        c = s["SiteCode"]
        qs += [(f"{c}|now", dax_for(c, None)), (f"{c}|0", dax_for(c, 0)), (f"{c}|-1", dax_for(c, -1))]
    say(f"{len(qs)} DAX queries on Desktop {pid}")
    res = run_batch(pid, qs)
    errs = [f"{k}: {r.get('error')}" for k, r in res.items() if r.get("error")]
    md = ["# Data gaps and previous-day activity per site", "",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py tools/data_gaps.py` from the open ALL_SITES model (all numbers are model measures; "
          "report day = site-local shift day). Re-run after every refresh; exit code 1 = a site without previous-day activity.", ""]
    if errs:
        md += ["## Query errors (fix before trusting this report)", ""] + [f"- {e}" for e in errs] + [""]
    md += ["## 1. Today vs previous shift day", "",
           "| Site | Day | Inbound trucks | Outbound trucks | TTAT in (min) | TTAT out (min) | Pallets moved | Active users | PrIME produced plt |"
           + (" SAP FG plt |" if _SAP else ""),
           "|---" * (len(DAY_MEASURES) + 2) + "|"]
    fails = []
    for s in sites:
        c = s["SiteCode"]
        now = res.get(f"{c}|now")
        today = val(now, "today")
        for off, lbl in ((0, "today (so far)"), (-1, "previous day")):
            r = res.get(f"{c}|{off}")
            md.append(f"| {c} | {lbl} | " + " | ".join(num(val(r, k), "{:,.0f}" if k not in ("ttat_in", "ttat_out") else "{:,.0f}") for k, _ in DAY_MEASURES) + " |")
        prev = res.get(f"{c}|-1")
        act = {k: float(val(prev, k) or 0) for k in ("in_trucks", "out_trucks", "moves", "wms_prod") + (("sap_prod",) if _SAP else ())}
        if not any(v > 0 for v in act.values()):
            fails.append(c)
    md += ["", "## 2. Previous-day activity rule", "",
           "Rule: every site must show trucks (TTAT), pallet movement or production on the previous shift day when today has none yet. "
           "The cockpit tiles show 'Previous day' and 'Prior-days average' next to today; every diagnosis page shows 'prev day'.", ""]
    for s in sites:
        c = s["SiteCode"]
        prev = res.get(f"{c}|-1")
        parts = [f"{lbl} {num(val(prev, k))}" for k, lbl in (("in_trucks", "inbound trucks"), ("out_trucks", "outbound trucks"),
                                                             ("moves", "pallets moved"), ("wms_prod", "PrIME production pallets"),
                                                             *((("sap_prod", "SAP FG pallets"),) if _SAP else ()))]
        md.append(f"- **{c}** {'PASS' if c not in fails else 'FAIL'}: " + ", ".join(parts) + ".")
    md += [] if not _SAP else ["", "## 3. Production - PrIME vs SAP (why production is empty or low)", "",
           "| Site | SAP plant | PrIME production tracked | SAP FG pallets (window) | PrIME pallets (window) | Explanation (model, data-driven) |", "|---|---|---|---|---|---|"]
    for s in (sites if _SAP else []):
        c = s["SiteCode"]
        now = res.get(f"{c}|now")
        md.append(f"| {c} | {s.get('SAP_Plant') or '-'} | {'yes' if s.get('Has_Production') == '1' else 'no'} | {num(val(now, 'sap_window'))} | "
                  f"{num(val(now, 'wms_window'))} | {(val(now, 'prod_text') or '-').replace('|', '/')} |")
    md += ["", "## 4. Live process snapshot - where is it stuck now", "",
           "| Site | Snapshot (site time) | Waiting | Past warning | Past critical | Trucks on site | Pallets in flow | Open shipments | Orders flow in WMS | Verdict |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for s in sites:
        c = s["SiteCode"]
        now = res.get(f"{c}|now")
        md.append(f"| {c} | {str(val(now, 'snapshot') or '-')[:16]} | {num(val(now, 'waiting'))} | {num(val(now, 'warn'))} | {num(val(now, 'crit'))} | "
                  f"{num(val(now, 'trucks_on_site'))} | {num(val(now, 'pallets_flow'))} | {num(val(now, 'ship_open'))} | "
                  f"{'yes' if str(val(now, 'orders_used')) == '1' else 'no (shipments stay Ready)'} | {(val(now, 'verdict') or '-').replace('|', '/')} |")
    md += ["", "## 5. Replica coverage", "", "| Site | Replica keeps data from | Newest transaction | Replica lag at refresh (min) | Last activity |", "|---|---|---|---|---|"]
    for s in sites:
        c = s["SiteCode"]
        now = res.get(f"{c}|now")
        md.append(f"| {c} | {str(val(now, 'first_txn') or '-')[:16]} | {str(val(now, 'last_txn') or '-')[:16]} | {num(val(now, 'lag_min'))} | "
                  f"{(val(now, 'last_text') or '-').replace('|', '/')} |")
    md += ["", "## 6. Site notes (config/site_config.csv)", ""] + [f"- **{s['SiteCode']}**: {s.get('Notes') or '-'}" for s in sites] + [""]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    say(f"DONE -> {OUT.relative_to(ROOT)}; previous-day rule: {len(sites) - len(fails)}/{len(sites)} PASS" + (f", FAIL {fails}" if fails else ""))
    if errs:
        say(f"!! {len(errs)} query error(s) - see the report")
    sys.exit(1 if fails or errs else 0)


if __name__ == "__main__":
    main()
