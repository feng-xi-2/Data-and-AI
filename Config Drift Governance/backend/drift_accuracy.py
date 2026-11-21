"""drift_accuracy — measure the ACCURACY of PrIME Config Drift against the LIVE replicas,
across ALL sites, using Power BI as the benchmark.

WHAT IT MEASURES
----------------
For each site, it pulls that site's Power BI "Policy Maintenance" deviations (the benchmark)
and checks each one against the site's LIVE `prodwms.POLDAT_VIEW` replica — i.e. is the
deviation actually true in the current live data?

  * Unexpected record            -> the element MUST be PRESENT in the live replica.
  * Missing record               -> the element MUST be ABSENT in the live replica.
  * Unexpected mismatching value -> the element MUST be PRESENT, and (value-level) the PBI
                                    "A value" MUST appear in the live row's values.

Confirmation rate = confirmed / total. High = the PBI drift reproduces from live data
(the drift is accurate); low counter-examples point at staleness or key-shape issues.

WHY POLICY MAINTENANCE ONLY / WHY THESE SITES
---------------------------------------------
Policy Maintenance is the one config section the replicas expose as data (POLDAT_VIEW). All
16 sites in diamond.db.SITES expose it, so accuracy is measured estate-wide here (migration
mode in replica_drift.py needs a 2014 archive schema, which only Crailsheim has — that is
why migration was Crailsheim-only; this presence-accuracy check is not so limited).

PBI audited-instance names differ from the replica site codes (e.g. NEM_PRODWMS vs NEMC),
so SITE_TO_PBI below maps each replica site to its Power BI instance (verified from the live
model's distinct Audited Instance values, Aug 2026).

Grounded key reconstruction is reused from validate_against_replica.replica_policy_keys.

USAGE
  python drift_accuracy.py                 # all mapped sites
  python drift_accuracy.py --sites NEMC,WCMC,ALBANY
  python drift_accuracy.py --limit-sites 5 # quick sample

Follows workspace rules: timestamped heartbeat logs; no silent failures (log type+message,
then raise); the replica/PBI layers carry their own timeouts + token reuse.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
DIAMOND_PARENT = os.path.abspath(os.path.join(BASE, "..", "Diamond_Translation"))
if DIAMOND_PARENT not in sys.path:
    sys.path.insert(0, DIAMOND_PARENT)

OUT_DIR = os.path.join(BASE, "_replica_drift")

# Replica site code (diamond.db.SITES) -> Power BI Audited Instance (A) name.
# Verified against the live model's distinct Audited Instance list (_diag_pbi_instances.py).
SITE_TO_PBI = {
    "ALBANY":     "ALB_PRODWMS",
    "ANDOVER":    "AND_PRODWMS",
    "BRANTFORD":  "BRC_PRODWMS",
    "DALLAS":     "DAL_PRODWMS",
    "DAYTON":     "DYMC_PRODWMS",
    "GCFC":       "GCFC_PRODWMS",
    "GREENSBORO": "GBSP_PRODWMS",
    "LIMA":       "LIMA_PRODWMS",
    "NEMC":       "NEM_PRODWMS",
    "SEFC":       "SEFC_PRODWMS",
    "TABLER":     "TAB_PRODWMS",
    "WCMC":       "WCMC_PRODWMS",
    "PHOENIX":    "PHOENIX_PRODWMS",
    "CRAILSHEIM": "CRAILSHEIM_2022_PRODWMS",
    # BOXELDER: no matching PBI PRODWMS instance found in the model (excluded).
}

POLICY_SECTION = "Policy Maintenance"
DEV_TYPES = ("Unexpected record", "Missing record", "Unexpected mismatching value")


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def _pbi_policy_devs(pbi, instance: str) -> list[dict]:
    """Pull a single instance's Policy-Maintenance deviations from the live PBI model."""
    safe = instance.replace('"', '""')
    dax = (
        "EVALUATE\n"
        "SELECTCOLUMNS(\n"
        f"    FILTER('{pbi.TABLE}',\n"
        f'        {pbi._col("Audited Instance (A)")} = "{safe}"\n'
        f'        && {pbi._col("Configuration Section")} = "Policy Maintenance"),\n'
        f'    "Element",  {pbi._col("Configuration Element")},\n'
        f'    "Type",     {pbi._col("Deviation Type")},\n'
        f'    "Severity", {pbi._col("Deviation Severity")},\n'
        f'    "A_value",  {pbi._col("A value")},\n'
        f'    "R_value",  {pbi._col("R value")}\n'
        ")"
    )
    return [pbi._clean(r) for r in pbi.run_dax(dax)]


def _norm_type(t: str) -> str:
    t = str(t or "").strip().lower()
    if t.startswith("missing"):
        return "Missing record"
    if "mismatch" in t:
        return "Unexpected mismatching value"
    if t.startswith("unexpected"):
        return "Unexpected record"
    return str(t)


