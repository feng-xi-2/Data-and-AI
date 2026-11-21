"""Inputs file -> config. The ONE inputs file (Hypercare_KPI_Inputs.xlsx, config/inputs_source.csv) decides which sites are in the report
and their business settings; its Alert targets are also read live by the report at every refresh (no rebuild needed for a target).

    py tools/apply_inputs.py              check the file and show what would change (nothing written)
    py tools/apply_inputs.py --apply      write config/site_config.csv + config/kpi_thresholds.csv for ADDED / CHANGED sites and targets
    py tools/apply_inputs.py --confirm    also REMOVE sites that are no longer in the Sites tab (their config row; next build drops them)
then rebuild: py tools/build_pbip.py ; py tools/build_pbip.py --service  (a NEW site: py tools/add_site.py <CODE> does everything)

Rules: at most Max_Sites sites (config/inputs_source.csv, 6); exactly one Is_Default = 1; a new site gets engine defaults and
'AUTO-PROFILED' technical settings from tools/add_site.py. Never fails silently: every problem is listed and nothing is written."""
import csv
import sys

import inputs_file as IF

CFG = IF.CFG


def read(name):
    return list(csv.DictReader(open(CFG / name, encoding="utf-8-sig")))


def write(name, rows, cols):
    with open(CFG / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def fmt(x):
    return "" if x is None else (str(int(x)) if float(x).is_integer() else f"{x:g}")


def plan(sites_in, targets_in):
    """-> (site rows, threshold rows, changes, removed codes)"""
    sites = read("site_config.csv")
    cols = list(sites[0].keys())
    by_code = {s["SiteCode"]: s for s in sites}
    changes = []
    new_codes = []
    for r in sites_in:
        code = r["SiteCode"]
        cur = by_code.get(code)
        if cur is None:
            cur = {c: "" for c in cols}
            cur.update({"SiteCode": code, "Config_Status": "NEW - run py tools/add_site.py " + code, "ACT_DAYS": "14", "MOVEMENT_DAYS": "7",
                        "DETAIL_DAYS": "14", "WO_WINDOW_DAYS": "30", "CAL_FUTURE_DAYS": "30", "Has_LevelA": "0", "Has_HOFF": "0",
                        "Has_SAP_Plan": "0", "Has_RPM_Master": "0", "Has_SAP_Prod": "1" if r.get("SAP_Plant") else "0"})
            sites.append(cur)
            by_code[code] = cur
            new_codes.append(code)
            changes.append(f"ADD site {code} ({r['SiteName']}, {r['WMS_Version']}) - technical settings: py tools/add_site.py {code}")
        for c, _ in IF.SITE_COLS:
            v = r[c]
            if c == "WH_ID" and not v:
                continue                                    # blank = keep / profile
            if (cur.get(c) or "") != v:
                if code not in new_codes:
                    changes.append(f"{code}.{c}: '{cur.get(c, '')}' -> '{v}'")
                cur[c] = v
    keep = {r["SiteCode"] for r in sites_in}
    removed = [s["SiteCode"] for s in sites if s["SiteCode"] not in keep]
    for c in removed:
        changes.append(f"REMOVE site {c} (not in the Sites tab) - its config row is deleted; the next build drops its partitions")
    th = read("kpi_thresholds.csv")
    tcols = list(th[0].keys())
    idx = {(r["Site"], r["KPI_Key"]): r for r in th}
    for t in targets_in:
        site = "*" if t["Site"] == IF.ALL_SITES else t["Site"]
        row = idx.get((site, t["KPI_Key"]))
        if row is None:
            row = dict(idx[("*", t["KPI_Key"])], Site=site)
            th.append(row)
            idx[(site, t["KPI_Key"])] = row
            changes.append(f"target {site}/{t['KPI_Key']}: new site row")
        for src, dst in (("Target", "Target"), ("Warning_At", "Warn_Abs"), ("Critical_At", "Crit_Abs")):
            v = t[src]
            if v is None:
                continue
            cur = row.get(dst) or ""
            try:
                same = cur != "" and abs(float(cur) - v) <= 1e-6 * max(1.0, abs(v))
            except ValueError:
                same = False
            if not same and dst != "Target":
                # a warning / critical equal to the percentage rule is not a change (the file shows the derived limit)
                pct = row.get(dst.replace("_Abs", "_Pct"))
                try:
                    tv = float(row["Target"]); p = float(pct)
                    derived = tv * p if row["Direction"] == "Higher" else tv * (1 + p) if row["Direction"] == "Lower" else None
                    same = derived is not None and cur == "" and abs(derived - v) <= 1e-6 * max(1.0, abs(v))
                except (TypeError, ValueError):
                    pass
            if not same:
                changes.append(f"target {site}/{t['KPI_Key']}.{dst}: '{cur}' -> '{fmt(v)}'")
                row[dst] = fmt(v)
    th = [r for r in th if r["Site"] == "*" or r["Site"] in keep]
    return [s for s in sites if s["SiteCode"] in keep], cols, th, tcols, changes, removed


def main(argv):
    sites_in, targets_in, issues = IF.read()
    print(f"inputs file: {IF.local_path()}\n   {len(sites_in)} site(s), {len(targets_in)} alert target row(s), {len(issues)} problem(s)")
    hard = [i for i in issues if i[0] == "Sites"]
    for tab, row, what, msg in issues:
        print(f"   !! {tab} row {row} {what}: {msg}")
    if hard:
        raise SystemExit("!! nothing written - fix the Sites tab first")
    sites, cols, th, tcols, changes, removed = plan(sites_in, targets_in)
    print(f"{len(changes)} change(s)" + (":\n   " + "\n   ".join(changes) if changes else " - the config equals the inputs file"))
    if not ("--apply" in argv or "--confirm" in argv):
        print("dry run - nothing written (--apply to write; --confirm also removes sites)")
        return
    if removed and "--confirm" not in argv:
        raise SystemExit(f"!! nothing written: site(s) {removed} would be REMOVED - rerun with --confirm if that is intended")
    write("site_config.csv", sites, cols)
    write("kpi_thresholds.csv", th, tcols)
    print("written: config/site_config.csv, config/kpi_thresholds.csv -> rebuild: py tools/build_pbip.py ; py tools/build_pbip.py --service")


if __name__ == "__main__":
    main(sys.argv[1:])
