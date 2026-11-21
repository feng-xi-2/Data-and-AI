"""Copilot-ready descriptions for EVERY table, measure and visible column of a built model (post-build, all sites, Desktop + Service).

    py tools/ai_descriptions.py "<...>.SemanticModel"     # fill missing descriptions in place and print the coverage
    (build_pbip.py calls apply() after the Copilot instructions step)

Microsoft guidance (Copilot 'evaluate your data', 2026): Copilot reads the first ~200 characters of a description, so each one
starts with the business meaning and unit; the formula follows (visible to users in the field tooltip / model view).
Sources, first match wins - nothing is invented:
  measures  config/field_guide.csv + config/copilot_descriptions.csv (already in the TMDL) > readable name + unit
            (config/measure_units.csv) + display folder; then 'Formula:' = the DAX on one line (long DAX: the measures it uses)
  columns   config/column_glossary.csv (regex on 'Table|Column') > readable column name; + unit (config/column_units.csv)
            + the table's meaning; calculated columns add their formula
  tables    the existing description (SQL header line) > config/table_basis.csv Meaning > 'Calculated table: <DAX head>'
Hidden columns / hidden tables are skipped (Copilot does not use them). Existing descriptions are kept, only extended with the formula.
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
HEAD = 200        # what Copilot reads
MAX = 700         # whole description (meaning + formula)

WORDS = [(r"\bPlts?\b", "pallets"), (r"\bPal\b", "pallet"), (r"\bAvg\b", "average"), (r"\bProd\b", "production"),
         (r"/h\b", " per hour"), (r"/Hr\b", " per hour"), (r"\bHr\b", "hour"), (r"\bPPH\b", "pallets per hour (PPH)"),
         (r"\bTTAT\b", "truck turn-around time (TTAT)"), (r"\bUtil\b", "utilisation"), (r"\bThr\b", "threshold"),
         (r"\bEff\b", "effective"), (r"\bCfg\b", "config"), (r"\bCrit\b", "critical"), (r"\bWarn\b", "warning"),
         (r"\bPrev\b", "previous day"), (r"\bQty\b", "quantity"), (r"\bLoc\b", "location"), (r"\bInv\b", "inventory"),
         (r"\bLTA\b", "line take-away lane (LTA)"), (r"\bHOFF(IN)?\b", "hand-off lane"), (r"\bWO\b", "work order"),
         (r"\bTxn\b", "transactions"), (r"\bMin\b", "minutes"), (r"\bPct\b", "%"), (r"\bNum\b", "number"),
         (r"\bDesc\b", "description"), (r"\bDte\b", "date"), (r"\bBD\b", "Binh Duong (BD) template"), (r"\bIn\b", "inbound"),
         (r"\bOut\b", "outbound"), (r"\bRF\b", "RF (hand-held scanner)"), (r"\bSKU\b", "product (SKU)")]


def _csv(name):
    f = CFG / name
    return list(csv.DictReader(open(f, encoding="utf-8-sig"))) if f.exists() else []


def readable(name):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace("_", " ")).strip()
    for p, w in WORDS:
        s = re.sub(p, w, s)
    s = re.sub(r"\s+", " ", s)
    return s[:1].upper() + s[1:]


def one_line(dax):
    dax = re.sub(r"//[^\n]*|--[^\n]*", "", dax)
    dax = re.sub(r"/\*.*?\*/", "", dax, flags=re.S)
    return re.sub(r"\s+", " ", dax).strip()


def formula(dax, limit=320):
    d = one_line(dax)
    if len(d) <= limit:
        return f"Formula: {d}"
    used = list(dict.fromkeys(re.findall(r"(?<!')\[[^\]]+\](?!\s*\()", d)))      # measures referenced (not 'T'[col])
    cols = list(dict.fromkeys(re.findall(r"'[^']+'\[[^\]]+\]|\b[A-Za-z_]\w*\[[^\]]+\]", d)))
    parts = []
    if used:
        parts.append("uses " + ", ".join(u for u in used if not any(u in c for c in cols))[:220])
    if cols:
        parts.append("reads " + ", ".join(cols)[:200])
    fn = re.match(r"(VAR\b|[A-Z]+\s*\()", d)
    return f"Formula ({len(d)} characters of DAX, see the model): " + "; ".join(p for p in parts if p.split(' ', 1)[1]) + \
        ("" if not fn else "")


def cap(s):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= MAX else s[:MAX - 3].rstrip() + "..."


class Glossary:
    def __init__(self):
        self.col = [(re.compile(r["Pattern"]), r["Meaning"]) for r in _csv("column_glossary.csv")]
        self.unit = [(re.compile(r["Pattern"]), r.get("Unit") or "", r.get("Note") or "") for r in _csv("column_units.csv")]
        self.munit = {r["Measure"]: r.get("Unit") or "" for r in _csv("measure_units.csv")}
        self.tmean = {r["Table"]: r.get("Meaning") or "" for r in _csv("table_basis.csv")}

    def column(self, table, col, tdesc, dax=None, dtype=""):
        key = f"{table}|{col}"
        meaning = next((m for p, m in self.col if p.search(key)), None)
        unit = None
        if dtype in ("int64", "double", "decimal"):        # column_units.csv = number formats: numeric columns only
            for p, u, n in self.unit:
                tgt = key if re.search(r"\w\\\|", p.pattern) else f"|{col}"   # table-less rules never match the table name
                if p.search(tgt):
                    unit = (u, n)
                    break
        s = meaning or readable(col)
        if unit and unit[0] and not unit[0].startswith("#"):
            s += f" (unit: {unit[0]}{'; ' + unit[1] if unit[1] else ''})"
        ctx = (self.tmean.get(table) or tdesc or "").split(". ")[0]
        s += f". Column of '{table}'" + (f" - {ctx[:90]}" if ctx else "")
        if dax:
            s += ". " + formula(dax, 200)
        return cap(s)

    def measure(self, name, folder, dax, existing):
        unit = self.munit.get(name, "")
        if existing:
            s = existing.rstrip(". ")
            if "formula:" not in s.lower():
                s += ". " + formula(dax)
            return cap(s)
        s = readable(name) + (f" ({unit})" if unit else "")
        if folder:
            s += f". KPI group: {re.sub(r'(^|[\\\\>] ?)\d+[a-z]? ', r'\1', folder).replace(chr(92), ' > ')}"
        return cap(s + ". " + formula(dax))

    def table(self, name, kind_dax):
        if self.tmean.get(name):
            return cap(self.tmean[name])
        if kind_dax:
            return cap(f"Calculated table ({readable(name)}) built in the model from other tables. {formula(kind_dax, 200)}")
        return cap(f"{readable(name)} - data table loaded from the site data replica")


NAME = r"('(?:[^']|'')+'|[^\s=]+)"


def _block(lines, i, first):
    """DAX after ' = ' on line i: single line or a ``` fenced block. Returns (dax, last_index)."""
    rest = first.split(" = ", 1)[1] if " = " in first else ""
    if rest.strip() == "```":
        j, buf = i + 1, []
        while j < len(lines) and lines[j].strip() != "```":
            buf.append(lines[j])
            j += 1
        return "\n".join(buf), j
    return rest, i


