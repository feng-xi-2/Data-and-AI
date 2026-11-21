"""validate_against_replica — accuracy check of the PrIME Config Drift export vs live data.

Cross-checks the "Config report/data.xlsx" deviations against the real PrIME 2022 replica
(prodwms.POLDAT_VIEW) on the Azure SQL Managed Instance estate.

SECTION-AWARE KEY MATCHING (the fix)
------------------------------------
The report's "Configuration Element" is a '#'-concatenation of a section's primary keys, and
the number of keys varies by section (per PrIME CoE P&G Standards). For Policy Maintenance it
is polcod#polvar#polval, but polval itself may contain '#' (e.g. SPLIT-STATUS-VALIDATION#B#U),
so splitting the element is ambiguous. Instead of parsing the element, we RECONSTRUCT the key
from the replica's separate columns:  f"{POLCOD}#{POLVAR}#{POLVAL}"  and compare the whole
string. This removes all parser artifacts.

Semantics validated (mirrors the report's own meaning):
  * Unexpected record            -> element MUST be PRESENT in the replica
  * Unexpected mismatching value -> element MUST be PRESENT (and A value checked separately)
  * Missing record               -> element MUST be ABSENT in the replica

Only "Policy Maintenance" is checked here because that is the section the replica exposes as a
view (POLDAT_VIEW). Area/Job sections are not exposed in the prodwms schema of these replicas.

Follows workspace rules: timestamped heartbeat logging; no silent failures; the DB layer
(diamond/db.py) provides timeouts + token reuse.
"""
from __future__ import annotations

import datetime
import importlib.util
import os
import re
import sys

import openpyxl

