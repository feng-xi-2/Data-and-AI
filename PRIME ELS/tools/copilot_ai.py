"""Copilot "Prep data for AI" for the hypercare model - one source for every build and for the shared .pbix.

AI instructions = config/copilot_instructions.md with {{SITES}} / {{KPIS}} filled from site_config.csv, kpi_thresholds.csv and
alert_rules.csv (max 10,000 characters - Power BI limit). They are stored where Power BI keeps them: CustomInstructions in the
model culture's linguistic metadata (the same text Desktop shows under Home > Prep data for AI > Add AI instructions).
Key measure descriptions = config/copilot_descriptions.csv (Copilot reads descriptions to pick the right measure).

    py tools/copilot_ai.py                 # render + print length, writes dist/copilot_instructions.md (preview)
    py tools/copilot_ai.py --live <PID>    # write instructions + descriptions into an open Desktop model (no data reload)
    py tools/copilot_ai.py --verify <PID>  # read them back from the open model; exit 1 if missing / different
build_pbip.build_model calls apply_pbip() so every generated PBIP carries them."""
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pbi_common import ROOT, read_csv, report_sites  # noqa: E402

LIMIT = 10000
CULTURE = "en-US"
TOOLING = "CopilotTooling"
PS = Path(__file__).resolve().parent / "apply_copilot_live.ps1"


# ---- Copilot answer tables: flat rows computed at refresh. Copilot answers far better from plain columns than from measures that
# only work inside a KPI-row context (KPI Status needs Cfg_Threshold[KPI_Key] + one site). (name, type, format, description)
# Clock KPIs describe the age of the copy, not the warehouse, and freeze when a table is calculated: freshness = Site Summary[Data As Of].
CLOCK_KPIS = {"DATA_LAG", "REFRESH_AGE"}
_ALERT = "MAXX(FILTER(Cfg_AlertRule, Cfg_AlertRule[KPI_Key] = k), Cfg_AlertRule[{c}])"
KPI_STATUS_DAX = (
    "VAR R = GENERATE(VALUES(Cfg_Site[SiteCode]),\n"
    "    SUMMARIZE(FILTER(Cfg_Threshold, Cfg_Threshold[SiteCode] = Cfg_Site[SiteCode] && Cfg_Threshold[Direction] IN {\"Higher\", \"Lower\", \"Band\"}\n"
    "            && NOT Cfg_Threshold[KPI_Key] IN {" + ", ".join(f'"{k}"' for k in sorted(CLOCK_KPIS)) + "}),\n"
    "        Cfg_Threshold[KPI_Key], Cfg_Threshold[Pillar_No], Cfg_Threshold[Pillar], Cfg_Threshold[KPI_Name], Cfg_Threshold[Unit], Cfg_Threshold[Direction]))\n"
    "VAR A = ADDCOLUMNS(R, \"@site\", CALCULATE([Site Name]), \"@s\", CALCULATE([KPI Status]), \"@a\", CALCULATE([KPI Actual]),\n"
    "    \"@at\", CALCULATE([KPI Actual Text]), \"@t\", CALCULATE([Thr Eff Target]), \"@w\", CALCULATE([Thr Eff Warn]), \"@c\", CALCULATE([Thr Eff Crit]),\n"
    "    \"@tt\", CALCULATE([KPI Target Text]), \"@p\", CALCULATE([KPI Predicted]), \"@pt\", CALCULATE([KPI Predicted Text]),\n"
    "    \"@ps\", CALCULATE([KPI Predicted Status]), \"@day\", CALCULATE([Report Date]), \"@asof\", CALCULATE([Last Refresh Site]),\n"
    "    \"@how\", CALCULATE([KPI How Text]), \"@num\", CALCULATE([KPI Numbers Text]), \"@diag\", CALCULATE([KPI Diagnosis]))\n"
    "RETURN SELECTCOLUMNS(A,\n"
    "    \"Site\", Cfg_Site[SiteCode], \"Site Name\", [@site], \"Pillar No\", Cfg_Threshold[Pillar_No], \"Pillar\", Cfg_Threshold[Pillar],\n"
    "    \"KPI\", Cfg_Threshold[KPI_Name], \"KPI Key\", Cfg_Threshold[KPI_Key], \"Status\", [@s],\n"
    "    \"Priority\", SWITCH([@s], \"CRITICAL\", 1, \"WARNING\", 2, \"OK\", 3, \"NO DATA\", 4, 5),\n"
    "    \"Actual\", [@a], \"Actual Text\", [@at], \"Unit\", Cfg_Threshold[Unit],\n"
    "    \"Better When\", SWITCH(Cfg_Threshold[Direction], \"Higher\", \"higher\", \"Lower\", \"lower\", \"close to target\"),\n"
    "    \"Target\", [@t], \"Warning Limit\", [@w], \"Critical Limit\", [@c], \"Target Text\", [@tt],\n"
    "    \"Forecast End Of Day\", [@p], \"Forecast Text\", [@pt], \"Forecast Status\", [@ps],\n"
    "    \"Report Day\", [@day], \"Data As Of\", [@asof], \"How Calculated\", [@how], \"Numbers Behind\", [@num], \"What To Check\", [@diag],\n"
    "    \"Meaning If Breached\", VAR k = Cfg_Threshold[KPI_Key] RETURN " + _ALERT.format(c="Insight_If_Breached") + ",\n"
    "    \"Recommended Action\", VAR k = Cfg_Threshold[KPI_Key] RETURN " + _ALERT.format(c="Recommended_Action") + ",\n"
    "    \"Owner\", VAR k = Cfg_Threshold[KPI_Key] RETURN " + _ALERT.format(c="Owner") + ")")
