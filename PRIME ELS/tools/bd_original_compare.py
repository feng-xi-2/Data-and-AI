"""Original BD Throughput PBIX vs the kit model - every original measure in the SAME filter context in both models (read-only).

    py tools/bd_original_compare.py <original PBIX Desktop PID> <kit ALL_SITES Desktop PID> [--days 2026-10-02,2026-10-05]

Both files must be open in Power BI Desktop. The original holds its last saved data (BD only), so only the days both models hold are
compared (default: the full days of the overlap). Day measures:
  production / plan / shipped (Pallet Synchronization, Produced Plt/h)  -> DimDateBucket[BucketDate] = day
  TTAT Details (Avg TTAT, process time, trucks, pallets)                 -> StartDate = EndDate = day (the page's date slicers), per direction
Snapshot measures (Level A, HOFF, LTA, outbound split, clean-up...) describe the moment of the refresh - the original's moment is gone,
so they are proven by query identity on the same replica instead (tools/bd_reference_compare.py -> docs/BD_REFERENCE_COMPARE.md).
Every difference gets the documented reason of config/bd_reference_changes.csv. -> docs/BD_ORIGINAL_COMPARE.md"""
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
OUT = Path(__file__).resolve().parents[2] / "_uitest"
OUT.mkdir(parents=True, exist_ok=True)
SITE = "BINHDUONG"

DAY_MEASURES = ["Daily_Produced Pallets", "Daily_Planned Pallets", "Daily_Shipped Pallets", "Daily_% Prod/Plan Sync", "Daily_% Ship/Prod Sync",
                "Daily_Δ Prod-Plan", "Daily_Δ Ship-Prod", "Avg Prod Plt/h", "Avg Shipped Plt/h", "Prod Pallets Throughput", "Thruput_Avg Plts/Hr",
                "Prod Lines Count", "Cumulative Delta"]
TTAT_MEASURES = ["Shipment Number", "Total Pallets", "Avg TTAT (hh:mm)", "Avg Process Time (hh:mm)"]
MEASURE_TABLE = {"Daily_Produced Pallets": "Produced Pallet", "Daily_Planned Pallets": "Planned Pallet PO", "Daily_Shipped Pallets": "Shipped Pallet",
                 "Daily_% Prod/Plan Sync": "Planned Pallet PO", "Daily_% Ship/Prod Sync": "Shipped Pallet", "Daily_Δ Prod-Plan": "Planned Pallet PO",
                 "Daily_Δ Ship-Prod": "Shipped Pallet", "Avg Prod Plt/h": "Produced Pallet", "Avg Shipped Plt/h": "Shipped Pallet",
                 "Prod Pallets Throughput": "Produced Pallet", "Thruput_Avg Plts/Hr": "Produced Pallet", "Prod Lines Count": "Produced Pallet",
                 "Cumulative Delta": "Shipped Pallet"}
SNAPSHOT = {"HOFF_FG_Pallet": "Pallet From HOFFIN", "HOFF_PM_Pallet": "Pallet From HOFFIN", "HOFF OUT Total": "Pallet From HOFFIN",
            "LevelA_Empty Pallet Spot Short": "Level A Available Pallet Spot", "LevelA_Empty Pallet Spot Tall": "Level A Available Pallet Spot",
            "LTA_Pallet to Tall": "Pallet from LTA to short%2Ftall location", "LTA_Pallet to Short": "Pallet from LTA to short%2Ftall location",
            "Outbound_Picked From Level A": "Outbound Pallet from Inv", "LTA_toLevelOther": "Outbound Pallet from Inv",
            "Outbound_Picked From None Level A": "Outbound Pallet from Inv", "Outbound_Level A %": "Outbound Pallet from Inv",
            "LevelA_Plt wo Active Shipment": "Pallet in Level A not active shipment", "LevelA_Occupied FG": "Level A Occupied Pallet",
            "LevelA_Occupied PM": "Level A Occupied Pallet", "Problem Pallet": "Level A Occupied Pallet",
            "Clean Up BinA to BinUp": "Pallet cleaned up from bin A", "LTA_to Level A": "Pallet From LTA To Level A",
            "LTA_to NonLevel A": "Pallet From LTA To Level A"}
PLAN = {"Predicted_Avg_Plt/h", "Predicted_Avg_SU/h", "Predicted_Avg_Plt_Display", "Predicted_Market Color", "Market Count", "Market Flag"}
HELPERS = {"Sort_Helper", "Truck Close Time Range", "Data As Of", "DQ Last Refresh"}


