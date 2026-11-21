"""explain_config_values — attach a plain-English MEANING to every configuration value in
the Config-Drift feed: what the setting IS, what the site's value means vs the standard's,
and the record context — grounded, never guessed.

WHAT PROBLEM THIS SOLVES
------------------------
The drift report says e.g. `Area Maintenance · DRPR · cap_fill_flg · A=1 · R=0`. A reviewer
who is not a Blue Yonder config expert cannot tell what "cap_fill_flg = 1" MEANS or whether it
matters. This module turns each row into a sentence a business reviewer can read:
  "Optimize Replenishment Quantity (cap_fill_flg) is a Yes/No setting. This site has it
   ENABLED (1); the standard has it DISABLED (0). Applies to Area Type DRPR 'BASE-DMGE …'."

GROUNDING — three honest sources, each cited (Citation Rule)
-----------------------------------------------------------
  [FEED]    the report itself supplies the GUI label and the Deviation Details context
            (Area Type, Area Description, Building, Number of Locations, Group Name …).
  [GENERAL] Blue Yonder / WMS convention decodes boolean FLAGs deterministically
            (1/Y/T = enabled, 0/N/F = disabled). 100 of 221 attributes are flags.
  [DICT]    an EDITABLE dictionary you own — config_value_dictionary.json — where you paste
            the authoritative SharePoint definitions for CODE attributes (atecod, devcls,
            pckcod …) whose meaning cannot be derived. Once filled, your text wins and PERSISTS.

NO GUESSING: a CODE value with no dictionary entry is reported as "needs definition" and
listed in the dictionary with needs_definition=true — a task, not a fabricated meaning.

THE DICTIONARY (config_value_dictionary.json) — create-once, never clobbered
----------------------------------------------------------------------------
First run SEEDS it from the feed: every attribute gets its GUI label + value-type; flags get
auto value-meanings; codes get blank stubs flagged needs_definition. Re-runs only ADD newly
seen attributes/values — they never overwrite a 'means' you have filled in. So you can edit it
(or paste SharePoint content) and re-run safely.

OUTPUTS
-------
  Config report/config_value_dictionary.json   the editable source of truth (you extend this)
  Config report/config_value_meanings.csv      one row per distinct value-context, human text
  UIUX/assets/config-meanings.js               window.WHS_MEAN lookup for inline HTML tooltips

Follows workspace rules: timestamped heartbeat logs; no silent failure (log type+message then
raise); fixed absolute paths under the M&M workspace; no network.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
from collections import Counter, defaultdict

import pandas as pd

from paths import WORKSPACE as ONEDRIVE  # portable workspace root (see paths.py)
COE = os.path.join(ONEDRIVE, "Config report", "data.xlsx")
DICT_PATH = os.path.join(ONEDRIVE, "Config report", "config_value_dictionary.json")
OUT_CSV = os.path.join(ONEDRIVE, "Config report", "config_value_meanings.csv")
OUT_JS = os.path.join(ONEDRIVE, "UIUX", "assets", "config-meanings.js")

PAIR_RE = re.compile(r"([A-Za-z0-9 _/&.\-]+?)\s*<([^>]*)>")
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Blue Yonder / WMS boolean-flag convention (domain knowledge — [GENERAL]).
FLAG_TRUE = {"1", "Y", "T", "YES", "TRUE"}
FLAG_FALSE = {"0", "N", "F", "NO", "FALSE"}


def log(msg: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def classify(attr_id: str, values: set[str]) -> str:
    """FLAG | NUMERIC | COMMAND | TEXT | CODE — deterministic from id + observed values."""
    keys = {v for v in values if v != ""}
    low = attr_id.lower()
    if low.endswith("flg") or (keys and keys <= (FLAG_TRUE | FLAG_FALSE)):
        return "FLAG"
    if any(t in low for t in ("cmd", "command")):
        return "COMMAND"
    if any(t in low for t in ("txt", "text", "desc", "mls")) or low in ("name",):
        return "TEXT"
    if keys and all(NUM_RE.match(k) for k in keys):
        return "NUMERIC"
    return "CODE"


def flag_meaning(v: str) -> str:
    u = v.strip().upper()
    if u in FLAG_TRUE:
        return "enabled / yes"
    if u in FLAG_FALSE:
        return "disabled / no"
    return ""


def read_text(path: str) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, FileNotFoundError):
            if not os.path.exists(path):
                return ""
            continue
    return ""


def load_dictionary() -> dict:
    if os.path.exists(DICT_PATH):
        try:
            d = json.loads(read_text(DICT_PATH))
            log(f"loaded existing dictionary ({len(d.get('attributes', {}))} attributes) — your edits are preserved")
            return d
        except Exception as e:
            log(f"ERROR dictionary unreadable ({type(e).__name__}: {e}); refusing to overwrite — fix or remove {DICT_PATH}")
            raise
    log("no dictionary yet — a fresh one will be seeded from the feed")
    return {"_meta": {}, "attributes": {}}


def seed_dictionary(d: dict, seen: dict) -> tuple[dict, int, int]:
    """Add attributes/values observed in the feed WITHOUT clobbering any human 'means'."""
    attrs = d.setdefault("attributes", {})
    new_attr = new_val = 0
    for aid, info in seen.items():
        vtype = info["type"]
        label = info["label"]
        entry = attrs.get(aid)
        if entry is None:
            entry = attrs[aid] = {
                "label": label,
                "type": vtype,
                "sections": sorted(info["sections"])[:6],
                "means": "",                      # <- YOU fill this (authoritative, from SharePoint)
                "values": {},
                "needs_definition": vtype == "CODE",
                "source": ("auto-seed: flag convention" if vtype == "FLAG"
                           else "auto-seed: numeric setting" if vtype == "NUMERIC"
                           else "auto-seed: command/script" if vtype == "COMMAND"
                           else "auto-seed: free text" if vtype == "TEXT"
                           else "auto-seed: NEEDS SharePoint definition"),
            }
            new_attr += 1
        else:
            # keep human fields; only refresh the auto label if it was blank
            if not entry.get("label"):
                entry["label"] = label
            entry.setdefault("type", vtype)
            entry.setdefault("values", {})
        vmap = entry["values"]
        for v in info["values"]:
            if v == "" or v in vmap:
                continue
            if entry["type"] == "FLAG":
                vmap[v] = {"means_auto": flag_meaning(v) or "(non-standard flag value)", "means": ""}
            elif entry["type"] in ("NUMERIC", "COMMAND", "TEXT"):
                vmap[v] = {"means_auto": "", "means": ""}
            else:  # CODE — the honest gap
                vmap[v] = {"means_auto": "", "means": "", "needs_definition": True}
            new_val += 1
    return d, new_attr, new_val


def resolve_value_meaning(entry: dict, v: str) -> tuple[str, str]:
    """Return (meaning_text, citation) for a single value using dictionary then convention."""
    vmap = entry.get("values", {})
    ve = vmap.get(v, {})
    if ve.get("means"):
        return ve["means"], "[DICT] your definition"
    if entry.get("means") and entry["type"] != "FLAG":
        # attribute-level human definition applies
        pass
    if entry["type"] == "FLAG":
        m = flag_meaning(v)
        if m:
            return m, "[GENERAL] BY flag convention"
    if ve.get("means_auto"):
        return ve["means_auto"], "[GENERAL] convention"
    return "", ""


def decode_details(details: str) -> str:
    """Turn 'Area Type <DRPR>, Area Description <BASE-DMGE …>' into 'Area Type=DRPR; …'."""
    if not details:
        return ""
    pairs = PAIR_RE.findall(details)
    keep = []
    for k, val in pairs:
        k = k.strip(" ,;").strip()
        val = val.strip()
        if not k or not val:
            continue
        if k.lower() in ("modification date", "modification user", "last updated date",
                         "last updated user", "stats reset date", "last execution date"):
            continue
        keep.append(f"{k}={val}")
    return "; ".join(keep[:6])


def main() -> int:
    if not os.path.exists(COE):
        log(f"ERROR COE reference not found: {COE}")
        raise SystemExit(2)

    log(f"reading {COE}")
    try:
        df = pd.read_excel(COE, sheet_name="Export")
    except Exception as e:
        log(f"ERROR failed to read COE xlsx: {type(e).__name__}: {e}")
        raise
    df.columns = [c.strip() for c in df.columns]
    n = len(df)
    log(f"{n:,} rows loaded")

    def col(name, *alts):
        for c in (name, *alts):
            if c in df.columns:
                return df[c].fillna("").astype(str)
        return pd.Series([""] * n)

    section = col("Configuration Section")
    element = col("Configuration Element")
    attr = col("Element Attribute ID")
    gui = col("Element Attribute Name (GUI)")
    aval = col("Audited Value")
    rval = col("Reference Value")
    typ = col("Deviation Type")
    details = col("Deviation Details")

    # ---- inventory attributes + values seen in the feed ----
    log("inventorying attributes and value domains…")
    seen: dict[str, dict] = {}
    for i in range(n):
        aid = attr.iloc[i].strip()
        if not aid:
            continue
        e = seen.get(aid)
        if e is None:
            e = seen[aid] = {"label": "", "type": "", "values": Counter(), "sections": set(),
                             "gui": Counter()}
        if gui.iloc[i].strip():
            e["gui"][gui.iloc[i].strip()] += 1
        for v in (aval.iloc[i].strip(), rval.iloc[i].strip()):
            if v != "":
                e["values"][v] += 1
        e["sections"].add(section.iloc[i].strip())
    for aid, e in seen.items():
        e["label"] = e["gui"].most_common(1)[0][0] if e["gui"] else aid
        e["type"] = classify(aid, set(e["values"]))
        e["values"] = set(e["values"])

    # ---- load + seed the editable dictionary (persist human edits) ----
    d = load_dictionary()
    d, new_attr, new_val = seed_dictionary(d, seen)
    d["_meta"] = {
        "purpose": "Editable meaning dictionary for Config-Drift attribute values. Fill 'means' "
                   "(attribute-level) and values[*].means (value-level) from the authoritative "
                   "SharePoint/CoE definitions. FLAG meanings are auto (BY convention). CODE "
                   "attributes with needs_definition=true are awaiting your SharePoint text.",
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        "attributes_total": len(d["attributes"]),
        "needs_definition": sorted(a for a, e in d["attributes"].items() if e.get("needs_definition")
                                   and not e.get("means")
                                   and not any(v.get("means") for v in e.get("values", {}).values())),
    }
    try:
        with open(DICT_PATH, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    except Exception as e:
        log(f"ERROR failed to write {DICT_PATH}: {type(e).__name__}: {e}")
        raise
    log(f"dictionary saved: {DICT_PATH} (+{new_attr} attributes, +{new_val} values this run; "
        f"{len(d['_meta']['needs_definition'])} CODE attrs still need SharePoint definitions)")

    attrs = d["attributes"]

    # ---- build per-distinct-context explanations ----
    log("writing plain-English value meanings…")
    seen_ctx: set[tuple] = set()
    rows = []
    byattr = {}
    bycontext = {}
    cite_tot = Counter()
    for i in range(n):
        aid = attr.iloc[i].strip()
        if not aid:
            continue
        a = aval.iloc[i].strip()
        r = rval.iloc[i].strip()
        tp = typ.iloc[i].strip()
        sec = section.iloc[i].strip()
        ctx = (aid, a, r, tp)
        if ctx in seen_ctx:
            continue
        seen_ctx.add(ctx)

        entry = attrs.get(aid, {"label": gui.iloc[i].strip() or aid, "type": classify(aid, {a, r}),
                                "means": "", "values": {}})
        label = entry.get("label") or aid
        vtype = entry.get("type", "CODE")

        a_mean, a_cite = resolve_value_meaning(entry, a) if a else ("", "")
        r_mean, r_cite = resolve_value_meaning(entry, r) if r else ("", "")

        # attribute-level meaning: prefer human dictionary text, else describe by type
        if entry.get("means"):
            what = entry["means"]
            what_cite = "[DICT] your definition"
        else:
            what_cite = "[FEED] GUI label"
            if vtype == "FLAG":
                what = f"'{label}' — a Yes/No setting (on/off flag)."
            elif vtype == "NUMERIC":
                what = f"'{label}' — a numeric setting."
            elif vtype == "COMMAND":
                what = f"'{label}' — an executable command/script; the two sides run different logic."
            elif vtype == "TEXT":
                what = f"'{label}' — a free-text field."
            else:
                what = f"'{label}' — a coded value." + ("" if a_mean or r_mean else " (code meanings awaiting SharePoint definition)")

        # compose the value comparison sentence honouring the deviation type
        def side(txt_val, mean):
            if txt_val == "":
                return "(blank)"
            return f"{txt_val}" + (f" = {mean}" if mean else "")

        tpl = tp.lower()
        if "missing" in tpl:
            comp = (f"The standard defines this record but the site does not have it "
                    f"(standard value {side(r, r_mean)}).")
        elif "unexpected record" in tpl:
            comp = (f"The site carries this record but the standard does not "
                    f"(site value {side(a, a_mean)}).")
        elif "mismatch" in tpl or "mismatching" in tpl:
            comp = (f"Site value {side(a, a_mean)}; standard value {side(r, r_mean)}.")
        else:
            comp = f"Site {side(a, a_mean)} vs standard {side(r, r_mean)}."

        context = decode_details(details.iloc[i])
        meaning = f"{what} {comp}" + (f" Applies to: {context}." if context else "")

        cites = "; ".join(sorted({c for c in (what_cite, a_cite, r_cite) if c}))
        cite_tot[vtype] += 1
        needs = (vtype == "CODE" and not entry.get("means")
                 and not a_mean and not r_mean and (bool(a) or bool(r)))

        rows.append({
            "Configuration Section": sec,
            "Configuration Element": element.iloc[i].strip(),
            "Attribute ID": aid,
            "Setting (GUI)": label,
            "Value type": vtype,
            "Deviation Type": tp,
            "Site value (A)": a,
            "Site value means": a_mean,
            "Standard value (R)": r,
            "Standard value means": r_mean,
            "What this value means": meaning,
            "Record context": context,
            "Grounding": cites,
            "Needs SharePoint definition": "YES" if needs else "",
        })

        # lookups for the UI
        if aid not in byattr:
            byattr[aid] = {"label": label, "type": vtype,
                           "means": entry.get("means", ""),
                           "values": {k: (v.get("means") or v.get("means_auto") or "")
                                      for k, v in entry.get("values", {}).items()}}
        bycontext[f"{aid}|{a}|{r}"] = meaning

    rows.sort(key=lambda x: (x["Needs SharePoint definition"] == "", x["Configuration Section"],
                             x["Attribute ID"]))
    cols = list(rows[0].keys()) if rows else ["Attribute ID"]
    try:
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    except Exception as e:
        log(f"ERROR failed to write {OUT_CSV}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_CSV} ({len(rows)} distinct value-contexts)")

    payload = {
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": os.path.basename(COE),
        "dictionary": os.path.basename(DICT_PATH),
        "byAttr": byattr,
        "byContext": bycontext,
        "totals": {"contexts": len(rows), "attributes": len(byattr),
                   "byType": dict(cite_tot),
                   "needs_definition": sum(1 for r in rows if r["Needs SharePoint definition"] == "YES")},
    }
    header = ("/* AUTO-GENERATED by explain_config_values.py — do not edit by hand.\n"
              f"   Meanings from {os.path.basename(DICT_PATH)} (editable) + feed + BY convention.\n"
              f"   {payload['generatedAt']} */\n"
              "window.WHS_MEAN = ")
    try:
        os.makedirs(os.path.dirname(OUT_JS), exist_ok=True)
        with open(OUT_JS, "w", encoding="utf-8") as fh:
            fh.write(header)
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write(";\n")
    except Exception as e:
        log(f"ERROR failed to write {OUT_JS}: {type(e).__name__}: {e}")
        raise
    log(f"wrote {OUT_JS}")

    log("")
    log("SUMMARY:")
    log(f"  distinct value-contexts explained   {len(rows):,}")
    log(f"  attributes covered                  {len(byattr)}")
    log(f"  by value type                       {dict(cite_tot)}")
    log(f"  contexts needing SharePoint text    {payload['totals']['needs_definition']:,}")
    log(f"  -> fill 'means' in {os.path.basename(DICT_PATH)} then re-run to enrich CODE values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
