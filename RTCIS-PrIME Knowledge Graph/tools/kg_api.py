"""RTCIS <-> PrIME 2014 <-> PrIME 2022 graph API for the knowledge-graph.html tab (local bridge, like graph_api.py).
    python tools/kg_api.py            ->  http://127.0.0.1:8738/rp/health
Graph from Cosmos DB (Gremlin), model from the GenAI platform, validation on the replica databases. Read-only: every
SQL passes the sqlglot guard before any database call; execution is capped (50 rows, 120 s)."""
import json
import os
import re
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))
import kg_core as k  # noqa: E402

SITES = {"RTCIS_EUS": "RTCIS", "RTCIS_LON": "RTCIS", "PRIME14_XQ": "PrIME2014", "PRIME22_DE08": "PrIME2022", "PRIME22_WMD1": "PrIME2022"}


class Ask(BaseModel):
    question: str
    engine: str = "PrIME2022"
    site: str = "PRIME22_DE08"
    params: dict | None = None


class Convert(BaseModel):
    sql: str
    source_engine: str = "RTCIS"
    target_engine: str = "PrIME2022"
    source_site: str = "RTCIS_EUS"
    target_site: str = "PRIME22_DE08"
    params: dict | None = None
    source_params: dict | None = None


class Batch(BaseModel):
    kind: str = "ask"
    text: str
    engine: str = "PrIME2022"
    site: str = "PRIME22_DE08"
    target_engine: str | None = None
    target_site: str | None = None
    params: dict | None = None


class Validate(BaseModel):
    sql: str
    site: str
    params: dict | None = None


class Approve(BaseModel):
    question: str
    engine: str
    sql: str
    site: str


def _site(s):
    if s and s not in SITES:
        raise HTTPException(400, f"unknown site {s}; one of {', '.join(SITES)}")


LOCAL_ORIGIN = r"^(null|https?://(127\.0\.0\.1|localhost)(:\d+)?)$"
LOCAL_HOST = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$")


def create_app(svc):
    app = FastAPI(title="RTCIS-PrIME knowledge graph API")
    # the API acts as the signed-in user (replicas, model, Cosmos): only the local page may call it
    app.add_middleware(CORSMiddleware, allow_origin_regex=LOCAL_ORIGIN, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if not LOCAL_HOST.match(request.headers.get("host", "")):
            return JSONResponse({"detail": "host not allowed"}, status_code=400)          # DNS rebinding
        origin = request.headers.get("origin")
        if origin is not None and not re.match(LOCAL_ORIGIN, origin):
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        if request.method == "POST" and not request.headers.get("content-type", "").lower().startswith("application/json"):
            return JSONResponse({"detail": "send application/json"}, status_code=415)     # forces a CORS preflight
        return await call_next(request)

    @app.get("/rp/health")
    def health():
        return {"ok": True, "sites": SITES, "templates": len(svc.templates)}

    @app.get("/rp/graph")
    def graph(view: str = "versions", key: str = "invlod", limit: int = 40):
        return svc.graph.view(view, key, min(limit, 80))

    @app.get("/rp/search")
    def search(q: str):
        return svc.graph.search(q)

    @app.get("/rp/templates")
    def templates():
        return [{x: t.get(x, "") for x in ("qid", "engine", "title", "intent", "grade", "params", "sql")} for t in svc.templates]

    @app.post("/rp/ask")
    def ask(b: Ask):
        _site(b.site)
        return svc.assistant.ask(b.question, engine=b.engine, site=b.site, params=b.params)

    @app.post("/rp/convert")
    def convert(b: Convert):
        _site(b.source_site), _site(b.target_site)
        return svc.assistant.convert(b.sql, b.source_engine, b.target_engine, b.source_site, b.target_site,
                                     params=b.params, source_params=b.source_params)

    @app.post("/rp/batch")
    def batch(b: Batch):
        _site(b.site), _site(b.target_site)
        parts = k.parse_batch(b.text, b.kind)[:25]
        items = [{"kind": "ask", "question": p} if b.kind == "ask" else {"kind": "convert", "sql": p} for p in parts]
        return svc.assistant.batch(items, engine=b.engine, site=b.site, target_engine=b.target_engine, target_site=b.target_site,
                                   params=b.params)

    @app.post("/rp/validate")
    def validate(b: Validate):
        _site(b.site)
        return svc.db.validate(b.sql, b.site, b.params)

    @app.post("/rp/approve")
    def approve(b: Approve):
        try:
            sql = k.guard_sql(b.sql)
        except k.UnsafeSQL as e:
            raise HTTPException(400, str(e))
        rec = {"qid": "approved", "engine": b.engine, "intent": b.question, "sql": sql, "site": b.site}
        with open(svc.approved_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        svc.assistant.approved.append(rec)
        return {"approved": True}

    return app


if __name__ == "__main__":
    import asyncio
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    import kg_services
    uvicorn.run(create_app(kg_services.services()), host="127.0.0.1", port=int(os.environ.get("KG_API_PORT", "8738")))
