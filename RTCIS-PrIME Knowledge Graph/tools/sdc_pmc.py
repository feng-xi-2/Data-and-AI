"""SDC module / PMC process layer of the knowledge graph (business process -> RTCIS / PrIME tables).

Sources (curated earlier in SQL_Translations, Neo4j era):
  _build_sdc_prime_hierarchy.py : SDC_RTCIS, SDC_PRIME, PMC_PRIME_CONFIG, TRANSFORMATIONS (read with ast, never executed)
  _mm_audit/_sdc_pmc_standards.json : PMC titles + source xlsx from the SDC standard documents
Gate: every table must exist in the live catalog of its engine (V1); transformations are compared with the
value-validated MAPS_TO harvest. Only PASS rows become edges; the rest are reported in benchmark/sdc_pmc_validation.json."""
import ast
import re

MOD_NAME = re.compile(r'^\s*"(\d{2})"\s*:\s*\{\s*#\s*(.+?)\s*$', re.M)


def _assignments(script_text):
    import warnings
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(script_text)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("SDC_RTCIS", "SDC_PRIME", "PMC_PRIME_CONFIG", "TRANSFORMATIONS"):
                out[name] = ast.literal_eval(node.value)
    return out


def parse_sources(script_text, standards):
    a = _assignments(script_text)
    names = {}
    for num, name in MOD_NAME.findall(script_text):
        names.setdefault(num, re.sub(r"\s*[—-]\s*(management, )?no WMS tables$", "", name).strip())
    modules = {}
    for num in sorted(set(a.get("SDC_RTCIS", {})) | set(a.get("SDC_PRIME", {}))):
        r, p = a.get("SDC_RTCIS", {}).get(num, {}), a.get("SDC_PRIME", {}).get(num, {})
        modules[num] = {"number": num, "name": names.get(num, num), "description": p.get("description", ""),
                        "rtcis_tables": [t.lower() for t in r.get("tables", [])], "rtcis_views": [t.lower() for t in r.get("views", [])],
                        "prime_tables": [t.lower() for t in p.get("tables", [])], "prime_config": [t.lower() for t in p.get("config", [])]}
    pmc = {}
    for pid, tables in a.get("PMC_PRIME_CONFIG", {}).items():
        code = pid.replace("PMC-", "")
        std = standards.get(code, {})
        pmc[pid] = {"id": pid, "code": code, "module": code[:2], "tables": [t.lower() for t in tables],
                    "title": (std.get("title") or "").strip(), "source_file": std.get("source_file", "")}
    trans = [{"rtcis": s.lower(), "prime": (t or "").lower() or None, "type": ty, "rule": rule}
             for s, t, ty, rule in a.get("TRANSFORMATIONS", [])]
    return {"modules": modules, "pmc": pmc, "transformations": trans}


def _check(kind, subject, obj, engine, ok, detail, role=""):
    return {"kind": kind, "subject": subject, "object": obj, "engine": engine, "role": role,
            "verdict": "PASS" if ok else "REJECT", "detail": detail}