def validate_site(db, vr, pbi, site: str, instance: str) -> dict:
    """Validate one site's PBI Policy deviations against its live replica."""
    log(f"{site}: reading live prodwms.POLDAT_VIEW")
    present_full, present_nw, value_lookup = vr.replica_policy_keys(db, site)
    # case-insensitive presence set (defensive: PBI element casing vs stored poldat casing)
    present_ci = {k.casefold() for k in present_nw}

    log(f"{site}: querying PBI Policy deviations for instance {instance}")
    devs = _pbi_policy_devs(pbi, instance)

    stats = {t: {"ok": 0, "bad": 0, "ex": []} for t in DEV_TYPES}
    vmatch = vcheck = 0
    for d in devs:
        typ = _norm_type(d.get("Type"))
        if typ not in DEV_TYPES:
            continue
        element = str(d.get("Element") or "").strip()
        if not element:
            continue
        present = (element in present_nw) or (element.casefold() in present_ci)
        good = (not present) if typ == "Missing record" else present
        bucket = "ok" if good else "bad"
        stats[typ][bucket] += 1
        if not good and len(stats[typ]["ex"]) < 6:
            stats[typ]["ex"].append(element)

        if typ == "Unexpected mismatching value":
            a_val = d.get("A_value")
            if a_val is not None and str(a_val).strip() != "":
                # gather candidate live values for this element (any template)
                cands = [rec for (k, _t), recs in value_lookup.items()
                         if k == element for rec in recs]
                if not cands:
                    cands = [rec for (k, _t), recs in value_lookup.items()
                             if k.casefold() == element.casefold() for rec in recs]
                if cands:
                    vcheck += 1
                    flat = {str(v).strip() for rec in cands for v in rec}
                    if str(a_val).strip() in flat:
                        vmatch += 1

    total = sum(st["ok"] + st["bad"] for st in stats.values())
    ok = sum(st["ok"] for st in stats.values())
    return {"site": site, "instance": instance, "pbiDevs": len(devs),
            "checked": total, "confirmed": ok,
            "rate": (ok / total * 100) if total else 0.0,
            "vmatch": vmatch, "vcheck": vcheck, "stats": stats}


def main() -> int:
    ap = argparse.ArgumentParser(description="Config Drift accuracy vs live replicas (all sites)")
    ap.add_argument("--sites", help="comma-separated replica site codes (default: all mapped)")
    ap.add_argument("--limit-sites", type=int, default=0, help="only the first N mapped sites")
    args = ap.parse_args()

    import diamond.db as db
    import pbi_drift_alert as pbi
    import validate_against_replica as vr

    if args.sites:
        want = [s.strip().upper() for s in args.sites.split(",") if s.strip()]
        sites = [s for s in want if s in SITE_TO_PBI]
        missing = [s for s in want if s not in SITE_TO_PBI]
        for m in missing:
            log(f"skip {m}: no PBI instance mapping")
    else:
        sites = list(SITE_TO_PBI)
    if args.limit_sites:
        sites = sites[: args.limit_sites]

    log("=== Config Drift accuracy (PBI benchmark vs LIVE replica) START ===")
    log(f"sites ({len(sites)}): {', '.join(sites)}")

    results, errors = [], []
    for site in sites:
        instance = SITE_TO_PBI[site]
        log("-" * 72)
        try:
            res = validate_site(db, vr, pbi, site, instance)
        except Exception as e:
            log(f"{site}: ERROR {type(e).__name__}: {e}")
            traceback.print_exc()
            errors.append({"site": site, "error": f"{type(e).__name__}: {e}"})
            continue
        for typ, st in res["stats"].items():
            tot = st["ok"] + st["bad"]
            rate = (st["ok"] / tot * 100) if tot else 0.0
            log(f"   {typ:32s} {tot:5d} | confirmed {st['ok']:5d} ({rate:5.1f}%) | unmatched {st['bad']}")
            for ex in st["ex"]:
                log(f"        counter-example: {ex}")
        log(f"   {site} TOTAL: {res['confirmed']}/{res['checked']} = {res['rate']:.1f}% confirmed"
            f" | value-level {res['vmatch']}/{res['vcheck']}"
            f" | PBI rows {res['pbiDevs']}")
        results.append(res)

    log("=" * 72)
    g_ok = sum(r["confirmed"] for r in results)
    g_tot = sum(r["checked"] for r in results)
    g_vok = sum(r["vmatch"] for r in results)
    g_vt = sum(r["vcheck"] for r in results)
    log(f"SITES validated: {len(results)}/{len(sites)}"
        + (f"  (errors: {len(errors)})" if errors else ""))
    if g_tot:
        log(f"OVERALL presence accuracy: {g_ok}/{g_tot} = {g_ok / g_tot * 100:.1f}% confirmed")
    if g_vt:
        log(f"OVERALL value-level match : {g_vok}/{g_vt} = {g_vok / g_vt * 100:.1f}% exact")
    # per-site leaderboard
    log("--- per-site confirmation rate ---")
    for r in sorted(results, key=lambda x: -x["rate"]):
        log(f"   {r['site']:12s} {r['rate']:5.1f}%  ({r['confirmed']}/{r['checked']}, PBI {r['pbiDevs']})")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "accuracy.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "benchmark": "Power BI 'DAP SP PROD Data Combined' (Policy Maintenance)",
                   "method": "PBI deviation confirmed against live prodwms.POLDAT_VIEW",
                   "overall": {"confirmed": g_ok, "checked": g_tot,
                               "rate": (g_ok / g_tot * 100) if g_tot else 0.0,
                               "valueMatch": g_vok, "valueChecked": g_vt},
                   "sites": results, "errors": errors}, f, indent=2, ensure_ascii=False)
    log(f"wrote {out}")
    log("=== DONE ===")
    try:
        db.close_all()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
