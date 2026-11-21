"""Render the two Home-page guide images (how to change the site / how to add a site) from config -> theme/howto/*.png.

    py tools/render_howto.py

Uses Microsoft Edge headless (no extra installs). Site rows come from config/site_config.csv, so the images stay current.
"""
import csv
import html
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "theme" / "howto"
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
W, H = 620, 700

CSS = """
*{box-sizing:border-box;font-family:'Segoe UI',Arial,sans-serif}
body{margin:0;width:%dpx;height:%dpx;background:#fff;color:#252423;overflow:hidden}
.hd{background:#0B2A4A;color:#fff;padding:12px 16px;font-size:19px;font-weight:600}
.hd small{display:block;font-size:11.5px;font-weight:400;color:#cfdcec;margin-top:2px}
.wrap{padding:10px 14px}
.step{display:flex;gap:10px;margin:8px 0 6px}
.n{flex:0 0 24px;height:24px;border-radius:12px;background:#D13438;color:#fff;font-weight:700;text-align:center;line-height:24px;font-size:13px}
.t{font-size:13px;line-height:1.35}.t b{color:#0B2A4A}
.ribbon{border:1px solid #d6d6d6;border-radius:4px;background:#f6f6f6;font-size:11px;margin:4px 0 0 34px;position:relative}
.tabs{display:flex;gap:14px;padding:4px 8px;border-bottom:1px solid #ddd;color:#444}.tabs .on{color:#0B2A4A;font-weight:600;border-bottom:2px solid #F2C811}
.btns{display:flex;gap:6px;padding:6px 8px}.btn{border:1px solid transparent;padding:3px 7px;border-radius:3px;background:#fff}
.hl{outline:2px solid #D13438;outline-offset:1px}
.menu{position:absolute;left:236px;top:52px;background:#fff;border:1px solid #bbb;box-shadow:0 2px 6px rgba(0,0,0,.2);font-size:11px;z-index:2}
.menu div{padding:4px 12px}.menu .sel{background:#e5eefc}
.dlg{border:1px solid #bbb;border-radius:4px;margin:4px 0 0 34px;box-shadow:0 2px 8px rgba(0,0,0,.15);font-size:11px}
.dlg .ti{background:#f3f3f3;padding:5px 9px;font-weight:600;border-bottom:1px solid #ddd}
.dlg .bd{padding:6px 10px}.fld{margin:3px 0}.fld i{display:block;color:#605E5C;font-style:normal}
.fld span{display:block;border:1px solid #8a8886;padding:2px 5px;background:#fff;font-family:Consolas,monospace;font-size:10.5px}
table{border-collapse:collapse;width:100%%;font-size:10.5px;margin-top:4px}
th{background:#0B2A4A;color:#fff;text-align:left;padding:3px 5px;font-weight:600}td{padding:3px 5px;border-bottom:1px solid #e8ecf2;font-family:Consolas,monospace}
tr:nth-child(even) td{background:#F5F8FC}
.note{background:#FFF4CE;border-left:4px solid #F2A900;padding:6px 9px;font-size:11.5px;margin:8px 0 0 34px}
.two{display:flex;gap:8px;margin-left:34px}.card{flex:1;border:1px solid #D9DFE8;border-radius:6px;padding:6px 8px;font-size:11px}
.card h4{margin:0 0 3px;font-size:12px;color:#003DA5}
.ok{color:#107C10;font-weight:600}
""" % (W, H)


def sites():
    return list(csv.DictReader(open(ROOT / "config" / "site_config.csv", encoding="utf-8-sig")))


CSS += """
.bn{margin:4px 0 0 34px;background:#0B2A4A;border-radius:4px;color:#fff;display:flex;align-items:center;gap:8px;padding:6px 8px;font-size:12px;position:relative}
.bn .tt{font-weight:600;font-size:13px;flex:1}.bn .pg{color:#9FC3E7;font-size:11px;flex:1}
.dd{background:#fff;color:#252423;border:1px solid #8a8886;border-radius:3px;padding:2px 22px 2px 6px;font-size:11px;position:relative;min-width:120px}
.dd:after{content:'\\25BE';position:absolute;right:6px;top:1px}
.lst{position:absolute;right:8px;top:44px;background:#fff;color:#252423;border:1px solid #bbb;box-shadow:0 2px 6px rgba(0,0,0,.2);font-size:11px;min-width:150px;z-index:3}
.lst div{padding:4px 10px}.lst .sel{background:#e5eefc;font-weight:600}
.inp{display:inline-block;border:1px solid #8a8886;padding:1px 6px;background:#fff;font-family:Consolas,monospace;font-size:11px;min-width:56px}
"""


