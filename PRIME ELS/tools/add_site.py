"""ONE command to add (or re-profile) a PrIME 2014 / 2022 site.

    py tools/add_site.py CODE                 the site is a row of the Sites tab in the inputs file (Hypercare_KPI_Inputs.xlsx)
    py tools/add_site.py CODE --dry-run       do everything, then put config/ and dist/ back as they were (test / preview)
    py tools/add_site.py CODE --server S --db D [--wh WH] [--utc 8] --dry-run    try a replica that is not in the inputs file yet

Steps (each must pass before the next; a heartbeat line every 30 s, nothing fails silently):
  1 inputs file  : Sites tab valid (max sites, one default, numbers)        tools/inputs_file.py
  2 apply        : the Sites row -> config/site_config.csv (NEW row)        tools/apply_inputs.py --apply
  3 profile      : technical settings from the replica, with evidence       tools/profile_site.py CODE --write
  4 check        : replica health / tokens / robot users / history          tools/site_config_check.py CODE
  5 validate SQL : every query compiles and runs on the replica             tools/validate_sql.py CODE
  6 build        : single-site file + ALL_SITES + Service file              tools/build_pbip.py
  7 report       : docs/ONBOARDING_<CODE>.md  (what was found, what to confirm with the site, next steps)
Then open dist/<CODE>/... in Power BI Desktop and refresh, or publish: py tools/publish.py.
"""
import sys, os, csv, json, shutil, subprocess, threading, time, datetime, argparse

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(TOOLS, ".."))
CFG = os.path.join(ROOT, "config")
sys.path.insert(0, TOOLS)