def validate(layer, catalog, table_maps):
    """catalog: {engine: set(lower table names)} from the live replicas; table_maps: {(rtcis, prime)} validated MAPS_TO."""
    out = []
    for num, m in layer["modules"].items():
        subj = f"SDCModule:{num}"
        for role, eng, tabs in (("rtcis", "RTCIS", m["rtcis_tables"]), ("rtcis view", "RTCIS", m["rtcis_views"]),
                                ("operational", "PrIME2022", m["prime_tables"]), ("configuration", "PrIME2022", m["prime_config"])):
            for t in tabs:
                ok = t in catalog.get(eng, set())
                out.append(_check("module_table", subj, t, eng, ok, "in live catalog" if ok else f"not in the live {eng} catalog", role))
    for pid, p in layer["pmc"].items():
        for t in p["tables"]:
            ok = t in catalog.get("PrIME2022", set())
            out.append(_check("pmc_table", f"PMCProcess:{pid}", t, "PrIME2022", ok, "in live catalog" if ok else "not in the live PrIME2022 catalog"))
    for x in layer["transformations"]:
        obj = f"{x['rtcis']}->{x['prime'] or '(none)'}"
        src_ok = x["rtcis"] in catalog.get("RTCIS", set())
        if x["prime"] is None:
            out.append(_check("transformation", "Transformation", obj, "RTCIS", src_ok,
                              "source in catalog; no PrIME table by design" if src_ok else "source not in the live RTCIS catalog"))
            continue
        dst_ok = x["prime"] in catalog.get("PrIME2022", set())
        if not (src_ok and dst_ok):
            out.append(_check("transformation", "Transformation", obj, "RTCIS", False,
                              "missing in live catalog: " + ", ".join(t for t, ok in ((x["rtcis"], src_ok), (x["prime"], dst_ok)) if not ok)))
            continue
        agree = (x["rtcis"], x["prime"]) in table_maps
        out.append(_check("transformation", "Transformation", obj, "RTCIS", True,
                          "both in catalog; agrees with validated MAPS_TO" if agree else "both in catalog; not in the validated mappings (curated rule only)"))
    return out


def annotate_presence(edges, checks):
    """Put each check's data presence on its edge, matched by (subject, table, engine) - the same name can exist in both."""
    engine_of = {"rtcis": "RTCIS", "prime": "PrIME2022", "prime14": "PrIME2014"}
    pop = {(c["subject"], c["object"], c["engine"]): c for c in checks if "populated" in c}
    for e in edges:
        if not e["dst"].startswith("Table:"):
            continue
        _, side, table = e["dst"].split(":", 2)
        c = pop.get((e["src"], table, engine_of.get(side)))
        if c:
            e["populated"] = ("rows at " + ", ".join(s for s, v in c["presence"].items() if v == "rows")) if c["populated"] \
                else "no rows at checked sites"
    return edges


def to_graph(layer, checks):
    passed = {(c["subject"], c["object"], c["role"]) for c in checks if c["verdict"] == "PASS"}
    trans_ok = {c["object"]: c for c in checks if c["kind"] == "transformation" and c["verdict"] == "PASS"}
    nodes, edges = [], []
    for num, m in layer["modules"].items():
        nodes.append({"id": f"SDCModule:{num}", "label": "SDCModule", "number": num, "name": m["name"], "description": m["description"]})
        for role, side, tabs in (("rtcis", "rtcis", m["rtcis_tables"]), ("rtcis view", "rtcis", m["rtcis_views"]),
                                 ("operational", "prime", m["prime_tables"]), ("configuration", "prime", m["prime_config"])):
            for t in tabs:
                if (f"SDCModule:{num}", t, role) in passed:
                    edges.append({"label": "USES_TABLE", "src": f"SDCModule:{num}", "dst": f"Table:{side}:{t}", "role": role,
                                  "validated": "V1 live catalog", "source": "SDC flow mapping"})
    for pid, p in layer["pmc"].items():
        nodes.append({"id": f"PMCProcess:{pid}", "label": "PMCProcess", "code": p["code"], "name": p["title"] or pid,
                      "source_file": p["source_file"], "documented": "SDC standard xlsx" if p["source_file"] else "no standard document found"})
        if p["module"] in layer["modules"]:
            edges.append({"label": "IN_MODULE", "src": f"PMCProcess:{pid}", "dst": f"SDCModule:{p['module']}"})
        for t in p["tables"]:
            if (f"PMCProcess:{pid}", t, "") in passed:
                edges.append({"label": "CONFIGURES", "src": f"PMCProcess:{pid}", "dst": f"Table:prime:{t}",
                              "validated": "V1 live catalog", "source": "PrIME Config 2022 sections"})
    for x in layer["transformations"]:
        c = trans_ok.get(f"{x['rtcis']}->{x['prime'] or '(none)'}")
        if c and x["prime"]:
            edges.append({"label": "TRANSFORMS_TO", "src": f"Table:rtcis:{x['rtcis']}", "dst": f"Table:prime:{x['prime']}",
                          "type": x["type"], "rule": x["rule"], "validated": c["detail"]})
    return nodes, edges
