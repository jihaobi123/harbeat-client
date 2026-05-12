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


def _migrate_add_missing_columns():
    """Add columns that exist in models but not in the database."""
    import logging
    from sqlalchemy import inspect as sa_inspect, text
    logger = logging.getLogger(__name__)
    with engine.connect() as conn:
        inspector = sa_inspect(engine)
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(engine.dialect)
                    # Determine default value for NOT NULL columns
                    default_val = None
                    if col.default is not None and col.default.arg is not None and not callable(col.default.arg):
                        default_val = col.default.arg
                    if col.nullable:
                        sql = f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} NULL'
                    elif default_val is not None:
                        sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} NOT NULL DEFAULT '{default_val}'"
                    else:
                        # Add as nullable first to avoid errors on existing rows, then set a safe default
                        sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} NULL"
                    try:
                        logger.info("[migrate] %s", sql)
                        conn.execute(text(sql))
                    except Exception:
                        # Column may already be added by another worker — safe to ignore
                        logger.debug("[migrate] skipped (already exists?): %s", sql)
        conn.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_add_missing_columns()

    # Use Redis SETNX to ensure only one worker runs heavy startup tasks
    _is_primary = False
    try:
        from app.shared.redis import get_redis
        _is_primary = get_redis().set("harbeat:startup_lock", str(os.getpid()), nx=True, ex=120)
    except Exception:
        # If Redis is unavailable, fall back to running (safe for single-worker)
        _is_primary = True

    if _is_primary:
        # Clean up old DJ mix files on startup
        _cleanup_old_mix_files()
        # Purge shared/processed — this directory was historically used to cache
        # audio copies named "{id}_hiphop_fast_raw.mp3" but is no longer needed.
        _purge_processed_cache()
        # Auto-analyze songs that have files but were never analyzed
        if os.getenv("ENABLE_STARTUP_ANALYSIS", "1") == "1":
            _schedule_pending_analyses()

    yield

    # Release lock on shutdown
    if _is_primary:
        try:
            from app.shared.redis import get_redis
            get_redis().delete("harbeat:startup_lock")
        except Exception:
            pass


def _cleanup_old_mix_files(max_age_hours: int = 1):
    """Remove DJ mix files older than max_age_hours to save disk space."""
    import time
    import logging
    logger = logging.getLogger(__name__)
    mixes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "music-files", "shared", "mixes")
    if not os.path.isdir(mixes_dir):
        return
    now = time.time()
    cutoff = now - max_age_hours * 3600
    removed = 0
    for fname in os.listdir(mixes_dir):
        fpath = os.path.join(mixes_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info("[startup] Cleaned up %d old mix files from %s", removed, mixes_dir)


def _purge_processed_cache() -> None:
    """Remove the deprecated shared/processed cache directory entirely.

    Historical versions of _build_processed_fallback copied audio into this
    directory as "{song_id}_{style}_{quality_mode}_raw.mp3". Those copies are
    never used by the online playback path and were being picked up by the
    dev scanner as spurious library entries.
    """
    import logging, shutil
    logger = logging.getLogger(__name__)
    proc_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "data", "music-files", "shared", "processed",
    )
    if os.path.isdir(proc_dir):
        try:
            shutil.rmtree(proc_dir)
            logger.info("[startup] Purged deprecated processed cache: %s", proc_dir)
        except OSError as exc:
            logger.warning("[startup] Could not purge processed cache: %s", exc)


def _schedule_pending_analyses():
    """Find songs that need analysis and queue a limited batch on startup.

    Only queues songs that were explicitly imported (fangpi/library upload),
    not dev_mix placeholder entries. Limits to 3 songs per startup to avoid
    flooding the system with heavy Demucs processing.
    """
    import os
    import threading
    from app.shared.database import SessionLocal
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song, SongTag  # noqa: F401 — ensure models loaded

    db = SessionLocal()
    try:
        pending = db.query(LibrarySong).filter(
            LibrarySong.analysis_status.in_(["none", "pending", "analyzing"]),
            LibrarySong.source_type != "local_dev_scan",
        ).order_by(LibrarySong.created_at.desc()).limit(3).all()
        to_analyze = [s.id for s in pending if s.source_path and os.path.isfile(s.source_path)]
        db.close()
    except Exception:
        db.close()
        return

    if not to_analyze:
        return

    import logging
    logger = logging.getLogger(__name__)
    logger.info("[startup] Queuing analysis for %d pending songs (max 3)", len(to_analyze))

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
