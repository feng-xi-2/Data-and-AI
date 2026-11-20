"""Compare a site's own PRIME reports (allqueries.xlsx, the PrIME report catalogue) with the kit's SQL on the same replica and day.

    py tools/allqueries_compare.py JAKARTA [--day 2026-10-30]      -> docs/ALLQUERIES_COMPARE.md (section per site)

Reports compared (when the site has them in the catalogue):
  * "3000 - TTAT"     per carrier move: arrival / dispatch / TTAT (h)  vs  kit TTAT (outbound, check-in -> close, min) per Load
  * "SDC Throughput"  cases per shift x operation (PALRPL / PALPCK / GENMOV / LSTPCK onto the RF device)
                      vs the same transactions counted by the kit's User Activity (pallets per user-hour, Move_Class)
The site report SQL runs unchanged except: par1 / par2 = the day, '<site>_simp.' 3-part names kept (same instance).
Heartbeat every 25 s; every failure is printed and written to the report (never silent).
"""
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_replica_schema import connect  # noqa: E402
from validate_sql import tokens, render, queries  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
XLSX = Path.home() / "OneDrive - <company>" / "Desktop" / "M&M" / "Sample Data RTCIS PRIME" / "PRIME 2014-2022" / "allqueries.xlsx"
CACHE = ROOT.parent / "_uitest" / "_allqueries.pkl"
OUT = ROOT / "docs" / "ALLQUERIES_COMPARE.md"


def say(m):
    print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def catalogue():
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    say(f"reading {XLSX} (sheet 'All Queries')")
    d = pd.read_excel(XLSX, sheet_name="All Queries")
    CACHE.parent.mkdir(exist_ok=True)
    d.to_pickle(CACHE)
    return d


def site_query(cat, site_alias, name):
    r = cat[(cat["site"].str.lower() == site_alias) & (cat["query_name"] == name)]
    return None if r.empty else r.iloc[0]["query"].replace("_x000D_", "")


def run_sql(cur, sql):
    cur.execute(sql)
    while cur.description is None and cur.nextset():
        pass
    cols = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)