def change_site():
    ss = sites()
    s1 = ss[1] if len(ss) > 1 else ss[0]
    items = "".join(f"<div{' class=\"sel\"' if s is s1 else ''}>{html.escape(s['SiteName'])}</div>" for s in ss)
    rows = "".join(f"<tr><td>{html.escape(s['SiteName'])}</td><td>{html.escape(s['WMS_Version'])}</td><td>{html.escape(s['ReplicaServer'].split('.')[0])}...</td>"
                   f"<td>{html.escape(s['ReplicaDatabase'])}</td></tr>" for s in ss)
    return f"""<div class="hd">&#9312; How to change the site<small>Site file <b>WH Hypercare KPI - &lt;SITE&gt;</b> loads ONE site (open another site's file to switch). All-sites file: every site loaded, pick it in the Site slicer.</small></div>
<div class="wrap">
<div class="step"><div class="n">1</div><div class="t">Open the <b>Site</b> drop-down at the <b>top right of any page</b> (navy banner):</div></div>
<div class="bn"><span class="tt">{html.escape(s1['SiteName'])} PRIME ELS Dashboard</span><span class="pg">Hypercare Cockpit</span>
<span style="font-size:10px;color:#cfdcec">Site</span><span class="dd hl">{html.escape(s1['SiteName'])}</span>
<div class="lst">{items}</div></div>
<div style="height:{18 + 22 * len(ss)}px"></div>
<div class="step"><div class="n">2</div><div class="t">Pick <b>one</b> site. The slicer is <b>synced on every page</b> and forces exactly one selection, so every table, chart, KPI, target, alert and RCA text switches to that site.</div></div>
<div class="step"><div class="n">3</div><div class="t">The title becomes <b>&lt;Site&gt; PRIME ELS Dashboard</b>. Pages a site does not run (e.g. SAP plan, Level A) say <b>&#9888; NOT USED AT &lt;site&gt;</b> in the banner.</div></div>
<div class="step"><div class="n">4</div><div class="t">Check <b>Config &amp; Health</b>: <span class="ok">ALL CHECKS PASSED</span> for the site (freshness, feeds, accuracy).</div></div>
<div style="margin-left:34px"><table><tr><th>Site</th><th>WMS</th><th>Replica server</th><th>Database</th></tr>{rows}</table></div>
<div class="note">Sharing: send the <b>site file</b> (dist/&lt;SITE&gt;) - it needs only that replica (Microsoft account in Desktop; gateway MI-&lt;SITE&gt;_REPLICA-...-PaaS-ADHOC in the recipient's workspace).<br>Thresholds: type them on <b>Config &amp; Health &rarr; Alert threshold inputs</b> (Target / Warning / Critical boxes, <span class="inp">120</span>). Empty box = saved Cfg_Threshold value of the selected site.</div>
</div>"""


def add_site():
    return """<div class="hd">&#9313; How to add a new site (PrIME 2022 or PrIME 2014)<small>No SQL / DAX edits - one row in config/site_config.csv, then rebuild the kit.</small></div>
<div class="wrap">
<div class="step"><div class="n">1</div><div class="t">Profile the replica (fills location / area / production patterns): <b>py tools/profile_site.py &lt;SITE&gt;</b></div></div>
<div class="step"><div class="n">2</div><div class="t">Add a row to <b>config/site_config.csv</b> (copy the closest site of the same engine):</div></div>
<div class="dlg"><div class="ti">config/site_config.csv - new row</div><div class="bd"><table>
<tr><th>Column</th><th>Example</th><th>Meaning</th></tr>
<tr><td>SiteCode / SiteName</td><td>NEWSITE</td><td>key + slicer / banner name</td></tr>
<tr><td>WMS_Version</td><td>PrIME 2022</td><td>picks the engine profile</td></tr>
<tr><td>ReplicaServer</td><td><replica-server></td><td>from the replica access e-mail</td></tr>
<tr><td>ReplicaDatabase</td><td>NEWSITE_REPLICA</td><td>2022: &lt;SITE&gt;_REPLICA &middot; 2014: &lt;SITE&gt;</td></tr>
<tr><td>WH_ID / UTC_Offset_h</td><td>XX01 / 8</td><td>warehouse id, site time zone</td></tr>
<tr><td>Shift1..3_Start / Hypercare_Start</td><td>6 / 14 / 22</td><td>shift-day buckets, data window</td></tr>
<tr><td>Has_Production / LevelA / HOFF / SAP_Plan</td><td>1 / 0 / 0 / 0</td><td>turn queries on / off</td></tr>
<tr><td>LOC_*, AREA_*, FG_PRTNUM_LIKE</td><td>LT% / RDTS</td><td>location patterns of the site</td></tr>
</table></div></div>
<div class="two" style="margin-top:8px">
<div class="card"><h4>PrIME 2022</h4>db &lt;SITE&gt;_REPLICA &middot; schema dbo<br>zones = sto_zone_id &middot; loc_typ flags</div>
<div class="card"><h4>PrIME 2014</h4>db &lt;SITE&gt; &middot; schema prodwms<br>zones = area (arecod) &middot; no loc_typ</div></div>
<div class="t" style="margin:3px 0 0 34px;font-size:11px;color:#605E5C">Engine differences are applied automatically from <b>Cfg_Engine</b> by WMS_Version.</div>
<div class="step"><div class="n">3</div><div class="t">Optional: lines in <b>config/line_map.csv</b>, per-site targets in <b>config/kpi_thresholds.csv</b> (Site = &lt;SiteCode&gt; overrides '*').</div></div>
<div class="step"><div class="n">4</div><div class="t"><b>py tools/validate_sql.py &lt;SITE&gt;</b> &rarr; <b>py tools/build_pbip.py</b> &rarr; open <b>dist/ALL_SITES/WH Hypercare KPI.pbip</b> &rarr; <b>Refresh</b>. The new site appears in the Site slicer, and its own site file <b>dist/&lt;SITE&gt;/WH Hypercare KPI - &lt;SITE&gt;.pbip</b> is built for sharing.</div></div>
<div class="note">Service: <b>py tools/publish.py</b>; each replica needs its gateway connection <b>MI-&lt;SITE&gt;_REPLICA-...-PaaS-ADHOC</b> (bound automatically).</div>
</div>"""


def render(name, body):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{name}.html"
    f.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    png = OUT / f"{name}.png"
    edge = next(p for p in EDGE if Path(p).exists())
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={W},{H}", f"--screenshot={png}", f.as_uri()], check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return png


if __name__ == "__main__":
    for n, b in (("howto_change_site", change_site()), ("howto_add_site", add_site())):
        print(render(n, b))