KPI_STATUS_COLS = [
    ("Site", "string", None, "Site code (BINHDUONG, MINHANG, JAKARTA, AKASHI, XIQING, ATHENS). Filter on it - never add sites together."),
    ("Site Name", "string", None, "Site name with plant code."),
    ("Pillar No", "int64", "0", "Sort order of the pillar."),
    ("Pillar", "string", None, "KPI group: Production, Inbound, Outbound, Warehouse, Users, Health."),
    ("KPI", "string", None, "KPI name."),
    ("KPI Key", "string", None, "Short KPI code (PPH, TTAT_IN, TTAT_OUT, LOC_UTIL, USER_PROD ...)."),
    ("Status", "string", None, "CRITICAL / WARNING / OK vs the site's limits; NO DATA = no activity; N/A = the site has no such process."),
    ("Priority", "int64", "0", "1 = CRITICAL, 2 = WARNING, 3 = OK, 4 = NO DATA, 5 = N/A. Sort ascending for the action plan."),
    ("Actual", "double", "#,0.00", "KPI value of the report day (percent KPIs as fractions: 0.82 = 82%). Use Actual Text to show it."),
    ("Actual Text", "string", None, "KPI value formatted with its unit, e.g. '127 min' or '81.9%'."),
    ("Unit", "string", None, "Unit of the KPI (min, %, plt/h, locs ...)."),
    ("Better When", "string", None, "higher / lower / close to target."),
    ("Target", "double", "#,0.00", "Target in use for this site."),
    ("Warning Limit", "double", "#,0.00", "Warning limit in use for this site."),
    ("Critical Limit", "double", "#,0.00", "Critical limit in use for this site."),
    ("Target Text", "string", None, "Target and limits formatted, e.g. '<= 45 min (warn > 50, crit > 54)'."),
    ("Forecast End Of Day", "double", "#,0.00", "End-of-day forecast of the KPI (blank when the KPI has no forecast)."),
    ("Forecast Text", "string", None, "Forecast formatted with its unit."),
    ("Forecast Status", "string", None, "Status of the forecast against the same limits."),
    ("Report Day", "dateTime", "yyyy-mm-dd", "Site-local shift day the values describe."),
    ("Data As Of", "dateTime", "yyyy-mm-dd hh:nn", "Time of the data refresh, site-local."),
    ("How Calculated", "string", None, "How the KPI is calculated, in plain words."),
    ("Numbers Behind", "string", None, "The numbers behind the value (counts, totals)."),
    ("What To Check", "string", None, "What to check when the KPI is off target."),
    ("Meaning If Breached", "string", None, "What a WARNING / CRITICAL status means for the operation."),
    ("Recommended Action", "string", None, "Action to take when the KPI is WARNING or CRITICAL."),
    ("Owner", "string", None, "Role that owns the action (Inbound lead, Warehouse lead, Shift leader ...)."),
]
SITE_SUMMARY_DAX = (
    "VAR K = 'KPI Scorecard'\n"
    "RETURN SELECTCOLUMNS(VALUES(Cfg_Site[SiteCode]),\n"
    "    \"Site\", Cfg_Site[SiteCode], \"Site Name\", CALCULATE([Site Name]), \"Region\", CALCULATE(SELECTEDVALUE(Cfg_Site[Region])),\n"
    "    \"WMS\", CALCULATE(SELECTEDVALUE(Cfg_Site[WMS_Version])), \"Report Day\", CALCULATE([Report Date]), \"Data As Of\", CALCULATE([Last Refresh Site]),\n"
    "    \"Critical KPIs\", VAR s = Cfg_Site[SiteCode] RETURN COUNTROWS(FILTER(K, [Site] = s && [Status] = \"CRITICAL\")) + 0,\n"
    "    \"Warning KPIs\", VAR s = Cfg_Site[SiteCode] RETURN COUNTROWS(FILTER(K, [Site] = s && [Status] = \"WARNING\")) + 0,\n"
    "    \"Overall State\", VAR s = Cfg_Site[SiteCode] VAR c = COUNTROWS(FILTER(K, [Site] = s && [Status] = \"CRITICAL\")) + 0\n"
    "        VAR w = COUNTROWS(FILTER(K, [Site] = s && [Status] = \"WARNING\")) + 0\n"
    "        RETURN IF(c > 0, \"CRITICAL - act now: \", IF(w > 0, \"WARNING - watch: \", \"OK: \")) & c & \" critical and \" & w & \" warning KPIs\",\n"
    "    \"Main Constraint\", CALCULATE([Narrative Verdict]),\n"
    "    \"Action Plan\", VAR s = Cfg_Site[SiteCode] RETURN CONCATENATEX(FILTER(K, [Site] = s && [Priority] <= 2 && [Recommended Action] <> \"\"),\n"
    "        [Status] & \": \" & [KPI] & \" \" & [Actual Text] & \" vs target \" & [Target Text] & \" -> \" & [Recommended Action] & \" (\" & [Owner] & \")\",\n"
    "        \" | \", [Priority], ASC, [Pillar No], ASC),\n"
    "    \"Production Outlook\", CALCULATE([Narrative Production Outlook]),\n"
    "    \"Failed Health Checks\", CALCULATE([KPI Health Fails]), \"Settings Status\", CALCULATE(SELECTEDVALUE(Cfg_Site[Config_Status])),\n"
    "    \"Also Called\", {{ALIASES}})")
