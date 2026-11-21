"""Real-data TEST environment in the workspace for a site whose replica the Service cannot reach (no shared gateway connection).

    py tools/test_env.py BINHDUONG [--workspace "<workspace>"] [--no-build] [--no-refresh] [--tests] [--min-free-gb 2]

1. build   : py tools/build_pbip.py <SITE>  -> dist/<SITE> (same generator, pages and measures as the Service file)
2. refresh : open the .pbip in Power BI Desktop (minimized), full refresh from the replica (Desktop reaches it with your sign-in),
             measure check (no measure in error), Save As dist/_testenv/WH Hypercare KPI - <SITE> (TEST data).pbix, close
3. import  : the .pbix WITH its data into the workspace as 'WH Hypercare KPI - <SITE> (TEST data)' (Imports API, CreateOrOverwrite
             keeps the report link). The Service does not refresh it - it is a snapshot of real data to test every visual on.
4. --tests : the workspace test round on it - alerts, every visual x day, every slicer value, every field (tools/*.py --service).
Writes dist/_testenv/<SITE>_published.json (workspace / model / report ids, snapshot time). Heartbeat every 30 s; stops with a
clear message on any failure (nothing fails silently).
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import snapshot_pbix as S  # noqa: E402
from publish import token, workspace_id  # noqa: E402

PBI = "https://api.powerbi.com/v1.0/myorg"
args = sys.argv[1:]


def opt(n, d=None):
    return args[args.index(n) + 1] if n in args else d


def run(cmd, tag):
    S.hb(f"{tag}: {' '.join(cmd)}")
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    last = []
    for ln in p.stdout:
        last = (last + [ln.rstrip()])[-12:]
        if any(k in ln for k in ("gate", "layout", "rror", "FAIL", "heartbeat", "DONE", "defects", "->")):
            S.hb("    " + ln.rstrip()[:220])
    if p.wait() != 0:
        raise S.Fail(f"{tag} failed (exit {p.returncode}):\n" + "\n".join(last))


def import_pbix(path, name, ws):
    h = {"Authorization": "Bearer " + token("https://analysis.windows.net/powerbi/api/.default")}
    r = None
    for attempt in range(1, 6):
        try:
            with open(path, "rb") as f:
                r = requests.post(f"{PBI}/groups/{ws}/imports?datasetDisplayName={quote(name)}&nameConflict=CreateOrOverwrite",
                                  headers=h, files={"file": (path.name, f, "application/octet-stream")}, timeout=900)
            if r.status_code == 202:
                break
            S.hb(f"  import refused {r.status_code} {r.text[:200]} (attempt {attempt}/5)")
        except requests.exceptions.RequestException as e:
            S.hb(f"  import retry {attempt}/5 ({type(e).__name__})")
        time.sleep(15 * attempt)
    if r is None or r.status_code != 202:
        raise S.Fail(f"workspace import refused: {getattr(r, 'status_code', '-')} {getattr(r, 'text', '')[:300]}")
    iid, t0, beat = r.json()["id"], time.time(), time.time()
    while time.time() - t0 < 1200:
        time.sleep(10)
        j = requests.get(f"{PBI}/groups/{ws}/imports/{iid}", headers=h, timeout=60).json()
        if j.get("importState") in ("Succeeded", "Failed"):
            break
        if time.time() - beat > 30:
            S.hb(f"  import {j.get('importState')} ({time.time() - t0:.0f} s)")
            beat = time.time()
    if j.get("importState") != "Succeeded":
        raise S.Fail(f"import {j.get('importState')}: {json.dumps(j.get('error'))[:300]}")
    return j["datasets"][0]["id"], j["reports"][0]["id"]


def main():
    codes = [a.upper() for a in args if not a.startswith("--") and a not in (opt("--workspace"), opt("--min-free-gb"))]
    if len(codes) != 1:
        sys.exit(__doc__)
    code = codes[0]
    name = f"WH Hypercare KPI - {code} (TEST data)"
    pbip = ROOT / "dist" / code / f"WH Hypercare KPI - {code}.pbip"
    out_dir = ROOT / "dist" / "_testenv"
    out_dir.mkdir(parents=True, exist_ok=True)
    pbix = out_dir / f"{name}.pbix"
    ws, wsname = workspace_id(opt("--workspace", "<workspace>"))
    if opt("--min-free-gb"):
        S.MIN_FREE_GB = float(opt("--min-free-gb"))
    try:
        if "--no-build" not in args:
            run([sys.executable, "-u", str(HERE / "build_pbip.py"), code], "build")
        if "--no-refresh" not in args:
            title = pbip.stem
            for d in S.desktops():                 # one copy of the project at a time (memory, file locks)
                if d["Title"] in (title, pbix.stem):
                    S.close(d["Id"])
            if S.free_gb() < S.MIN_FREE_GB:
                raise S.Fail(f"only {S.free_gb():.1f} GB memory free (need {S.MIN_FREE_GB}); biggest apps: {S.top_memory()}")
            pid = S.open_file(pbip, title)
            try:
                S.refresh(title, "*")
                S.measure_errors(pid)
                S.save_as(pid, pbix)
                S.hb(f"saved {pbix.name} ({pbix.stat().st_size / 1e6:.1f} MB)")
            finally:
                S.close(pid)
        if not pbix.exists():
            raise S.Fail(f"{pbix} not found - run without --no-refresh first")
        S.hb(f"importing {pbix.name} into '{wsname}' as '{name}'")
        ds, rep = import_pbix(pbix, name, ws)
        info = {"site": code, "workspace": wsname, "workspaceId": ws, "semanticModelId": ds, "reportId": rep,
                "reportUrl": f"https://app.powerbi.com/groups/{ws}/reports/{rep}", "snapshot": time.strftime("%Y-%m-%d %H:%M"),
                "note": "pbix import with data inside - not refreshed by the Service (no gateway connection for this replica)"}
        (out_dir / f"{code}_published.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
        S.hb(f"TEST environment ready: {info['reportUrl']}")
        if "--tests" in args:
            target = f"{ws}/{ds}"
            rep_def = str(ROOT / "dist" / code / f"WH Hypercare KPI - {code}.Report" / "definition")
            model = str(ROOT / "dist" / code / f"WH Hypercare KPI - {code}.SemanticModel")
            run([sys.executable, "-u", str(HERE / "alert_test.py"), "--service", target, "--site", code], "alerts")
            run([sys.executable, "-u", str(HERE / "visual_replay.py"), "--service", target, "--report", rep_def, "--sites", code, "--days", "3"], "visuals")
            run([sys.executable, "-u", str(HERE / "visual_replay.py"), "--service", target, "--report", rep_def, "--sites", code, "--days", "1",
                 "--filters", "3"], "filters")
            run([sys.executable, "-u", str(HERE / "audit_fields.py"), "--service", target, "--model", model], "fields")
    except S.Fail as e:
        S.hb(f"STOPPED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
