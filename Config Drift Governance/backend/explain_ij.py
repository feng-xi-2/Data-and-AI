"""explain_ij — natural-language, cited explanation of Config Drift deviations (columns I & J).

WHAT THIS IS
------------
A focused, additive explainer for the PCD deviation export. For every row it reads the two
value columns the report is built around:

    I = "A value"  -> the value at the AUDITED site   (the site being checked, e.g. AHM_PRODWMS)
    J = "R value"  -> the value in the REFERENCE       (the golden standard, e.g. mnt-wms)

and writes TWO new columns into a COPY of the CSV (never mutates the original):

    Deviation Explanation (NL)   plain-English account of what deviated and why it matters
    Grounding & Citations        the source each claim rests on, tagged:
        [MOCA]    RedPrairie/Blue Yonder MOCA data model (poldat_view, aremst, dlytrn ...)
        [PRIME]   PrIME 2022 / Config Drift (PCD) product behaviour
        [CRFC]    the authoritative CFG-RFC governance register (Configuration_RFC.csv)
        [PYTHON]  how this row was classified by the enrichment code
        [GENERAL] general WMS/data domain knowledge (not from a workspace file)

The three deviation types (per the PCD - Deviations Report) are explained differently:
    Missing record               record exists in R (standard) but is absent at A (site)
    Unexpected record            record exists at A (site) but is not in R (standard)
    Unexpected mismatching value both define the element; a single attribute value differs
                                 (this is where I and J are both populated)

USAGE
    python explain_ij.py --in "<...>/20260817_0038_ahm_output.csv" --out "<...>_explained.csv"
    # defaults resolve to the AHM report and a sibling *_explained.csv if flags are omitted.

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then
raise); writes a copy, leaving the source report untouched.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# paths (dual workspace: code on Desktop, report CSVs on OneDrive)
# ---------------------------------------------------------------------------
from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
DEFAULT_IN = os.path.join(ONEDRIVE, "Config report", "20260817_0038_ahm_output.csv")
DEFAULT_CRFC = os.path.join(ONEDRIVE, "Config report", "Configuration_RFC.csv")


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# grounding dictionaries — small, auditable domain maps
# ---------------------------------------------------------------------------
# GUI attribute label -> underlying MOCA poldat column (Policy Maintenance rows).
# poldat_view is the SAME table used by the USR-AUTO-LOGOUT job (UC-JOB policies).
POLDAT_COL = {
    "return string 1": "rtstr1",
    "return string 2": "rtstr2",
    "return number 1": "rtnum1",
    "return number 2": "rtnum2",
    "sort sequence": "rtnum1 (sort seq)",
    "warehouse id template": "wh_id (template)",
}

# section -> (underlying MOCA table, grounding tag)
SECTION_TABLE = {
    "policy maintenance": ("poldat / poldat_view (polcod # polvar # polval)", "MOCA"),
    "area maintenance": ("aremst (area master)", "MOCA"),
    "inventory mixing rules maintenance": ("mixing-rule policy (UC-MIX-* poldat)", "MOCA"),
    "note type maintenance": ("ntetyp (note-type master)", "MOCA"),
    "bar code template maintenance": ("barcode template config", "PRIME"),
    "web services": ("PrIME web-service endpoint config", "PRIME"),
    "variable default maintenance": ("variable default config", "PRIME"),
    "variable configuration maintenance": ("variable config", "PRIME"),
    "variable validation": ("variable validation config", "PRIME"),
    "workflow instructions": ("workflow / job step config", "PRIME"),
    "configuration and health checks": ("PrIME health-check config", "PRIME"),
}

# well-known HOST-MU unit-of-measure defaults -> what the value means
HOSTMU_HINT = {
    "linear": "linear/length unit of measure sent to the host",
    "mass": "mass/weight unit of measure sent to the host",
    "volume": "volume unit of measure sent to the host",
    "area": "area unit of measure sent to the host",
}

_cfg_re = re.compile(r"\bCFG\d+\b", re.IGNORECASE)
_mod_user_re = re.compile(r"(?:Modification user|Last Updated User) <([^>]*)>")
_mod_date_re = re.compile(r"(?:Modification Date|Last Updated Date) <([^>]*)>")
_group_re = re.compile(r"Group Name <([^>]*)>")
_num_re = re.compile(r"^-?\d+(\.\d+)?$")
_token_re = re.compile(r"[A-Za-z0-9_]+")

# CFG-RFC request statuses that mean the backing ticket is NO LONGER live — an
# accepted exception citing one of these is STALE and must be re-reviewed.
DEAD_STATUSES = {"superseded", "withdrawn", "rejected", "closed", "disused", "cancelled"}


def row_cfg_code(row: dict) -> str:
    """The governing CFGxxxx for a row: Rationale first, else Group Name in Comments."""
    rationale = row.get("Rationale") or ""
    m = _cfg_re.search(rationale)
    if m:
        return m.group(0).upper()
    grp = _group_re.search(row.get("Deviation Comments") or "")
    if grp:
        m = _cfg_re.search(grp.group(1))
        if m:
            return m.group(0).upper()
    return ""


# ---------------------------------------------------------------------------
# formatting-vs-functional value diff (columns I vs J)
# ---------------------------------------------------------------------------
def _normalize(v: str) -> str:
    s = str(v or "").strip().lower()
    if _num_re.match(s):
        try:
            return str(float(s))
        except ValueError:
            pass
    s = re.sub(r"\s+", " ", s)
    s = s.replace("_", "-").replace("|", ",").replace(";", ",")
    return s.strip("[]<>\"' ")


def _tokens(s: str) -> list[str]:
    return _token_re.findall(str(s or "").lower())


def _looks_command(s: str) -> bool:
    """True when a value is an executable MOCA/SQL script rather than a simple setting."""
    low = str(s or "").lower()
    return (_is_codeblob(s) or "select " in low or "publish " in low
            or "catch(" in low or "@?" in low or bool(_len_cmd_re.match(str(s or ""))))


_len_cmd_re = re.compile(r"^\s*(\d+)\s*\*\*(.*)$", re.DOTALL)


def _split_len_cmd(v: str):
    """For the 'Length and Command' format 'NNNN**[ ...command... ]' return (declared_len, body).

    PrIME stores some job/command policies as a byte-length header, the '**' separator, then
    the command body. Returns (None, original) when the value is not length-prefixed.
    """
    m = _len_cmd_re.match(str(v or ""))
    if not m:
        return None, str(v or "")
    return int(m.group(1)), m.group(2).strip()


def _describe_val(v: str) -> str:
    """Render a value for the plain-English explanation.

    Short settings are shown in full; long scripts/commands are summarised with a short
    preview instead of dumping hundreds of characters into the sentence.
    """
    s = str(v or "").strip()
    if not s:
        return "(blank)"
    dlen, body = _split_len_cmd(s)
    if dlen is not None:
        flat = re.sub(r"\s+", " ", body)
        preview = flat[:56].rstrip()
        return (f'a length-prefixed command (declared length {dlen}, body {len(flat)} chars, '
                f'starts: "{preview}…")')
    flat = re.sub(r"\s+", " ", s)
    if _looks_command(s):
        preview = flat[:60].rstrip()
        return f'an executable script/command ({len(flat)} chars, starts: "{preview}…")'
    if len(flat) > 80:
        preview = flat[:60].rstrip()
        return f'a long value ({len(flat)} chars, starts: "{preview}…")'
    return f"'{flat}'"


def diff_ij(aval: str, rval: str) -> dict:
    """Classify how I (A value) differs from J (R value), in plain English."""
    a, r = str(aval or ""), str(rval or "")
    if a == r:
        return {"kind": "NONE", "formatting": True, "text": "The two values are identical."}
    if _normalize(a) == _normalize(r):
        return {"kind": "COSMETIC", "formatting": True,
                "text": "The difference is only in capitalisation, spacing or punctuation — "
                        "there is no real change, so this is safe to ignore."}
    ca, cr = Counter(_tokens(a)), Counter(_tokens(r))
    if ca and ca == cr:
        return {"kind": "REORDER", "formatting": True,
                "text": "Both hold exactly the same items but in a different order — there is "
                        "no real change, so this is safe to ignore."}
    # executable script / job body on either side -> don't echo the text, summarise the diff
    if _looks_command(a) or _looks_command(r):
        la, ba = _split_len_cmd(a)
        lr, br = _split_len_cmd(r)
        # diff the command BODIES (not the length header) so keyword changes are meaningful
        bca, bcr = Counter(_tokens(ba)), Counter(_tokens(br))
        site_only = list(dict.fromkeys((bca - bcr).elements()))[:6]
        std_only = list(dict.fromkeys((bcr - bca).elements()))[:6]
        parts = []
        if site_only:
            parts.append("only in the site's command: " + ", ".join(site_only))
        if std_only:
            parts.append("only in the standard's command: " + ", ".join(std_only))
        detail = "; ".join(parts) if parts else "the wording differs throughout"
        if la is not None and lr is not None and la != lr:
            sign = "longer" if la > lr else "shorter"
            text = (f"The site's command declares length {la} vs the standard's {lr} "
                    f"(the site's is {abs(la - lr)} bytes {sign}), and the command logic itself "
                    "differs — the site runs a customised version. The differing keywords are "
                    + detail + " (the full command text is in the report's A value and R value columns).")
        else:
            text = ("Both sides hold an executable command and the logic genuinely differs — "
                    "the site runs a customised version. The differing keywords are " + detail
                    + " (the full command text is in the report's A value and R value columns).")
        return {"kind": "VALUE_DELTA", "formatting": False, "text": text,
                "site_only": site_only, "standard_only": std_only}
    site_only = list(dict.fromkeys((ca - cr).elements()))[:8]
    std_only = list(dict.fromkeys((cr - ca).elements()))[:8]
    # simple scalar / UOM / flag change: one short value each -> plain phrasing
    if len(_tokens(a)) <= 1 and len(_tokens(r)) <= 1:
        return {"kind": "VALUE_DELTA", "formatting": False,
                "text": "So the site's setting is genuinely different from what the standard requires.",
                "site_only": site_only, "standard_only": std_only}
    bits = []
    if site_only:
        bits.append("only at the site: " + ", ".join(site_only))
    if std_only:
        bits.append("only in the standard: " + ", ".join(std_only))
    return {"kind": "VALUE_DELTA", "formatting": False,
            "text": ("The two genuinely differ — " + "; ".join(bits) + ".") if bits
                    else "The two values genuinely differ.",
            "site_only": site_only, "standard_only": std_only}


# ---------------------------------------------------------------------------
# CRFC register: CFG#### -> title/status (authoritative governance grounding)
# ---------------------------------------------------------------------------
def load_crfc(path: str) -> dict:
    reg: dict[str, dict] = {}
    if not os.path.exists(path):
        log(f"WARN CRFC register not found at {path} — CFG citations will be uncorroborated")
        return reg
    # register is cp1252
    with open(path, encoding="cp1252", newline="") as fh:
        for row in csv.DictReader(fh):
            title = (row.get("Title") or "").strip()
            m = _cfg_re.search(title)
            if not m:
                continue
            code = m.group(0).upper()
            reg.setdefault(code, {
                "title": title,
                "site": (row.get("Site") or "").strip(),
                "status": (row.get("Request Status") or "").strip(),
                "type": (row.get("Code") or "").strip(),
            })
    log(f"CRFC register loaded: {len(reg)} CFG codes")
    return reg


# ---------------------------------------------------------------------------
# element parsing + attribute grounding
# ---------------------------------------------------------------------------
def parse_element(section: str, element: str) -> dict:
    sec = (section or "").lower()
    el = element or ""
    if "policy" in sec and "#" in el:
        parts = el.split("#")
        d = {"polcod": parts[0]}
        if len(parts) > 1:
            d["polvar"] = parts[1]
        if len(parts) > 2:
            d["polval"] = parts[2]
        return d
    return {}


def attr_grounding(section: str, attr: str) -> tuple[str, str]:
    """Return (human phrase, tag) for the GUI attribute that deviated."""
    a = (attr or "").strip().lower()
    if a in POLDAT_COL:
        return (f"the GUI field '{attr}' maps to MOCA column {POLDAT_COL[a]} on poldat", "MOCA")
    if "countable" in a:
        return ("'Countable Area' is the aremst countable/cycle-count flag "
                "(1 = area is cycle-counted, 0 = excluded)", "MOCA")
    if "command" in a:
        return (f"'{attr}' stores an executable MOCA/job command body that the job runs at "
                "runtime; where the setting is 'Length and Command', the value is a byte-length "
                "header, then '**', then the command text", "MOCA")
    return ("", "")


# ---------------------------------------------------------------------------
# the explainer
# ---------------------------------------------------------------------------
AUD_LABEL = "audited site"
REF_LABEL = "reference standard"


def explain_row(row: dict, crfc: dict) -> tuple[str, str]:
    section = (row.get("Configuration Section") or "").strip()
    level = (row.get("Configuration Level") or "").strip()
    element = (row.get("Configuration Element") or "").strip()
    attr = (row.get("Configuration Element Attribute Name (GUI)")
            or row.get("Configuration Element Attribute ID") or "").strip()
    aval = (row.get("A value") or "").strip()
    rval = (row.get("R value") or "").strip()
    dtype = (row.get("Deviation Type") or "").strip()
    sev = (row.get("Deviation Severity") or "").strip()
    comments = (row.get("Deviation Comments") or "").strip()
    rationale = (row.get("Rationale") or "").strip()
    aud = (row.get("Audited Instance (A)") or "A").strip()
    ref = (row.get("Reference Instance (R)") or "R").strip()

    cites: list[str] = []
    sentences: list[str] = []

    # ---- section / table grounding -------------------------------------
    tbl_tag = SECTION_TABLE.get(section.lower())
    if tbl_tag:
        cites.append(f"[{tbl_tag[1]}] {section} is stored in {tbl_tag[0]}.")

    # ---- element grounding (policy key) --------------------------------
    pk = parse_element(section, element)
    if pk:
        key = " / ".join(f"{k}={v}" for k, v in pk.items())
        sentences.append(
            f"The element '{element}' is a MOCA policy key ({key}) held in poldat_view — "
            f"the same policy table the site's jobs read at runtime.")
        cites.append("[MOCA] Policy Maintenance element = polcod#polvar#polval in poldat_view.")
        low = element.lower()
        if low.startswith("host-mu"):
            for k, hint in HOSTMU_HINT.items():
                if k in low:
                    sentences.append(f"HOST-MU/{k.upper()} sets the {hint}.")
                    cites.append("[PRIME] HOST-MU policy defines host unit-of-measure defaults.")
                    break

    # ---- attribute grounding -------------------------------------------
    if attr:
        phrase, tag = attr_grounding(section, attr)
        if phrase:
            cites.append(f"[{tag}] {phrase}.")

    # ---- per-type narrative --------------------------------------------
    if dtype.lower().startswith("missing"):
        sentences.insert(0,
            f"Deviation type 'Missing record': the {REF_LABEL} ({ref}) defines this "
            f"{section or 'configuration'} record but the {AUD_LABEL} ({aud}) does not have it. "
            f"Columns I (A value) and J (R value) are blank because an ENTIRE record is absent — "
            f"not a single attribute — so the expected content is carried in Deviation Comments.")
        cites.append("[PRIME] 'Missing record' = present in the golden standard, absent at the site.")
    elif dtype.lower().startswith("unexpected") and "mismatch" not in dtype.lower():
        sentences.insert(0,
            f"Deviation type 'Unexpected record': the {AUD_LABEL} ({aud}) has this "
            f"{section or 'configuration'} record but it does NOT exist in the {REF_LABEL} ({ref}). "
            f"Columns I and J are blank because the whole record is extra site-specific config; "
            f"its content is in Deviation Comments.")
        cites.append("[PRIME] 'Unexpected record' = extra config at the site not in the standard; "
                     "normally needs a CFG-RFC to be productised, or removal.")
    elif "mismatch" in dtype.lower():
        d = diff_ij(aval, rval)
        elem_name = element or attr or "this element"
        head = (
            f"This is a value difference. Both the audited site ({aud}) and the reference "
            f"standard ({ref}) have '{elem_name}', but they hold different values for the "
            f"'{attr or 'attribute'}' setting. "
            f"The site has {_describe_val(aval)}; the standard expects {_describe_val(rval)}. "
        )
        head += d["text"]
        sentences.insert(0, head)
        if d["formatting"]:
            cites.append("[PYTHON] After normalising case, spacing and order, the two values are "
                         "the same — the difference is formatting only, not a real change.")
        else:
            cites.append("[PYTHON] The two values are genuinely different content (not just "
                         "formatting or ordering), so this is a real difference in the setting.")

    # ---- severity / exception grounding --------------------------------
    if sev.lower() == "accepted":
        sentences.append("This deviation is severity 'accepted' — it is a governed, signed-off "
                         "exception rather than an open finding.")
        cites.append("[PRIME] severity 'accepted' = a governed exception, excluded from the open score.")

    grp = _group_re.search(comments)
    cfg = _cfg_re.search(rationale or "") or _cfg_re.search(grp.group(1) if grp else "")
    if cfg:
        code = cfg.group(0).upper()
        rec = crfc.get(code)
        if rec:
            sentences.append(f"It is governed by {code} — \"{rec['title']}\" "
                             f"(site: {rec['site'] or 'n/a'}; status: {rec['status'] or 'n/a'}"
                             f"{'; type: ' + rec['type'] if rec['type'] else ''}).")
            cites.append(f"[CRFC] {code} found in the CFG-RFC register (Configuration_RFC.csv).")
        else:
            sentences.append(f"Its rationale cites {code}, but that code is NOT in the current "
                             f"CFG-RFC register — the exception is an orphan and should be re-reviewed.")
            cites.append(f"[CRFC] {code} NOT found in Configuration_RFC.csv (orphan exception).")

    # ---- modification provenance ---------------------------------------
    mu = _mod_user_re.search(comments)
    md = _mod_date_re.search(comments)
    if mu or md:
        who = mu.group(1) if mu else "?"
        when = md.group(1) if md else "?"
        sentences.append(f"Last changed by {who} on {when} (from Deviation Comments).")
        cites.append("[PYTHON] modification user/date parsed from the Deviation Comments blob.")

    explanation = " ".join(s.strip() for s in sentences if s.strip())
    grounding = " ".join(cites)
    return explanation, grounding


def _is_codeblob(v: str) -> bool:
    """True when a value is a MOCA/txplan code block (a job body), not a scalar setting."""
    s = str(v or "")
    return len(s) > 200 and ("select" in s.lower() or "catch(" in s.lower() or "@?" in s)


def triage_row(row: dict, crfc: dict) -> tuple[str, str, str]:
    """Deterministic, register-grounded triage of one deviation.

    Returns (exception_trail_status, recommended_action, ai_info) where:
      exception_trail_status  HEALTHY / STALE (<status>) / ORPHAN / UNBACKED  (accepted rows only)
      recommended_action      a single filterable verb for Power BI
      ai_info                 the plain-English 'why + what to do' sentence — the AI Info column
                              that the CoE asked to feed Power BI (e.g. the CFG1600 case).
    """
    sev = (row.get("Deviation Severity") or "").strip().lower()
    typ = (row.get("Deviation Type") or "").strip().lower()
    aval = (row.get("A value") or "").strip()
    rval = (row.get("R value") or "").strip()
    element = (row.get("Configuration Element") or "").strip()

    code = row_cfg_code(row)
    rec = crfc.get(code) if code else None
    status = (rec or {}).get("status", "")
    title = (rec or {}).get("title", "")
    ctype = (rec or {}).get("type", "")
    is_stale = bool(rec) and status.lower() in DEAD_STATUSES

    is_health = sev.startswith("health")
    is_2022 = sev == "2022"
    is_accepted = sev == "accepted"

    # ---- Exception Trail Status (accepted rows only) -----------------------
    trail = ""
    if is_accepted:
        if not code:
            trail = "UNBACKED"
        elif not rec:
            trail = "ORPHAN"
        elif is_stale:
            trail = f"STALE ({status})"
        else:
            trail = "HEALTHY"

    # ---- Recommended Action + AI Info -------------------------------------
    if is_health:
        action = "HEALTH_CHECK"
        ai = "Health-check row — affects the Health Score only, not the Config Score. No config action."
    elif is_2022:
        action = "FIX_BEFORE_MIGRATION"
        ai = ("Migration-only deviation (2014->2022). Fix this before migrating the site; "
              "it does not affect the live Config Score.")
    elif is_accepted:
        if trail == "HEALTHY":
            action = "MONITOR"
            ai = (f"Accepted exception, governed by {code} - \"{title}\" (status: {status or 'n/a'}"
                  f"{'; type: ' + ctype if ctype else ''}). Backing ticket is live; no action, monitor only.")
            if _is_codeblob(aval) and _is_codeblob(rval):
                ai = (f"Accepted exception: the audited code matches an approved earlier version "
                      f"associated with change request {code} (\"{title}\"). The site will receive the "
                      f"updated version in a future product release. Backing ticket status: {status or 'n/a'}.")
        elif trail.startswith("STALE"):
            action = "REVIEW_STALE_EXCEPTION"
            ai = (f"Accepted, but its backing change request {code} (\"{title}\") is {status} in the "
                  f"register. The exception is no longer clearly governed - confirm which CFG-RFC "
                  f"currently applies or re-open the deviation.")
            if _is_codeblob(aval) and _is_codeblob(rval):
                ai = (f"Accepted exception: the site runs an approved earlier version tied to {code} "
                      f"(\"{title}\"), BUT {code} is now {status} in the register. Confirm the current "
                      f"governing CFG-RFC before relying on this acceptance.")
        elif trail == "ORPHAN":
            action = "FIND_ORPHAN_TICKET"
            ai = (f"Accepted and cites {code}, but that code is NOT in the CFG-RFC register. "
                  f"Attach the real governing CFG-RFC or drop the acceptance.")
        else:  # UNBACKED
            action = "JUSTIFY_OR_REOPEN"
            ai = ("Accepted with no CFG-RFC recorded on the row. It has no governing ticket - "
                  "justify it with a CFG-RFC or re-open; an unbacked acceptance may be masking a real gap.")
    else:
        # OPEN row — counts against the Config Score
        if sev == "high":
            action = "FIX_NOW_HIGH"
            ai = ("HIGH-severity open deviation with significant WMS impact. Fix to the standard now, "
                  "or raise a CFG-RFC if the site value is genuinely required.")
        elif "mismatch" in typ and aval and rval:
            d = diff_ij(aval, rval)
            if d["formatting"]:
                action = "IGNORE_FORMATTING"
                ai = ("Open, but the difference is formatting-only (case/whitespace/order). "
                      "No functional change - safe to ignore or normalise.")
            else:
                action = "FIX_OR_RAISE_CFG_RFC"
                ai = (f"Open value difference: the site uses {_describe_val(aval)} where the standard "
                      f"expects {_describe_val(rval)}. Fix to the standard, or raise a CFG-RFC if the "
                      f"site value is genuinely required.")
        elif typ.startswith("missing"):
            action = "ADD_STANDARD_OR_RAISE_CFG_RFC"
            ai = ("Open 'Missing record': the standard defines this record but the site lacks it. "
                  "Add it to match the standard, or raise a CFG-RFC if the site legitimately omits it.")
        elif typ.startswith("unexpected"):
            action = "REMOVE_OR_RAISE_CFG_RFC"
            ai = ("Open 'Unexpected record': the site has config not in the standard. Remove it, "
                  "or raise a CFG-RFC to productise it as an allowed variation.")
        else:
            action = "REVIEW"
            ai = "Open deviation - review against the standard and decide fix vs CFG-RFC."

    return trail, action, ai


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN, help="deviation CSV to explain")
    ap.add_argument("--out", dest="out", default="", help="output CSV (default: <in>_explained.csv)")
    ap.add_argument("--crfc", dest="crfc", default=DEFAULT_CRFC, help="CFG-RFC register CSV")
    args = ap.parse_args()

    inp = args.inp
    if not os.path.exists(inp):
        log(f"ERROR input not found: {inp}")
        raise SystemExit(2)
    out = args.out or os.path.splitext(inp)[0] + "_explained.csv"

    log(f"reading {inp}")
    try:
        with open(inp, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except Exception as e:
        log(f"ERROR failed to read input: {type(e).__name__}: {e}")
        raise
    log(f"{len(rows)} rows, {len(fieldnames)} columns")

    crfc = load_crfc(args.crfc)

    new_cols = ["Deviation Explanation (NL)", "Grounding & Citations",
                "Exception Trail Status", "Recommended Action", "AI Info"]
    out_fields = fieldnames + [c for c in new_cols if c not in fieldnames]

    kinds: Counter = Counter()
    actions: Counter = Counter()
    trails: Counter = Counter()
    try:
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=out_fields)
            writer.writeheader()
            for i, row in enumerate(rows, 1):
                try:
                    expl, grnd = explain_row(row, crfc)
                    trail, action, ai = triage_row(row, crfc)
                except Exception as e:
                    log(f"ERROR row {i} ({row.get('Configuration Element','?')}): "
                        f"{type(e).__name__}: {e}")
                    raise
                row["Deviation Explanation (NL)"] = expl
                row["Grounding & Citations"] = grnd
                row["Exception Trail Status"] = trail
                row["Recommended Action"] = action
                row["AI Info"] = ai
                kinds[(row.get("Deviation Type") or "?").strip()] += 1
                actions[action] += 1
                if trail:
                    trails[trail.split(" ")[0]] += 1
                writer.writerow(row)
                if i % 100 == 0:
                    log(f"  explained {i}/{len(rows)}")
    except Exception as e:
        log(f"ERROR failed to write output: {type(e).__name__}: {e}")
        raise

    log(f"DONE wrote {out}")
    for k, v in kinds.most_common():
        log(f"  {v:4d}  {k}")
    log("--- Exception Trail Status (accepted rows) ---")
    for k, v in trails.most_common():
        log(f"  {v:4d}  {k}")
    log("--- Recommended Action ---")
    for k, v in actions.most_common():
        log(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
