"""START HERE page for new users of the PRIME ELS Hypercare KPI report: which file to open, how, how fresh the data is.

    py tools/make_start_here.py [--capture <PBIDesktop PID>] [--upload]

--capture  screenshot of the open report (PrintWindow on the Power BI window only: shown off-screen without activation, then minimized
           again - no focus change) -> dist/_share/_start_here_report.png, embedded in the page
--upload   uploads the PDF (SharePoint previews PDFs in the browser) next to the report .pbix in the PRIME ELS folder
Output: dist/_share/START HERE - how to open the Hypercare report.html + .pdf (Edge headless print).
Times come from config/desktop_refresh.csv (Snapshot_Hour_*) and config/site_config.csv (UTC_Offset_h) - nothing hard-coded.
"""
import base64
import csv
import ctypes
import ctypes.wintypes as W
import datetime as dt
import html
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "dist" / "_share"
NAME = "START HERE - how to open the Hypercare report"
SHOT = OUT / "_start_here_report.png"
PBIX_NAME = "WH Hypercare KPI - ALL_SITES.pbix"
sys.path.insert(0, str(HERE))
from make_copilot_bundle import BUILDER_FOLDER  # noqa: E402


def hb(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def capture(pid, out, width=2000, height=1125):
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    hw = []

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, _):
        p = W.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u.IsWindowVisible(h) and u.GetWindowTextLengthW(h) > 0:
            hw.append(h)
        return True
    u.EnumWindows(cb, 0)
    if not hw:
        raise SystemExit(f"no Power BI window for PID {pid}")
    h = hw[0]

    class WP(ctypes.Structure):
        _fields_ = [("length", W.UINT), ("flags", W.UINT), ("showCmd", W.UINT), ("ptMin", W.POINT), ("ptMax", W.POINT), ("rc", W.RECT)]
    old = WP()
    old.length = ctypes.sizeof(WP)
    u.GetWindowPlacement(h, ctypes.byref(old))
    # Windows keeps a restored window on a monitor, so it cannot be parked off-screen: make it fully transparent and click-through
    # (layered, alpha 0), put it behind every other window, render it with PrintWindow, then minimize it and restore its style
    u.GetWindowLongW.restype = ctypes.c_long
    ex = u.GetWindowLongW(h, -20)                                    # GWL_EXSTYLE
    u.SetWindowLongW(h, -20, ex | 0x80000 | 0x20)                    # WS_EX_LAYERED | WS_EX_TRANSPARENT
    u.SetLayeredWindowAttributes(h, 0, 0, 2)                         # LWA_ALPHA = 0 -> invisible
    try:
        tmp = WP.from_buffer_copy(old)
        tmp.flags &= ~0x2                                            # restore to the normal rectangle, not maximized
        tmp.showCmd = 4                                              # SW_SHOWNOACTIVATE
        tmp.rc = W.RECT(0, 0, width, height)
        u.SetWindowPlacement(h, ctypes.byref(tmp))
        u.SetWindowPos(h, 1, 0, 0, width, height, 0x10)              # HWND_BOTTOM, SWP_NOACTIVATE
        time.sleep(20)                                               # let the report repaint at the new size (visuals re-query)
        r = W.RECT()
        u.GetWindowRect(h, ctypes.byref(r))
        w_, h_ = r.right - r.left, r.bottom - r.top
        hdc = u.GetWindowDC(h)
        mdc = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, w_, h_)
        g.SelectObject(mdc, bmp)
        u.PrintWindow(h, mdc, 2)

        class BIH(ctypes.Structure):
            _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                        ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                        ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]
        bi = BIH(ctypes.sizeof(BIH), w_, -h_, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w_ * h_ * 4)
        g.GetDIBits(mdc, bmp, 0, h_, buf, ctypes.byref(bi), 0)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(h, hdc)
    finally:
        old.showCmd = 7 if old.showCmd in (2, 6, 7) else old.showCmd    # back to minimized without activation
        u.SetWindowPlacement(h, ctypes.byref(old))
        u.SetWindowLongW(h, -20, ex)
    from PIL import Image
    Image.frombuffer("RGBA", (w_, h_), buf, "raw", "BGRA", 0, 1).convert("RGB").save(out)
    hb(f"screenshot {w_} x {h_} -> {out.name}")


