"""Refresh a published workspace model TABLE BY TABLE (enhanced refresh API) and report each table's result.

    py tools/service_refresh.py --site JAKARTA [--workspace "<workspace>"] [--tables "A,B"] [--timeout-min 30]
    py tools/service_refresh.py --name "WH Hypercare KPI" ...        # the multi-site model
    py tools/service_refresh.py --site JAKARTA --status              # per-table progress of the refresh now running
    py tools/service_refresh.py --site JAKARTA --cancel              # cancel the refresh now running
    py tools/service_refresh.py --site JAKARTA --all [--parallel 6]  # ONE refresh of the whole model, per-table progress every 30 s
    py tools/service_refresh.py --site JAKARTA --test ...            # the TEST model (build_pbip.py JAKARTA --service --test-server S)

Why table by table: one slow / failing replica query no longer hides the others. Small tables (config, inputs, dims) go first,
then each data table on its own, so the log shows which table failed, its error and its time. A failed table is retried once.
Calculated tables / relationships are recalculated at the end (type=calculate). Writes _uitest/service_refresh_<model>.csv.
Heartbeat every 30 s. Exit 1 when any table failed.
"""
import csv
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from publish import token, workspace_id, H, FAB  # noqa: E402

ROOT = HERE.parent
OUT = ROOT.parent / "_uitest"
PBI = "https://api.powerbi.com/v1.0/myorg"
args = sys.argv[1:]
KNOWN = {"--site", "--name", "--workspace", "--tables", "--timeout-min", "--status", "--cancel", "--all", "--parallel", "--test",
         "--calculate", "--config"}
if "-h" in args or "--help" in args or any(a.startswith("-") and a not in KNOWN for a in args):
    print(__doc__)
    sys.exit(0 if ("-h" in args or "--help" in args) else 2)


def opt(n, d=None):
    return args[args.index(n) + 1] if n in args else d


def ph():
    return {"Authorization": "Bearer " + token("https://analysis.windows.net/powerbi/api/.default"), "Content-Type": "application/json"}


def call(method, url, **kw):
    """Retry transient network / TLS drops (seen 20-Nov: SSLEOFError while polling)."""
    for i in range(5):
        try:
            return requests.request(method, url, headers=ph(), timeout=90, **kw)
        except requests.RequestException as e:
            print(f"   network retry {i + 1}/5: {type(e).__name__}", flush=True)
            time.sleep(10 * (i + 1))
    raise SystemExit(f"{method} {url} failed 5 times")


def model_tables(model_dir: Path):
    """(table, kind, size) from the model's TMDL: kind m = Power Query partition, calc = calculated table, policy = incremental refresh."""
    out = []
    for f in sorted((model_dir / "definition" / "tables").glob("*.tmdl")):
        t = f.read_text(encoding="utf-8")
        name = next(ln[6:].strip().strip("'").replace("''", "'") for ln in t.splitlines() if ln.startswith("table "))
        out.append((name, "calc" if "= calculated" in t else "policy" if "\trefreshPolicy" in t else
                    "embedded" if "Binary.Decompress(Binary.FromText(" in t or 'Book = "embedded"' in t else "m", len(t)))
    return out


def running(base):
    j = call("GET", f"{base}/refreshes?$top=1").json().get("value", [])
    return j[0] if j and j[0].get("status") in ("Unknown", "NotStarted", "InProgress") else None


def wait(base, rid, label, limit_s):
    t0 = time.time()
    while True:
        r = call("GET", f"{base}/refreshes/{rid}")
        j = r.json() if r.ok else {}
        st = j.get("extendedStatus") or j.get("status") or f"HTTP {r.status_code}"
        if st in ("Completed", "Failed", "Cancelled", "Disabled", "TimedOut"):
            return st, j, time.time() - t0
        if time.time() - t0 > limit_s:
            call("DELETE", f"{base}/refreshes/{rid}")
            return "TimedOut", j, time.time() - t0
        print(f"   [{time.strftime('%H:%M:%S')}] {label}: {st} ({time.time() - t0:.0f}s)", flush=True)
        time.sleep(30)


