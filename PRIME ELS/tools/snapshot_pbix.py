"""Publish the all-sites report as ONE .pbix WITH its data to the PRIME ELS SharePoint folder - what new users open (no refresh, no sign-in).

    py tools/snapshot_pbix.py --from-pbip     # after a rebuild: open dist/ALL_SITES .pbip, full refresh, Save As the .pbix, upload, close
    py tools/snapshot_pbix.py --publish       # refresh the .pbix (opened minimized when Desktop is closed), save, upload, close if opened here
    py tools/snapshot_pbix.py --catch-up 10 --delay 600   # (unlock / logon task) publish when the SharePoint copy is older than 10 h
    py tools/snapshot_pbix.py --save-only     # save the open .pbix (no refresh, no upload)
    py tools/snapshot_pbix.py --copilot       # Copilot AI instructions + descriptions (tools/copilot_ai.py) into the .pbix, save, upload - no refresh
    options: --no-upload  --tables "A|B" (default: HOT + WARM tiers of config/refresh_policy.csv)  --log (also write tools/_auto_refresh.log)
             --min-free-gb N (hand-started runs: memory needed before opening / refreshing, default 2)
Every publish also writes the Copilot AI instructions into the model before saving (copilot_sync).

Runs: tools/auto_refresh.py at Snapshot_Hour_1 / _2 of config/desktop_refresh.csv, and the 'on unlock' task (auto_refresh.py --install).
A LOCKED screen defers the run (exit 3): Power BI Desktop cannot renew its replica sign-in there (measured 5-Nov: Minhang stalled,
the replica itself answered in seconds) - the unlock task catches up.
Power BI Desktop has no API to save a .pbix: the tool drives the Save / Save As UI (UI Automation + window messages - no keyboard,
no mouse, no focus change). Every step prints a heartbeat and stops with a clear message; nothing fails silently.
"""
import ctypes
import ctypes.wintypes as W
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PBIP = ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.pbip"
PBIX = ROOT / "dist" / "_share" / "WH Hypercare KPI - ALL_SITES.pbix"
PBIP_TITLE = "WH Hypercare KPI"                      # Desktop window title of the project
PBIX_TITLE = PBIX.stem                               # ... and of the saved file
u32 = ctypes.windll.user32
u32.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u32.SendMessageW.restype = ctypes.c_ssize_t


class Fail(Exception):
    pass


class Defer(Fail):
    """Not now (locked screen, too little memory) - logged as deferred, exit 3; the next snapshot hour / unlock tries again."""