def hb(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(step, args, log):
    """Run a tool, stream its output, print a heartbeat every 30 s; return (exit code, output lines)."""
    hb(f"STEP {step}: py {' '.join(args)}")
    p = subprocess.Popen([sys.executable, "-u"] + args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    lines, last = [], [time.time()]
    stop = threading.Event()

    def beat():
        t0 = time.time()
        while not stop.wait(5):
            if time.time() - last[0] >= 30:
                hb(f"  ... {step} still running ({time.time() - t0:.0f} s)")
                last[0] = time.time()
    threading.Thread(target=beat, daemon=True).start()
    for ln in p.stdout:
        lines.append(ln.rstrip("\n"))
        print("    " + ln.rstrip("\n")[:220], flush=True)
        last[0] = time.time()
    p.wait()
    stop.set()
    log.append({"step": step, "args": args, "exit": p.returncode, "tail": lines[-15:]})
    hb(f"STEP {step}: exit {p.returncode}")
    return p.returncode, lines


def fail(log, code, step, why, ctx):
    hb(f"STOPPED at {step}: {why}")
    report(code, log, ctx, stopped=f"{step}: {why}")
    sys.exit(1)


def read_rows(name):
    with open(os.path.join(CFG, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_rows(name, rows):
    with open(os.path.join(CFG, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)


def test_row(code, a):
    """--server/--db: a site that is not in the inputs file yet - a NEW row from the default site (static settings only)."""
    rows = read_rows("site_config.csv")
    if any(r["SiteCode"] == code for r in rows):
        return
    peer = next(r for r in rows if r.get("Is_Default") == "1")
    keep = {"ACT_DAYS", "CAL_FUTURE_DAYS", "TALL_HEIGHT_CM", "LOC_TRAILER", "ROBOT_TXN_PER_HOUR", "WO_WINDOW_DAYS", "MOVEMENT_DAYS", "DETAIL_DAYS",
            "RPM_VendorList_Sheet", "Databricks_Host", "Databricks_HttpPath"}
    row = {c: (peer[c] if c in keep else "") for c in peer}
    row.update({"SiteCode": code, "SiteName": f"{code} (test)", "Region": "TEST", "ReplicaServer": a.server, "ReplicaDatabase": a.db,
                "WH_ID": a.wh or "", "UTC_Offset_h": str(a.utc), "Shift1_Start": "6", "Shift2_Start": "14", "Shift3_Start": "22",
                "Hypercare_Start": f"{datetime.date.today()} 00:00:00", "Is_Default": "0", "Has_Production": "", "Has_LevelA": "0", "Has_HOFF": "0",
                "Has_SAP_Plan": "0", "Has_SAP_Prod": "0", "Has_RPM_Master": "0", "Config_Status": f"NEW - run py tools/add_site.py {code}"})
    rows.append(row)
    write_rows("site_config.csv", rows)
    hb(f"{code}: test row added to config/site_config.csv (from --server / --db)")


def report(code, log, ctx, stopped=None):
    prof = {}
    pj = os.path.join(ROOT, "docs", f"profile_{code}.json")
    if os.path.exists(pj):
        prof = json.load(open(pj, encoding="utf-8")).get("proposal", {})
    row = next((r for r in read_rows("site_config.csv") if r["SiteCode"] == code), {})
    L = [f"# Onboarding {code} - {row.get('SiteName', '')}", "",
         f"Generated {datetime.datetime.now():%Y-%m-%d %H:%M} by `py tools/add_site.py {code}`{' (DRY RUN - config restored)' if ctx.get('dry') else ''}.", "",
         f"**Result: {'STOPPED - ' + stopped if stopped else 'OK - ready to open / refresh / publish'}**", "",
         f"- Engine {row.get('WMS_Version', '?')}, replica `{row.get('ReplicaServer', '?')}` / `{row.get('ReplicaDatabase', '?')}`, warehouse `{row.get('WH_ID', '?')}`",
         f"- Config status: {row.get('Config_Status', '?')}", "", "## Steps", "", "| Step | Exit | Last lines |", "|---|---|---|"]
    for s in log:
        tail = " / ".join(x.strip() for x in s["tail"][-3:] if x.strip()).replace("|", "/")[:220]
        L.append(f"| {s['step']} | {s['exit']} | {tail} |")
    if ctx.get("validate"):
        v = ctx["validate"]
        L += ["", f"## Queries on the replica: {v['ok']} OK, {v['off']} feature OFF, {len(v['fail'])} failed", ""]
        L += [f"- FAIL {n}: {e}" for n, e in v["fail"]]
    if ctx.get("check"):
        L += ["", "## Site check (tools/site_config_check.py)", ""] + [f"- {x}" for x in ctx["check"]]
    if prof:
        L += ["", "## Profiled settings", "", "Confidence: HIGH = clear replica evidence, MED = evidence but check, LOW / CHECK = **confirm with the site** (safe default used).", "",
              "| Setting | Value | Confidence | Evidence |", "|---|---|---|---|"]
        for k, v in sorted(prof.items(), key=lambda kv: ({"CHECK": 0, "LOW": 1, "MED": 2, "HIGH": 3}.get(kv[1]["confidence"], 4), kv[0])):
            L.append(f"| {k} | `{str(v['value'])[:60]}` | {v['confidence']} | {str(v['evidence'])[:200].replace('|', '/')} |")
    L += ["", "## Next steps", "",
          "1. Confirm the LOW / CHECK settings with the site; change them in `config/site_config.csv` (or re-run with corrected inputs).",
          "2. Alert targets: the site uses the 'All sites' (BD) targets until it gets its own rows in the **Alert targets** tab of the inputs file.",
          f"3. Open `dist/{code}/WH Hypercare KPI - {code}.pbip` in Power BI Desktop, sign in to the replica when asked, Refresh.",
          f"4. Test: `powershell -File tools/run_full_tests.ps1 -Sites {code}` (field audit, visual / filter replay, reconciliation).",
          "5. Publish: `py tools/publish.py` (the ALL_SITES report has every site of the Sites tab, at most 6)."]
    out = os.path.join(ROOT, "docs", f"ONBOARDING_{code}.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    hb(f"report: {out}")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("code"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--server"); ap.add_argument("--db"); ap.add_argument("--wh"); ap.add_argument("--utc", type=float, default=0)
    ap.add_argument("--no-build", action="store_true", help="stop after the SQL validation")
    a = ap.parse_args(argv)
    code = a.code.upper()
    log, ctx = [], {"dry": a.dry_run}
    backup = {}
    if a.dry_run:
        for n in ("config/site_config.csv", "config/kpi_thresholds.csv", "docs/SITE_CONFIG_CHECK.md"):
            if os.path.exists(os.path.join(ROOT, n)):
                backup[n] = open(os.path.join(ROOT, n), encoding="utf-8").read()
        hb("DRY RUN: config/site_config.csv, config/kpi_thresholds.csv and docs/SITE_CONFIG_CHECK.md are restored at the end")
    try:
        # 1 + 2: inputs file -> config row
        if a.server:
            if not a.db:
                fail(log, code, "inputs", "--server needs --db", ctx)
            test_row(code, a)
        else:
            import inputs_file as IF
            sites, targets, issues = IF.read()
            if issues:
                fail(log, code, "inputs", "the inputs file has problems: " + "; ".join(f"{t} row {r} {k}: {m}" for t, r, k, m in issues[:5]), ctx)
            if code not in {s["SiteCode"] for s in sites}:
                fail(log, code, "inputs", f"{code} is not a row of the Sites tab in {IF.local_path()} - add it there first", ctx)
            rc, _ = run("2 apply inputs", ["tools/apply_inputs.py", "--apply"], log)
            if rc:
                fail(log, code, "2 apply inputs", "apply_inputs refused (see the lines above)", ctx)
        # 3 profile
        rc, _ = run("3 profile", ["tools/profile_site.py", code, "--write"] + (["--wh", a.wh] if a.wh else []), log)
        if rc:
            fail(log, code, "3 profile", "profiler failed (replica unreachable / not a PrIME replica?)", ctx)
        # 4 site check
        rc, lines = run("4 site check", ["tools/site_config_check.py", code], log)
        ctx["check"] = [x.strip() for x in lines if any(k in x for k in ("FAIL", "WARN"))][:25]
        if rc:
            fail(log, code, "4 site check", "site_config_check reported FAIL (see docs/SITE_CONFIG_CHECK.md)", ctx)
        # 5 validate every query on the replica
        rc, _ = run("5 validate SQL", ["tools/validate_sql.py", code], log)
        vj = os.path.join(TOOLS, f"_validate_{code}.json")
        res = json.load(open(vj, encoding="utf-8"))["results"] if os.path.exists(vj) else []
        bad = [(r["table"], (r["compile"] if not r["compile"].startswith("OK") else r["exec"])[:160]) for r in res
               if not r["compile"].startswith("OK") or (r["enabled"] and not str(r["exec"]).startswith("OK"))]
        ctx["validate"] = {"ok": sum(1 for r in res if str(r["exec"]).startswith("OK")), "off": sum(1 for r in res if not r["enabled"]), "fail": bad}
        if rc or not res or bad:
            fail(log, code, "5 validate SQL", f"{len(bad)} query(ies) failed on the replica", ctx)
        if a.no_build:
            report(code, log, ctx); return
        # 6 build: the site file always; ALL_SITES + Service only for a real (non dry-run) add
        rc, _ = run("6 build site file", ["tools/build_pbip.py", code], log)
        if rc:
            fail(log, code, "6 build", "build failed (see the lines above)", ctx)
        if not a.dry_run:
            for step, args in (("6 build ALL_SITES", ["tools/build_pbip.py", "--all-only"]), ("6 build Service file", ["tools/build_pbip.py", code, "--service"])):
                rc, _ = run(step, args, log)
                if rc:
                    fail(log, code, step, "build failed", ctx)
        report(code, log, ctx)
        hb(f"{code}: DONE")
    finally:
        if a.dry_run:
            for n, txt in backup.items():
                open(os.path.join(ROOT, n), "w", encoding="utf-8", newline="").write(txt)
            for d in (os.path.join(ROOT, "dist", code), os.path.join(ROOT, "dist", "_service", code)):
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)
            hb("DRY RUN: config restored, dist output of the test site removed")


if __name__ == "__main__":
    main(sys.argv[1:])
