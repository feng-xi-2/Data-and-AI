"""
skill_platform.py — Skill Platform backend for the WHS GenAI UIUX.

Provides four Skill-Platform capabilities on top of the local bridge (graph_api.py),
all persisted to a local _skill_platform/ folder so nothing is faked:

  1. Skill registry   — scans the real .github/skills/*/SKILL.md catalogue, tracks
                        installed / enabled state, supports create + uninstall.
  2. Light-app builder— HTML + CSV "light apps": the HTML is the view, the CSV is the
                        data layer, with write-back and a one-click "publish as website"
                        that serves a shareable URL.
  3. Experts          — single-role Expert (persona + methodology + toolchain) and
                        multi-agent Expert Team (leader + members), seeded from agents.
  4. Projects         — a space bundling chosen skills + apps + experts + data sources
                        for team reuse.

Design rules honoured (user memory):
  * visible timestamped logs, no silent failures (catch -> log -> raise / typed error),
  * fixed absolute state path (not cwd),
  * never writes outside the M&M workspace.

This module is pure-stdlib and is imported by graph_api.py, which dispatches the
/sp/* and /p/* routes to the functions here.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import os
import re
import uuid

# ------------------------------------------------------------------ paths ---
BASE = os.path.dirname(os.path.abspath(__file__))
# workspace root = ...\M&M  (this file lives in ...\M&M\SQL_Translations\PBI_Config_Drift_Alert)
WORKSPACE = os.path.abspath(os.path.join(BASE, "..", ".."))

STATE_DIR = os.path.join(BASE, "_skill_platform")
APPS_DIR = os.path.join(STATE_DIR, "apps")
CUSTOM_SKILLS_DIR = os.path.join(STATE_DIR, "skills_custom")
SKILL_STATE = os.path.join(STATE_DIR, "skills_state.json")
EXPERTS_FILE = os.path.join(STATE_DIR, "experts.json")
PROJECTS_FILE = os.path.join(STATE_DIR, "projects.json")

# The real skill catalogue. Override with SP_SKILLS_ROOT if needed.
def _resolve_skills_root():
    env = os.environ.get("SP_SKILLS_ROOT") or os.environ.get("WB_SKILLS_ROOT")
    if env:
        return env
    candidates = [os.path.join(WORKSPACE, ".github", "skills")]
    # The workspace is mirrored between a local Desktop copy and a OneDrive copy;
    # the SKILL.md catalogue may live in either. Pick the copy that actually has skills.
    up = os.path.dirname(WORKSPACE)
    home = os.path.expanduser("~")
    for base in {up, home, os.path.join(home, "Desktop"),
                 os.path.join(home, "OneDrive - Procter and Gamble", "Desktop")}:
        if not base:
            continue
        try:
            for entry in os.listdir(base):
                if "m&m" in entry.lower() or entry.lower() == "m&m":
                    candidates.append(os.path.join(base, entry, ".github", "skills"))
        except Exception:
            pass

    def _has_skills(d):
        try:
            return any(os.path.isfile(os.path.join(d, e, "SKILL.md"))
                       for e in os.listdir(d))
        except Exception:
            return False

    for c in candidates:
        if os.path.isdir(c) and _has_skills(c):
            return c
    return candidates[0]


SKILLS_ROOT = _resolve_skills_root()

# Public base for published light-apps.
PUBLISH_BASE = os.environ.get("WB_PUBLISH_BASE", "http://127.0.0.1:8737")


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] wb: {m}", flush=True)


def _ensure_dirs():
    for d in (STATE_DIR, APPS_DIR, CUSTOM_SKILLS_DIR):
        os.makedirs(d, exist_ok=True)


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"WARN could not read {os.path.basename(path)}: {type(e).__name__}: {e}")
        return default


def _write_json(path, data):
    _ensure_dirs()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log(f"ERROR writing {os.path.basename(path)}: {type(e).__name__}: {e}")
        raise


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").strip().lower()).strip("-")
    return s or ("item-" + uuid.uuid4().hex[:8])


# =============================================================== SKILLS ======
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_md(text):
    """Light YAML-frontmatter parse (no PyYAML dependency)."""
    name = desc = None
    m = _FRONT.search(text)
    front = m.group(1) if m else text[:800]
    for key in ("name", "description"):
        km = re.search(rf"(?m)^{key}\s*:\s*(.+?)\s*$", front)
        if km:
            v = km.group(1).strip()
            if v and v[0] in "\"'" and v[-1] == v[0] and len(v) > 1:
                v = v[1:-1]
            if key == "name":
                name = v
            else:
                desc = v
    body = text[m.end():] if m else text
    return name, desc, body


def _guess_kind(folder, desc):
    d = (desc or "").lower()
    f = (folder or "").lower()
    if f.startswith("bmad"):
        return "workflow", "Workflow"
    # knowledge / reasoning skills first (interpret, reason, answer, govern)
    if any(w in d for w in ("reason about", "interpret", "answer", "q&a", "governance",
                            "explain", "knowledge", "rag", "search over")):
        return "knowledge", "Knowledge"
    if any(w in d for w in ("transform", "migrat", "validate", "build ", "mine",
                            "discover", "process model", "event log")):
        return "flow", "Flow"
    if any(w in d for w in ("run ", "query", "execute", "connector", "call ", "api")):
        return "tool", "Tool"
    return "knowledge", "Knowledge"


def _first_sentence(desc):
    if not desc:
        return ""
    s = re.split(r"(?<=[.。])\s", desc.strip())[0]
    return s[:240]


def _trigger_phrases(desc):
    m = re.search(r"[Tt]rigger phrases?\s*:\s*(.+)$", desc or "")
    if not m:
        return []
    raw = m.group(1)
    out = re.findall(r"'([^']+)'|\"([^\"]+)\"", raw)
    phrases = [a or b for a, b in out]
    return phrases[:12]


def _scan_skill_dirs():
    roots = []
    if os.path.isdir(SKILLS_ROOT):
        roots.append((SKILLS_ROOT, False))
    if os.path.isdir(CUSTOM_SKILLS_DIR):
        roots.append((CUSTOM_SKILLS_DIR, True))
    items = []
    for root, custom in roots:
        for entry in sorted(os.listdir(root)):
            folder = os.path.join(root, entry)
            md = os.path.join(folder, "SKILL.md")
            if not os.path.isfile(md):
                continue
            try:
                with open(md, encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                log(f"WARN read {entry}/SKILL.md failed: {type(e).__name__}: {e}")
                continue
            name, desc, _body = _parse_skill_md(text)
            kind, kind_label = _guess_kind(entry, desc)
            files = [x for x in sorted(os.listdir(folder))]
            items.append({
                "id": entry,
                "name": name or entry,
                "desc": desc or "",
                "summary": _first_sentence(desc),
                "kind": kind, "kindLabel": kind_label,
                "triggers": _trigger_phrases(desc),
                "custom": custom,
                "files": files,
                "mdPath": os.path.relpath(md, WORKSPACE).replace("\\", "/"),
                "chars": len(text),
            })
    return items


def skills_list():
    state = _read_json(SKILL_STATE, {})
    items = _scan_skill_dirs()
    for it in items:
        st = state.get(it["id"], {})
        it["installed"] = bool(st.get("installed", False))
        it["enabled"] = bool(st.get("enabled", False))
    installed = sum(1 for i in items if i["installed"])
    enabled = sum(1 for i in items if i["enabled"])
    by_kind = {}
    for i in items:
        by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
    return {"available": True, "count": len(items),
            "installed": installed, "enabled": enabled,
            "byKind": by_kind, "root": SKILLS_ROOT.replace("\\", "/"),
            "skills": items}


def skill_detail(sid):
    for root in (SKILLS_ROOT, CUSTOM_SKILLS_DIR):
        md = os.path.join(root, sid, "SKILL.md")
        if os.path.isfile(md):
            with open(md, encoding="utf-8") as f:
                text = f.read()
            name, desc, body = _parse_skill_md(text)
            state = _read_json(SKILL_STATE, {}).get(sid, {})
            return {"available": True, "id": sid, "name": name or sid,
                    "desc": desc or "", "body": body.strip(),
                    "installed": bool(state.get("installed")),
                    "enabled": bool(state.get("enabled")),
                    "mdPath": os.path.relpath(md, WORKSPACE).replace("\\", "/")}
    return {"available": False, "error": f"skill not found: {sid}"}


def skill_set_state(sid, installed=None, enabled=None):
    ids = {i["id"] for i in _scan_skill_dirs()}
    if sid not in ids:
        return {"available": False, "error": f"skill not found: {sid}"}
    state = _read_json(SKILL_STATE, {})
    cur = state.get(sid, {"installed": False, "enabled": False})
    if installed is not None:
        cur["installed"] = bool(installed)
        if not installed:
            cur["enabled"] = False
        elif enabled is None:
            cur["enabled"] = True  # installing enables by default
    if enabled is not None:
        cur["enabled"] = bool(enabled)
        if enabled:
            cur["installed"] = True
    state[sid] = cur
    _write_json(SKILL_STATE, state)
    log(f"skill '{sid}' -> installed={cur['installed']} enabled={cur['enabled']}")
    return {"available": True, "id": sid, **cur}


def skill_create(name, description, instructions=""):
    if not (name or "").strip():
        return {"available": False, "error": "name is required"}
    sid = _slug(name)
    folder = os.path.join(CUSTOM_SKILLS_DIR, sid)
    if os.path.exists(folder):
        sid = sid + "-" + uuid.uuid4().hex[:4]
        folder = os.path.join(CUSTOM_SKILLS_DIR, sid)
    os.makedirs(folder, exist_ok=True)
    desc = (description or "").strip() or f"Custom skill: {name}."
    body = (instructions or "").strip() or (
        f"# {name}\n\nUse when: {desc}\n\n## Steps\n1. ...\n")
    md = f"---\nname: {sid}\ndescription: \"{desc}\"\n---\n\n{body}\n"
    try:
        with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(md)
    except Exception as e:
        log(f"ERROR create skill '{sid}': {type(e).__name__}: {e}")
        raise
    skill_set_state(sid, installed=True, enabled=True)
    log(f"created custom skill '{sid}'")
    return {"available": True, "id": sid, "name": name, "custom": True}


# ================================================================ APPS ========
def _app_dir(aid):
    return os.path.join(APPS_DIR, aid)


def _app_manifest_path(aid):
    return os.path.join(_app_dir(aid), "app.json")


def apps_list():
    _ensure_dirs()
    out = []
    for entry in sorted(os.listdir(APPS_DIR)):
        mf = _app_manifest_path(entry)
        if not os.path.isfile(mf):
            continue
        m = _read_json(mf, None)
        if not m:
            continue
        out.append({"id": m.get("id", entry), "name": m.get("name", entry),
                    "kind": m.get("kind", "dashboard"),
                    "published": bool(m.get("published")),
                    "publishUrl": m.get("publishUrl"),
                    "updated": m.get("updated"),
                    "hasCsv": bool(m.get("csv"))})
    out.sort(key=lambda x: (not x["published"], (x["name"] or "").lower()))
    return {"available": True, "count": len(out), "apps": out}


def app_get(aid):
    m = _read_json(_app_manifest_path(aid), None)
    if not m:
        return {"available": False, "error": f"app not found: {aid}"}
    html = ""
    hp = os.path.join(_app_dir(aid), "index.html")
    if os.path.isfile(hp):
        with open(hp, encoding="utf-8") as f:
            html = f.read()
    csv_text = ""
    cp = os.path.join(_app_dir(aid), "data.csv")
    if os.path.isfile(cp):
        with open(cp, encoding="utf-8") as f:
            csv_text = f.read()
    return {"available": True, **m, "html": html, "csv": csv_text}


def app_save(aid, name=None, html=None, csv=None, kind=None):
    aid = aid or _slug(name) or ("app-" + uuid.uuid4().hex[:8])
    if not re.fullmatch(r"[a-z0-9\-]+", aid or ""):
        aid = _slug(aid)
    d = _app_dir(aid)
    os.makedirs(d, exist_ok=True)
    m = _read_json(_app_manifest_path(aid), None) or {
        "id": aid, "name": name or aid, "kind": kind or "dashboard",
        "published": False, "publishUrl": None,
        "created": datetime.datetime.now().isoformat()}
    if name is not None:
        m["name"] = name
    if kind is not None:
        m["kind"] = kind
    if html is not None:
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
    if csv is not None:
        with open(os.path.join(d, "data.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv)
        m["csv"] = True
    m["updated"] = datetime.datetime.now().isoformat()
    _write_json(_app_manifest_path(aid), m)
    log(f"app '{aid}' saved (html={html is not None} csv={csv is not None})")
    return {"available": True, "id": aid, "name": m["name"],
            "published": m["published"], "publishUrl": m.get("publishUrl")}


def app_csv_rows(aid):
    cp = os.path.join(_app_dir(aid), "data.csv")
    if not os.path.isfile(cp):
        return {"available": False, "error": "no csv"}
    with open(cp, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    return {"available": True, "header": header,
            "rows": [dict(zip(header, r)) for r in body]}


def app_csv_write(aid, header, rows):
    d = _app_dir(aid)
    if not os.path.isdir(d):
        return {"available": False, "error": f"app not found: {aid}"}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        if isinstance(r, dict):
            w.writerow([r.get(h, "") for h in header])
        else:
            w.writerow(r)
    with open(os.path.join(d, "data.csv"), "w", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
    m = _read_json(_app_manifest_path(aid), {}) or {}
    m["csv"] = True
    m["updated"] = datetime.datetime.now().isoformat()
    _write_json(_app_manifest_path(aid), m)
    log(f"app '{aid}' csv written ({len(rows)} rows)")
    return {"available": True, "id": aid, "rows": len(rows)}


def app_publish(aid, publish=True):
    mf = _app_manifest_path(aid)
    m = _read_json(mf, None)
    if not m:
        return {"available": False, "error": f"app not found: {aid}"}
    m["published"] = bool(publish)
    m["publishUrl"] = f"{PUBLISH_BASE}/p/{aid}" if publish else None
    m["updated"] = datetime.datetime.now().isoformat()
    _write_json(mf, m)
    log(f"app '{aid}' published={m['published']} url={m['publishUrl']}")
    return {"available": True, "id": aid, "published": m["published"],
            "publishUrl": m["publishUrl"]}


def app_delete(aid):
    import shutil
    d = _app_dir(aid)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        log(f"app '{aid}' deleted")
        return {"available": True, "id": aid, "deleted": True}
    return {"available": False, "error": f"app not found: {aid}"}


def published_html(aid):
    """Serve a published light-app: HTML with its CSV injected as window.APP_DATA."""
    m = _read_json(_app_manifest_path(aid), None)
    if not m or not m.get("published"):
        return None
    d = _app_dir(aid)
    hp = os.path.join(d, "index.html")
    if not os.path.isfile(hp):
        return None
    with open(hp, encoding="utf-8") as f:
        html = f.read()
    data = app_csv_rows(aid)
    inject = ("<script>window.APP_DATA=" +
              json.dumps(data if data.get("available") else {"header": [], "rows": []},
                         ensure_ascii=False) + ";</script>")
    if "</head>" in html:
        html = html.replace("</head>", inject + "\n</head>", 1)
    else:
        html = inject + "\n" + html
    return html


# ============================================================= EXPERTS =======
def experts_list():
    data = _read_json(EXPERTS_FILE, None)
    if data is None:
        data = {"experts": []}
    return {"available": True, "count": len(data.get("experts", [])),
            "experts": data.get("experts", [])}


def expert_save(expert):
    data = _read_json(EXPERTS_FILE, {"experts": []})
    experts = data.get("experts", [])
    eid = expert.get("id") or _slug(expert.get("name", ""))
    expert["id"] = eid
    expert.setdefault("type", "expert")   # "expert" | "team"
    expert["updated"] = datetime.datetime.now().isoformat()
    for i, e in enumerate(experts):
        if e.get("id") == eid:
            experts[i] = expert
            break
    else:
        experts.append(expert)
    data["experts"] = experts
    _write_json(EXPERTS_FILE, data)
    log(f"expert '{eid}' saved (type={expert['type']})")
    return {"available": True, "id": eid, "type": expert["type"]}


def expert_delete(eid):
    data = _read_json(EXPERTS_FILE, {"experts": []})
    before = len(data.get("experts", []))
    data["experts"] = [e for e in data.get("experts", []) if e.get("id") != eid]
    _write_json(EXPERTS_FILE, data)
    return {"available": True, "id": eid, "deleted": before != len(data["experts"])}


def experts_seed(seed):
    """Seed experts from the UIUX agents/assistants (only if empty)."""
    data = _read_json(EXPERTS_FILE, None)
    if data and data.get("experts"):
        return {"available": True, "seeded": 0, "count": len(data["experts"])}
    experts = []
    for a in seed or []:
        experts.append({
            "id": a.get("id") or _slug(a.get("name", "")),
            "name": a.get("name", ""),
            "type": "team" if a.get("members") else "expert",
            "persona": a.get("role") or a.get("desc", ""),
            "methodology": a.get("desc", ""),
            "skills": a.get("skills", []),
            "members": a.get("members", []),
            "icon": a.get("icon", ""),
            "updated": datetime.datetime.now().isoformat(),
        })
    _write_json(EXPERTS_FILE, {"experts": experts})
    log(f"seeded {len(experts)} experts")
    return {"available": True, "seeded": len(experts), "count": len(experts)}


# ============================================================ PROJECTS =======
def projects_list():
    data = _read_json(PROJECTS_FILE, {"projects": []})
    return {"available": True, "count": len(data.get("projects", [])),
            "projects": data.get("projects", [])}


def project_save(project):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    projects = data.get("projects", [])
    pid = project.get("id") or _slug(project.get("name", ""))
    project["id"] = pid
    project.setdefault("skills", [])
    project.setdefault("apps", [])
    project.setdefault("experts", [])
    project.setdefault("dataSources", [])
    project["updated"] = datetime.datetime.now().isoformat()
    for i, p in enumerate(projects):
        if p.get("id") == pid:
            projects[i] = project
            break
    else:
        project.setdefault("created", project["updated"])
        projects.append(project)
    data["projects"] = projects
    _write_json(PROJECTS_FILE, data)
    log(f"project '{pid}' saved")
    return {"available": True, "id": pid}


def project_delete(pid):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    before = len(data.get("projects", []))
    data["projects"] = [p for p in data.get("projects", []) if p.get("id") != pid]
    _write_json(PROJECTS_FILE, data)
    return {"available": True, "id": pid, "deleted": before != len(data["projects"])}


def summary():
    """Small status object for the bridge /health and UI headers."""
    try:
        sk = skills_list()
    except Exception as e:
        sk = {"count": 0, "installed": 0, "enabled": 0, "error": str(e)}
    return {"skillsRoot": SKILLS_ROOT.replace("\\", "/"),
            "skills": sk.get("count", 0),
            "skillsInstalled": sk.get("installed", 0),
            "apps": apps_list().get("count", 0),
            "experts": experts_list().get("count", 0),
            "projects": projects_list().get("count", 0),
            "stateDir": STATE_DIR.replace("\\", "/")}