# ---- every child process (refresh script, Desktop windows this tool opens) dies with this process: Task Scheduler ends a task by
# killing only its main process - on 12-Nov that left a refresh retrying for hours with nobody to save or upload its result
class _JOBINFO(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", W.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD),
                ("IoInfo", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


_k32 = ctypes.windll.kernel32
_k32.CreateJobObjectW.restype = W.HANDLE
_k32.OpenProcess.restype = W.HANDLE
_JOB = _k32.CreateJobObjectW(None, None)
_ji = _JOBINFO()
_ji.LimitFlags = 0x2000                                  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_k32.SetInformationJobObject(_JOB, 9, ctypes.byref(_ji), ctypes.sizeof(_ji))   # JobObjectExtendedLimitInformation


def bind(pid):
    """Tie a process to this tool's lifetime (its later children follow it into the job)."""
    h = _k32.OpenProcess(0x0101, False, pid)             # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    ok = bool(h) and bool(_k32.AssignProcessToJobObject(_JOB, h))
    if h:
        _k32.CloseHandle(h)
    return ok


REFRESH_MAX_MIN = 45     # a normal all-sites refresh is 8-11 min; beyond this the PC is paging or a source hangs - stop, close, log


LOG = None                                           # --log: also append to tools/_auto_refresh.log (scheduled runs have no console)
STATE = HERE / "_snapshot_state.json"                # last successful upload (the unlock catch-up reads it)


def hb(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  snapshot | {msg}\n")


def locked():
    """Locked screen: Power BI Desktop cannot renew its replica sign-in (passwordless / Windows Hello) and the refresh stalls."""
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq LogonUI.exe", "/NH"], capture_output=True, text=True)
    return "LogonUI.exe" in r.stdout


def last_upload_age_h():
    try:
        t = json.loads(STATE.read_text(encoding="utf-8"))["last_upload"]
        return (time.time() - time.mktime(time.strptime(t, "%Y-%m-%d %H:%M:%S"))) / 3600
    except (OSError, KeyError, ValueError):
        return 1e9


def ps(script, timeout=120):
    """Run a Windows PowerShell 5.1 snippet (UI Automation lives in .NET Framework)."""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
        f.write(script)
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f.name],
                           capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    finally:
        os.unlink(f.name)


def desktops():
    out = ps("Get-Process PBIDesktop -ErrorAction SilentlyContinue | ForEach-Object { "
             "$e = [bool](Get-CimInstance Win32_Process -Filter \"Name='msmdsrv.exe' AND ParentProcessId=$($_.Id)\"); "
             "[pscustomobject]@{Id=$_.Id; Title=$_.MainWindowTitle; Engine=$e} } | ConvertTo-Json -Compress")
    if not out:
        return []
    d = json.loads(out)
    return d if isinstance(d, list) else [d]


def find(title):
    return next((d["Id"] for d in desktops() if d["Title"] == title and d["Engine"]), None)


def open_file(path, title, timeout=480):
    before = {d["Id"] for d in desktops()}
    hb(f"opening {path.name} in Power BI Desktop (minimized)")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath '{path}' -WindowStyle Minimized"], check=True)
    t0 = time.time()
    bound = set()
    while time.time() - t0 < timeout:
        time.sleep(15)
        new = [d for d in desktops() if d["Id"] not in before]
        for d in new:                                     # tie it to this tool at once: a failed open must not leave a window behind
            if d["Id"] not in bound and bind(d["Id"]):
                bound.add(d["Id"])
        st = f"{new[0]['Title'] or '(starting)'}, engine {'up' if new[0]['Engine'] else 'not yet'}" if new else "no window yet"
        hb(f"  opening {int(time.time() - t0)} s: {st}")
        if new and new[0]["Title"] == title and new[0]["Engine"]:
            time.sleep(15)                                # report finishes loading after the title appears
            return new[0]["Id"]
    for d in desktops():                                  # 18-Nov: a 480 s timeout left the window open for hours, holding memory
        if d["Id"] not in before:
            close(d["Id"])
    raise Fail(f"{path.name} did not open within {timeout} s - open it by hand to see the message Power BI shows")


def refresh(title, tables):
    """-> sites refreshed. A partial refresh keeps the previous data of the failed sites (the banner shows each site's 'data as of'),
    so the copy is still published; nothing refreshed at all = Fail. Every progress line goes to the log; capped at REFRESH_MAX_MIN."""
    import threading
    if free_gb() < MIN_FREE_GB:
        raise Defer(f"only {free_gb():.1f} GB memory free (need {MIN_FREE_GB}) - the refresh would page for hours; biggest apps now: "
                    f"{top_memory()} - deferred")
    hb(f"refreshing '{title}' ({'full model' if tables == '*' else str(len(tables.split('|'))) + ' tables'}), "
       f"{free_gb():.1f} GB memory free, limit {REFRESH_MAX_MIN} min")
    p = subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "refresh_desktop.ps1"),
                          "-Tables", tables, "-TitleLike", title, "-StallSec", "300", "-HeartbeatSec", "30"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    bind(p.pid)
    timed_out = []
    timer = threading.Timer(REFRESH_MAX_MIN * 60, lambda: (timed_out.append(1), p.kill()))
    timer.start()
    last = ""
    try:
        for ln in p.stdout:
            if ln.strip():
                last = ln.strip()
                hb("    " + last[:300])
        p.wait()
    finally:
        timer.cancel()
    if timed_out:
        raise Fail(f"refresh still running after {REFRESH_MAX_MIN} min (normal: 8-11 min) - stopped; {free_gb():.1f} GB memory free, "
                   f"biggest apps: {top_memory()}. Last progress: {last[:160]}")
    if "refreshed " in last and "PARTIAL" not in last:
        return [s.split("=")[0].strip() for s in last.split("refreshed ", 1)[1].split(" partitions")[0].split(",") if "(config)" not in s]
    ok = []
    if "PARTIAL" in last and "ok:" in last:
        ok = [s.split("=")[0].strip() for s in last.split("ok:", 1)[1].split("|")[0].split(",") if "=" in s and "(config)" not in s]
    if not ok:
        raise Fail(f"refresh did not complete (exit {p.returncode}): {last[:200]}")
    hb(f"  PARTIAL - refreshed {', '.join(ok)}; the other sites keep their previous data: {last.split('FAILED:', 1)[-1][:160]}")
    return ok


def top_memory(n=4):
    """The apps holding the most memory, e.g. 'msedgewebview2 6.7 GB, Code 5.1 GB' - so a deferral says what to close."""
    out = ps("Get-Process | Group-Object Name | ForEach-Object { [pscustomobject]@{N=$_.Name; G=($_.Group | Measure-Object PrivateMemorySize64 -Sum).Sum} } "
             f"| Sort-Object G -Descending | Select-Object -First {n} | ForEach-Object {{ '{{0}} {{1:N1}} GB' -f $_.N, ($_.G / 1GB) }}")
    return ", ".join(ln.strip() for ln in out.splitlines() if ln.strip())


# ------------------------------------------------------------------ Save / Save As through the Desktop UI
UIA_HEAD = """Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [Windows.Automation.AutomationElement]; $TS = [Windows.Automation.TreeScope]
function P($prop, $v) { New-Object Windows.Automation.PropertyCondition($prop, $v) }
$root = $A::FromHandle((Get-Process -Id __PID__).MainWindowHandle)
"""


def file_state(path):
    return (path.stat().st_mtime, path.stat().st_size) if path.exists() else (0, 0)


def _cpu_s(pid):
    try:
        import psutil
        return psutil.Process(pid).cpu_times().user + psutil.Process(pid).cpu_times().system
    except Exception:
        return None


SENSITIVITY_LABEL = "Business Use"   # tenant policy: a new .pbix needs a label before Desktop saves it (21-Nov: Save As hung 9 min)


def answer_label(pid, label=SENSITIVITY_LABEL):
    """Desktop's in-app 'Select a sensitivity label' dialog (a WebView, not a Windows dialog): pick the label, Apply. -> True if answered."""
    out = ps(UIA_HEAD.replace("__PID__", str(pid)) + f"""
$d = $root.FindFirst($TS::Descendants, (P $A::NameProperty "Add sensitivity label"))
if (-not $d) {{ "NONE"; exit }}
$d.GetCurrentPattern([Windows.Automation.ExpandCollapsePattern]::Pattern).Expand(); Start-Sleep 2
$c = New-Object Windows.Automation.AndCondition((P $A::NameProperty "{label}"), (P $A::ControlTypeProperty ([Windows.Automation.ControlType]::ListItem)))
$i = $root.FindFirst($TS::Descendants, $c)
if (-not $i) {{ "NO_LABEL"; exit }}
$i.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep 2
$c = New-Object Windows.Automation.AndCondition((P $A::NameProperty "Apply"), (P $A::ControlTypeProperty ([Windows.Automation.ControlType]::Button)))
$root.FindFirst($TS::Descendants, $c).GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke(); "APPLIED"
""")
    if "NO_LABEL" in out:
        raise Fail(f"Desktop asks for a sensitivity label but '{label}' is not offered - pick one in the Desktop window")
    if "APPLIED" in out:
        hb(f"  sensitivity label '{label}' applied (required by the tenant before saving)")
        return True
    return False


def wait_written(path, before, timeout=240, pid=None, busy_max=1800):
    """Wait until the file changed and stayed the same for one poll. While Desktop is still working (its CPU time rises) the wait goes
    on up to busy_max s - a paging PC took 9.5 min (19-Nov) and > 10 min (20-Nov) to compress a 23 MB model."""
    t0, last, cpu = time.time(), None, _cpu_s(pid) if pid else None
    while True:
        time.sleep(10)
        st = file_state(path)
        dlg = [t for t in (_text(h) for h in _windows(pid)) if t] if pid else []
        now_cpu = _cpu_s(pid) if pid else None
        busy = cpu is not None and now_cpu is not None and now_cpu - cpu > 1.0
        cpu = now_cpu
        el = int(time.time() - t0)
        hb(f"  saving {el} s: {st[1] / 1e6:.1f} MB" + (" (Desktop busy)" if busy else "") + (f" | dialog: {', '.join(dlg)}" if dlg else ""))
        if st != before and st[1] > 0 and st == last:
            return True
        if pid and st == before and not busy and el % 30 < 10:
            answer_label(pid)
        last = st
        if el >= timeout and not (busy and el < busy_max):
            return False


def save_button(pid):
    out = ps(UIA_HEAD.replace("__PID__", str(pid)) + """
$b = $root.FindFirst($TS::Descendants, (P $A::AutomationIdProperty "save"))
if (-not $b) { "NO_SAVE_BUTTON"; exit }
$b.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke(); "OK"
""")
    if "OK" not in out:
        raise Fail(f"Save button not found in Power BI Desktop ({out[:120]})")


def _windows(pid, cls="#32770"):
    found = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if p.value == pid and b.value == cls and u32.IsWindowVisible(h):
            found.append(h)
        return True
    u32.EnumWindows(cb, 0)
    return found


def _text(h):
    b = ctypes.create_unicode_buffer(1024)
    u32.SendMessageW(h, 0x000D, 1024, ctypes.cast(b, ctypes.c_void_p).value)
    return b.value


def _children(h):
    out = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(c, _):
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(c, b, 256)
        out.append((c, b.value, _text(c), u32.GetDlgCtrlID(c), u32.GetParent(c)))
        return True
    u32.EnumChildWindows(h, cb, 0)
    return out


def _cls(h):
    b = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, b, 256)
    return b.value


class COMBOBOXINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcItem", W.RECT), ("rcButton", W.RECT), ("stateButton", W.DWORD),
                ("hwndCombo", W.HWND), ("hwndItem", W.HWND), ("hwndList", W.HWND)]


def save_as(pid, target):
    """File > Save as > Browse this device, then the Windows dialog: type = .pbix (picked like a mouse click - a plain
    CB_SETCURSEL changes the text but not the dialog's file type), full path, Save, answer the overwrite question."""
    hb(f"Save As -> {target}")
    script = UIA_HEAD.replace("__PID__", str(pid)) + """
$f = $root.FindFirst($TS::Descendants, (P $A::AutomationIdProperty "Ribbon-file"))
if (-not $f) { "NO_FILE_TAB"; exit }
$f.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep 3
$c = New-Object Windows.Automation.AndCondition((P $A::NameProperty "Save as"), (P $A::ControlTypeProperty ([Windows.Automation.ControlType]::TabItem)))
$s = $root.FindFirst($TS::Descendants, $c)
if (-not $s) { "NO_SAVE_AS"; exit }
$s.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep 3; "OK"
"""
    # after a large model change (Copilot step hides ~65 tables) Desktop redraws its ribbon / field list for a while: wait for it
    t0 = time.time()
    while True:
        out = ps(script)
        if "OK" in out or time.time() - t0 > 300:
            break
        dlg = [_text(h) for h in _windows(pid)]
        hb(f"  File tab not ready yet ({out.strip()[:40]}{'; dialog: ' + ', '.join(dlg) if dlg else ''}) - retry in 15 s")
        time.sleep(15)
    if "OK" not in out:
        raise Fail(f"File > Save as not reachable after {int(time.time() - t0)} s ({out[:120]})")
    # 'Browse this device' opens a modal dialog: invoke it from a separate process so this one is not blocked
    browse = UIA_HEAD.replace("__PID__", str(pid)) + """
$c = New-Object Windows.Automation.AndCondition((P $A::NameProperty "Browse this device"), (P $A::ControlTypeProperty ([Windows.Automation.ControlType]::Button)))
$root.FindFirst($TS::Descendants, $c).GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig")
    f.write(browse)
    f.close()
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", f.name])
    dlg = None
    for _ in range(30):
        time.sleep(2)
        dlg = next((h for h in _windows(pid) if _text(h) == "Save As"), None)
        if dlg:
            break
    os.unlink(f.name)
    if not dlg:
        raise Fail("the Windows 'Save As' dialog did not open")
    kids = _children(dlg)
    combo = next((c for c, k, t, _, _ in kids if k == "ComboBox" and "(*.pbi" in t), None)
    name = next((c for c, k, t, i, par in kids if k == "Edit" and i == 1001 and _cls(par) == "ComboBox"), None)
    save = next((c for c, k, t, i, _ in kids if k == "Button" and i == 1), None)
    if not (combo and name and save):
        raise Fail(f"Save As dialog controls not found (type {bool(combo)}, name {bool(name)}, save {bool(save)})")
    n = u32.SendMessageW(combo, 0x0146, 0, 0)                                    # CB_GETCOUNT
    items = []
    for i in range(n):
        b = ctypes.create_unicode_buffer(u32.SendMessageW(combo, 0x0149, i, 0) + 1)
        u32.SendMessageW(combo, 0x0148, i, ctypes.cast(b, ctypes.c_void_p).value)
        items.append(b.value)
    idx = next((i for i, t in enumerate(items) if "(*.pbix)" in t), None)
    if idx is None:
        raise Fail(f"no .pbix file type offered: {items}")
    ci = COMBOBOXINFO()
    ci.cbSize = ctypes.sizeof(COMBOBOXINFO)
    u32.GetComboBoxInfo(combo, ctypes.byref(ci))
    u32.SendMessageW(combo, 0x014F, 1, 0)                                        # CB_SHOWDROPDOWN
    time.sleep(1)
    r = W.RECT()
    u32.SendMessageW(ci.hwndList, 0x0198, idx, ctypes.cast(ctypes.byref(r), ctypes.c_void_p).value)   # LB_GETITEMRECT
    lp = (((r.top + r.bottom) // 2) << 16) | ((r.left + r.right) // 2)
    for msg, wp in ((0x0200, 0), (0x0201, 1), (0x0202, 0)):                       # mouse move / down / up on the item
        u32.SendMessageW(ci.hwndList, msg, wp, lp)
    time.sleep(1)
    if "(*.pbix)" not in _text(combo):
        raise Fail(f"file type not switched to .pbix (shows '{_text(combo)}')")
    u32.SendMessageW(name, 0x00B1, 0, -1)                                         # select all + type the path
    u32.SendMessageW(name, 0x0102, 0x08, 0)
    for ch in str(target):
        u32.SendMessageW(name, 0x0102, ord(ch), 0)
    if _text(name) != str(target):
        raise Fail(f"file name not set ('{_text(name)}')")
    before = file_state(target)
    u32.PostMessageW(save, 0x00F5, 0, 0)                                          # BM_CLICK
    for _ in range(10):
        time.sleep(2)
        conf = next((h for h in _windows(pid) if _text(h) == "Confirm Save As"), None)
        if conf:
            # the question text from the dialog's own child windows (UI Automation FromHandle fails on a dialog still being built)
            msg = " ".join(t for _, _, t, _, _ in _children(conf) if t)
            if target.name not in msg:
                msg += " " + ps(f"Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes\n"
                                f"try {{ $e = [Windows.Automation.AutomationElement]::FromHandle([IntPtr]{conf})\n"
                                "($e.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition) | "
                                "ForEach-Object { $_.Current.Name }) -join ' ' } catch { '' }")
            if not re.search(r"\.(pbix|pbip)\b", msg, re.I):
                continue                                                          # question not readable yet - look again
            ok = target.name in msg                                               # replacing our own .pbix = yes; anything else = no
            btn = next((c for c, k, t, _, _ in _children(conf) if k == "Button" and t == ("&Yes" if ok else "&No")), None)
            hb(f"  dialog: {' '.join(msg.split())[:120]} -> {'Yes' if ok else 'No'}")
            u32.PostMessageW(btn, 0x00F5, 0, 0)
            if not ok:
                raise Fail(f"Save As asked to replace something else: {msg[:160]}")
            break
        if not any(_text(h) == "Save As" for h in _windows(pid)):
            break
    # a paging PC (Copilot step + full refresh just ran) can take several minutes to compress and write the file
    if not wait_written(target, before, timeout=600, pid=pid):
        raise Fail(f"{target.name} was not written - look at the Power BI Desktop window for a message")


def save(pid, target, title):
    """Plain Save when the window already is the .pbix (verified by the file time), else / if nothing was written: Save As."""
    before = file_state(target)
    if title == target.stem and target.exists():
        hb("saving (File > Save)")
        save_button(pid)
        if wait_written(target, before, timeout=180):
            return
        hb("  Save wrote nothing (Desktop saw no change) - using Save As over the same file")
    save_as(pid, target)


def close(pid):
    hb(f"closing Power BI Desktop {pid}")
    ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).CloseMainWindow() | Out-Null")
    for _ in range(12):
        time.sleep(5)
        if not any(d["Id"] == pid for d in desktops()):
            return
    # a 'save changes?' question after a refresh: the data is already saved -> end that process only
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"], check=False)
    hb("  closed (it asked to save again - the file was already saved)")


def upload(path):
    sys.path.insert(0, str(HERE))
    import make_copilot_bundle as B
    B.upload(path)
    publish_workspace(path)


def publish_workspace(path):
    """Also put the .pbix WITH data into the Power BI workspace of dist/ALL_SITES/_published.json (published_as = pbix import) - the
    Service cannot refresh the replicas itself until the MI-<SITE>-...-ADHOC gateway connections are shared (verified 18-Nov: the
    replicas are on the P&G private network). Never blocks the SharePoint copy: problems are logged."""
    import requests
    pub_f = ROOT / "dist" / "ALL_SITES" / "_published.json"
    try:
        pub = json.loads(pub_f.read_text(encoding="utf-8"))
        if pub.get("published_as") != "pbix import (data inside)":
            return
        sys.path.insert(0, str(HERE))
        import auto_refresh as R
        h = R.pbi_headers()
        B = "https://api.powerbi.com/v1.0/myorg"
        ws = pub["workspaceId"]
        name = "WH Hypercare KPI"                      # CreateOrOverwrite matches by NAME: use the current name (renamed in the Service on 18-Nov)
        try:
            d = requests.get(f"{B}/groups/{ws}/datasets/{pub.get('semanticModelId')}", headers=h, timeout=60)
            if d.ok and d.json().get("name"):
                name = d.json()["name"]
        except requests.exceptions.RequestException:
            pass
        from urllib.parse import quote
        r = None
        for attempt in range(1, 6):
            try:
                with open(path, "rb") as f:
                    r = requests.post(f"{B}/groups/{ws}/imports?datasetDisplayName={quote(name)}&nameConflict=CreateOrOverwrite",
                                      headers={"Authorization": h["Authorization"]}, files={"file": (path.name, f, "application/octet-stream")},
                                      timeout=900)
                break
            except requests.exceptions.RequestException as e:
                hb(f"  workspace upload retry {attempt}/4 ({type(e).__name__})")
                time.sleep(10 * attempt)
        if r is None or r.status_code != 202:
            hb(f"  workspace '{pub['workspace']}': import refused {getattr(r, 'status_code', '-')} {getattr(r, 'text', '')[:160]}")
            return
        iid, t0 = r.json()["id"], time.time()
        while time.time() - t0 < 900:
            time.sleep(10)
            j = requests.get(f"{B}/groups/{ws}/imports/{iid}", headers=h, timeout=60).json()
            if j.get("importState") in ("Succeeded", "Failed"):
                break
        if j.get("importState") != "Succeeded":
            hb(f"  workspace '{pub['workspace']}': import {j.get('importState')} {json.dumps(j.get('error'))[:200]}")
            return
        pub.update({"semanticModelId": j["datasets"][0]["id"], "reportId": j["reports"][0]["id"]})
        pub["reportUrl"] = f"https://app.powerbi.com/groups/{ws}/reports/{pub['reportId']}"
        pub_f.write_text(json.dumps(pub, indent=1), encoding="utf-8")
        hb(f"  published to workspace '{pub['workspace']}' ({int(time.time() - t0)} s): {pub['reportUrl']}")
        try:                                           # the workspace model must carry the Copilot AI instructions too - check, log
            import copilot_ai
            copilot_ai.service_check()
        except (Exception, SystemExit) as e:
            hb(f"  Copilot check in the workspace skipped: {e!r}"[:200])
    except Exception as e:                                # the SharePoint copy is already done - log and go on
        hb(f"  workspace publish skipped: {e!r}"[:240])


def default_tables():
    sys.path.insert(0, str(HERE))
    import auto_refresh as R
    return R.tables_for(["HOT", "WARM"], R.policy())


def free_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", W.DWORD), ("dwMemoryLoad", W.DWORD), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MS()
    m.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 2 ** 30


MIN_FREE_GB = 2      # an all-sites model needs ~1.2 GB loaded (+ ~1 GB while refreshing); two at once ran a 16 GB PC out of memory


def ensure_pbix_open(min_gb=MIN_FREE_GB):
    """-> (pid, opened_here). Uses an open window of the .pbix, else opens it minimized (when the PC has the memory for it)."""
    if not PBIX.exists():
        raise Fail(f"{PBIX} missing - create it once with: py tools/snapshot_pbix.py --from-pbip")
    pid = find(PBIX_TITLE)
    if pid:
        return pid, False
    if free_gb() < min_gb:
        raise Defer(f"only {free_gb():.1f} GB memory free (need {min_gb}) to open the report copy; biggest apps now: {top_memory()}")
    return open_file(PBIX, PBIX_TITLE), True


def copilot_sync(pid):
    """Copilot AI instructions + key measure descriptions (tools/copilot_ai.py, config/copilot_*) into the open model before it is
    saved - an edited instruction reaches the shared .pbix at the next snapshot without a rebuild. Never blocks publishing."""
    try:
        sys.path.insert(0, str(HERE))
        import copilot_ai
        rc = copilot_ai.live(pid)
        hb("Copilot AI instructions in the model: " + ("verified" if rc == 0 else "NOT verified - see the lines above"))
    except (Exception, SystemExit) as e:
        hb(f"  Copilot AI instructions not applied: {e!r}"[:240])


def measure_errors(pid):
    """Measures the engine holds in error (TMSCHEMA_MEASURES State <> Ready) - a broken measure shows as an error box on the report
    (20-Nov: the banner [Report Label] on every page). Raises Fail so such a file is never saved over the shared copy."""
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(pid),
                        "-Dax", "SELECT [Name], [State], [ErrorMessage] FROM $SYSTEM.TMSCHEMA_MEASURES WHERE [State] <> 1", "-TimeoutSec", "120"],
                       capture_output=True, text=True, timeout=300)
    out = (p.stdout or "").strip().splitlines()
    try:
        d = json.loads(out[-1]) if out else {"error": "no output"}
    except ValueError:
        d = {"error": out[-1][:200]}
    if isinstance(d, dict) and d.get("error"):
        raise Fail(f"measure check could not run: {d['error'][:200]}")
    if d:
        raise Fail(f"{len(d)} measure(s) in error - not saved / published: " +
                   "; ".join(f"[{r.get('Name')}] {str(r.get('ErrorMessage') or '')[:120]}" for r in d[:5]))
    hb("measure check: every measure is valid")


def publish_open(pid, opened, do_upload=True, sites=None, fresh=True):
    """Save the refreshed .pbix, upload it, close it when this tool opened it. fresh=False (--copilot): data unchanged, so the
    copy-age clock of the catch-up run is left alone."""
    try:
        copilot_sync(pid)
        measure_errors(pid)
        save(pid, PBIX, PBIX_TITLE)
        hb(f"saved {PBIX.name} ({PBIX.stat().st_size / 1e6:.1f} MB)")
    finally:
        if opened:
            close(pid)
    if do_upload:
        upload(PBIX)
        if not fresh:
            hb("published to SharePoint (Copilot settings only - data as before)")
            return
        STATE.write_text(json.dumps({"last_upload": time.strftime("%Y-%m-%d %H:%M:%S"), "sites_refreshed": sites or []}), encoding="utf-8")
        hb(f"published to SharePoint (sites refreshed: {', '.join(sites or []) or 'all'})")


def main(argv):
    global LOG, PBIX, PBIX_TITLE, MIN_FREE_GB
    if "--min-free-gb" in argv:                       # hand-started runs only (scheduled runs keep the 2 GB default)
        MIN_FREE_GB = float(argv[argv.index("--min-free-gb") + 1])
    do_upload = "--no-upload" not in argv
    tables = argv[argv.index("--tables") + 1] if "--tables" in argv else None
    if "--log" in argv:
        LOG = HERE / "_auto_refresh.log"
    if "--target" in argv:                            # tests: another .pbix path (never overwrite the published copy with test data)
        PBIX = Path(argv[argv.index("--target") + 1]).resolve()
        PBIX_TITLE = PBIX.stem
        do_upload = False
    try:
        model = ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.SemanticModel" / "definition" / "model.tmdl"
        # a rebuilt model reaches the .pbix only through the project (full refresh + Save As) - for timed and catch-up runs alike
        rebuilt = "--target" not in argv and (not PBIX.exists() or (model.exists() and model.stat().st_mtime > PBIX.stat().st_mtime))
        if "--catch-up" in argv:
            # unlock / logon trigger: publish only when the SharePoint copy is older than <hours>, after a pause to let the user settle in
            limit = float(argv[argv.index("--catch-up") + 1])
            age = last_upload_age_h()
            if age < limit and not rebuilt:
                hb(f"catch-up: SharePoint copy is {age:.1f} h old (< {limit:g} h) - nothing to do")
                return 0
            delay = int(argv[argv.index("--delay") + 1]) if "--delay" in argv else 0
            why = "the report was rebuilt since the last copy" if rebuilt else ("never published" if age > 1e8 else f"{age:.1f} h old")
            hb(f"catch-up: SharePoint copy {why} - publishing in {delay // 60} min")
            for i in range(delay // 30):
                time.sleep(30)
                if i % 4 == 3:
                    hb(f"  catch-up starts in {(delay - (i + 1) * 30) // 60} min")
            argv = argv + ["--publish"]
        if "--publish" in argv and rebuilt:
            hb("the report was rebuilt since the last .pbix - publishing from the project (full refresh)")
            argv = [a for a in argv if a != "--publish"] + ["--from-pbip"]
            tables = None
        if ("--publish" in argv or "--from-pbip" in argv) and locked() and "--ignore-lock" not in argv:
            hb("workstation locked - Power BI Desktop cannot renew its replica sign-in on a locked screen; deferred to the next unlock")
            return 3
        if "--from-pbip" in argv:
            for d in desktops():                       # the old .pbix is replaced: close it (one all-sites model at a time - memory)
                if d["Title"] == PBIX_TITLE:
                    close(d["Id"])
            pid = find(PBIP_TITLE)
            opened = pid is None                       # a window the user opened stays open (it becomes the .pbix window)
            if opened and free_gb() < MIN_FREE_GB:
                raise Defer(f"only {free_gb():.1f} GB memory free (need {MIN_FREE_GB}) to open the report; biggest apps now: {top_memory()}")
            pid = pid or open_file(PBIP, PBIP_TITLE)
            try:
                sites = refresh(PBIP_TITLE, tables or "*")
            except Fail:
                if opened:
                    close(pid)
                raise
            copilot_sync(pid)
            try:
                measure_errors(pid)
            except Fail:
                if opened:
                    close(pid)
                raise
            save_as(pid, PBIX)
            hb(f"saved {PBIX.name} ({PBIX.stat().st_size / 1e6:.1f} MB)")
            if do_upload:
                try:                                   # new report version -> new screenshot for the START HERE page (never blocks publishing)
                    import make_start_here as SH
                    SH.capture(pid, SH.SHOT)
                except Exception as e:
                    hb(f"  START HERE screenshot skipped: {e!r}"[:200])
            if opened:
                close(pid)                             # the window is now the .pbix; the project files stay as built
            if do_upload:
                upload(PBIX)
                STATE.write_text(json.dumps({"last_upload": time.strftime("%Y-%m-%d %H:%M:%S"), "sites_refreshed": sites}), encoding="utf-8")
                try:
                    import make_start_here as SH
                    SH.main(["--upload"])
                except (Exception, SystemExit) as e:
                    hb(f"  START HERE page not updated: {e!r}"[:200])
        elif "--publish" in argv:
            pid, opened = ensure_pbix_open()
            try:
                sites = refresh(PBIX_TITLE, tables or default_tables())
            except Fail:
                if opened:
                    close(pid)
                raise
            publish_open(pid, opened, do_upload, sites)
        elif "--copilot" in argv:                     # Copilot instructions / descriptions only: no refresh, data unchanged
            pid, opened = ensure_pbix_open(min_gb=1)   # open + save only (no refresh): measured to open with 0.8 GB free
            publish_open(pid, opened, do_upload, fresh=False)
        elif "--save-only" in argv:
            pid = find(PBIX_TITLE)
            if not pid:
                raise Fail(f"{PBIX_TITLE} is not open in Power BI Desktop")
            save(pid, PBIX, PBIX_TITLE)
        else:
            print(__doc__)
            return 2
    except Defer as e:
        hb(f"DEFERRED: {e}")
        return 3
    except Fail as e:
        hb(f"FAILED: {e}")
        return 1
    hb("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
