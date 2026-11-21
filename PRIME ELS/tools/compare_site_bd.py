"""Consistency of one site's report with the BD reference site: same visual, same result type, filled where BD is filled.

    py tools/compare_site_bd.py <site replay csv> <reference replay csv> [--site JAKARTA] [--ref BINHDUONG] [--expect intent_check.csv]

Inputs are tools/visual_replay.py result files (any days). Per page x visual:
  BOTH_OK        filled at both sites (result columns and value types compared: number / text / date / duration)
  TYPE_DIFF      filled at both, but a value has a different type or format (e.g. '0:09' vs 9.0) -> formatting defect
  EMPTY_HERE     filled at BD on some day, empty at the site on every replayed day -> explained by the site's intent check
                 (EMPTY_NO_ACTIVITY / EMPTY_EXPECTED / EMPTY_SOURCE_STATE) or a defect to fix
  ERROR_HERE     error at the site -> defect
  NOT_USED_HERE  the visual's feature flag is OFF for the site (e.g. no Level A) - shown as not used, by design
  ONLY_HERE      visual not replayed at BD (page off at BD, e.g. feature flag)
Writes docs/SITE_VS_BD_<SITE>.md; exit 1 on TYPE_DIFF / ERROR_HERE / unexplained EMPTY_HERE.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def kind(v):
    if v is None or v == "":
        return "blank"
    if isinstance(v, (int, float)):
        return "number"
    s = str(v)
    if re.fullmatch(r"/Date\(-?\d+\)/", s):
        return "date"
    if re.fullmatch(r"-?\d+:\d\d", s):
        return "duration"
    if re.fullmatch(r"-?[\d,]+(\.\d+)?%?", s):
        return "number-text"
    return "text"


def load(path, site):
    """Visual titles normalised like the build does (tools/report_pages.clean_title: no numbering, no source names) so a
    replay recorded before a title cleanup still matches."""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    from report_pages import clean_title
    out = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["Site"] == site:
            out[(r["Page"], clean_title(r["Visual"]))].append(r)
    return out


def sample_kinds(rows):
    ks = {}
    for r in rows:
        if r["Status"] != "OK":
            continue
        try:
            s = json.loads(r["Sample"] or "{}")
        except ValueError:
            continue
        for c, v in s.items():
            k = kind(v)
            if k != "blank":
                ks.setdefault(c, k)
    return ks


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    site, ref = opt("--site", "JAKARTA"), opt("--ref", "BINHDUONG")
    here, bd = load(sys.argv[1], site), load(sys.argv[2], ref)
    explained = {}
    if "--expect" in sys.argv:
        for r in csv.DictReader(open(opt("--expect", ""), encoding="utf-8-sig")):
            if r["Check"].startswith("EMPTY_") and r["Where"].startswith(site):
                explained[(r["Page"], r["Visual"])] = f"{r['Check']}: {r['Detail'][:140]}"
    rows, bad = [], 0
    for key in sorted(set(here) | set(bd)):
        h, b = here.get(key, []), bd.get(key, [])
        h_ok, b_ok = any(r["Status"] == "OK" for r in h), any(r["Status"] == "OK" for r in b)
        h_err = [r for r in h if r["Status"] == "ERROR"]
        if not h:
            continue
        if h_err:
            st, why = "ERROR_HERE", h_err[0]["Error"][:160]
        elif all(r["Status"] == "NA" for r in h):
            st, why = "NOT_USED_HERE", "the feature this visual needs is OFF for the site (config) - the page says so"
        elif not b:
            st, why = "ONLY_HERE", "not replayed at the reference site"
        elif h_ok and b_ok:
            hk, bk = sample_kinds(h), sample_kinds(b)
            diff = [f"{c}: {hk[c]} vs {bk[c]}" for c in hk if c in bk and hk[c] != bk[c] and {hk[c], bk[c]} != {"number", "number-text"}]
            st, why = ("TYPE_DIFF", "; ".join(diff)) if diff else ("BOTH_OK", "")
        elif b_ok and not h_ok:
            st, why = "EMPTY_HERE", explained.get(key, "NOT EXPLAINED")
        else:
            st, why = "BOTH_EMPTY", ""
        if st in ("ERROR_HERE", "TYPE_DIFF") or (st == "EMPTY_HERE" and why == "NOT EXPLAINED"):
            bad += 1
        rows.append((key[0], key[1], st, why))
    from collections import Counter
    cnt = Counter(r[2] for r in rows)
    md = [f"# {site} vs {ref} - visual by visual", "",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py tools/compare_site_bd.py` from the visual replays "
          f"(`{Path(sys.argv[1]).name}` vs `{Path(sys.argv[2]).name}`). Result: " + ", ".join(f"**{k}** {v}" for k, v in sorted(cnt.items())), "",
          "| Page | Visual | Status | Detail |", "|---|---|---|---|"]
    md += [f"| {p} | {v[:90]} | {s} | {w} |" for p, v, s, w in rows if s != "BOTH_OK"]
    md += ["", f"{cnt.get('BOTH_OK', 0)} visuals are filled at both sites with the same result types (not listed)."]
    (ROOT / "docs" / f"SITE_VS_BD_{site}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{site} vs {ref}: {dict(cnt)}; defects {bad} -> docs/SITE_VS_BD_{site}.md")
    for p, v, s, w in rows:
        if s in ("ERROR_HERE", "TYPE_DIFF") or (s == "EMPTY_HERE" and w == "NOT EXPLAINED"):
            print(f"  !! {s:10s} {p} :: {v[:80]} | {w}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
