"""Automatic refresh of the PRIME ELS Hypercare dashboards, every HOT-tier interval (config/refresh_policy.csv, 60 min).

    py tools/auto_refresh.py --once            # one cycle (what the scheduled task runs)
    py tools/auto_refresh.py --install         # Windows scheduled task every HOT Every_Minutes, aligned to :00 + Service schedule
    py tools/auto_refresh.py --uninstall

Each cycle (tier by clock: HOT + WARM every hour, PLAN every 4 h, COLD once a day at COLD_HOUR):
  1. Power BI Desktop: the open 'WH Hypercare KPI' model (all sites, one partition per site) is refreshed through its local engine (refresh_desktop.ps1).
  2. Power BI Service: the published model (dist/ALL_SITES/_published.json) gets an enhanced refresh of the tier's tables
     (needs a Premium / PPU / Fabric workspace). On a Pro / My workspace the API only allows 8 refreshes a day -> one
     full refresh is sent only in COLD / WARM slots that fit that budget.
Log: tools/_auto_refresh.log
"""
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import requests

try:  # corporate TLS inspection: trust the Windows certificate store
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import replica_auth as auth  # noqa: E402

LOG = HERE / "_auto_refresh.log"
TASK = "PRIME ELS Hypercare refresh"
COLD_HOUR = 5
PRO_SLOTS = {5, 7, 9, 11, 13, 15, 17, 19}          # 8 refreshes / day allowed on shared capacity
PBI = "https://api.powerbi.com/v1.0/myorg"


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def policy():
    return {r["Tier"]: r for r in csv.DictReader(open(ROOT / "config" / "refresh_policy.csv", encoding="utf-8-sig"))}


def due_tiers(now, pol):
    """Every tier whose Every_Minutes divides the 15-minute slot of the day is due (HOT every slot, WARM on the hour,
    PLAN every 4 h...); COLD = the full model once a day at COLD_HOUR."""
    if now.hour == COLD_HOUR and now.minute < 15:
        return ["COLD"]
    slot = (now.hour * 60 + now.minute) // 15 * 15
    return [t for t, r in pol.items() if t != "COLD" and slot % max(15, int(r["Every_Minutes"])) == 0]


def tables_for(tiers, pol):
    if "COLD" in tiers:
        return "*"
    # only tables the built model has (e.g. the SAP / CDL tables are left out by config/build_options.csv) - an unknown table fails the refresh
    from urllib.parse import unquote
    built = {unquote(p.stem) for p in (ROOT / "dist" / "ALL_SITES").glob("*.SemanticModel/definition/tables/*.tmdl")}
    names = []
    for t in tiers:
        names += [n for n in pol[t]["Tables"].split("|") if n and n not in names and (not built or n in built)]
    return "|".join(names)


def refresh_desktop(tables, exclude=""):
    ps = HERE / "refresh_desktop.ps1"
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps), "-Tables", tables]
    if exclude:
        args += ["-ExcludeTitle", exclude]
    r = subprocess.run(args, capture_output=True, text=True, timeout=1500)
    for ln in (r.stdout + r.stderr).strip().splitlines():
        if ln.strip():
            if "NO_OPEN_MODEL" in ln:                 # nothing open in Desktop = nothing to refresh live (not an error)
                log("  desktop | skipped - no report open in Power BI Desktop (the shared copy is published at the snapshot hours)")
                continue
            log(f"  desktop | {ln.strip()}")