SITE_SUMMARY_COLS = [
    ("Site", "string", None, "Site code. One row per site."),
    ("Site Name", "string", None, "Site name with plant code."),
    ("Region", "string", None, "Region of the site."),
    ("WMS", "string", None, "WMS version (PrIME 2014 / PrIME 2022)."),
    ("Report Day", "dateTime", "yyyy-mm-dd", "Site-local shift day the values describe."),
    ("Data As Of", "dateTime", "yyyy-mm-dd hh:nn", "Time of the data refresh, site-local. Use it for data freshness."),
    ("Critical KPIs", "int64", "0", "Number of KPIs in CRITICAL (rows of 'KPI Scorecard')."),
    ("Warning KPIs", "int64", "0", "Number of KPIs in WARNING (rows of 'KPI Scorecard')."),
    ("Overall State", "string", None, "One-line state of the site: CRITICAL / WARNING / OK with the counts."),
    ("Main Constraint", "string", None, "Main constraint of the site (space allocation, racking capacity, warehouse full, line, none) with the numbers."),
    ("Action Plan", "string", None, "Open KPIs critical first: status, KPI, actual vs target, action and owner, separated by ' | '."),
    ("Production Outlook", "string", None, "Production of the day: pallets so far, run rate, projected end of day vs plan."),
    ("Failed Health Checks", "int64", "0", "Failed data-health checks; above 0 = data may be incomplete."),
    ("Settings Status", "string", None, "VALIDATED or AUTO-PROFILED (site settings not yet confirmed by the site)."),
    ("Also Called", "string", None, "Other names users type for the site: abbreviation (BD), spelling variants, WH ID, SAP plant, country. "
     "Match a site name in a question against Site, Site Name and this column, ignoring case, accents and small typos."),
]
RETIRED_TABLES = ["KPI Status"]  # first name of 'KPI Scorecard' (clashed with the [KPI Status] measure) - removed from open models
ANSWER_TABLES = {
    "KPI Scorecard": ("COPILOT ANSWER TABLE - one row per site x KPI of the report day: value, target, limits, status, forecast, explanation, "
                      "action and owner (calculated at refresh). Use it for every KPI / status / action-plan question.", KPI_STATUS_DAX, KPI_STATUS_COLS),
    "Site Summary": ("COPILOT ANSWER TABLE - one row per site: KPI counts, overall state, main constraint, action plan, production outlook, "
                     "data as of (calculated at refresh).", SITE_SUMMARY_DAX, SITE_SUMMARY_COLS),
}


