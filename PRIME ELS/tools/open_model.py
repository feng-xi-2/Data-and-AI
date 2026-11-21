"""Open a .pbip in Power BI Desktop and wait until the model is really loaded (engine has tables) - heartbeat every 15 s.

    py tools/open_model.py "<path>.pbip" [--timeout 900]

Closes any running Desktop first, answers the "Sign in to Power BI - choose cloud" prompt (Power BI), and checks the engine
with a DAX query, not only the window title (Desktop can replace its window / show "Untitled" while loading).
Prints READY <pid> or FAILED ... (exit 1) - never silent.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ctypes.windll.shcore.SetProcessDpiAwareness(2)
import psutil  # noqa: E402
from pywinauto import Desktop  # noqa: E402
from _ui import click  # noqa: E402

HERE = Path(__file__).resolve().parent
PBIP = sys.argv[1]
TIMEOUT = int(sys.argv[sys.argv.index("--timeout") + 1]) if "--timeout" in sys.argv else 900


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def desktops():
    return [p for p in psutil.process_iter(["name", "pid"]) if (p.info["name"] or "").lower() == "pbidesktop.exe"]


def tables(pid):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "pbi_dax.ps1"), "-ProcId", str(pid),
                        "-Dax", 'EVALUATE ROW("t", COUNTROWS(INFO.TABLES()))', "-TimeoutSec", "30"], capture_output=True, text=True, timeout=90)
    try:
        d = json.loads(r.stdout.strip())
        return d[0]["[t]"] if isinstance(d, list) else 0
    except Exception:
        return 0


def close_all():
    for p in desktops():
        say(f"closing Desktop {p.pid}")
        for ch in p.children(recursive=True):
            try:
                ch.kill()
            except Exception:
                pass
        p.kill()
    time.sleep(3)


close_all()
say(f"opening {PBIP}")
os.startfile(PBIP)
t0 = time.time()
launched, relaunched = time.time(), False
STUCK = int(sys.argv[sys.argv.index("--stuck") + 1]) if "--stuck" in sys.argv else 300
while time.time() - t0 < TIMEOUT:
    time.sleep(15)
    ds = desktops()
    if not ds:
        say("heartbeat: no Desktop process yet")
        continue
    info = []
    for p in ds:
        try:
            ws = Desktop(backend="uia").windows(process=p.pid)
        except Exception:
            ws = []
        dl = []
        for w in ws:
            try:
                for c in w.children():
                    if c.element_info.control_type == "Window":
                        tx = [x.window_text() for x in c.descendants() if x.window_text()]
                        dl += tx[:3]
                        if "Sign in to Power BI" in tx:
                            r = [x for x in c.descendants(control_type="RadioButton") if x.window_text() == "Power BI"]
                            if r:
                                click(r[0])
                            click([x for x in c.descendants(control_type="Button") if x.window_text() == "OK"][0])
                            say("answered 'Sign in to Power BI' cloud prompt -> Power BI")
            except Exception:
                pass
        n = tables(p.pid)
        info.append(f"pid {p.pid} '{', '.join(w.window_text() for w in ws)}' tables={n} dialogs={dl[:3]}")
        if n > 0 and not dl:
            say(f"READY {p.pid} ({n} tables)")
            sys.exit(0)
    say("heartbeat: " + " | ".join(info))
    # seen 30-Oct: Desktop can hang on its splash screen (engine up, 0 tables, no dialog) - one automatic restart
    if not relaunched and time.time() - launched > STUCK and all("tables=0 dialogs=[]" in x for x in info):
        say(f"Desktop stuck on the splash screen for {STUCK} s (0 tables, no dialog) - restarting it once")
        close_all()
        os.startfile(PBIP)
        launched, relaunched = time.time(), True
say(f"FAILED: model not loaded after {TIMEOUT} s - look at the Desktop window")
sys.exit(1)
