"""End-to-end test of the single-site files (dist/<SITE>/WH Hypercare KPI - <SITE>.pbip) in Power BI Desktop.

    py tools/test_site_files.py [SITE ...] [--out <dir>]

Per site: open the file, Refresh from the ribbon (answers a credential prompt with the signed-in Microsoft account),
wait until every partition is loaded, then
  1. partitions: all loaded, no error
  2. row counts of the replica tables vs tools/_validate_<SITE>.json (direct SQL, validate_sql.py)
  3. tools/selfcheck_measures.ps1 - every measure evaluated for the site, 0 errors expected
  4. tools/ui_test_sites.py - every page opened, no visual error text, title = site
then closes Desktop (nothing saved - recipients refresh with their own credentials).
Writes <out>/site_files_results.json.
"""
import csv
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ctypes.windll.shcore.SetProcessDpiAwareness(2)
import psutil  # noqa: E402
from _ui import main_win, dialogs, find, click  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PS = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
args = [a for a in sys.argv[1:]]
OUT = Path(args[args.index("--out") + 1]) if "--out" in args else (Path(__file__).resolve().parents[2] / "_uitest" / "site_files")
OUT.mkdir(parents=True, exist_ok=True)
codes = [a.upper() for a in args if not a.startswith("--") and (("--out" not in args) or a != args[args.index("--out") + 1])]
SITES = {r["SiteCode"]: r for r in csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig"))}
codes = codes or list(SITES)
OUT.mkdir(parents=True, exist_ok=True)
COUNT_TABLES = ["TTAT", "Produced Pallet", "Shipped Pallet", "Outbound TTA", "Location Utilisation", "User Activity", "Pallets Movement", "WorkLine Activities"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def dax(pid, q, timeout=300):
    r = subprocess.run(PS + [str(HERE / "pbi_dax.ps1"), "-ProcId", str(pid), "-Dax", q, "-TimeoutSec", str(timeout)],
                       capture_output=True, text=True, timeout=timeout + 60)
    out = r.stdout.strip()
    try:
        return json.loads(out) if out else {"error": r.stderr[-300:]}
    except json.JSONDecodeError:
        return {"error": out[-300:]}


def desktop_pid(title_prefix, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in psutil.process_iter(["name", "pid"]):
            if (p.info["name"] or "").lower() == "pbidesktop.exe":
                try:
                    w = main_win(p.info["pid"])
                    if w.exists(timeout=1) and w.window_text().startswith(title_prefix):
                        return p.info["pid"]
                except Exception:
                    pass
        time.sleep(5)
    raise TimeoutError(f"Desktop window '{title_prefix}' not found")


def answer_credentials(w):
    """Credential prompt -> Microsoft account (the signed-in work account) -> Connect. Returns the source name or None."""
    for c in dialogs(w):
        texts = [x.window_text() for x in c.descendants() if x.window_text()]
        if "SQL Server database" not in texts and "Databricks" not in texts:
            continue
        src = next((t for t in texts if "database.windows.net" in t or "azuredatabricks" in t), "?")
        tab = next((x for x in c.descendants(control_type="TabItem") if x.window_text() in ("Microsoft account", "Azure Active Directory")), None)
        if tab:
            click(tab)
            time.sleep(2)
        texts = [x.window_text() for x in c.descendants() if x.window_text()]
        if not any("currently signed in" in t.lower() for t in texts):
            click(find(c, "Sign in", "Button"))
            for _ in range(36):
                time.sleep(5)
                if any("currently signed in" in x.window_text().lower() for x in c.descendants() if x.window_text()):
                    break
        click(find(c, "Connect", "Button"))
        return src
    return None


def kill(pid):
    for ch in psutil.Process(pid).children(recursive=True):
        try:
            ch.kill()
        except Exception:
            pass
    psutil.Process(pid).kill()


def expected_rows(code):
    f = HERE / f"_validate_{code}.json"
    if not f.exists():
        return {}
    out = {}
    for r in json.loads(f.read_text(encoding="utf-8"))["results"]:
        m = re.search(r"OK (\d+) rows", r.get("exec", ""))
        if m:
            out[r["table"]] = int(m.group(1))
    return out


results = {}
for code in codes:
    site = SITES[code]
    res = {"site": code}
    pbip = ROOT / "dist" / code / f"WH Hypercare KPI - {code}.pbip"
    log(f"===== {code}: open {pbip.name}")
    os.startfile(pbip)
    pid = desktop_pid(f"WH Hypercare KPI - {code}")
    w = main_win(pid)
    time.sleep(20)
    click(find(w, "Refresh", "Button", "splitPrimaryButton", timeout=180))
    t0 = time.time()
    creds = []
    state = None
    while time.time() - t0 < 1500:
        time.sleep(10)
        try:
            s = answer_credentials(w)
            if s:
                creds.append(s)
                log("  credential prompt answered:", s)
        except Exception as e:
            log("  credential prompt handling failed:", repr(e)[:150])
        state = dax(pid, 'EVALUATE GROUPBY(ADDCOLUMNS(FILTER(INFO.PARTITIONS(), [Type] = 4), "S", [State], "E", [ErrorMessage] <> ""), [S], [E], "n", COUNTX(CURRENTGROUP(), 1))')
        if isinstance(state, list) and state and all(r["[S]"] == 1 for r in state) and not dialogs(w):
            break
        if isinstance(state, list) and any(r["[E]"] for r in state):
            break
    res["refresh_s"] = int(time.time() - t0)
    res["credential_prompts"] = creds
    res["partitions"] = state
    loaded = isinstance(state, list) and state and all(r["[S]"] == 1 and not r["[E]"] for r in state)
    res["refresh_ok"] = bool(loaded)
    if not loaded:
        texts = [x.window_text() for c in dialogs(w) for x in c.descendants() if x.window_text()]
        res["refresh_errors"] = [t[:300] for t in texts if "rror" in t or t.startswith("Failed")][:5]
        log("  REFRESH FAILED", res.get("refresh_errors"))
    else:
        log(f"  refresh OK in {res['refresh_s']} s ({sum(r['[n]'] for r in state)} partitions)")
        q = "EVALUATE ROW(" + ", ".join(f'"{t}", COUNTROWS({chr(39) + t + chr(39)})' for t in COUNT_TABLES) + ")"
        counts = dax(pid, q)
        val = subprocess.Popen([sys.executable, str(HERE / "validate_sql.py"), code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sl = dax(pid, 'EVALUATE ROW("sites", COUNTROWS(VALUES(Cfg_Site[SiteCode])), "blank", COUNTROWS(FILTER(VALUES(Cfg_Site[SiteCode]), ISBLANK(Cfg_Site[SiteCode]))) + 0)')
        res["site_members"] = sl
        if not (isinstance(sl, list) and sl and sl[0].get("[sites]") == 1 and sl[0].get("[blank]") == 0):
            log("  !! site slicer members not exactly one site:", sl)
        csv_out = OUT / f"{code}_measures.csv"
        r = subprocess.run(PS + [str(HERE / "selfcheck_measures.ps1"), "-ProcId", str(pid), "-OutCsv", str(csv_out)], capture_output=True, text=True, timeout=3600)
        res["measures"] = r.stdout.strip().splitlines()[-3:] if r.stdout.strip() else [r.stderr[-300:]]
        log("  measures:", res["measures"])
        r = subprocess.run([sys.executable, str(HERE / "ui_test_sites.py"), str(pid), str(OUT / code)], capture_output=True, text=True, timeout=3600)
        lines = r.stdout.strip().splitlines()
        res["ui"] = [ln for ln in lines if ln.startswith("DONE") or "ERROR" in ln or "MISMATCH" in ln or "NOT OPENED" in ln][-10:] or lines[-3:] or [r.stderr[-300:]]
        log("  ui:", res["ui"])
        try:
            val.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            val.kill()
        exp = expected_rows(code)
        cmp = {}
        if isinstance(counts, list) and counts:
            for t in COUNT_TABLES:
                got = counts[0].get(f"[{t}]")
                e = exp.get(t)
                cmp[t] = {"model": got, "sql": e, "diff_pct": None if not e or got is None else round(100 * (got - e) / e, 1)}
        res["row_counts"] = cmp
        log("  row counts (model at refresh vs SQL re-run now):", {t: (v["model"], v["sql"], v["diff_pct"]) for t, v in cmp.items()})
    kill(pid)
    time.sleep(5)
    results[code] = res
    (OUT / "site_files_results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
log("ALL DONE")