def run_all(base, label, body, limit):
    """One enhanced refresh; prints done / running tables every 30 s; returns '<label>: <status>'."""
    r = call("POST", f"{base}/refreshes", json=body)
    if r.status_code != 202:
        print(f"{label}: refused HTTP {r.status_code} {r.text[:300]}", flush=True)
        return f"{label}: refused"
    rid = r.headers.get("Location", "").rstrip("/").split("/")[-1]
    t0 = time.time()
    while True:
        j = call("GET", f"{base}/refreshes/{rid}").json()
        st = j.get("extendedStatus") or j.get("status")
        objs = j.get("objects") or []
        done = sum(1 for o in objs if o.get("status") == "Completed")
        bad = [o.get("table") for o in objs if o.get("status") == "Failed"]
        busy = [o.get("table") for o in objs if o.get("status") not in ("Completed", "Failed")]
        print(f"[{time.strftime('%H:%M:%S')}] {label}: {st} {time.time() - t0:.0f}s, {done}/{len(objs)} done"
              + (f", FAILED {', '.join(bad)}" if bad else "")
              + (f"; running {', '.join(busy[:5])}{' ...' if len(busy) > 5 else ''}" if busy and st not in ("Completed", "Failed") else ""),
              flush=True)
        if st in ("Completed", "Failed", "Cancelled", "TimedOut"):
            if st != "Completed":
                print("   error: " + err_text(j), flush=True)
            return f"{label}: {st}"
        if time.time() - t0 > limit:
            call("DELETE", f"{base}/refreshes/{rid}")
            print(f"   TIMED OUT after {limit}s - cancelled; still running: {', '.join(busy)}", flush=True)
            return f"{label}: TimedOut"
        time.sleep(30)


def err_text(j):
    msgs = []
    for m in j.get("messages") or []:
        msgs.append(f"{m.get('type', '')}: {m.get('message', '')}"[:400])
    for o in j.get("objects") or []:
        if o.get("status") not in (None, "Completed"):
            msgs.append(f"{o.get('table')}: {o.get('status')}")
    if j.get("serviceExceptionJson"):
        msgs.append(str(j["serviceExceptionJson"])[:400])
    return " | ".join(msgs)