def visible_fields():
    """config/copilot_fields.csv: what Copilot may see. Everything else is hidden in the shared .pbix (Microsoft: hide fields Copilot
    does not need - helper measures, config tables, technical columns confuse it)."""
    return {r["Table"]: [f.strip() for f in r["Fields"].split("|") if f.strip()] for r in read_csv("copilot_fields.csv")}


def site_aliases(s):
    """Every name a user may type for a site: config/site_aliases.csv + code, name, WH_ID and SAP plant (fuzzy site matching)."""
    manual = next((r["Aliases"] for r in read_csv("site_aliases.csv") if r["SiteCode"] == s["SiteCode"]), "") \
        if (ROOT / "config" / "site_aliases.csv").exists() else ""
    auto = [s["SiteCode"], re.sub(r"\s*\(.*\)", "", s["SiteName"]).strip(), s.get("WH_ID", "")] + \
           ([f"plant {s['SAP_Plant']}"] if s.get("SAP_Plant") else [])
    out = []
    for a in auto + manual.split("|"):
        a = a.strip()
        if a and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out


def _alias_switch():
    # code / name / WH ID / SAP plant come from the model's own Cfg_Site row (a Service or ID12 override is then reflected);
    # only the hand-written names of config/site_aliases.csv are listed per site
    manual = {r["SiteCode"]: [a.strip() for a in r["Aliases"].split("|") if a.strip()] for r in read_csv("site_aliases.csv")} \
        if (ROOT / "config" / "site_aliases.csv").exists() else {}
    pairs = ", ".join(f'"{c}", "{", ".join(a).replace(chr(34), "")}"' for c, a in manual.items() if a)
    return ('VAR _w = CALCULATE(SELECTEDVALUE(Cfg_Site[WH_ID])) VAR _p = CALCULATE(SELECTEDVALUE(Cfg_Site[SAP_Plant])) '
            f'VAR _m = SWITCH(Cfg_Site[SiteCode], {pairs}, BLANK()) '
            'RETURN _w & IF(_p <> "", ", plant " & _p) & IF(_m <> "", ", " & _m)')


SITE_SUMMARY_DAX = SITE_SUMMARY_DAX.replace("{{ALIASES}}", _alias_switch())
ANSWER_TABLES["Site Summary"] = (ANSWER_TABLES["Site Summary"][0], SITE_SUMMARY_DAX, SITE_SUMMARY_COLS)


def sites_text(sites):
    out = []
    for s in sites:
        off = float(s.get("UTC_Offset_h") or 0)
        lacks = [n for k, n in (("Has_Production", "production line"), ("Has_LevelA", "Level A"), ("Has_HOFF", "HOFF area"))
                 if str(s.get(k, "1")).strip() in ("0", "")]
        status = (s.get("Config_Status") or "").split(" - ")[0]
        out.append(f"- {s['SiteCode']} = {s['SiteName']}, {s.get('WMS_Version', '')}, UTC{off:+g}"
                   + (f", {status}" if status else "") + (f"; no {', no '.join(lacks)}" if lacks else "")
                   + "; also called: " + ", ".join(site_aliases(s)[1:]))
    return "\n".join(out)


def _sap_left_out():
    return any(r.get("Setting") == "Include_SAP_CDL" and str(r.get("Value", "")).strip() == "0" for r in read_csv("build_options.csv"))


def kpis_text():
    """Compact KPI glossary: key = name (unit, better direction). Targets, limits, actions and owners are site-specific and live in
    'KPI Scorecard' - repeating them here could contradict the data (Microsoft: keep instructions focused, avoid conflicts)."""
    no_sap = _sap_left_out()
    rows = [r for r in read_csv("kpi_thresholds.csv") if r["Site"] == "*" and r["Direction"] in ("Higher", "Lower", "Band")
            and not (no_sap and "SAP" in r["KPI_Name"]) and r["KPI_Key"] not in CLOCK_KPIS]
    rows.sort(key=lambda r: (int(r["Pillar_No"] or 99), r["KPI_Key"]))
    word = {"Higher": "higher better", "Lower": "lower better", "Band": "near target"}
    words = {r["KPI_Key"]: r["User_Words"].replace("|", ", ") for r in read_csv("copilot_kpi_words.csv")} \
        if (ROOT / "config" / "copilot_kpi_words.csv").exists() else {}
    out, pillar = [], None
    for r in rows:
        if r["Pillar"] != pillar:
            pillar = r["Pillar"]
            out.append(f"{pillar}:")
        out.append(f"- {r['KPI_Key']}: {r['KPI_Name']}; {r['Unit']}, {word[r['Direction']]}"
                   + (f'; aka {words[r["KPI_Key"]]}' if words.get(r["KPI_Key"]) else ""))
    return "\n".join(out)


