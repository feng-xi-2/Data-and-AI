"""Snapshot the engine-inferred return type of every measure into config/measure_types.csv.

    py tools/sync_measure_types.py [<PBIDesktop PID>]     (default: the first open Power BI Desktop)

model_gate.py uses the snapshot to (a) give visible numeric measures without a formatString a standard format
and (b) exempt text / boolean measures from rule R1. Re-run after adding measures (they show up as R1 until then).
DataType codes (INFO.MEASURES): 2 text, 6 whole number, 8 decimal, 9 date/time, 10 currency, 11 true/false.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "config" / "measure_types.csv"
if len(sys.argv) > 1:
    pid = int(sys.argv[1])
else:
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "(Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1).Id"],
                       capture_output=True, text=True)
    if not p.stdout.strip():
        raise SystemExit("!! no Power BI Desktop is open - open dist/ALL_SITES/WH Hypercare KPI.pbip first")
    pid = int(p.stdout.strip())
p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(pid),
                    "-Dax", 'EVALUATE SELECTCOLUMNS(INFO.MEASURES(), "N", [Name], "DT", [DataType])', "-TimeoutSec", "120"],
                   capture_output=True, text=True, timeout=300)
rows = json.loads(p.stdout.strip() or "{}")
if not isinstance(rows, list) or not rows:
    raise SystemExit(f"!! INFO.MEASURES failed: {p.stdout[:300]} {p.stderr[:300]}")
old = {}
if OUT.exists():
    old = {r["Measure"]: r["DataType"] for r in csv.DictReader(open(OUT, encoding="utf-8-sig"))}
new = {r["[N]"]: str(r["[DT]"]) for r in rows}
merged = {**old, **new}
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Measure", "DataType"])
    for k in sorted(merged):
        w.writerow([k, merged[k]])
changed = sum(1 for k in new if old.get(k) != new[k])
print(f"{len(new)} measures read from PID {pid}; {changed} new/changed; {len(merged)} in {OUT.relative_to(HERE.parent)}")