def apply_file(path: Path, g: Glossary):
    lines = path.read_text(encoding="utf-8").splitlines()
    out, stats = [], {"measure": [0, 0], "column": [0, 0], "table": [0, 0]}
    tname, thidden, tdesc = None, False, ""
    i = 0
    # table header: description lines (///) then 'table X'
    for k, ln in enumerate(lines):
        if ln.startswith("table "):
            tname = ln[6:].strip().strip("'").replace("''", "'")
            tdesc = " ".join(x[3:].strip() for x in lines[:k] if x.startswith("///"))
            thidden = any(x.strip() == "isHidden" for x in lines[k + 1:k + 4])
            calc = next((x for x in lines if re.match(r"^\tpartition .* = calculated", x)), None)
            cdax = None
            if calc:
                ci = lines.index(calc)
                src = next((m for m in range(ci, min(ci + 6, len(lines))) if lines[m].strip().startswith("source =")), None)
                if src is not None:
                    cdax, _ = _block(lines, src, lines[src].replace("source =", "x = ", 1))
            stats["table"][0] += 1
            if not tdesc:
                lines[k:k] = [f"/// {g.table(tname, cdax)}"]
                stats["table"][1] += 1
            else:
                stats["table"][1] += 1
            break
    while i < len(lines):
        ln = lines[i]
        m = re.match(rf"^\t(measure|column) {NAME}", ln)
        if not m:
            out.append(ln)
            i += 1
            continue
        kind, name = m.group(1), m.group(2).strip("'").replace("''", "'")
        prev = [x for x in out if x.strip()][-1] if any(x.strip() for x in out) else ""
        have = prev.startswith("\t///")
        dax, last = _block(lines, i, ln) if " = " in ln else ("", i)
        props = []
        j = last + 1
        while j < len(lines) and (lines[j].startswith("\t\t") or not lines[j].strip()):
            props.append(lines[j])
            j += 1
            if len(props) > 40:
                break
        hidden = any(p.strip() == "isHidden" for p in props)
        if kind == "column" and (hidden or thidden):
            out.extend(lines[i:last + 1])
            i = last + 1
            continue
        stats[kind][0] += 1
        if kind == "measure":
            folder = next((p.strip()[15:] for p in props if p.strip().startswith("displayFolder:")), "")
            existing = ""
            if have:
                k = len(out)
                while k and out[k - 1].startswith("\t///"):
                    k -= 1
                existing = " ".join(x.strip()[3:].strip() for x in out[k:])
                del out[k:]
            text = g.measure(name, folder, dax, existing)
        else:
            if have:
                out.extend(lines[i:last + 1])
                i = last + 1
                stats[kind][1] += 1
                continue
            dtype = next((p.strip()[9:].strip() for p in props if p.strip().startswith("dataType:")), "")
            text = g.column(tname, name, tdesc, dax if " = " in ln else None, dtype)
        out.append(f"\t/// {text}")
        stats[kind][1] += 1
        out.extend(lines[i:last + 1])
        i = last + 1
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return stats