def questions():
    return read_csv("copilot_questions.csv")


def questions_for(sites):
    """copilot_questions.csv with the example site names swapped for the sites IN THIS FILE (a Jakarta-only file never shows
    'How is BINHDUONG doing today?'); several sites in the file: every other site code maps onto them in turn."""
    codes = [s["SiteCode"] for s in sites] or [s["SiteCode"] for s in report_sites()]
    known = sorted({s["SiteCode"] for s in read_csv("site_config.csv")} | set(codes), key=len, reverse=True)
    others = [c for c in known if c not in codes]
    swap = {c: codes[i % len(codes)] for i, c in enumerate(others)}
    out = []
    for r in questions():
        r = dict(r)
        for col in ("Example", "Template", "What_You_Get"):
            if r.get(col):
                r[col] = re.sub(r"\b(" + "|".join(map(re.escape, others)) + r")\b", lambda m: swap[m.group(1)], r[col]) if others else r[col]
        out.append(r)
    return out


def questions_text(sites=None):
    rows = questions_for(sites) if sites else questions()
    if sites and len(sites) == 1:          # one-site file: no cross-site templates
        rows = [r for r in rows if "compare" not in (r.get("Group") or "").lower()]
    return "\n".join(f"- Q: {r['Template']}\n  A: {r['Steps']}" for r in rows)


def example_prompts(sites=None):
    """Starter questions Copilot shows when it opens (PBIP Copilot/examplePrompts.json) - the Example column, real site names."""
    sites = sites if sites else report_sites()
    codes = {s["SiteCode"] for s in sites}
    out_of_report = {s["SiteCode"] for s in read_csv("site_config.csv")} - codes
    ex = [r["Example"] for r in questions_for(sites)]
    bad = [e for e in ex if any(re.search(rf"\b{c}\b", e, re.I) for c in out_of_report)]
    if bad:
        raise SystemExit(f"config/copilot_questions.csv Example names a site that is not in the report: {bad}")
    return ex


def render(sites=None):
    sites = sites if sites is not None else report_sites()
    tpl = (ROOT / "config" / "copilot_instructions.md").read_text(encoding="utf-8")
    txt = (tpl.replace("{{SITES}}", sites_text(sites)).replace("{{KPIS}}", kpis_text())
           .replace("{{QUESTIONS}}", questions_text(sites)).strip() + "\n")
    if len(txt) > LIMIT:
        raise SystemExit(f"Copilot AI instructions are {len(txt)} characters - Power BI allows {LIMIT}. "
                         "Shorten config/copilot_instructions.md or config/copilot_questions.csv")
    return txt


def descriptions():
    return {r["Measure"]: r["Description"] for r in read_csv("copilot_descriptions.csv")}


def merge_culture(content, text):
    """Linguistic metadata JSON with CustomInstructions = text (keeps the Q&A entities Desktop generated)."""
    payload = json.loads(content) if content and content.strip() else \
        {"Version": "4.2.0", "Language": CULTURE, "Entities": {}, "Agents": {"Internal": {"Version": "1.1.0"}}}
    payload["CustomInstructions"] = text
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def tooling_annotation(model_tmdl):
    m = re.search(r"^annotation PBI_ProTooling = (\[.*\])$", model_tmdl, re.M)
    if m:
        lst = json.loads(m.group(1))
        if TOOLING in lst:
            return model_tmdl
        return model_tmdl.replace(m.group(0), "annotation PBI_ProTooling = " + json.dumps(lst + [TOOLING]))
    return model_tmdl.rstrip("\n") + f"\n\nannotation PBI_ProTooling = {json.dumps([TOOLING])}\n"