def snapshot_times():
    cfg = {r["Setting"]: int(r["Value"]) for r in csv.DictReader(open(ROOT / "config" / "desktop_refresh.csv", encoding="utf-8-sig"))}
    hours = [h for h in (cfg.get("Snapshot_Hour_1", -1), cfg.get("Snapshot_Hour_2", -1)) if h >= 0]
    pub = round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 900) / 4
    from pbi_common import report_sites  # same sites as the shared .pbix (build_options AllSites_Exclude)
    sites = report_sites()
    rows = []
    for s in sites:
        off = float(s["UTC_Offset_h"])
        local = [((h + 0.5 - pub + off) % 24) for h in hours]
        rows.append((s["SiteName"], off, ", ".join(f"{int(x):02d}:{int(round(x % 1 * 60)):02d}" for x in local)))
    pub_txt = ", ".join(f"{h:02d}:30" for h in hours)
    return pub, pub_txt, rows


CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#f4f6f9;color:#1f2933;line-height:1.55}
header{background:linear-gradient(90deg,#0B2A4A,#1F5FA8);color:#fff;padding:24px 40px}
header h1{margin:0 0 6px;font-size:26px} header p{margin:0;opacity:.92}
nav{background:#fff;border-bottom:1px solid #dde3ea;padding:10px 40px;position:sticky;top:0;z-index:5}
nav a{margin-right:16px;color:#1F5FA8;text-decoration:none;font-weight:600;font-size:14px}
main{max-width:1100px;margin:0 auto;padding:16px 40px 50px}
section{background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:20px 28px;margin:20px 0;page-break-inside:avoid}
h2{color:#0B2A4A;border-bottom:2px solid #e4ecf7;padding-bottom:6px;margin-top:4px} h3{color:#1F5FA8;margin:18px 0 6px}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
th,td{border:1px solid #d5dde6;padding:7px 9px;text-align:left;vertical-align:top} th{background:#eef3fa}
code{font-family:Consolas,monospace;background:#eef1f5;padding:1px 5px;border-radius:4px}
.box{border-left:5px solid;padding:10px 14px;border-radius:6px;margin:12px 0}
.ok{background:#ecf9f0;border-color:#2e9e5b} .warn{background:#fff6e5;border-color:#e0a100} .info{background:#eaf2fd;border-color:#2f6fd6}
.stepnum{display:inline-block;background:#0B2A4A;color:#fff;border-radius:50%;width:26px;height:26px;text-align:center;line-height:26px;margin-right:8px;font-weight:700}
.file{font-weight:700;color:#0B2A4A} .big{font-size:18px}
.two{display:flex;gap:18px} .two>div{flex:1;border:1px solid #d5dde6;border-radius:8px;padding:12px 16px;background:#fafbfc}
.tag{font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:6px;background:#d9f5e3;color:#16723a}
.tag.alt{background:#fff1cc;color:#8a5a00}
figure{margin:12px 0} figure img{max-width:100%;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.18)}
figcaption{font-size:13px;color:#52606d;margin-top:6px}
.tree{font-family:Consolas,monospace;font-size:14px;background:#fafbfc;border:1px solid #d5dde6;border-radius:8px;padding:10px 14px;white-space:pre}
@media print{nav{display:none} body{background:#fff} section{border:1px solid #ccc}}
"""


def build():
    pub, pub_txt, rows = snapshot_times()
    pub_name = f"UTC{'+' if pub >= 0 else ''}{pub:g}"
    img = ""
    if SHOT.exists():
        b64 = base64.b64encode(SHOT.read_bytes()).decode()
        img = (f"<figure><img alt='report Home page' src='data:image/png;base64,{b64}'><figcaption><span class='tag'>real screenshot</span> "
               f"the report as it opens in Power BI Desktop: the Home page with the index of all pages (Ctrl + click a button). Navy strip = "
               f"page name and, on the right, <b>data as of</b> + when the next copy comes; the bar below = <b>Site</b>, <b>Day</b>, "
               f"<b>Shift</b> for every page. The panes on the right (Filters, Visualizations) are for editing - you can collapse them "
               f"with the » arrows.</figcaption></figure>")
    site_rows = "".join(f"<tr><td>{html.escape(n)}</td><td>UTC{'+' if o >= 0 else ''}{o:g}</td><td>{t}</td></tr>" for n, o, t in rows)
    body = f"""
<header><h1>PRIME ELS Hypercare KPI – how to open the report</h1>
<p>For site leads, shift leads and the hypercare team · 2 minutes to read · updated {dt.date.today():%d %b %Y}</p></header>
<nav><a href='#file'>Which file</a><a href='#open'>Open it</a><a href='#fresh'>How fresh</a><a href='#use'>Use it</a><a href='#problems'>Problems</a></nav>
<main>
<section id='file'><h2><span class='stepnum'>1</span>The one file you need</h2>
<p class='big'>Open <span class='file'>{PBIX_NAME}</span> – nothing else. You do <b>not</b> need any zip file.</p>
<div class='tree'>SharePoint › OSS warehousing data and GenAI › Documents › Data Projects › PRIME ELS › Hypercare KPI
  ├── <b>{PBIX_NAME}</b>     ← the report, with data of all sites
  ├── {NAME}.pdf     ← this page
  ├── Hypercare_KPI_Inputs.xlsx     (hypercare lead only: sites and alert targets)
  └── {BUILDER_FOLDER}/     (people who change the report - not needed to view it)</div>
<div class='box info'>The file holds the data of every site, so it opens with numbers straight away - no sign-in, no refresh.
Pick your site in the <b>Site</b> filter on top of any page.</div>
</section>

<section id='open'><h2><span class='stepnum'>2</span>Open it - two ways</h2>
<div class='two'>
<div><h3>A. In the browser <span class='tag'>fastest</span></h3>
<ol><li>Go to the SharePoint folder above.</li><li><b>Click</b> <span class='file'>{PBIX_NAME}</span>.</li>
<li>The report opens in the browser - nothing to install.</li></ol>
<p>Needs a Power BI <b>Pro</b> or <b>E5</b> licence. If SharePoint only offers <i>Download</i>, use B.</p></div>
<div><h3>B. In Power BI Desktop <span class='tag alt'>works for everyone</span></h3>
<ol><li>Select the file › <b>Download</b>.</li><li><b>Double-click</b> the downloaded file.</li>
<li>Power BI Desktop (free - Microsoft Store or Software Center) opens it with data in about 1 minute.</li></ol>
<p>Buttons in Desktop: <b>Ctrl + click</b>.</p></div>
</div>
<div class='box warn'><b>Do not press Refresh.</b> You don't need to - the data is inside the file. Refresh reloads every site from the
data replicas: it needs extra access and takes about 10 minutes (see 3).</div>
{img}
</section>

<section id='fresh'><h2><span class='stepnum'>3</span>How fresh is the data?</h2>
<p>A new copy of the file, with fresh data, is put in the folder <b>twice a day</b> (about {pub_txt} {pub_name}). The banner on top of every
page says <b>data as of</b> &lt;time&gt; and when the next copy comes, in your site's time:</p>
<table><tr><th>Site</th><th>Site time</th><th>New copy on SharePoint (site time)</th></tr>{site_rows}</table>
<div class='box warn'>The banner shows <b>⚠ this copy is N h old</b> when you opened an old download: open the file in SharePoint again.</div>
<h3>Need live data right now?</h3>
<p>Only if you have read access to the site's data replica (AD group <code><ad-group>-&lt;SITE&gt;-READONLY</code>):
<b>Home › Refresh</b> in Power BI Desktop › sign in with <b>Microsoft account</b> (your @<company>) - never <i>Windows</i> › wait about 10 minutes.
In the browser (A) the file cannot be refreshed.</p>
</section>

<section id='use'><h2><span class='stepnum'>4</span>Use it in one minute</h2>
<table><tr><th>Where</th><th>What</th></tr>
<tr><td>Filter bar (every page)</td><td><b>Site</b> · <b>Day</b> (blank = today's shift day) · <b>Shift</b> (blank = whole day) - one choice drives all pages</td></tr>
<tr><td>Home</td><td>index of all pages by process: Overview › Inbound &amp; Trucks › Production &amp; Lines › Storage &amp; Inventory › Outbound &amp; Orders › People › Admin</td></tr>
<tr><td>Hypercare Cockpit</td><td>the 6 KPIs vs target, yesterday and forecast; <i>What to do now</i> = open alerts, critical first</td></tr>
<tr><td>Alerts</td><td>every alert: actual vs target and why; click one for the numbers behind it and the action</td></tr>
<tr><td>Then the red section</td><td>each page reads top-down: KPIs › where it is stuck › why › detail list</td></tr>
<tr><td>⌂ Home button</td><td>top left of every page</td></tr>
<tr><td>Ask Copilot <span class='tag'>Desktop, signed in</span></td><td><b>Home › Copilot</b> (first time: pick workspace <b><workspace></b>), skill <i>Answers questions about the data</i>.
Name the site: <i>"What should we do first at MINHANG? Give issue - evidence - action - owner."</i> · <i>"Compare all sites: critical and warning KPIs."</i>
Copilot also suggests these questions when it opens. The file tells Copilot every KPI, target, action and owner; check key numbers on the page.</td></tr></table>
</section>

<section id='problems'><h2><span class='stepnum'>5</span>If something looks wrong</h2>
<table><tr><th>You see</th><th>Do</th></tr>
<tr><td>SharePoint shows only <i>Download</i> / "can't open in browser"</td><td>no Power BI Pro licence or the browser view is off: way B</td></tr>
<tr><td>Power BI Desktop asks to sign in or shows a refresh error</td><td>someone pressed Refresh - close the file without saving and open it again</td></tr>
<tr><td>⚠ this copy is N h old</td><td>open the current file from SharePoint</td></tr>
<tr><td>A page says "No production planned" / "NOT USED AT &lt;site&gt;"</td><td>that site does not run the process - nothing to do</td></tr>
<tr><td>A number looks wrong</td><td>Config &amp; Health page first; then send a screenshot + page + site + day to the hypercare team</td></tr></table>
<p style='font-size:13px;color:#52606d'>The file contains the data of every site in the report; who can open it = who can open this SharePoint folder.</p>
</section>
</main>"""
    page = f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{NAME}</title><style>{CSS}</style></head><body>{body}</body></html>"
    out = OUT / f"{NAME}.html"
    out.write_text(page, encoding="utf-8")
    hb(f"page -> {out.name} ({out.stat().st_size / 1e3:.0f} KB)")
    return out


def to_pdf(src):
    edge = next((p for p in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                             Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")) if p.exists()), None)
    if not edge:
        raise SystemExit("Microsoft Edge not found - the PDF needs it (the HTML page is ready)")
    pdf = src.with_suffix(".pdf")
    if pdf.exists():
        pdf.unlink()
    # own profile folder (a running Edge would take the job and write nothing) + a temp name without spaces (Edge ignores the switch
    # when the quoted output path has spaces), then moved
    prof = Path(tempfile.gettempdir()) / "hypercare_edge_pdf"
    tmp = Path(tempfile.gettempdir()) / "hypercare_start_here.pdf"
    if tmp.exists():
        tmp.unlink()
    subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                    f"--print-to-pdf={tmp}", src.as_uri()], capture_output=True, timeout=120)
    for _ in range(20):                                              # Edge can return before the file is flushed
        if tmp.exists() and tmp.stat().st_size > 0:
            break
        time.sleep(1)
    if tmp.exists():
        tmp.replace(pdf)
    if not pdf.exists():
        raise SystemExit("Edge did not write the PDF")
    hb(f"pdf  -> {pdf.name} ({pdf.stat().st_size / 1e3:.0f} KB)")
    return pdf


def main(argv):
    if "--capture" in argv:
        capture(int(argv[argv.index("--capture") + 1]), SHOT)
    pdf = to_pdf(build())
    if "--upload" in argv:
        from make_copilot_bundle import upload
        upload(pdf)


if __name__ == "__main__":
    main(sys.argv[1:])
