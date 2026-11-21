"""Shared helpers for the WH Hypercare KPI generator: config CSV -> PBI 'Enter data' M, TMDL text helpers, M tokenizer."""
import base64
import csv
import json
import re
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
NS = uuid.UUID("6d1b7a1e-0c55-4a8e-9b1e-5a1c0de0f001")


def tag(*parts):
    """Deterministic lineage tag -> stable diffs between builds."""
    return str(uuid.uuid5(NS, "|".join(parts)))


def read_csv(name):
    with open(CONFIG / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def excluded_sites():
    """config/build_options.csv AllSites_Exclude (e.g. XIQING|ATHENS): codes left out of the all-sites report."""
    if not (CONFIG / "build_options.csv").exists():
        return set()
    v = next((r["Value"] for r in read_csv("build_options.csv") if r["Setting"] == "AllSites_Exclude"), "")
    return {c.strip().upper() for c in v.split("|") if c.strip()}


SAP_TABLES = ("SAP Plan PO", "Shipping Market", "SAP Production")   # Databricks (CDL) feeds
SAP_PAGES = ("SAPPROD", "PRED")                                     # page_guide keys that only show SAP data


def sap_included():
    """config/build_options.csv Include_SAP_CDL = 1 -> SAP tables, measures and pages are built; 0 -> left out of the file entirely."""
    if not (CONFIG / "build_options.csv").exists():
        return False
    return next((r["Value"].strip() for r in read_csv("build_options.csv") if r["Setting"] == "Include_SAP_CDL"), "0") == "1"


def report_sites():
    """Site rows of the all-sites report = config/site_config.csv minus AllSites_Exclude (one rule for build, Copilot text, tests)."""
    ex = excluded_sites()
    return [r for r in read_csv("site_config.csv") if r["SiteCode"].upper() not in ex]


def q(name):
    """TMDL object name quoting."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


def m_ident(name):
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else '#"' + name.replace('"', '""') + '"'


def m_str(s):
    return '"' + s.replace('"', '""') + '"'


def enter_data_source(rows, cols):
    """Exact Power BI 'Enter data' pattern -> editable in Desktop (Transform data > Source step gear)."""
    data = [[(r.get(c) if r.get(c) not in ("", None) else None) for c in cols] for r in rows]
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    b64 = base64.b64encode(co.compress(raw) + co.flush()).decode()
    tdef = ", ".join(f"{m_ident(c)} = _t" for c in cols)
    return (f'Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("{b64}", BinaryEncoding.Base64), Compression.Deflate)), '
            f'let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [{tdef}])')


M_TYPE = {"string": "text", "int64": "Int64.Type", "double": "number", "dateTime": "datetime",
          "decimal": "Currency.Type", "boolean": "logical"}


def indent(text, n):
    pad = "\t" * n
    return "\n".join(pad + ln if ln.strip() else pad for ln in text.splitlines())


def tmdl_source_block(expr, depth=2):
    """TMDL `source =` block with a fenced multi-line expression."""
    return f"{chr(9) * depth}source = ```\n{indent(expr, depth + 2)}\n{chr(9) * (depth + 2)}```\n"


def tmdl_column(table, name, dtype, fmt=None, hidden=False, source=None, summarize="none", sort_by=None):
    s = f"\tcolumn {q(name)}\n\t\tdataType: {dtype}\n"
    if fmt:
        s += f"\t\tformatString: {fmt}\n"
    if hidden:
        s += "\t\tisHidden\n"
    s += f"\t\tlineageTag: {tag(table, 'col', name)}\n\t\tsummarizeBy: {summarize}\n\t\tsourceColumn: {source or name}\n"
    if sort_by:
        s += f"\t\tsortByColumn: {q(sort_by)}\n"
    s += "\n\t\tannotation SummarizationSetBy = Automatic\n\n"
    return s


def tmdl_m_table(name, columns, m_expr, description=None, hidden=False):
    """columns: list of (name, dataType, formatString|None)."""
    s = ""
    if description:
        s += "".join(f"/// {ln}\n" for ln in description.splitlines())
    s += f"table {q(name)}\n"
    if hidden:
        s += "\tisHidden\n"
    s += f"\tlineageTag: {tag(name)}\n\n"
    for c in columns:
        s += tmdl_column(name, c[0], c[1], c[2] if len(c) > 2 else None)
    s += f"\tpartition {q(name)} = m\n\t\tmode: import\n" + tmdl_source_block(m_expr) + "\n"
    s += "\tannotation PBI_ResultType = Table\n"
    return s


def tmdl_measure(table, name, folder, fmt, dax, description=None):
    s = ""
    if description:
        s += "".join(f"\t/// {ln}\n" for ln in description.splitlines())
    s += f"\tmeasure {q(name)} = ```\n{indent(dax, 3)}\n\t\t\t```\n"
    if fmt:
        s += f"\t\tformatString: {fmt}\n"
    if folder:
        s += f"\t\tdisplayFolder: {folder}\n"
    s += f"\t\tlineageTag: {tag(table, 'measure', name)}\n\n"
    return s


def parse_tmdl_columns(text):
    """Return [(sourceColumn, dataType)] for data columns of an exported TMDL table (calculated columns skipped)."""
    out = []
    for m in re.finditer(r"\n\tcolumn (?P<decl>[^\n]+)\n(?P<body>(?:\t\t[^\n]*\n|\n)*?)(?=\n?\t[^\t]|\Z)", text):
        decl, body = m.group("decl"), m.group("body")
        if re.search(r"\s=\s*$|\s=\s", decl):
            continue
        dt = re.search(r"dataType: (\w+)", body)
        sc = re.search(r"sourceColumn: (.+)", body)
        if sc:
            out.append((sc.group(1).strip(), dt.group(1) if dt else "string"))
    return out


def empty_table_m(cols):
    fields = ", ".join(f"{m_ident(c)} = {M_TYPE.get(t, 'any')}" for c, t in cols)
    return f"#table(type table [{fields}], {{}})"