def apply_pbip(out_sm, sites=None):
    """Write the AI instructions into a generated PBIP semantic model folder; returns the instruction length."""
    defn = Path(out_sm) / "definition"
    text = render(sites)
    cf = defn / "cultures" / f"{CULTURE}.tmdl"
    if cf.exists():
        t = cf.read_text(encoding="utf-8")
        m = re.search(r"^(\tlinguisticMetadata = )(.*)$", t, re.M)
        if not m:
            raise SystemExit(f"{cf}: no linguisticMetadata line - cannot add the Copilot AI instructions")
        t = t[:m.start(2)] + merge_culture(m.group(2), text) + t[m.end(2):]
    else:
        cf.parent.mkdir(parents=True, exist_ok=True)
        t = f"cultureInfo {CULTURE}\n\n\tlinguisticMetadata = {merge_culture('', text)}\n\t\tcontentType: json\n\n"
    cf.write_text(t, encoding="utf-8")
    mf = defn / "model.tmdl"
    mt = mf.read_text(encoding="utf-8")
    if f"ref cultureInfo {CULTURE}" not in mt:
        mt = mt.rstrip("\n") + f"\n\nref cultureInfo {CULTURE}\n"
    mf.write_text(tooling_annotation(mt), encoding="utf-8")
    write_copilot_folder(Path(out_sm), text, sites)
    return len(text)


SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"


def write_copilot_folder(out_sm, text, sites=None):
    """PBIP <Model>.SemanticModel/Copilot/ in the layout Power BI Desktop saves (microsoft/fabric-data-agent-workshop sample + json-schemas):
    Instructions (same text as the culture CustomInstructions), example prompts = the starter questions Copilot offers, Q&A indexing on."""
    cp = out_sm / "Copilot"
    ver = {"$schema": SCHEMA + "version/1.0.0/schema.json", "version": "1.0.0"}
    files = {
        "version.json": ver,
        "settings.json": {"$schema": SCHEMA + "semanticModel/copilot/settings/1.0.0/schema.json", "indexingEnabled": True},
        "examplePrompts.json": {"$schema": SCHEMA + "semanticModel/copilot/examplePrompts/1.0.0/schema.json", "prompts": example_prompts(sites)},
        "Instructions/version.json": ver,
    }
    too_long = [p for p in files["examplePrompts.json"]["prompts"] if len(p) > 500]
    if too_long:
        raise SystemExit(f"config/copilot_questions.csv Example longer than 500 characters (Power BI limit): {too_long[0][:60]}...")
    for rel, obj in files.items():
        f = cp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (cp / "Instructions" / "instructions.md").write_text(text, encoding="utf-8")
    write_schema(out_sm)


