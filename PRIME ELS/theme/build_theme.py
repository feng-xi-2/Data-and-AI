"""Assemble the PRIME ELS Power BI theme from the downloaded public-domain snippets (theme/downloaded, deldersveld/PowerBI-ThemeTemplates, Unlicense).

    py theme/build_theme.py          -> theme/PRIME_ELS_Theme.json

Edit theme/palette.json (colours / fonts) and re-run; tools/build_pbip.py registers the theme in every site report.
"""
import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DL = HERE / "downloaded"
P = json.loads((HERE / "palette.json").read_text(encoding="utf-8"))


def solid(c):
    return {"solid": {"color": c}}


def snippet(name):
    return json.loads((DL / f"{name}.json").read_text(encoding="utf-8"))["visualStyles"]


def fill(obj, mapping):
    """Overwrite keys of a downloaded snippet object with our values (keeps the snippet's structure)."""
    out = copy.deepcopy(obj)
    for k, v in mapping.items():
        out[k] = v
    return out


def build():
    g = snippet("GlobalLevelTemplate")
    star = g["*"]["*"]
    star["title"] = [fill(star["title"][0], {"show": True, "fontColor": solid(P["navy"]), "background": solid(P["visual_bg"]),
                                             "alignment": "left", "fontSize": 11, "fontFamily": P["font_title"]})]
    star["background"] = [fill(star["background"][0], {"show": True, "color": solid(P["visual_bg"]), "transparency": 0})]
    star["border"] = [fill(star["border"][0], {"show": True, "color": solid(P["border"]), "radius": 8})]
    star["dropShadow"] = [fill(star["dropShadow"][0], {"show": True, "color": solid(P["navy"]), "position": "Outer", "preset": "Custom",
                                                       "angle": 90, "shadowBlur": 6, "shadowDistance": 1, "shadowSpread": 0, "transparency": 88})]
    star["visualHeader"] = [{"foreground": solid(P["navy"]), "border": solid(P["border"]), "background": solid(P["visual_bg"]),
                             "showTooltipButton": False}]
    for k in ("lockAspect", "visualHeaderTooltip", "stylePreset"):
        star.pop(k, None)
    star["padding"] = [{"top": 6, "bottom": 6, "left": 8, "right": 8}]
    page = g["page"]["*"]
    page["background"] = [{"color": solid(P["page_bg"]), "transparency": 0}]
    page["outspace"] = [{"color": solid(P["page_bg"]), "transparency": 0}]
    page["outspacePane"] = [fill(page["outspacePane"][0], {"backgroundColor": solid("#FFFFFF"), "foregroundColor": solid(P["text"]),
                                                           "borderColor": solid(P["border"]), "fontFamily": P["font"]})]
    page["filterCard"] = [fill(c, {"backgroundColor": solid(P["accent"] if c["$id"] == "Applied" else "#FFFFFF"),
                                   "foregroundColor": solid("#FFFFFF" if c["$id"] == "Applied" else P["text"]),
                                   "borderColor": solid(P["border"]), "inputBoxColor": solid("#FFFFFF"), "fontFamily": P["font"]})
                          for c in page["filterCard"]]

    vs = {"*": g["*"], "page": g["page"]}

    tbl = snippet("Table")["tableEx"]["*"]
    grid = fill(tbl["grid"][0], {"gridVertical": False, "gridHorizontal": True, "gridHorizontalColor": solid(P["grid"]), "gridHorizontalWeight": 1,
                                 "rowPadding": 3, "outlineColor": solid(P["border"]), "outlineWeight": 1, "textSize": 10})
    grid.pop("imageHeight", None)
    hdr = fill(tbl["columnHeaders"][0], {"fontColor": solid("#FFFFFF"), "backColor": solid(P["navy"]), "outline": "None",
                                         "fontFamily": P["font_title"], "fontSize": 10, "wordWrap": True})
    val = fill(tbl["values"][0], {"fontColorPrimary": solid(P["text"]), "backColorPrimary": solid("#FFFFFF"),
                                  "fontColorSecondary": solid(P["text"]), "backColorSecondary": solid(P["row_alt"]),
                                  "outline": "None", "fontFamily": P["font"], "fontSize": 10, "wordWrap": True})
    tot = fill(tbl["total"][0], {"totals": False, "fontColor": solid(P["navy"]), "backColor": solid(P["row_alt"]), "outline": "None",
                                 "fontFamily": P["font_title"], "fontSize": 10})
    table_style = {"grid": [grid], "columnHeaders": [hdr], "values": [val], "total": [tot], "stylePreset": [{"name": "None"}]}
    vs["tableEx"] = {"*": table_style}
    mtx = snippet("Matrix")["pivotTable"]["*"]
    vs["pivotTable"] = {"*": {**{k: v for k, v in table_style.items() if k != "total"},
                              "rowHeaders": [fill(mtx.get("rowHeaders", [{}])[0], {"fontColor": solid(P["navy"]), "backColor": solid(P["row_alt"]),
                                                                                    "fontFamily": P["font_title"], "fontSize": 10, "outline": "None"})]}}

    sl = snippet("Slicer")["slicer"]["*"]
    vs["slicer"] = {"*": {"general": [fill(sl["general"][0], {"outlineColor": solid(P["border"]), "outlineWeight": 1})],
                          "header": [fill(sl["header"][0], {"fontColor": solid(P["navy"]), "background": solid("#FFFFFF"), "textSize": 10,
                                                            "fontFamily": P["font_title"]})],
                          "items": [fill(sl["items"][0], {"fontColor": solid(P["text"]), "background": solid("#FFFFFF"), "textSize": 10,
                                                          "fontFamily": P["font"]})],
                          "slider": [{"color": solid(P["accent"])}]}}

    cd = snippet("Card")["card"]["*"]
    vs["card"] = {"*": {"labels": [fill(cd["labels"][0], {"color": solid(P["navy"]), "fontSize": 22, "fontFamily": P["font_title"]})],
                        "categoryLabels": [fill(cd["categoryLabels"][0], {"color": solid(P["muted"]), "fontSize": 10, "fontFamily": P["font"]})],
                        "wordWrap": cd["wordWrap"]}}
    # showBlankAs: a new card with no value reads "–" (same as the KPI strip twins), never "(Blank)"
    vs["cardVisual"] = {"*": {"label": [{"fontColor": solid(P["muted"]), "fontSize": 10, "fontFamily": P["font"]}],
                              "value": [{"fontColor": solid(P["navy"]), "fontFamily": P["font_title"], "showBlankAs": "–"},
                                        {"$id": "default", "showBlankAs": "–"}],
                              "divider": [{"show": False}]}}

    for vt, snip in (("clusteredColumnChart", "ClusteredColumn"), ("clusteredBarChart", "ClusteredBar"), ("lineChart", "Line"),
                     ("lineClusteredColumnComboChart", "LineClusteredColumnCombo")):
        s = snippet(snip)
        body = next(iter(s.values()))["*"]
        out = {}
        for axis in ("categoryAxis", "valueAxis"):
            if axis in body:
                out[axis] = [{"show": True, "labelColor": solid(P["muted"]), "fontFamily": P["font"], "fontSize": 9, "showAxisTitle": False,
                              "gridlineShow": axis == "valueAxis", "gridlineColor": solid(P["grid"])}]
        out["legend"] = [{"show": True, "position": "Top", "labelColor": solid(P["muted"]), "fontFamily": P["font"], "fontSize": 9}]
        out["labels"] = [{"color": solid(P["text"]), "fontFamily": P["font"], "fontSize": 9}]
        vs[vt] = {"*": out}

    tb = snippet("Textbox")
    vs["textbox"] = {"*": {"background": [{"show": False}], "border": [{"show": False}], "dropShadow": [{"show": False}]}}
    vs["image"] = {"*": {"background": [{"show": False}], "border": [{"show": False}], "dropShadow": [{"show": False}]}}
    vs["shape"] = {"*": {"dropShadow": [{"show": False}]}}
    _ = tb

    theme = {
        "name": P["name"],
        "dataColors": P["data_colors"],
        "background": P["visual_bg"], "foreground": P["text"], "tableAccent": P["accent"],
        "good": P["good"], "neutral": P["neutral"], "bad": P["bad"],
        "maximum": P["accent"], "center": P["neutral"], "minimum": P["bad"],
        "textClasses": {
            "title": {"fontFace": P["font_title"], "fontSize": 11, "color": P["navy"]},
            "header": {"fontFace": P["font_title"], "fontSize": 12, "color": P["navy"]},
            "label": {"fontFace": P["font"], "fontSize": 10, "color": P["text"]},
            "callout": {"fontFace": P["font_title"], "fontSize": 22, "color": P["navy"]},
        },
        "visualStyles": vs,
    }
    out = HERE / "PRIME_ELS_Theme.json"
    out.write_text(json.dumps(theme, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build())