# --- locate the shared MSAL/pyodbc replica connector (diamond/db.py) ---------
# External dependency (not shipped in this package). Point DIAMOND_DB_PATH at your
# checkout of SQL_Translations/Diamond_Translation/diamond/db.py, or drop that tree
# beside this package.
DB_PATH = os.environ.get(
    "DIAMOND_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "SQL_Translations", "Diamond_Translation", "diamond", "db.py"))
EXCEL_PATH = os.environ.get(
    "DRIFT_EXCEL_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "Config report", "data.xlsx"),
)

# Report "Audited Site" display name -> replica code understood by db.connect().
SITE_TO_REPLICA = {
    "NEM": "NEMC",
    "WCMC": "WCMC",
    "Dallas": "DALLAS",
    "Dayton DYMC": "DAYTON",
    "SEFC Boombox": "SEFC",
    "Greater Chicago GCFC": "GCFC",
    "Albany FP": "ALBANY",
    "Greensboro GBSP": "GREENSBORO",
    "Brantford": "BRANTFORD",
    "Tabler": "TABLER",
    "Lima": "LIMA",
    "Andover": "ANDOVER",
    "Box Elder": "BOXELDER",
    "Phoenix": "PHOENIX",
}

POLICY_SECTION = "Policy Maintenance"
DEV_TYPES = ("Unexpected record", "Missing record", "Unexpected mismatching value")


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _load_db():
    spec = importlib.util.spec_from_file_location("db", DB_PATH)
    db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(db)
    return db


def replica_policy_keys(db, replica: str):
    """Return (present_full, present_nw, value_lookup) reconstructed from the replica.

    present_full : set of 'POLCOD#POLVAR#POLVAL' @ WH_ID_TMPL  -> (key, tmpl)
    present_nw   : set of 'POLCOD#POLVAR#POLVAL' ignoring template
    value_lookup : (key, tmpl) -> list of [RTSTR1, RTSTR2, RTNUM1, RTNUM2] as strings
    """
    cn = db.connect(replica, timeout=30)
    cur = cn.cursor()
    cur.execute(
        "SELECT POLCOD,POLVAR,POLVAL,WH_ID_TMPL,RTSTR1,RTSTR2,RTNUM1,RTNUM2 "
        "FROM prodwms.POLDAT_VIEW"
    )
    present_full: set = set()
    present_nw: set = set()
    value_lookup: dict = {}
    rows = 0
    for r in cur.fetchall():
        rows += 1
        base = f"{str(r.POLCOD).strip()}#{str(r.POLVAR).strip()}#{str(r.POLVAL).strip()}"
        s1 = str(r.RTSTR1).strip() if r.RTSTR1 is not None else ""
        s2 = str(r.RTSTR2).strip() if r.RTSTR2 is not None else ""
        # Some policy sections identify the element with EXTRA discriminator keys appended
        # after polval (per PrIME CoE P&G Standards, key count varies by section). Verified
        # against live data: the suffix is RTSTR1 (4-part) or RTSTR1#RTSTR2 (5-part), e.g.
        #   VC-PRIME-SAP#SPLIT-UNSPLIT#SPLIT-STATUS-VALIDATION#B#U  -> RTSTR1=B, RTSTR2=U
        #   VAR-BLIND-FINDS#REQUIRED-FIELDS#invdsp#prtnum          -> RTSTR1=prtnum
        # Register the base and both extended forms so matching is section-shape agnostic.
        variants = {base}
        if s1:
            variants.add(f"{base}#{s1}")
            if s2:
                variants.add(f"{base}#{s1}#{s2}")
        tmpl = str(r.WH_ID_TMPL).strip()
        for key in variants:
            present_full.add((key, tmpl))
            present_nw.add(key)
            value_lookup.setdefault((key, tmpl), []).append(
                [s1, s2,
                 str(r.RTNUM1).strip() if r.RTNUM1 is not None else "",
                 str(r.RTNUM2).strip() if r.RTNUM2 is not None else ""]
            )
    log(f"{replica}: loaded {rows} poldat rows ({len(present_nw)} distinct keys)")
    return present_full, present_nw, value_lookup


def _tmpl_of(details: str):
    m = re.search(r"Warehouse ID template <(.*?)>", details or "")
    return m.group(1).strip() if m else None


def validate_site(db, wb, idx, ncol, site_label: str, replica: str) -> dict:
    present_full, present_nw, value_lookup = replica_policy_keys(db, replica)

    stats = {t: {"ok": 0, "bad": 0, "ex": []} for t in DEV_TYPES}
    vmatch = vcheck = 0

    it = wb["Export"].iter_rows(values_only=True)
    next(it)  # header
    for raw in it:
        row = list(raw) + [None] * (ncol - len(raw))
        if row[idx["Audited Site"]] != site_label:
            continue
        if row[idx["Configuration Section"]] != POLICY_SECTION:
            continue
        typ = row[idx["Deviation Type"]]
        if typ not in DEV_TYPES:
            continue
        element = row[idx["Configuration Element"]]
        if not element:
            continue
        tmpl = _tmpl_of(row[idx["Deviation Details"]])

        present = (element, tmpl) in present_full or element in present_nw
        if typ == "Missing record":
            good = not present
        else:
            good = present
        bucket = "ok" if good else "bad"
        stats[typ][bucket] += 1
        if not good and len(stats[typ]["ex"]) < 8:
            stats[typ]["ex"].append((element, tmpl))

        # value-level check for mismatching values that have an Audited Value
        if typ == "Unexpected mismatching value":
            a_val = row[idx["Audited Value"]]
            if a_val is not None:
                cand = value_lookup.get((element, tmpl))
                if cand:
                    vcheck += 1
                    flat = {v for rec in cand for v in rec}
                    if str(a_val).strip() in flat:
                        vmatch += 1

    return {"stats": stats, "vmatch": vmatch, "vcheck": vcheck}


def main() -> int:
    log("=== Config Drift accuracy validation START ===")
    if not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(EXCEL_PATH)
    db = _load_db()

    log(f"opening export: {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    hdr_it = wb["Export"].iter_rows(values_only=True)
    hdr = list(next(hdr_it))
    idx = {h: i for i, h in enumerate(hdr)}
    ncol = len(hdr)

    sites = [a.strip() for a in os.environ.get("VALIDATE_SITES", "").split(",") if a.strip()]
    if not sites:
        sites = ["NEM", "WCMC", "Dallas"]

    grand_ok = grand = 0
    v_ok = v_tot = 0
    for site in sites:
        replica = SITE_TO_REPLICA.get(site)
        if not replica:
            log(f"{site}: no replica mapping — skipping")
            continue
        log("-" * 70)
        log(f"VALIDATING {site} -> {replica}")
        try:
            res = validate_site(db, wb, idx, ncol, site, replica)
        except Exception as e:
            log(f"{site}: ERROR {type(e).__name__}: {e}")
            raise
        site_ok = site_tot = 0
        for typ, st in res["stats"].items():
            tot = st["ok"] + st["bad"]
            site_ok += st["ok"]
            site_tot += tot
            rate = (st["ok"] / tot * 100) if tot else 0.0
            log(f"   {typ}: {tot} | confirmed {st['ok']} ({rate:.1f}%) | unmatched {st['bad']}")
            for ex in st["ex"]:
                log(f"        counter-example: {ex}")
        grand_ok += site_ok
        grand += site_tot
        v_ok += res["vmatch"]
        v_tot += res["vcheck"]
        rate = (site_ok / site_tot * 100) if site_tot else 0.0
        log(f"   SITE TOTAL: {site_ok}/{site_tot} = {rate:.1f}% confirmed | "
            f"value-level {res['vmatch']}/{res['vcheck']}")

    log("=" * 70)
    if grand:
        log(f"OVERALL presence: {grand_ok}/{grand} = {grand_ok / grand * 100:.1f}% confirmed")
    if v_tot:
        log(f"OVERALL value-level: {v_ok}/{v_tot} = {v_ok / v_tot * 100:.1f}% exact match")
    log("=== DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
