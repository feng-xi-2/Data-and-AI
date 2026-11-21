"""Replica connections for the kit: Azure AD token of the signed-in user (device code on first use, cached ~1 h by the wiki's
db_session.py). Sites: tools/sites.local.json (git-ignored; template sites.example.json). Every connection gets a 120 s timeout."""
import json
import os
import sys

WIKI = os.environ.get("WIKI_ROOT", os.path.join(os.path.dirname(__file__), "..", "..", "RTCIS-PrIME-LLM-Wiki"))
sys.path.insert(0, os.path.join(WIKI, "tools"))
from db_session import get_connection_raw  # noqa: E402

_F = os.path.join(os.path.dirname(__file__), "sites.local.json")
SITES = {k: v for k, v in json.load(open(_F, encoding="utf-8")).items() if not k.startswith("_")} if os.path.exists(_F) else {}
_POOL = {}


def connect(key, database=None, timeout=120):
    s = SITES[key]
    db = database or s.get("query_db") or s["database"]
    if (key, db) not in _POOL:
        c = get_connection_raw(s["server"], db)
        c.timeout = timeout
        _POOL[(key, db)] = c
    return _POOL[(key, db)]
