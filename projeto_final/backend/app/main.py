import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .logging_config import configure_logging, log_event
from .routes import admin, analysis, llm, reports, teams, tactical_search, video_analysis


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Football Intelligence Platform",
    description="API para inteligência tática com busca pública, grafos e leitura visual de vídeos.",
    version="0.1.0",
    lifespan=lifespan,
)

logger = configure_logging()

DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started_at = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - started_at) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log_event(
        logger,
        "http_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=request.client.host if request.client else None,
    )
    return response

app.include_router(teams.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(llm.router)
app.include_router(admin.router)
app.include_router(tactical_search.router)
app.include_router(video_analysis.router)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
MEDIA_DIR = Path(__file__).resolve().parents[1] / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/api/health", tags=["health"])
def health():
    return {
        "status": "online",
        "service": "Football Intelligence Platform",
        "ai_integration": "evidence_assisted",
        "data_source": "public_and_local",
        "deployment_profile": "free_optimized" if os.getenv("FOOTBALL_INTEL_FREE_MODE", "0").strip().casefold() in {"1", "true", "yes", "on"} else "standard",
    }


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "Frontend build nao encontrado. Execute npm run build em frontend/.",
        "api_docs": "/docs",
    }