def main():
    code = (opt("--site") or "").upper()
    test = "--test" in args
    name = opt("--name") or (f"WH Hypercare KPI - {code}{' (TEST)' if test else ''}" if code else "WH Hypercare KPI")
    model_dir = ROOT / "dist" / (("_service_test" if test else "_service") if code else "") / (code or "ALL_SITES") / f"{name}.SemanticModel"
    ws, wsdisp = workspace_id(opt("--workspace"))
    items = requests.get(f"{FAB}/workspaces/{ws}/semanticModels", headers=H(), timeout=60).json().get("value", [])
    sm = next((i["id"] for i in items if i["displayName"] == name), None)
    if not sm:
        raise SystemExit(f"model {name!r} not in {wsdisp}")
    base = f"{PBI}/groups/{ws}/datasets/{sm}"
    print(f"model {name} ({sm}) in {wsdisp}", flush=True)

    cur = running(base)
    if "--status" in args or "--cancel" in args:
        if not cur:
            print("no refresh running")
            return 0
        print(f"running since {cur.get('startTime')} type {cur.get('refreshType')} id {cur.get('requestId')}")
        d = call("GET", f"{base}/refreshes/{cur['requestId']}").json()
        for o in d.get("objects") or []:
            print(f"   {o.get('table')}: {o.get('status')}")
        if "--cancel" in args:
            r = call("DELETE", f"{base}/refreshes/{cur['requestId']}")
            print(f"cancel: HTTP {r.status_code} {r.text[:200]}")
        return 0
    if cur:
        raise SystemExit(f"a refresh is already running (since {cur.get('startTime')}) - wait, or --cancel it first")

    tabs = model_tables(model_dir) if model_dir.exists() else []
    if not tabs:
        raise SystemExit(f"{model_dir} not found - build it first (py tools/build_pbip.py {code} --service)")
    if "--calculate" in args or "--config" in args:
        # after a republish imported data is kept: --calculate recalculates the calculated tables (~40 s); --config first reloads
        # the embedded config tables (Cfg_* / Input *: new RCA texts, thresholds, guide rows) - no replica query, then calculates
        res = []
        if "--config" in args:
            cfg = [t for t, k, _ in tabs if k == "embedded" or (k == "m" and (t.startswith("Cfg_") or t.startswith("Input ")))]
            res.append(run_all(base, "config tables", {"type": "full", "commitMode": "partialBatch", "maxParallelism": 6, "retryCount": 1,
                                                       "objects": [{"table": x} for x in cfg]}, 1800))
        res.append(run_all(base, "calculate", {"type": "calculate", "commitMode": "transactional", "retryCount": 1}, 900))
        print("RESULT: " + " | ".join(res))
        return 0 if all(x.endswith("Completed") for x in res) else 1
    if "--all" in args:     # the whole model in 2 enhanced refreshes (tables in parallel), per-table progress every 30 s
        # 1) every plain table with partialBatch: each table commits (usable in the report) as soon as it is loaded - transactional
        #    shows 0/85 until the very last table is done (20-Nov: 19 min of '0/85', every visual erroring meanwhile);
        # 2) the incremental-refresh tables: the Service only allows transactional for refresh-policy tables (20-Nov, measured);
        # 3) calculate: calculated tables (Cfg_Threshold, KPI Scorecard, Site Summary ...) over what is loaded
        par, limit = int(opt("--parallel", "12")), int(opt("--timeout-min", "60")) * 60
        plain = [t for t, k, _ in tabs if k in ("m", "embedded")]
        policy = [t for t, k, _ in tabs if k == "policy"]
        res = []
        for label, objs, mode in (("tables", plain, "partialBatch"), ("incremental tables", policy, "transactional")):
            if objs:
                res.append(run_all(base, label, {"type": "full", "commitMode": mode, "maxParallelism": par, "retryCount": 1,
                                                 "applyRefreshPolicy": True, "objects": [{"table": x} for x in objs]}, limit))
        res.append(run_all(base, "calculate", {"type": "calculate", "commitMode": "transactional", "retryCount": 1}, 900))
        print("RESULT: " + " | ".join(res))
        return 0 if all(x.endswith("Completed") for x in res) else 1
    only = {x.strip().lower() for x in (opt("--tables") or "").split(",") if x.strip()}
    data = [(t, n) for t, k, n in tabs if k in ("m", "embedded", "policy") and (not only or t.lower() in only)]
    data.sort(key=lambda x: x[1])                       # small (config / dims) first
    limit = int(opt("--timeout-min", "30")) * 60
    rows, failed = [], []
    for i, (t, _) in enumerate(data, 1):
        for attempt in (1, 2):
            body = {"type": "full", "commitMode": "transactional", "retryCount": 0, "objects": [{"table": t}],
                    "applyRefreshPolicy": True}     # incremental tables: create / refresh only the policy partitions
            r = call("POST", f"{base}/refreshes", json=body)
            if r.status_code != 202:
                st, j, secs = f"HTTP {r.status_code}", {"messages": [{"message": r.text[:300]}]}, 0
            else:
                rid = r.headers.get("Location", "").rstrip("/").split("/")[-1] or r.headers.get("RequestId")
                st, j, secs = wait(base, rid, f"{i}/{len(data)} {t}", limit)
            print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(data)} {t}: {st} in {secs:.0f}s"
                  + (f" (attempt {attempt})" if attempt > 1 else ""), flush=True)
            if st == "Completed":
                break
            e = err_text(j)
            print(f"      error: {e}", flush=True)
        rows.append({"Table": t, "Status": st, "Seconds": round(secs), "Attempts": attempt, "Error": "" if st == "Completed" else e})
        if st != "Completed":
            failed.append(t)
    if not only:
        r = call("POST", f"{base}/refreshes", json={"type": "calculate", "commitMode": "transactional", "retryCount": 1})
        if r.status_code == 202:
            rid = r.headers.get("Location", "").rstrip("/").split("/")[-1]
            st, j, secs = wait(base, rid, "calculate (calculated tables, relationships)", limit)
            print(f"[{time.strftime('%H:%M:%S')}] calculate: {st} in {secs:.0f}s", flush=True)
            rows.append({"Table": "(calculate)", "Status": st, "Seconds": round(secs), "Attempts": 1,
                         "Error": "" if st == "Completed" else err_text(j)})
            if st != "Completed":
                failed.append("(calculate)")
    OUT.mkdir(exist_ok=True)
    f = OUT / f"service_refresh_{(code or 'ALL').lower()}.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["Table", "Status", "Seconds", "Attempts", "Error"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows) - len(failed)}/{len(rows)} OK -> {f}")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
