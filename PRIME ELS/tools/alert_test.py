"""Alert test on a PUBLISHED model: every KPI status and every alert rule, recomputed independently from the numbers.

    py tools/alert_test.py --service <workspaceId>/<datasetId> [--site JAKARTA]

1. 'KPI Scorecard' (one row per site x KPI): the expected status is recomputed here from Actual, Warning / Critical limit and
   Better When (Higher: below critical = CRITICAL, below warning = WARNING; Lower: above ...; Band = distance from target) and
   compared with the model's Status. Blank Actual must be NO DATA / N/A (never OK / CRITICAL); N/A only where the site lacks the process.
2. Cfg_AlertRule: each rule's [Alert Status] (the Alerts page) must equal the scorecard status of its KPI, and every WARNING /
   CRITICAL rule must carry an action and an owner (the Cockpit 'What to do now' list).
3. Text columns of the answer tables (Actual Text, Target Text, How Calculated, Recommended Action ...) never empty on a live KPI.
Writes _uitest/alert_test.csv; exit 1 on any mismatch.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from svc_dax import Svc  # noqa: E402

OUT = HERE.parents[1] / "_uitest"
args = sys.argv[1:]
svc = Svc(args[args.index("--service") + 1])
SITE = args[args.index("--site") + 1].upper() if "--site" in args else None


def expected(a, w, c, t, better):
    if a is None:
        return None
    b = (better or "").lower()
    if b.startswith("higher"):
        return "CRITICAL" if c is not None and a < c else "WARNING" if w is not None and a < w else "OK"
    if b.startswith("lower"):
        return "CRITICAL" if c is not None and a > c else "WARNING" if w is not None and a > w else "OK"
    if "target" in b or b.startswith("band"):
        d = abs(a - (t or 0))
        return "CRITICAL" if c is not None and d > c else "WARNING" if w is not None and d > w else "OK"
    return "INFO"


flt = f', "{SITE}"' if SITE else ""
sc = svc.rows("EVALUATE SELECTCOLUMNS(" + (f"FILTER('KPI Scorecard', 'KPI Scorecard'[Site] = \"{SITE}\")" if SITE else "'KPI Scorecard'") +
              ', "Site", [Site], "K", [KPI Key], "A", [Actual], "T", [Target], "W", [Warning Limit], "C", [Critical Limit], '
              '"B", [Better When], "S", [Status], "AT", [Actual Text], "TT", [Target Text], "HC", [How Calculated], '
              '"RA", [Recommended Action], "OW", [Owner], "MB", [Meaning If Breached])')
rows, bad = [], 0
status = {}
for r in sc:
    site, k, a, s = r["[Site]"], r["[K]"], r["[A]"], r["[S]"]
    status[(site, k)] = s
    exp = expected(a, r["[W]"], r["[C]"], r["[T]"], r["[B]"])
    issue = ""
    if a is None and s not in ("NO DATA", "N/A", "INFO"):
        issue = f"blank actual but status {s}"
    elif a is not None and exp not in (None, "INFO") and s != exp:
        issue = f"status {s}, expected {exp} (actual {a}, warn {r['[W]']}, crit {r['[C]']}, {r['[B]']})"
    elif a is not None and not (r["[AT]"] or "").strip():
        issue = "Actual Text empty"
    elif s in ("WARNING", "CRITICAL") and not ((r["[RA]"] or "").strip() and (r["[OW]"] or "").strip()):
        issue = "breached KPI without recommended action / owner"
    elif not (r["[HC]"] or "").strip():
        issue = "How Calculated empty"
    bad += bool(issue)
    rows.append({"Check": "KPI", "Site": site, "Key": k, "Actual": a, "Status": s, "Expected": exp or "", "Issue": issue})

ar = svc.rows("EVALUATE ADDCOLUMNS(SUMMARIZE(Cfg_AlertRule, Cfg_AlertRule[Rule_No], Cfg_AlertRule[KPI_Key], Cfg_AlertRule[Rule], "
              "Cfg_AlertRule[Recommended_Action], Cfg_AlertRule[Owner]), \"S\", CALCULATE([Alert Status]" +
              (f", TREATAS({{\"{SITE}\"}}, Cfg_Site[SiteCode])" if SITE else "") + "))")
site0 = SITE or (sc[0]["[Site]"] if sc else "")
for r in ar:
    k, s = r["Cfg_AlertRule[KPI_Key]"], r["[S]"]
    ks = status.get((site0, k))
    issue = ""
    norm = lambda x: {"N/A": "NA", "NO DATA": "NODATA"}.get(x, x)
    if ks is not None and s is not None and norm(s) != norm(ks) and not (s in ("", None) and ks in ("N/A", "NO DATA")):
        issue = f"rule status {s} but KPI {k} is {ks}"
    elif s in ("WARNING", "CRITICAL") and not ((r["Cfg_AlertRule[Recommended_Action]"] or "").strip() and (r["Cfg_AlertRule[Owner]"] or "").strip()):
        issue = "breached rule without action / owner"
    bad += bool(issue)
    rows.append({"Check": "RULE", "Site": site0, "Key": f"#{r['Cfg_AlertRule[Rule_No]']} {k}", "Actual": "", "Status": s, "Expected": ks or "",
                 "Issue": issue})

open_txt = svc.rows("EVALUATE FILTER(ADDCOLUMNS(VALUES(Cfg_AlertRule[Rule_No]), \"t\", [Open Alert Text]), NOT ISBLANK([t]))")
n_open = sum(1 for r in rows if r["Check"] == "RULE" and r["Status"] in ("WARNING", "CRITICAL"))
if len(open_txt) != n_open:
    bad += 1
    rows.append({"Check": "TODO", "Site": site0, "Key": "What to do now", "Actual": len(open_txt), "Status": "", "Expected": n_open,
                 "Issue": f"{len(open_txt)} open-alert rows but {n_open} breached rules"})
OUT.mkdir(exist_ok=True)
with open(OUT / "alert_test.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
from collections import Counter
print(f"KPIs {sum(r['Check'] == 'KPI' for r in rows)} ({dict(Counter(r['Status'] for r in rows if r['Check'] == 'KPI'))}), "
      f"rules {sum(r['Check'] == 'RULE' for r in rows)}, open alerts {len(open_txt)} -> defects {bad}")
for r in rows:
    if r["Issue"]:
        print(f"  !! {r['Check']} {r['Site']} {r['Key']}: {r['Issue']}")
sys.exit(1 if bad else 0)
