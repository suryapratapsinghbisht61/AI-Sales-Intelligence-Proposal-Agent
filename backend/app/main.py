import json
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import approvals, auth, documents, knowledge, orgs, proposals, prospects
from app.config import get_settings
from app.db import engine
from app.security import Ctx, ctx
from app.services.llm import BudgetExceeded, LLMNotConfigured

log = logging.getLogger("salespilot.http")
logging.basicConfig(level=logging.INFO, format="%(message)s")
settings = get_settings()

app = FastAPI(title="SalesPilot AI", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# shortcut: in-process limiter, per instance only; move to Redis/Postgres when running >1 API replica
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.monotonic()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin != settings.frontend_origin:  # CSRF defence for cookie auth
            return JSONResponse({"detail": "Cross-origin request blocked"}, 403)
        key = request.cookies.get("sp_session") or (request.client.host if request.client else "anon")
        q = _hits[key]
        while q and q[0] < start - 60:
            q.popleft()
        if len(q) >= settings.rate_limit_per_minute:
            return JSONResponse({"detail": "Too many requests, please slow down"}, 429, {"Retry-After": "30"})
        q.append(start)
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    log.info(json.dumps({"request_id": rid, "method": request.method, "path": request.url.path,
                         "status": resp.status_code, "ms": int((time.monotonic() - start) * 1000)}))
    return resp


@app.exception_handler(LLMNotConfigured)
async def _not_configured(_, e):
    return JSONResponse({"detail": str(e), "code": "llm_not_configured"}, 503)


@app.exception_handler(BudgetExceeded)
async def _budget(_, e):
    return JSONResponse({"detail": str(e), "code": "budget_exceeded"}, 429)


@app.exception_handler(Exception)
async def _unhandled(request: Request, e: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, 500)


api = APIRouter(prefix="/api/v1")
for r in (auth, orgs, documents, knowledge, prospects, proposals, approvals):
    api.include_router(r.router)

INTEGRATIONS = [
    ("google_drive", "Google Drive", "Import documents into the Knowledge Base"),
    ("sharepoint", "Microsoft SharePoint / OneDrive", "Import documents into the Knowledge Base"),
    ("hubspot", "HubSpot", "Sync prospects and proposal status"),
    ("salesforce", "Salesforce", "Sync prospects and proposal status"),
    ("gmail", "Gmail", "Send approved outreach"),
    ("google_calendar", "Google Calendar", "Meeting briefs"),
    ("slack", "Slack", "Approval notifications"),
]


@api.get("/integrations")
def integrations(c: Ctx = Depends(ctx)):
    s = get_settings()
    built_in = [
        {"key": "document_upload", "name": "Document upload", "description": "Upload files to the Knowledge Base",
         "status": "connected"},
        {"key": "website_research", "name": "Public website research",
         "description": "Reads a prospect's own website (robots.txt respected)", "status": "connected"},
        {"key": "llm", "name": "AI model provider", "description": s.chat_model or "Set CHAT_MODEL",
         "status": "connected" if s.chat_model else "not_configured"},
        {"key": "embeddings", "name": "Embedding provider", "description": s.embedding_model or "Set EMBEDDING_MODEL",
         "status": "connected" if s.embedding_model else "not_configured"},
    ]
    return built_in + [{"key": k, "name": n, "description": d, "status": "coming_soon"} for k, n, d in INTEGRATIONS]


app.include_router(api)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "database unavailable"}, 503)
    return {"status": "ready", "llm_configured": bool(settings.chat_model and settings.embedding_model)}
