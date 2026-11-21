"""Best Practice Analyzer fixes applied to every built model (Microsoft / Tabular Editor community rules, microsoft/Analysis-Services
BestPracticeRules/BPARules.json), so the BPA run on the published model stays clean.

    [Performance] Set IsAvailableInMdx to false on non-attribute columns -> hidden columns not used by a relationship / sort / hierarchy
    [Formatting]  Do not summarize numeric columns                       -> visible numeric columns: summarizeBy none
    [Formatting]  Provide format string for measures / hide helpers      -> visual-helper measures (colours, labels, card texts, strip copies,
                                                                            thresholds; config/copilot_schema.csv 'Hidden' measure rules) hidden
    [Formatting]  Whole numbers with thousands separators                -> count formats '0 "plt"' -> '#,0 "plt"'
Hidden measures keep working in visuals; Copilot answer measures (config/copilot_descriptions.csv) stay visible.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNT_UNITS = ("plt", "locs", "txns", "lines", "cases", "cs", "items", "trucks", "users", "rows", "checks", "orders", "shipments", "BUoM", "hand-offs")


def _rules():
    rows = list(csv.DictReader(open(ROOT / "config" / "copilot_schema.csv", encoding="utf-8-sig")))
    return [(re.compile(r["Pattern"]), r["Visibility"]) for r in rows if r["Kind"] == "Measure"]


def _keep_visible():
    f = ROOT / "config" / "copilot_descriptions.csv"
    return {r["Measure"] for r in csv.DictReader(open(f, encoding="utf-8-sig"))} if f.exists() else set()


def _rel_columns(defn: Path):
    used = set()
    f = defn / "relationships.tmdl"
    if f.exists():
        for m in re.finditer(r"(?:fromColumn|toColumn):\s*(.+)", f.read_text(encoding="utf-8")):
            ref = m.group(1).strip()
            t, _, c = ref.rpartition(".")
            used.add((t.strip("'").replace("''", "'"), c.strip("'").replace("''", "'")))
    return used


def _count_format(fmt):
    # 0 "plt" / "0 ""plt""" -> #,0 "plt" (formats with decimals, % or time stay as they are)
    m = re.fullmatch(r'"?0 (""|")(.+?)(""|")"?', fmt.strip())
    if m and m.group(2) in COUNT_UNITS:
        q = m.group(1)
        return fmt.replace(f"0 {q}", f"#,0 {q}", 1)
    return fmt


def apply(model_dir: Path):
    defn = Path(model_dir) / "definition"
    rels = _rel_columns(defn)
    rules, keep = _rules(), _keep_visible()
    st = {"mdx_off": 0, "no_summarize": 0, "hidden_measures": 0, "count_formats": 0}
    for f in sorted((defn / "tables").glob("*.tmdl")):
        L = f.read_text(encoding="utf-8").splitlines()
        tl = next(i for i, x in enumerate(L) if x.startswith("table "))
        tname = L[tl][6:].strip().strip("'").replace("''", "'")
        thidden = any(x.strip() == "isHidden" for x in L[tl + 1:tl + 4])
        text = "\n".join(L)
        sort_targets = {m.group(1).strip("'").replace("''", "'") for m in re.finditer(r"sortByColumn:\s*(.+)", text)}
        hier_cols = {m.group(1).strip("'").replace("''", "'") for m in re.finditer(r"\n\t\t\t\tcolumn:\s*(.+)", text)}
        out, i = [], 0
        while i < len(L):
            ln = L[i]
            m = re.match(r"^\t(column|measure) ('(?:[^']|'')+'|[^\s=]+)", ln)
            if not m:
                out.append(ln)
                i += 1
                continue
            kind, name = m.group(1), m.group(2).strip("'").replace("''", "'")
            j = i + 1                                  # block = following lines indented deeper (or blank) until the next member
            while j < len(L) and (L[j].startswith("\t\t") or not L[j].strip()):
                j += 1
            block = L[i:j]
            props = [x.strip() for x in block[1:]]
            hidden = "isHidden" in props
            if kind == "column":
                dtype = next((p.split(":", 1)[1].strip() for p in props if p.startswith("dataType:")), "")
                if ((hidden or thidden) and name not in sort_targets and name not in hier_cols and (tname, name) not in rels
                        and not any(p.startswith("isAvailableInMdx") for p in props) and not any(p.startswith("sortByColumn") for p in props)):
                    k = next((n for n, x in enumerate(block) if x.strip().startswith("lineageTag:")), 0)
                    block.insert(k + 1, "\t\tisAvailableInMdx: false")
                    st["mdx_off"] += 1
                if not (hidden or thidden) and dtype in ("int64", "double", "decimal"):
                    for n, x in enumerate(block):
                        if x.strip().startswith("summarizeBy:") and x.strip() != "summarizeBy: none":
                            block[n] = "\t\tsummarizeBy: none"
                            st["no_summarize"] += 1
            else:
                for n, x in enumerate(block):
                    if x.strip().startswith("formatString:"):
                        new = "\t\tformatString: " + _count_format(x.strip()[len("formatString:"):].strip())
                        if new != x:
                            block[n] = new
                            st["count_formats"] += 1
                if not hidden and name not in keep:
                    vis = next((v for p, v in rules if p.search(name)), "Visible")
                    if vis == "Hidden":
                        k = next((n for n, x in enumerate(block) if x.startswith("\t\tlineageTag:")), None)
                        if k is not None:
                            block.insert(k + 1, "\t\tisHidden")
                            st["hidden_measures"] += 1
            out.extend(block)
            i = j
        f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return st


if __name__ == "__main__":
    import sys
    print(apply(Path(sys.argv[1])))