def publish_snapshot(tables):
    """Snapshot hour: refresh the all-sites .pbix (opened minimized when Desktop is closed), save it WITH data, upload it to SharePoint."""
    py = Path(sys.executable).with_name("python.exe") if Path(sys.executable).name.lower() == "pythonw.exe" else Path(sys.executable)
    r = subprocess.run([str(py), str(HERE / "snapshot_pbix.py"), "--publish", "--tables", tables],
                       capture_output=True, text=True, timeout=3000, encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
    keep = [ln for ln in lines if not ln.endswith(" MB") or "saved" in ln] if r.returncode == 0 else lines
    for ln in keep[-40:]:
        log(f"  snapshot | {ln[:300]}")
    if r.returncode == 3:
        log("  snapshot | deferred (locked screen or too little memory - reason above); the 'on unlock' task publishes the copy later")
    elif r.returncode != 0:
        log(f"  snapshot | FAILED (exit {r.returncode}) - the SharePoint copy keeps its previous data; next try at the next snapshot hour / unlock")


def pbi_headers():
    app = auth._load_msal_app()[0]
    tok = app.acquire_token_silent(["https://analysis.windows.net/powerbi/api/.default"], account=app.get_accounts()[0])["access_token"]
    return {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}


def refresh_service(tier, tables, now):
    H = pbi_headers()
    for pub in [p for p in (ROOT / "dist" / "ALL_SITES" / "_published.json",) if p.exists()]:
        p = json.loads(pub.read_text(encoding="utf-8"))
        base = f"{PBI}/datasets/{p['semanticModelId']}" if p["workspace"] == "My workspace" else f"{PBI}/groups/{p['workspaceId']}/datasets/{p['semanticModelId']}"
        site = pub.parent.name
        last = requests.get(f"{base}/refreshes?$top=1", headers=H, timeout=60).json().get("value", [])
        if last and last[0].get("status") == "Unknown":
            log(f"  service | {site}: previous refresh still running - skipped")
            continue
        err = (last[0].get("serviceExceptionJson") or "") if last and last[0].get("status") == "Failed" else ""
        # replicas unreachable from the Service (no credential / gateway / workspace identity / private network): one try a day
        # (COLD) detects when access is granted; the snapshot publisher keeps the workspace copy current meanwhile
        if any(k in err for k in ("NoCredential", "CredentialsNotSpecified", "Gateway", "DM_GWPipeline", "ASWL", "WorkspaceIdentity",
                                  "not accessible", "network-related")) and tier != "COLD":
            log(f"  service | {site}: waiting for replica credentials / gateway access (last refresh failed) - retried daily at {COLD_HOUR:02d}:00")
            continue
        body = {"type": "full", "commitMode": "transactional", "retryCount": 1, "applyRefreshPolicy": False}
        if tables != "*":
            body["objects"] = [{"table": t} for t in tables.split("|")]
        r = requests.post(f"{base}/refreshes", headers=H, json=body, timeout=60)
        if r.status_code == 202:
            log(f"  service | {site}: {tier} enhanced refresh accepted")
            continue
        # shared capacity (Pro / My workspace): no enhanced refresh -> plain refresh only inside the 8-per-day budget
        if now.hour in PRO_SLOTS and tier in ("WARM", "COLD"):
            r2 = requests.post(f"{base}/refreshes", headers=H, json={"notifyOption": "NoNotification"}, timeout=60)
            log(f"  service | {site}: shared capacity -> full refresh {'accepted' if r2.status_code == 202 else 'refused ' + r2.text[:160]}")
        else:
            log(f"  service | {site}: enhanced refresh not available ({r.status_code}) - Premium/PPU/Fabric workspace needed for 15-min refresh")


def set_service_schedule():
    """Safety net in the Service: daily schedule at the Pro-allowed slots (Premium users can raise it to 48 slots)."""
    H = pbi_headers()
    for pub in [p for p in (ROOT / "dist" / "ALL_SITES" / "_published.json",) if p.exists()]:
        p = json.loads(pub.read_text(encoding="utf-8"))
        base = f"{PBI}/datasets/{p['semanticModelId']}" if p["workspace"] == "My workspace" else f"{PBI}/groups/{p['workspaceId']}/datasets/{p['semanticModelId']}"
        body = {"value": {"enabled": True, "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                          "times": [f"{h:02d}:00" for h in sorted(PRO_SLOTS)], "localTimeZoneId": "Singapore Standard Time", "notifyOption": "MailOnFailure"}}
        r = requests.patch(f"{base}/refreshSchedule", headers=H, json=body, timeout=60)
        log(f"schedule | {pub.parent.name}: {'set' if r.status_code < 300 else 'not set - ' + r.text[:200]}")


def cycle():
    now = dt.datetime.now()
    pol = policy()
    tiers = due_tiers(now, pol)
    if not tiers:
        # a run outside the tier slots (manual run, task started late or installed unaligned) still refreshes the HOT tables
        log(f"cycle at {now:%H:%M} is outside the {pol['HOT']['Every_Minutes']}-min slots - running the HOT tier")
        tiers = ["HOT"]
    tier = "COLD" if "COLD" in tiers else ("WARM" if len(tiers) > 1 else tiers[0])
    tables = tables_for(tiers, pol)
    log(f"cycle {'+'.join(tiers)} ({'full model' if tables == '*' else str(len(tables.split('|'))) + ' tables'})")
    quiet = {r["Setting"]: int(r["Value"]) for r in csv.DictReader(open(ROOT / "config" / "desktop_refresh.csv", encoding="utf-8-sig"))}
    qf, qt = quiet.get("Quiet_From_Hour", 0), quiet.get("Quiet_To_Hour", 0)
    snap = now.minute < 15 and now.hour in {quiet.get("Snapshot_Hour_1", -1), quiet.get("Snapshot_Hour_2", -1)} - {-1}
    pbix_title = "WH Hypercare KPI - ALL_SITES"          # tools/snapshot_pbix.py PBIX_TITLE - refreshed by the snapshot step only
    if qf <= now.hour < qt and tier != "COLD":
        log(f"  desktop | skipped - office hours {qf:02d}:00-{qt:02d}:00 (config/desktop_refresh.csv): no 'Working on it' while you work; "
            f"Desktop refresh resumes at {qt:02d}:00, the Service refreshes as usual")
    else:
        try:
            refresh_desktop(tables, exclude=pbix_title if snap else "")
        except Exception as e:  # keep the Service part running
            log(f"  desktop | ERROR {e!r}"[:300])
    if snap:
        try:
            publish_snapshot(tables)
        except Exception as e:
            log(f"  snapshot | ERROR {e!r}"[:300])
    try:
        refresh_service(tier, tables, now)
    except Exception as e:
        log(f"  service | ERROR {e!r}"[:300])


def install():
    py = sys.executable.replace("python.exe", "pythonw.exe")
    if not Path(py).exists():
        py = sys.executable
    cmd = f'"{py}" "{Path(__file__).resolve()}" --once'
    # the task runs as often as the HOT tier (config/refresh_policy.csv) - one source for the scheduler, the tiers and the banner 'next refresh'
    every = max(15, int(policy()["HOT"]["Every_Minutes"]))
    # start ON a slot boundary: repeating every N min from 00:00 runs at 00:00 + k x N (every 30 min -> :00 / :30), exactly the slots
    # due_tiers expects (WARM on the hour ...); no /SD = no locale-dependent date format
    now = dt.datetime.now()
    nxt = ((now.hour * 60 + now.minute) // every + 1) * every
    start = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=nxt)
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(every), "/ST", "00:00", "/TN", TASK, "/TR", cmd],
                       capture_output=True, text=True)
    log(f"install | scheduled task '{TASK}' every {every} min on the {every}-min grid from 00:00 (next run ~{start:%H:%M}): "
        f"{(r.stdout or r.stderr).strip()}")
    if r.returncode:
        raise SystemExit(f"schtasks /Create failed ({r.returncode}) - task NOT installed")
    # schtasks defaults stop a run when the laptop goes on battery (seen 12-Nov: a run cut off at 13:24, nothing logged) and cap it at 72 h
    s = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                        f"$s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) "
                        f"-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; Set-ScheduledTask -TaskName '{TASK}' -Settings $s | Out-Null; "
                        f"(Get-ScheduledTask -TaskName '{TASK}').Settings.DisallowStartIfOnBatteries"], capture_output=True, text=True)
    log(f"install | '{TASK}': runs on battery, 3 h limit ({'ok' if 'False' in s.stdout else 'NOT set: ' + (s.stderr or s.stdout).strip()[:160]})")
    install_unlock_task(py)
    set_service_schedule()