def write_schema(out_sm):
    """Copilot/schema.json - written with the Copilot folder and again after tools/ai_descriptions.py added the Field Dictionary."""
    sch, st = ai_schema(out_sm)
    (Path(out_sm) / "Copilot" / "schema.json").write_text(json.dumps(sch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"   Copilot AI data schema: {st}", flush=True)


def ai_schema(out_sm):
    """Copilot/schema.json (Prep data for AI > Simplify the data schema): a compact business schema from config/copilot_schema.csv
    (first matching rule per table / measure / 'Table|Column'). Hidden model objects stay out. Every object a Visible measure uses
    (other measures, 'Table'[Column]) is kept Visible - Microsoft: the schema must include the dependencies of the selected measures."""
    rules = [(r["Kind"], re.compile(r["Pattern"]), r["Visibility"], [s for s in (r.get("Synonyms") or "").split("|") if s])
             for r in read_csv("copilot_schema.csv")]

    def rule(kind, key):
        return next(((v, syn) for k, p, v, syn in rules if k == kind and p.search(key)), ("Visible", []))

    tabs = {}
    for f in sorted((Path(out_sm) / "definition" / "tables").glob("*.tmdl")):
        L = f.read_text(encoding="utf-8").splitlines()
        tl = next(i for i, x in enumerate(L) if x.startswith("table "))
        tn = L[tl][6:].strip().strip("'").replace("''", "'")
        t = {"hidden": any(x.strip() == "isHidden" for x in L[tl + 1:tl + 4]), "cols": {}, "meas": {}}
        cur = None
        for i, ln in enumerate(L):
            m = re.match(r"^\t(measure|column) ('(?:[^']|'')+'|[^\s=]+)", ln)
            if m:
                n = m.group(2).strip("'").replace("''", "'")
                cur = (m.group(1), n)
                body = ln.split(" = ", 1)[1] if " = " in ln else ""
                hid = False
                (t["meas"] if cur[0] == "measure" else t["cols"])[n] = {"dax": body, "hidden": hid}
            elif cur and (ln.startswith("\t\t") or ln.startswith("\t\t\t")):
                o = (t["meas"] if cur[0] == "measure" else t["cols"])[cur[1]]
                if ln.strip() == "isHidden":
                    o["hidden"] = True
                elif not re.match(r"^\t\t(formatString|displayFolder|lineageTag|dataType|summarizeBy|sourceColumn|sortByColumn|"
                                  r"annotation|isHidden|dataCategory|formatStringDefinition|changedProperty)", ln):
                    o["dax"] += "\n" + ln
            elif ln.startswith("\t") and not ln.startswith("\t\t") and ln.strip():
                cur = None
        tabs[tn] = t
    vis = {}
    for tn, t in tabs.items():
        tv, tsyn = rule("Table", tn)
        vis[("t", tn)] = (tv if not t["hidden"] else "Hidden", tsyn)
        for n, o in t["meas"].items():
            v, syn = rule("Measure", n)
            vis[("m", tn, n)] = ("Hidden" if o["hidden"] else v, syn)
        for n, o in t["cols"].items():
            v, syn = rule("Column", f"{tn}|{n}")
            vis[("c", tn, n)] = ("Hidden" if o["hidden"] or t["hidden"] or tv == "Hidden" else v, syn)
    where = {n: tn for tn, t in tabs.items() for n in t["meas"]}
    todo = [k for k, (v, _) in vis.items() if k[0] == "m" and v == "Visible"]
    added = 0
    while todo:                                  # dependency closure of the visible measures
        k = todo.pop()
        dax = tabs[k[1]]["meas"][k[2]]["dax"]
        for m in re.finditer(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_][\w ]*?))?\[([^\]]+)\]", dax):
            tref, col = (m.group(1) or m.group(2) or "").replace("''", "'").strip(), m.group(3)
            if tref and tref in tabs and col in tabs[tref]["cols"]:
                dk = ("c", tref, col)
            elif not tref and col in where:
                dk = ("m", where[col], col)
            else:
                continue
            if vis.get(dk, ("Visible",))[0] != "Visible" and not (tabs[dk[1]]["cols" if dk[0] == "c" else "meas"][dk[2]]["hidden"]):
                vis[dk] = ("Visible", vis[dk][1])
                added += 1
                if dk[0] == "m":
                    todo.append(dk)
                if vis[("t", dk[1])][0] != "Visible":
                    vis[("t", dk[1])] = ("Visible", vis[("t", dk[1])][1])
    out = []
    for tn, t in tabs.items():
        tv, tsyn = vis[("t", tn)]
        e = {"name": tn, "visibility": tv}
        if tsyn:
            e["synonyms"] = tsyn
        if t["cols"]:
            e["columns"] = [dict({"name": n, "visibility": vis[("c", tn, n)][0]},
                                 **({"synonyms": vis[("c", tn, n)][1]} if vis[("c", tn, n)][1] else {})) for n in t["cols"]]
        if t["meas"]:
            e["measures"] = [dict({"name": n, "visibility": vis[("m", tn, n)][0]},
                                  **({"synonyms": vis[("m", tn, n)][1]} if vis[("m", tn, n)][1] else {})) for n in t["meas"]]
        out.append(e)
    cnt = lambda kind: (sum(1 for k, (v, _) in vis.items() if k[0] == kind and v == "Visible"), sum(1 for k in vis if k[0] == kind))
    st = (f"tables {cnt('t')[0]}/{cnt('t')[1]}, measures {cnt('m')[0]}/{cnt('m')[1]}, columns {cnt('c')[0]}/{cnt('c')[1]} visible "
          f"({added} kept as dependencies) - config/copilot_schema.csv")
    return {"$schema": SCHEMA + "semanticModel/copilot/schema/1.0.0/schema.json", "tables": out}, st


def _ps(*args):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    for ln in (r.stdout + r.stderr).splitlines():
        if ln.strip():
            print("   " + ln.rstrip(), flush=True)
    if r.returncode:
        raise SystemExit(f"apply_copilot_live.ps1 {args[0]} failed (exit {r.returncode})")


def _sites_live():
    return report_sites()


def _get(pid):
    f = Path(tempfile.mkdtemp(prefix="copilot_ai_")) / "model.json"
    _ps("-ProcId", str(pid), "-Mode", "get", "-File", str(f))
    return json.loads(f.read_text(encoding="utf-8-sig"))


