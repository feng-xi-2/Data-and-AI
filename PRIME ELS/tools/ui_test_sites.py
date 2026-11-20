"""UI self-test of the open WH Hypercare KPI report: for every site in the Site slicer and every page,
select the site, open the page, read all visual texts (UI Automation) and flag visual errors. Screenshots per site/page.
    py tools/ui_test_sites.py <PBIDesktop PID> [out_dir] [SITE ...] [--pages "Process Flow,Trucks & TTAT"]"""
import csv, ctypes, json, re, sys, time
from pathlib import Path
ctypes.windll.shcore.SetProcessDpiAwareness(2)
from _ui import main_win
from PIL import ImageGrab

ARGS = sys.argv[1:]
PAGES_ONLY = []
if "--pages" in ARGS:
    i = ARGS.index("--pages"); PAGES_ONLY = [x.strip() for x in ARGS[i + 1].split(",") if x.strip()]; del ARGS[i:i + 2]
PID = int(ARGS[0]); OUT = Path(ARGS[1] if len(ARGS) > 1 else str(Path(__file__).resolve().parents[2] / "_uitest")); OUT.mkdir(exist_ok=True)
ROOT = Path(__file__).resolve().parents[1]
ERR = re.compile(r"(?i)something's wrong|couldn't load|can't display|couldn't retrieve|error fetching|#ERR|calculation error|not enough memory|visual has exceeded|add it to this report first|to see this custom visual")
PAGES = [r["Page"] for r in csv.DictReader(open(ROOT / "config" / "page_guide.csv", encoding="utf-8-sig"))] if False else None
w = main_win(PID)


def texts():
    out = []
    for x in w.descendants():
        try:
            t = x.window_text()
            if t: out.append(t)
        except Exception:
            pass
    return out


def slicer():
    return [x for x in w.descendants(control_type="ComboBox") if "slicer-dropdown" in x.element_info.class_name and x.is_visible()][0]


def pick_site(name):
    for _ in range(4):
        try:
            cb = slicer(); cb.expand(); time.sleep(2)
            it = [x for x in w.descendants(control_type="ListItem") if x.window_text() == name]
            if it:
                it[0].invoke(); time.sleep(1.5)
                try: cb.collapse()
                except Exception: pass
                return True
            cb.collapse()
        except Exception:
            pass
        time.sleep(2)
    return False


def tabs():
    return {x.window_text().strip(): x for x in w.descendants(control_type="TabItem") if x.window_text()}


def goto(page):
    for _ in range(3):
        t = tabs().get(page)
        if t is None:
            return False
        try: t.select()
        except Exception:
            try: t.invoke()
            except Exception: t.click_input()
        time.sleep(14)
        if page in texts():
            return True
    return False


SHOT_WARNED = []


def shot(path):
    """Screenshot of the Desktop window; a locked workstation (LogonUI) cannot be captured -> say so once and keep testing via UIA."""
    r = w.rectangle()
    try:
        ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(path)
    except OSError as e:
        if not SHOT_WARNED:
            print(f"!! screenshots unavailable ({e}) - workstation locked or display off; visual texts are still checked via UI Automation",
                  flush=True)
            SHOT_WARNED.append(1)


REPORT_PAGES = {json.loads(p.read_text(encoding="utf-8"))["displayName"]
                for p in (ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.Report" / "definition" / "pages").glob("*/page.json")}
# right after Desktop opens (or after a model change) the page tab strip is not in the UIA tree yet - wait for it
for _try in range(12):
    PAGE_TABS = [n for n in tabs() if n in REPORT_PAGES or n.removeprefix("Hidden ") in REPORT_PAGES]
    if len(PAGE_TABS) > 1:
        break
    print(f"waiting for the page tabs ({_try + 1}/12) ...", flush=True)
    time.sleep(10)
if len(PAGE_TABS) <= 1:
    raise SystemExit("FAILED: no report page tabs found in the Desktop window (is the report view open?)")
PAGE_TABS = ["Home"] + [p for p in PAGE_TABS if p != "Home"]
if PAGES_ONLY:
    PAGE_TABS = [p for p in PAGE_TABS if p in PAGES_ONLY]
CFG = [r["SiteName"] for r in csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig"))]
goto("Home")
cb = slicer(); cb.expand(); time.sleep(2)
shown = {x.window_text() for x in w.descendants(control_type="ListItem")}
cb.collapse()
ONLY_SITES = [a for a in ARGS[2:]]
SITES = [n for n in CFG if n in shown and (not ONLY_SITES or any(n.upper().startswith(o.upper()) for o in ONLY_SITES))]
print("pages", PAGE_TABS, "\nsites", SITES, "| in config but not in slicer:", [n for n in CFG if n not in shown], flush=True)
results = []
for s in SITES:
    goto("Home")
    if not pick_site(s):
        results.append({"site": s, "page": "*", "status": "SITE NOT SELECTABLE"}); print(s, "NOT SELECTABLE", flush=True); continue
    for p in PAGE_TABS:
        if not goto(p):
            results.append({"site": s, "page": p, "status": "PAGE NOT OPENED"}); print(f"{s:18s} {p:24s} PAGE NOT OPENED", flush=True); continue
        tx = texts()
        title = next((t for t in tx if t.endswith("PRIME ELS Dashboard")), "")
        if not title.startswith(s):          # first page after a site switch can still show the previous site - re-read once
            time.sleep(8); tx = texts(); title = next((t for t in tx if t.endswith("PRIME ELS Dashboard")), "")
        errs = sorted({t[:120] for t in tx if ERR.search(t)})
        na = any("NOT USED AT" in t for t in tx)
        st = "ERROR" if errs else ("OK" if title.startswith(s) else "TITLE MISMATCH")
        results.append({"site": s, "page": p, "status": st, "title": title, "not_used_banner": na, "errors": errs})
        shot(OUT / f"{re.sub(r'[^A-Za-z0-9]+', '_', s)}__{re.sub(r'[^A-Za-z0-9]+', '_', p)}.png")
        print(f"{s:18s} {p:24s} {st}{' (page not used at site)' if na else ''} {errs if errs else ''}", flush=True)
(OUT / "ui_test_results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
bad = [r for r in results if r["status"] != "OK"]
print(f"DONE {len(results)} site-pages, {len(bad)} problems", flush=True)
goto("Home"); pick_site(SITES[0])

