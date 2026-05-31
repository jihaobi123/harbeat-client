import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.modules import models  # noqa: F401
from app.modules.router import api_router
from app.shared.config import get_settings
from app.shared.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("ENABLE_DB_CREATE_ALL", "0") == "1":
        Base.metadata.create_all(bind=engine)
    # Auto-analyze songs that have files but were never analyzed
    if os.getenv("ENABLE_STARTUP_ANALYSIS", "0") == "1":
        _schedule_pending_analyses()
    yield


def _schedule_pending_analyses():
    """Find songs that need analysis/stems and queue them."""
    import os
    import threading
    from app.shared.database import SessionLocal
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song, SongTag  # noqa: F401 — ensure models loaded

    db = SessionLocal()
    try:
        # Pick up songs never analyzed AND songs stuck in "analyzing" (interrupted by restart)
        pending = db.query(LibrarySong).filter(
            LibrarySong.analysis_status.in_(["none", "pending", "analyzing"])
        ).all()
        to_analyze = [s.id for s in pending if s.source_path and os.path.isfile(s.source_path)]
        db.close()
    except Exception:
        db.close()
        return

    if not to_analyze:
        return

    import logging
    logger = logging.getLogger(__name__)
    logger.info("[startup] Queuing analysis for %d unanalyzed songs", len(to_analyze))

    def _run_all(song_ids: list[str]):
        from app.modules.library.background_tasks import run_analysis_and_separation
        for sid in song_ids:
            try:
                run_analysis_and_separation(sid)
            except Exception:
                logger.exception("[startup] analysis failed for %s", sid)

    thread = threading.Thread(target=_run_all, args=(to_analyze,), daemon=True)
    thread.start()


settings = get_settings()

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

# Serve the web frontend (built into web/dist)
_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _web_dist.is_dir():
    _assets_dir = _web_dist / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    _index_html = _web_dist / "index.html"

    @app.get("/")
    @app.get("/{full_path:path}")
    async def _spa_fallback(request: Request, full_path: str = ""):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            raise HTTPException(status_code=404)
        # Serve static file if it exists
        candidate = _web_dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        # Otherwise serve SPA index
        if _index_html.is_file():
            return FileResponse(str(_index_html))
        raise HTTPException(status_code=404)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.detail, "data": {}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    details = exc.errors()
    fields = [".".join(str(p) for p in e.get("loc", [])) + ": " + e.get("msg", "") for e in details]
    msg = "validation error: " + "; ".join(fields) if fields else "validation error"
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": msg, "data": {"errors": details}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": str(exc), "data": {}},
    )
