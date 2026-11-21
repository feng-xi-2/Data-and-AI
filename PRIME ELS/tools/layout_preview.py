"""Layout preview + gate for the generated report (no Power BI needed - works on a locked PC).

    py tools/layout_preview.py [dist/ALL_SITES/WH Hypercare KPI.Report/definition] [--out <dir>]

Draws every page as a wireframe PNG (visual boxes with type + title, header bands, page height) and checks the layout:
  OVERLAP   two visible data visuals overlap (more than 4 px both ways)
  OFF_PAGE  a visual reaches beyond the page width / height
  TINY      a data visual smaller than 40 x 30 px
  COLLAPSED_SLICER  a responsive slicer under 50 px tall - the Service shows only a funnel icon (set responsive off)
  DUPLICATE the same visual (fields + visual filters) on two pages
  TEXT_OVERFLOW  a text box whose text (estimated from font size and width) does not fit - Power BI shows a scrollbar / cuts it
Exit 1 when any finding exists; summary -> docs/LAYOUT_CHECK.md, images -> <out>/<nn> <page>.png
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
args = [a for a in sys.argv[1:] if not a.startswith("--")]
DEFN = Path(args[0]) if args else ROOT / "dist" / "ALL_SITES" / "WH Hypercare KPI.Report" / "definition"
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else (Path(__file__).resolve().parents[2] / "_uitest" / "layout")
OUT.mkdir(parents=True, exist_ok=True)
DECOR = {"shape", "image", "textbox", "actionButton"}
SLICER_MIN_H = 50     # 21-Nov: 150 x 40 input boxes collapsed to a funnel icon in the Service (84 % fit-to-width); 54 px dropdowns draw fine
COLORS = {"slicer": "#7FA7D1", "card": "#B4C7E7", "multiRowCard": "#B4C7E7", "cardVisual": "#B4C7E7", "tableEx": "#C9E4CA", "pivotTable": "#C9E4CA",
          "barChart": "#F8CBAD", "clusteredBarChart": "#F8CBAD", "columnChart": "#F8CBAD", "clusteredColumnChart": "#F8CBAD",
          "lineClusteredColumnComboChart": "#FFE699", "lineChart": "#FFE699"}


def title_of(v):
    for t in v.get("visualContainerObjects", {}).get("title", []):
        x = t.get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value")
        if x:
            return x.strip("'")
    projs = [p for r in v.get("query", {}).get("queryState", {}).values() for p in r.get("projections", [])]
    return (projs[0].get("displayName") or projs[0].get("nativeQueryRef") or "") if projs else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads((DEFN / "pages" / "pages.json").read_text(encoding="utf-8"))
    try:
        font = ImageFont.truetype("segoeui.ttf", 12)
        small = ImageFont.truetype("segoeui.ttf", 10)
    except OSError:
        font = small = ImageFont.load_default()
    findings, summary = [], []
    seen_sig = {}         # DUPLICATE: the same visual (fields + visual filters) on two pages - every item has one home
    for n, pid in enumerate(meta["pageOrder"], 1):
        pj = json.loads((DEFN / "pages" / pid / "page.json").read_text(encoding="utf-8"))
        W, H = int(pj["width"]), int(pj["height"])
        vis, vis_tf = [], []
        for vf in (DEFN / "pages" / pid / "visuals").glob("*/visual.json"):
            j = json.loads(vf.read_text(encoding="utf-8"))
            if j.get("isHidden") or "visual" not in j or j.get("parentGroupName"):
                continue
            p = j["position"]
            v_ = j["visual"]
            if v_.get("visualType") not in DECOR and v_.get("visualType") != "slicer":
                flds = sorted(pr.get("queryRef", "") for role in v_.get("query", {}).get("queryState", {}).values() for pr in role.get("projections", []))
                flds = [f for f in flds if f.split(".", 1)[-1] not in ("Report Label", "Dashboard Title", "Window Label", "Page Guide Calc", "Page Guide Config")]
                if len(flds) >= 2:
                    flt = json.dumps([f.get("filter") for f in (j.get("filterConfig") or {}).get("filters", []) if f.get("filter")], sort_keys=True)
                    sig = json.dumps(flds) + flt
                    other = seen_sig.get(sig)
                    if other and other[0] != pj["displayName"]:
                        vis_tf.append(f"DUPLICATE {v_['visualType']} '{title_of(v_)[:40]}' also on page '{other[0]}' ('{other[1][:40]}') - keep one home")
                    seen_sig.setdefault(sig, (pj["displayName"], title_of(v_)))
            resp_off = v_.get("objects", {}).get("general", [{}])[0].get("properties", {}).get("responsive", {}).get("expr", {}) \
                .get("Literal", {}).get("Value") == "false"
            vis.append((j["visual"].get("visualType"), int(p["x"]), int(p["y"]), int(p["width"]), int(p["height"]), title_of(j["visual"]), resp_off))
        img = Image.new("RGB", (W, H), "#FFFFFF")
        d = ImageDraw.Draw(img)
        for vt, x, y, w, h, t, _ in sorted(vis, key=lambda v: (v[0] not in DECOR, v[2])):
            if vt in DECOR:
                d.rectangle([x, y, x + w, y + h], outline="#D0D0D0")
                continue
            d.rectangle([x, y, x + w, y + h], fill=COLORS.get(vt, "#E7E6E6"), outline="#404040")
            d.text((x + 4, y + 3), f"{vt}", fill="#404040", font=small)
            d.multiline_text((x + 4, y + 16), "\n".join(t[i:i + max(10, w // 7)] for i in range(0, min(len(t), 3 * max(10, w // 7)), max(10, w // 7))),
                             fill="#000000", font=font)
        data = [v for v in vis if v[0] not in DECOR]
        # text boxes: estimated lines (Segoe UI ~0.5 em per character, 1.45 line height, ~14 px padding - calibrated on the Desktop render 2-Nov)
        for vf in (DEFN / "pages" / pid / "visuals").glob("*/visual.json"):
            j = json.loads(vf.read_text(encoding="utf-8"))
            if j.get("isHidden") or j.get("visual", {}).get("visualType") != "textbox" or j.get("parentGroupName"):
                continue
            pos = j["position"]
            need = 14
            for para in j["visual"].get("objects", {}).get("general", [{}])[0].get("properties", {}).get("paragraphs", []):
                for run in para.get("textRuns", []):
                    pt = float(str(run.get("textStyle", {}).get("fontSize", "10pt")).rstrip("pt") or 10)
                    px = pt * 4 / 3
                    per_line = max(1, int((pos["width"] - 20) / (px * 0.5)))
                    lines = sum(max(1, -(-len(part) // per_line)) for part in run.get("value", "").split("\n"))
                    need += lines * px * (1.45 if pt <= 14 else 1.25)
            if need > pos["height"] + 2:
                txt = "".join(r.get("value", "") for para in j["visual"]["objects"]["general"][0]["properties"].get("paragraphs", [])
                              for r in para.get("textRuns", []))
                findings_page = f"TEXT_OVERFLOW textbox '{txt[:40]}' needs ~{need:.0f} px, box {pos['height']} px ({pos['width']} wide)"
                data_tf = findings_page
                vis_tf.append(data_tf)
        page_f = list(vis_tf)
        for i, a in enumerate(data):
            vt, x, y, w, h, t, resp = a
            if x + w > W + 2 or y + h > H + 2:
                page_f.append(f"OFF_PAGE {vt} '{t[:40]}' ({x},{y},{w}x{h}) page {W}x{H}")
            if vt != "slicer" and (w < 40 or h < 30):
                page_f.append(f"TINY {vt} '{t[:40]}' {w}x{h}")
            if vt == "slicer" and h < SLICER_MIN_H and not resp:
                page_f.append(f"COLLAPSED_SLICER '{t[:40]}' {w}x{h}: a responsive slicer under {SLICER_MIN_H} px shows only a funnel icon "
                              f"in the Service (page drawn below 100 %) - set general.responsive = false or make it taller")
            for b in data[i + 1:]:
                ox = min(x + w, b[1] + b[3]) - max(x, b[1])
                oy = min(y + h, b[2] + b[4]) - max(y, b[2])
                if ox > 4 and oy > 4:
                    page_f.append(f"OVERLAP '{t[:30]}' ({vt}) x '{b[5][:30]}' ({b[0]}) by {ox}x{oy} px")
        name = pj["displayName"]
        img.save(OUT / f"{n:02d} {name.replace('/', '-')}.png")
        summary.append(f"| {n} | {name} | {W}x{H} | {pj.get('displayOption', '-')} | {len(data)} | {len(page_f)} |")
        findings += [f"{name}: {f}" for f in page_f]
    md = ["# Layout check", "", f"`py tools/layout_preview.py` on `{DEFN.relative_to(ROOT) if ROOT in DEFN.parents else DEFN}` - wireframes in `{OUT.name}` (next to the kit, folder _uitest)", "",
          "| # | Page | Size | Display | Data visuals | Findings |", "|---|---|---|---|---|---|"] + summary + ["", "## Findings", ""] + \
         ([f"- {f}" for f in findings] or ["none"])
    (ROOT / "docs" / "LAYOUT_CHECK.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(summary[:40]))
    print(f"{len(findings)} finding(s)" + ("".join(f"\n  {f}" for f in findings[:40])))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