def apply(model_dir: Path):
    g = Glossary()
    tot = {"measure": [0, 0], "column": [0, 0], "table": [0, 0]}
    for f in sorted((Path(model_dir) / "definition" / "tables").glob("*.tmdl")):
        s = apply_file(f, g)
        for k in tot:
            tot[k][0] += s[k][0]
            tot[k][1] += s[k][1]
    return tot


DICT = "Field Dictionary"


def write_dictionary(model_dir: Path):
    """'Field Dictionary' (Copilot answer table, Microsoft: Copilot answers from data rows, descriptions mainly steer DAX): one row
    per table / measure / visible column / site setting with its meaning and formula = the descriptions written by apply().
    'What does LOC_LTA mean?' -> the LOC_LTA row (also hidden Cfg_Site setting columns, with the site's value)."""
    import json as _json
    from pbi_common import tmdl_m_table, enter_data_source  # noqa: F401
    tdir = Path(model_dir) / "definition" / "tables"
    g = Glossary()
    rows = []
    site_vals = {}
    for f in sorted(tdir.glob("*.tmdl")):
        if f.stem == DICT:
            continue
        L = f.read_text(encoding="utf-8").splitlines()
        tl = next(i for i, x in enumerate(L) if x.startswith("table "))
        tn = L[tl][6:].strip().strip("'").replace("''", "'")
        th = any(x.strip() == "isHidden" for x in L[tl + 1:tl + 4])
        tdesc = " ".join(x[3:].strip() for x in L[:tl] if x.startswith("///"))
        if not th:
            rows.append({"Table": tn, "Field": tn, "Kind": "table", "Meaning": tdesc, "Formula": ""})
        for i, ln in enumerate(L):
            m = re.match(rf"^\t(measure|column) {NAME}", ln)
            if not m:
                continue
            kind, name = m.group(1), m.group(2).strip("'").replace("''", "'")
            props = [x for x in L[i + 1:i + 30] if x.startswith("\t\t")]
            hidden = any(x.strip() == "isHidden" for x in props)
            desc = L[i - 1].strip()[4:] if L[i - 1].startswith("\t///") else ""
            setting = tn == "Cfg_Site" and kind == "column"
            if (hidden or th) and not setting:
                continue
            if not desc and setting:
                desc = g.column(tn, name, tdesc)
            meaning, _, formula = desc.partition("Formula")
            dax = _block(L, i, ln)[0] if " = " in ln else ""
            full = one_line(dax)[:4000] if dax else ""          # the whole DAX: a table row has no 200-character limit
            rows.append({"Table": tn, "Field": name, "Kind": "site setting" if setting else kind,
                         "Meaning": meaning.strip(" .;"), "Formula": ("DAX: " + full) if full else
                         (("Formula" + formula).strip() if formula else "")})
    cols = ["Table", "Field", "Kind", "Meaning", "Formula"]
    from build_pbip import dax_config_table
    for r in rows:
        r["Formula"] = (r["Formula"] or "")[:1500]
    desc = ("FIELD DICTIONARY - one row per table, measure, visible column and site setting: what it means (unit) and how it is "
            "calculated. Copilot: 'what does <field> mean' = the row whose Field matches (fuzzy). Generated by tools/ai_descriptions.py.")
    t = dax_config_table(DICT, cols, rows, {c: "string" for c in cols}, desc=desc)
    expl = {"Table": "Table the field belongs to", "Field": "Name of the table / measure / column / site setting as shown in the model",
            "Kind": "table, measure, column or site setting (Cfg_Site, per site)", "Meaning": "What the field means, with its unit",
            "Formula": "How it is calculated (DAX of the measure / calculated column, one line)"}
    from pbi_common import q as _q
    for c, d in expl.items():
        t = t.replace(f"\tcolumn {_q(c)}\n", f"\t/// {d}\n\tcolumn {_q(c)}\n", 1)
    (tdir / f"{DICT}.tmdl").write_text(t, encoding="utf-8")
    mf = Path(model_dir) / "definition" / "model.tmdl"
    mt = mf.read_text(encoding="utf-8")
    if f"ref table '{DICT}'" not in mt:
        mt = re.sub(r"(ref table [^\n]+\n)(?!ref table)", lambda x: x.group(1) + f"ref table '{DICT}'\n", mt, count=1)
        mt = re.sub(r"(annotation PBI_QueryOrder = \[)(.*)\]", lambda x: x.group(1) + x.group(2) + (", " if x.group(2) else "") +
                    _json.dumps(DICT) + "]", mt, count=1)
        mf.write_text(mt, encoding="utf-8")
    return len(rows)


def coverage(model_dir: Path):
    """(described, total) per kind without changing anything - used by the model gate."""
    tot = {"measure": [0, 0], "column": [0, 0]}
    for f in (Path(model_dir) / "definition" / "tables").glob("*.tmdl"):
        L = f.read_text(encoding="utf-8").splitlines()
        th = any(x.strip() == "isHidden" for x in L[:6])
        for i, ln in enumerate(L):
            m = re.match(r"^\t(measure|column) ", ln)
            if not m:
                continue
            k = m.group(1)
            if k == "column" and (th or any(x.strip() == "isHidden" for x in L[i + 1:i + 8] if x.startswith("\t\t"))):
                continue
            tot[k][1] += 1
            tot[k][0] += L[i - 1].startswith("\t///")
    return tot


if __name__ == "__main__":
    md = Path(sys.argv[1])
    t = apply(md)
    print(" | ".join(f"{k}s {v[1]}/{v[0]} described" for k, v in t.items()))
    print("coverage after:", coverage(md))