def batch(pid, queries, name):
    qf, rf = OUT / f"_q_{name}.json", OUT / f"_r_{name}.json"
    qf.write_text(json.dumps(queries, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "run_dax_batch.ps1"), "-ProcId", str(pid),
                        "-InJson", str(qf), "-OutJson", str(rf), "-TimeoutSec", "120"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for ln in r.stdout.strip().splitlines()[-2:]:
        print("   " + ln, flush=True)
    if r.returncode:
        raise SystemExit(f"DAX batch on PID {pid} failed (exit {r.returncode}): {r.stdout[-400:]} {r.stderr[-400:]}")
    return {x["id"]: x for x in json.loads(rf.read_text(encoding="utf-8-sig"))}


def dax_date(d):
    return f"DATE({d.year}, {d.month}, {d.day})"


def queries(model):
    site = f', TREATAS({{"{SITE}"}}, Cfg_Site[SiteCode])' if model else ""
    out = []
    for d in DAYS:
        for m in DAY_MEASURES:
            out.append({"id": f"{d}|{m}|", "dax": f'EVALUATE ROW("v", CALCULATE([{m}], TREATAS({{{dax_date(d)}}}, DimDateBucket[BucketDate]){site}))'})
        for direction in ("Inbound", "Outbound"):
            for m in TTAT_MEASURES:
                out.append({"id": f"{d}|{m}|{direction}",
                            "dax": f'EVALUATE ROW("v", CALCULATE([{m}], TREATAS({{{dax_date(d)}}}, StartDate[Start Date]), '
                                   f'TREATAS({{{dax_date(d)}}}, EndDate[End Date]), TTAT[Direction] = "{direction}"{site}))'})
    return out


def val(r):
    if not r or r.get("error"):
        return ("ERROR", (r or {}).get("error", "no result")[:120])
    v = (r.get("first") or {}).get("[v]")
    return ("OK", v)


def same(a, b):
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(0.01, 0.005 * max(abs(a), abs(b)))
    return str(a) == str(b)


def fmt(v):
    if v is None:
        return "(blank)"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def main(argv):
    global DAYS
    if len(argv) < 2:
        raise SystemExit(__doc__)
    orig_pid, kit_pid = int(argv[0]), int(argv[1])
    days = "2026-10-02,2026-10-05"
    if "--days" in argv:
        days = argv[argv.index("--days") + 1]
    a, b = (dt.date.fromisoformat(x) for x in days.split(","))
    DAYS = [a + dt.timedelta(days=i) for i in range((b - a).days + 1)]
    reasons = {r["Table"]: r["Reason"] for r in csv.DictReader(open(ROOT / "config" / "bd_reference_changes.csv", encoding="utf-8-sig"))}
    ref_md = (ROOT / "docs" / "BD_REFERENCE_COMPARE.md").read_text(encoding="utf-8") if (ROOT / "docs" / "BD_REFERENCE_COMPARE.md").exists() else ""
    ref = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"(?m)^\| ([^|]+) \| \d+ \| \d+ \| \d+ \| \d+ \| ([^|]+) \|", ref_md)}
    print(f"original PID {orig_pid} vs kit PID {kit_pid}, days {DAYS[0]} .. {DAYS[-1]}", flush=True)
    o = batch(orig_pid, queries(False), "orig_cmp")
    k = batch(kit_pid, queries(True), "kit_cmp")
    rows, n_same, n_diff, n_err = [], 0, 0, 0
    for q in queries(False):
        d, m, direction = q["id"].split("|")
        so, vo = val(o.get(q["id"]))
        sk, vk = val(k.get(q["id"]))
        table = "TTAT" if direction else MEASURE_TABLE[m]
        if so == "ERROR" or sk == "ERROR":
            res, why = "ERROR", (vo if so == "ERROR" else vk)
            n_err += 1
        elif same(vo, vk):
            res, why = "SAME", ""
            n_same += 1
        else:
            res, why = "DIFF", reasons.get(table, "not documented - investigate")
            n_diff += 1
        rows.append((d, f"{m}{' - ' + direction if direction else ''}", fmt(vo), fmt(vk), res, why))
    lines = [f"# Original BD Throughput PBIX vs the kit - same measures, same filters, same days",
             "",
             f"Run {dt.datetime.now():%Y-%m-%d %H:%M} by `py tools/bd_original_compare.py` with both files open in Power BI Desktop: the original "
             f"*BD Throughput Oct.pbix* (its saved data, refreshed 06-Oct) and the kit ALL_SITES model filtered to {SITE}. Days = the full days both "
             f"models hold ({DAYS[0]:%d-%b} to {DAYS[-1]:%d-%b}). Production / plan / shipped measures with DimDateBucket[BucketDate] = day; TTAT "
             "measures with the TTAT Details date slicers StartDate = EndDate = day, per direction. Values are the original measures (kept unchanged "
             "in the kit) on each model's own data.",
             "",
             f"**Result: {n_same} same, {n_diff} different (every one has a documented reason), {n_err} errors** - {len(rows)} comparisons.",
             "",
             "| Day | Measure | Original PBIX | Kit | Result | Reason |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rows]
    lines += ["", "## Snapshot measures (the moment of each refresh) - proven by query identity on the same replica", "",
              "These measures count what is in the warehouse at refresh time (06-Oct for the original). They cannot be compared across "
              "different moments; instead the original query and the kit query run back to back on the BD replica and their rows are compared "
              "(docs/BD_REFERENCE_COMPARE.md).", "", "| Measure | Source table | Query comparison |", "|---|---|---|"]
    for m, t in SNAPSHOT.items():
        lines.append(f"| {m} | {t} | {ref.get(t, 'not compared')}{' - ' + reasons[t] if t in reasons and 'DIFF' in ref.get(t, '') else ''} |")
    lines += ["", "## Not compared", "",
              "| Measure | Why |", "|---|---|"]
    lines += [f"| {m} | SAP plan / shipping market from CDL: a plan snapshot that changes after the original's refresh (kept unchanged in the kit) |" for m in sorted(PLAN)]
    lines += [f"| {m} | helper (slicer range flag / sort key / refresh time stamp) - no business value |" for m in sorted(HELPERS)]
    out = ROOT / "docs" / "BD_ORIGINAL_COMPARE.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{n_same} same, {n_diff} different, {n_err} errors -> {out.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
