"""xlsx_to_deviations_csv — normalise the multi-site Power BI export into the deviation CSV schema.

The full Config Drift export (Config report/data.xlsx, sheet "Export") holds ~97k deviations
across ~134 audited sites, but with slightly different column names than the single-site
AHM CSV (20260817_0038_ahm_output.csv). This script maps the multi-site sheet onto the SAME
column schema that explain_ij.py / export_drift_ui.py consume, so the exact same explain →
rollup → UIUX pipeline produces a multi-site drift-actions.js (one entry per Audited Site).

    data.xlsx "Export"                    ->  deviation CSV schema (AHM-compatible)
    ----------------------------------------------------------------------------------
    Audited Site                          ->  Audited Instance (A)
    (constant "mnt-wms")                  ->  Reference Instance (R)
    Configuration Section                 ->  Configuration Section
    Configuration Element                 ->  Configuration Element
    Element Attribute ID                  ->  Configuration Element Attribute ID
    Element Attribute Name (GUI)          ->  Configuration Element Attribute Name (GUI)
    Audited Value                         ->  A value
    Reference Value                       ->  R value
    Deviation Type                        ->  Deviation Type
    Deviation Severity                    ->  Deviation Severity
    Deviation Details + Deviation Notes   ->  Deviation Comments   (record body / mod blob)
    Rationale for Accepted                ->  Rationale            (holds the CFGxxxx code)
    First seen on / Last seen on          ->  First seen on / Last seen on

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then raise).
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import sys

import openpyxl

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
DEFAULT_IN = os.path.join(ONEDRIVE, "Config report", "data.xlsx")
DEFAULT_OUT = os.path.join(ONEDRIVE, "Config report", "all_sites_deviations.csv")
DEFAULT_SHEET = "Export"

# target schema — matches the AHM single-site CSV the pipeline already understands
OUT_FIELDS = [
    "Audited Instance (A)", "Reference Instance (R)", "Comparison Type",
    "Configuration Section", "Configuration Level", "Configuration Element",
    "Configuration Element Attribute ID", "Configuration Element Attribute Name (GUI)",
    "A value", "R value", "Deviation Type", "Deviation Severity", "Deviation Comments",
    "First seen on", "Last seen on", "Deviation Status", "Rationale", "Product Version",
]


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _s(v) -> str:
    """Cell -> clean string; None/'None' become empty; datetimes become ISO date."""
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    return "" if s.lower() == "none" else s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN, help="multi-site export xlsx")
    ap.add_argument("--out", dest="out", default=DEFAULT_OUT, help="output deviation CSV")
    ap.add_argument("--sheet", dest="sheet", default=DEFAULT_SHEET, help="worksheet name")
    ap.add_argument("--ref", dest="ref", default="mnt-wms", help="reference instance label")
    args = ap.parse_args()

    if not os.path.exists(args.inp):
        log(f"ERROR input not found: {args.inp}")
        raise SystemExit(2)

    log(f"reading {args.inp} · sheet {args.sheet}")
    try:
        wb = openpyxl.load_workbook(args.inp, read_only=True, data_only=True)
        if args.sheet not in wb.sheetnames:
            log(f"ERROR sheet '{args.sheet}' not found. sheets={wb.sheetnames}")
            raise SystemExit(2)
        ws = wb[args.sheet]
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(it)]
    except SystemExit:
        raise
    except Exception as e:
        log(f"ERROR failed to open workbook: {type(e).__name__}: {e}")
        raise

    idx = {h: i for i, h in enumerate(header)}
    required = ["Audited Site", "Configuration Section", "Deviation Severity",
                "Configuration Element", "Deviation Type"]
    missing = [c for c in required if c not in idx]
    if missing:
        log(f"ERROR missing expected columns: {missing} · found={header}")
        raise SystemExit(2)

    def cell(row, name):
        i = idx.get(name)
        return row[i] if (i is not None and i < len(row)) else None

    n = 0
    sites: set[str] = set()
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
            w.writeheader()
            for row in it:
                if row is None:
                    continue
                site = _s(cell(row, "Audited Site"))
                if not site:
                    continue
                details = _s(cell(row, "Deviation Details"))
                notes = _s(cell(row, "Deviation Notes"))
                comments = " ".join(x for x in (details, notes) if x)
                w.writerow({
                    "Audited Instance (A)": site,
                    "Reference Instance (R)": args.ref,
                    "Comparison Type": "",
                    "Configuration Section": _s(cell(row, "Configuration Section")),
                    "Configuration Level": "",
                    "Configuration Element": _s(cell(row, "Configuration Element")),
                    "Configuration Element Attribute ID": _s(cell(row, "Element Attribute ID")),
                    "Configuration Element Attribute Name (GUI)": _s(cell(row, "Element Attribute Name (GUI)")),
                    "A value": _s(cell(row, "Audited Value")),
                    "R value": _s(cell(row, "Reference Value")),
                    "Deviation Type": _s(cell(row, "Deviation Type")),
                    "Deviation Severity": _s(cell(row, "Deviation Severity")),
                    "Deviation Comments": comments,
                    "First seen on": _s(cell(row, "First seen on")),
                    "Last seen on": _s(cell(row, "Last seen on")),
                    "Deviation Status": "",
                    "Rationale": _s(cell(row, "Rationale for Accepted")),
                    "Product Version": "",
                })
                sites.add(site)
                n += 1
                if n % 20000 == 0:
                    log(f"  wrote {n} rows…")
        wb.close()
    except Exception as e:
        log(f"ERROR failed while writing {args.out}: {type(e).__name__}: {e}")
        raise

    log(f"DONE wrote {args.out} · {n} rows · {len(sites)} sites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