def live(pid):
    cur = _get(pid)
    text = render(_sites_live())
    payload = {"culture": merge_culture(cur.get("culture") or "", text),
               "descriptions": [{"table": "_KPI", "name": k, "description": v} for k, v in descriptions().items()],
               "tooling": TOOLING,
               "tables": [{"name": n, "description": d, "expression": dax,
                           "columns": {c[0]: {"description": c[3], "format": c[2]} for c in cols}} for n, (d, dax, cols) in ANSWER_TABLES.items()],
               "visible": visible_fields(), "retire": RETIRED_TABLES}
    pf = Path(tempfile.mkdtemp(prefix="copilot_ai_")) / "payload.json"
    pf.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _ps("-ProcId", str(pid), "-Mode", "set", "-File", str(pf))
    print(f"applied: AI instructions {len(text)} / {LIMIT} characters, {len(payload['descriptions'])} measure descriptions")
    return verify(pid)


def verify(pid):
    """AI instructions = the rendered config, every copilot_descriptions.csv measure carries a description, CopilotTooling flagged."""
    cur = _get(pid)
    lsdl = json.loads(cur["culture"]) if cur.get("culture") else {}
    got = lsdl.get("CustomInstructions")
    want = render(_sites_live())
    bad = []
    if got != want:
        bad.append(f"AI instructions {'missing' if got is None else f'differ ({len(got)} vs {len(want)} chars)'}")
    have = cur.get("descriptions") or {}
    nodesc = [m for m in descriptions() if not have.get(m)]
    if nodesc:
        bad.append(f"{len(nodesc)} key measure(s) without description: {', '.join(nodesc[:5])}")
    if TOOLING not in (cur.get("tooling") or ""):
        bad.append(f"model annotation PBI_ProTooling has no {TOOLING}")
    calc = cur.get("calculated") or {}
    for n in ANSWER_TABLES:
        if calc.get(n) != "Ready":
            bad.append(f"answer table '{n}' is {calc.get(n, 'missing')}")
    vis, want_vis = cur.get("visible") or {}, visible_fields()
    extra = sorted(set(vis) - set(want_vis))
    if extra:
        bad.append(f"tables visible to Copilot but not in config/copilot_fields.csv: {', '.join(extra[:6])}")
    nvis = sum(len(v) for v in vis.values())
    if bad:
        print("VERIFY FAILED: " + "; ".join(bad))
        return 1
    print(f"VERIFY OK: AI instructions ({len(got)} characters) = config/copilot_instructions.md, "
          f"{len(descriptions())} key measures described, {TOOLING} flagged, answer tables Ready, "
          f"Copilot sees {nvis} fields in {len(vis)} tables")
    return 0


def service_check():
    """The model in the Fabric workspace of dist/ALL_SITES/_published.json carries the same AI instructions (Fabric getDefinition)."""
    import base64
    import requests
    import publish as P
    pub = json.loads((ROOT / "dist" / "ALL_SITES" / "_published.json").read_text(encoding="utf-8"))
    r = requests.post(f"{P.FAB}/workspaces/{pub['workspaceId']}/semanticModels/{pub['semanticModelId']}/getDefinition?format=TMDL",
                      headers=P.H(), timeout=120)
    parts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in P.wait_lro(r).json()["definition"]["parts"]}
    cul = parts.get(f"definition/cultures/{CULTURE}.tmdl", "")
    m = re.search(r"linguisticMetadata =\s*(\{.*?\})\s*\n\s*contentType", cul, re.S)
    lsdl = json.loads(m.group(1)) if m else {}
    got, want = lsdl.get("CustomInstructions"), render(_sites_live())
    copilot = sorted(p for p in parts if p.lower().startswith("copilot/"))
    ok = got == want
    print(f"SERVICE {'OK' if ok else 'FAILED'}: workspace '{pub['workspace']}' model - AI instructions "
          f"{'equal to config' if ok else 'missing' if got is None else 'differ'} (linguistic metadata {lsdl.get('Version')})"
          + (f"; Copilot parts: {', '.join(copilot)}" if copilot else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--service"]:
        sys.exit(service_check())
    if a[:1] == ["--live"]:
        sys.exit(live(int(a[1])))
    if a[:1] == ["--verify"]:
        sys.exit(verify(int(a[1])))
    txt = render()
    out = ROOT / "dist" / "copilot_instructions.md"
    out.write_text(txt, encoding="utf-8")
    print(txt)
    print(f"--- {len(txt)} / {LIMIT} characters -> {out}")