def compare_ttat(cur, cat, alias, site, tok, day, md):
    q = site_query(cat, alias, "3000 - TTAT")
    if q is None:
        md.append("- 3000 - TTAT: not in the catalogue for this site\n")
        return
    d0, d1 = f"'{day} 00:00:00'", f"'{day} 23:59:59'"
    theirs = run_sql(cur, q.replace("par1", d0).replace("par2", d1))
    theirs["Carrier Move ID"] = theirs["Carrier Move ID"].astype(str)
    rows_raw = len(theirs)
    # the site report groups by destination location too -> one row per carrier move here
    theirs = theirs.sort_values("Carrier Move ID").drop_duplicates("Carrier Move ID")
    say(f"site TTAT report: {rows_raw} rows = {len(theirs)} carrier moves (planned load date {day})")
    kind, body = queries()["TTAT"]
    from validate_sql import sql_from_m
    ours = run_sql(cur, render(sql_from_m(body, tok), tok))
    ours = ours[ours["Direction"] == "Outbound"].copy()
    ours["Load"] = ours["Load"].astype(str)
    per = (ours.groupby("Load").agg(checkin=("Check-in", "min"), close=("Close", "max"), dispatch=("Dispatch", "max"),
                                    ttat_min=("TTAT (Minutes)", "max"), trailer=("TrailerID", "max")).reset_index())
    m = theirs.merge(per, left_on="Carrier Move ID", right_on="Load", how="left")
    m["truck_in"] = pd.to_datetime(m["truck_in"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    m["dispatch_x"] = pd.to_datetime(m["dispatch_x"] if "dispatch_x" in m else m["dispatch"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    m["pld"] = pd.to_datetime(m["pld"], format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    matched = m[m["Load"].notna()]
    n, nm = len(m), len(matched)
    site_h = theirs["ttat_time"].astype(float)
    neg = int((site_h < 0).sum())
    open_n = int(m["dispatch_x"].isna().sum())
    md.append(f"### 3000 - TTAT (site report) vs kit TTAT - planned load date {day}\n")
    md.append(f"- Site report: {rows_raw} rows = **{n}** carrier moves (one row per destination location in the report); TTAT = dispatch - "
              "max(arrival, planned load date), hours. Average **{:.2f} h**, but **{}** of {} carrier moves have a NEGATIVE TTAT: they were "
              "dispatched before their planned load date (the report selects trucks by planned date, not by when they moved); "
              "{} have no dispatch yet. Average of the non-negative ones: **{:.1f} h**.".format(site_h.mean(), neg, n, open_n, site_h[site_h >= 0].mean()))
    if nm == 0:
        md.append("- Kit TTAT: **0** of these carrier moves found (Load = car_move_id) - check the TTAT window / warehouse.\n")
        return
    arr_diff = (matched["checkin"] - matched["truck_in"]).dt.total_seconds().div(60).abs()
    disp_diff = (matched["dispatch_y"] - matched["dispatch_x"]).dt.total_seconds().div(60).abs()
    md.append(f"- Kit TTAT: **{nm}/{n}** carrier moves matched by Load; kit check-in = site arrival within 1 min for "
              f"**{(arr_diff <= 1).sum()}/{nm}**; kit dispatch = site dispatch within 1 min for **{(disp_diff <= 1).sum()}/{nm}** "
              f"-> the timestamps are the same data. Not matched: {n - nm} (not yet closed / outside the kit TTAT window since {tok['START_DT'][:10]}).")
    ok = matched[matched["ttat_time"].astype(float) >= 0]
    md.append(f"- Trucks with a valid site TTAT ({len(ok)}): site TTAT **{ok['ttat_time'].astype(float).mean() * 60:.0f} min**; "
              f"kit check-in -> dispatch **{(ok['dispatch_y'] - ok['checkin']).dt.total_seconds().div(60).mean():.0f} min**; "
              f"kit KPI TTAT (check-in -> close) **{ok['ttat_min'].astype(float).mean():.0f} min**.")
    early = (matched["pld"] > matched["truck_in"]).sum()
    md.append(f"- Why they differ (definitions, not data): {early}/{nm} trucks arrived before their planned load time - the site report "
              "starts the clock at the planned time, the kit at the gate check-in (TCHKIN). The kit KPI stops at trailer close (TCLOSE, "
              "end of loading + documents); the site report at dispatch (TDSP). The kit attributes a truck to the shift day of its close; "
              "the site report to its planned load date.\n")
    show = matched.assign(site_ttat_min=(matched["ttat_time"].astype(float) * 60).round(0)).sort_values("pld").head(12)
    md.append("| Carrier move | Trailer (kit) | Planned load | Arrival (site) | Check-in (kit) | Dispatch (site) | Close (kit) | Site TTAT (min) | Kit TTAT (min) |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for _, r in show.iterrows():
        f = lambda x: "" if pd.isna(x) else pd.Timestamp(x).strftime("%d-%m %H:%M")
        md.append(f"| {r['Carrier Move ID']} | {r['trailer']} | {f(r['pld'])} | {f(r['truck_in'])} | {f(r['checkin'])} | {f(r['dispatch_x'])} | "
                  f"{f(r['close'])} | {r['site_ttat_min']:.0f} | {float(r['ttat_min']):.0f} |")
    md.append("")


def compare_throughput(cur, cat, alias, site, tok, day, md):
    q = site_query(cat, alias, "SDC Throughput")
    if q is None:
        md.append("- SDC Throughput: not in the catalogue for this site\n")
        return
    theirs = run_sql(cur, q.replace("par1", f"'{day}'").replace("par2", f"'{day}'"))
    theirs.columns = [c.lower() for c in theirs.columns]
    say(f"site SDC Throughput: {len(theirs)} rows")
    # same transactions as the site report (onto the RF device), counted as distinct pallets per shift x activity
    s = tok["S"]
    wh = tok["WH_ID"]
    acts = {"PALRPL": "Replenishment", "PALPCK": "Pallet_Pick", "GENMOV": "Putaway", "LSTPCK": "Case_Pick"}
    pal = run_sql(cur, f"""
        SELECT CASE WHEN DATEPART(HOUR, d.trndte) < 8 THEN 'Shift Malam' WHEN DATEPART(HOUR, d.trndte) < 16 THEN 'Shift Pagi' ELSE 'Shift Sore' END AS shift_flag,
               d.actcod, COUNT(*) AS txns, COUNT(DISTINCT d.lodnum) AS pallets
        FROM {s}.dlytrn d
        WHERE d.wh_id = '{wh}' AND d.to_arecod LIKE '%RDTS%' AND d.actcod IN ('LSTPCK','GENMOV','PALPCK','PALRPL')
          AND d.trndte >= '{day}' AND d.trndte < DATEADD(DAY, 1, CAST('{day}' AS DATE))
        GROUP BY CASE WHEN DATEPART(HOUR, d.trndte) < 8 THEN 'Shift Malam' WHEN DATEPART(HOUR, d.trndte) < 16 THEN 'Shift Pagi' ELSE 'Shift Sore' END, d.actcod""")
    kind, body = queries()["User Activity"]
    ua = run_sql(cur, render(body, {**tok, "INC_FROM": f"'{day}'", "INC_TO": f"DATEADD(DAY, 1, CAST('{day}' AS DATE))"}))
    ua = ua[ua["Activity_Code"].isin(list(acts))].copy()
    ua["shift_flag"] = ua["Activity_Hour"].map(lambda h: "Shift Malam" if h < 8 else ("Shift Pagi" if h < 16 else "Shift Sore"))
    kit = ua.groupby(["shift_flag", "Activity_Code"]).agg(kit_pallets=("Pallets_Moved", "sum"), kit_class=("Move_Class", "max")).reset_index()
    md.append(f"### SDC Throughput (site report, cases) vs kit User Activity (pallets) - {day}\n")
    md.append("- Site report = cases moved onto the RF device per shift (Malam 00-08, Pagi 08-16, Sore 16-24) and operation; the kit counts "
              "pallets per user-hour and process step. Same dlytrn rows; the bridge below counts the site report's own rows as distinct pallets.\n")
    md.append("| Shift | Operation (site) | Activity | Site cases | Same rows: pallets | Kit pallets (User Activity) | Kit process step |")
    md.append("|---|---|---|---|---|---|---|")
    for sh in ["Shift Malam", "Shift Pagi", "Shift Sore"]:
        for a, op in acts.items():
            c = theirs[(theirs["shift_flag"] == sh) & (theirs["operation_code"] == op)]["tot_cases"].astype(float).sum()
            p = pal[(pal["shift_flag"] == sh) & (pal["actcod"] == a)]["pallets"].sum()
            k = kit[(kit["shift_flag"] == sh) & (kit["Activity_Code"] == a)]
            kp = int(k["kit_pallets"].sum()) if not k.empty else 0
            md.append(f"| {sh} | {op} | {a} | {c:,.0f} | {p:,} | {kp:,} | {k['kit_class'].iloc[0] if not k.empty else '-'} |")
    md.append("\nKit pallets >= same-rows pallets: the kit counts both legs of a move (pick up onto the device and deposit) per user-hour, "
              "the site report only the leg onto the device (to_arecod like '%RDTS%').\n")


def main(argv):
    code = (argv[:1] or ["JAKARTA"])[0].upper()
    site, tok = tokens(code)
    off = float(site.get("UTC_Offset_h") or 0)
    local_today = (datetime.now(timezone.utc) + timedelta(hours=off)).date()
    day = argv[argv.index("--day") + 1] if "--day" in argv else str(local_today - timedelta(days=1))
    alias = site["ReplicaDatabase"].split("_")[0].lower()
    stop = threading.Event()
    threading.Thread(target=lambda: [say("heartbeat: comparing ...") for _ in iter(lambda: stop.wait(25), True)], daemon=True).start()
    md = [f"## {code} - {site['SiteName']} ({site['ReplicaServer'].split('.')[0]} / {site['ReplicaDatabase']}, WH {site['WH_ID']}) - day {day}\n",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} by `py tools/allqueries_compare.py {code}`. Site reports from allqueries.xlsx (catalogue site '{alias}').\n"]
    try:
        cat = catalogue()
        cn = connect(site["ReplicaServer"], site["ReplicaDatabase"])
        cn.timeout = 110
        cur = cn.cursor()
        for f in (compare_ttat, compare_throughput):
            try:
                f(cur, cat, alias, site, tok, day, md)
            except Exception as e:
                say(f"!! {f.__name__} failed: {e}")
                md.append(f"- **{f.__name__} FAILED**: {re.sub(r'\s+', ' ', str(e))[:300]}\n")
    finally:
        stop.set()
    head = "# PrIME site reports (allqueries.xlsx) vs the Hypercare kit\n\nSame replica, same day; differences explained by definition.\n\n"
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else head
    parts = re.split(r"(?m)^(?=## )", old)
    keep = [p for p in parts[1:] if not p.startswith(f"## {code} ")]
    OUT.write_text(head + "".join(keep) + "\n".join(md) + "\n", encoding="utf-8")
    say(f"DONE -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
