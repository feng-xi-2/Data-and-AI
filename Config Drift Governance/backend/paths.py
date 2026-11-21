"""paths.py -- single source of truth for every filesystem path in the backend.

WHY
---
Historically each script hard-coded an absolute OneDrive path, e.g.:

    ONEDRIVE = r"c:\\Users\\<you>\\OneDrive - Procter and Gamble\\Desktop\\M&M"

That breaks the moment the project is copied to another machine. This module
resolves the workspace root *relative to the package* (the folder that contains
`backend/`, `UIUX/` and `Config report/`), so nothing needs editing after a
`git clone` / unzip. An optional `.env` (or the `WHS_WORKSPACE` environment
variable) can override the data location.

USAGE (drop-in, keeps the old variable name so nothing else changes)
    from paths import WORKSPACE as ONEDRIVE
    COE  = os.path.join(ONEDRIVE, "Config report", "data.xlsx")
    OUT  = os.path.join(ONEDRIVE, "UIUX", "assets", "exception-ledger.js")

Resolution order for the workspace root:
    1. WHS_WORKSPACE env var / .env value, if set and it exists
    2. the package root = parent of this backend/ folder  (default, portable)

No third-party dependency: the `.env` reader is a tiny built-in parser.
Follows workspace rules: fixed, explicit paths; fails loudly if the data
folder is missing rather than silently producing empty output.
"""
from __future__ import annotations

import os

# --- locate the package root (parent of the backend/ folder that holds this file)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PACKAGE_ROOT = os.path.dirname(_HERE)


def _load_dotenv(path: str) -> None:
    """Minimal KEY=VALUE .env loader (no dependency). Existing env wins."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError as exc:  # never fail the whole run over a bad .env
        print(f"[paths] WARN could not read .env ({type(exc).__name__}): {exc}")


# load .env from the package root, then from backend/, if present
_load_dotenv(os.path.join(_PACKAGE_ROOT, ".env"))
_load_dotenv(os.path.join(_HERE, ".env"))


def _resolve_workspace() -> str:
    override = os.environ.get("WHS_WORKSPACE", "").strip().strip('"').strip("'")
    if override:
        override = os.path.abspath(os.path.expanduser(override))
        if os.path.isdir(override):
            return override
        print(f"[paths] WARN WHS_WORKSPACE='{override}' not found; using package root")
    return _PACKAGE_ROOT


# The workspace root. Everything else hangs off this.
WORKSPACE = _resolve_workspace()

# Well-known sub-locations (kept as attributes for scripts that prefer them).
DATA_DIR = os.path.join(WORKSPACE, "Config report")          # inputs + generated CSVs
ASSETS_DIR = os.path.join(WORKSPACE, "UIUX", "assets")        # generated *.js for the frontend
CACHE_DIR = os.path.join(WORKSPACE, ".cache", "build")        # build cache / staging artifacts
SKILLS_DIR = os.path.join(WORKSPACE, ".github", "skills")     # integrated SKILL.md packages
SKILL_DIR = os.path.join(SKILLS_DIR, "config-drift-human-decision")  # the HITL decision skill

# The two real inputs, surfaced for convenience.
COE_XLSX = os.path.join(DATA_DIR, "data.xlsx")
CRFC_CSV = os.path.join(DATA_DIR, "Configuration_RFC.csv")


def require_data_dir() -> str:
    """Return DATA_DIR, or raise loudly if it is missing (no silent empty runs)."""
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(
            f"[paths] data folder not found: {DATA_DIR}\n"
            f"        Set WHS_WORKSPACE (or edit .env) to the folder that contains "
            f"'Config report/'."
        )
    return DATA_DIR


def ensure_cache_dir() -> str:
    """Return CACHE_DIR, creating it recursively if it does not exist."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


if __name__ == "__main__":
    print("WORKSPACE :", WORKSPACE)
    print("DATA_DIR  :", DATA_DIR, "(exists:", os.path.isdir(DATA_DIR), ")")
    print("ASSETS_DIR:", ASSETS_DIR, "(exists:", os.path.isdir(ASSETS_DIR), ")")
    print("COE_XLSX  :", COE_XLSX, "(exists:", os.path.isfile(COE_XLSX), ")")
    print("CRFC_CSV  :", CRFC_CSV, "(exists:", os.path.isfile(CRFC_CSV), ")")