UNLOCK_TASK = "PRIME ELS Hypercare snapshot (on unlock)"


def install_unlock_task(py):
    """Workstation unlock / logon -> publish the SharePoint .pbix when its copy is older than 10 h (a locked screen blocks the timed
    copies: Desktop cannot renew its replica sign-in there). 10 min pause first; one run at a time."""
    snap = HERE / "snapshot_pbix.py"
    ps = (f"$a = New-ScheduledTaskAction -Execute '{py}' -Argument '\"{snap}\" --catch-up 10 --delay 600 --log'\n"
          "$cls = Get-CimClass -ClassName MSFT_TaskSessionStateChangeTrigger -Namespace Root/Microsoft/Windows/TaskScheduler\n"
          "$t1 = New-CimInstance -CimClass $cls -ClientOnly; $t1.StateChange = 8; $t1.UserId = \"$env:USERDOMAIN\\$env:USERNAME\"; $t1.Enabled = $true\n"
          "$t2 = New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\"\n"
          "$s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable "
          "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries\n"
          f"Register-ScheduledTask -TaskName '{UNLOCK_TASK}' -Action $a -Trigger @($t1, $t2) -Settings $s -Force | Out-Null\n"
          f"(Get-ScheduledTask -TaskName '{UNLOCK_TASK}').State")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    log(f"install | task '{UNLOCK_TASK}': {(r.stdout or r.stderr).strip()[:200]}")
    if r.returncode or "Ready" not in r.stdout:
        raise SystemExit(f"unlock task NOT installed: {(r.stderr or r.stdout).strip()[:300]}")


def uninstall():
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True, text=True)
    log(f"uninstall | {(r.stdout or r.stderr).strip()}")
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", UNLOCK_TASK], capture_output=True, text=True)
    log(f"uninstall | {(r.stdout or r.stderr).strip()}")


if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    elif "--uninstall" in sys.argv:
        uninstall()
    else:
        cycle()
