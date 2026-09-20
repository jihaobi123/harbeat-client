"""Manifest API endpoints — downloadable asset blueprint for RK3588 edge."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.modules.manifest import build_song_manifest, build_playlist_manifest
from app.shared.database import get_db

router = APIRouter(prefix="/manifest", tags=["manifest"])


def _public_base_url(request: Request) -> str:
    from app.shared.config import get_settings

    settings = get_settings()
    configured = (
        getattr(settings, "public_asset_base_url", None)
        or os.environ.get("PUBLIC_ASSET_BASE_URL", "")
    ).strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}".rstrip("/")
    return ""


@router.get("/song/{song_id}")
def get_song_manifest(song_id: str, request: Request, db: Session = Depends(get_db)):
    """Return standard manifest for a single song (P5 / P8 compatible)."""
    from app.modules.library.models import LibrarySong

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    manifest = build_song_manifest(song, base_url=_public_base_url(request))
    return {"code": 0, "message": "ok", "data": {"manifest": manifest}, "ok": True, "manifest": manifest}


@router.get("/playlist/{playlist_id}")
def get_playlist_manifest(
    playlist_id: int,
    request: Request,
    plan_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return manifest for all tracks in a playlist (or mix plan).

    Called by Flutter app: GET /api/playlists/{id}/manifest
    """
    from app.modules.playlists.models import Playlist

    if db.get(Playlist, playlist_id) is None:
        raise HTTPException(status_code=404, detail="Playlist not found")

    manifest = build_playlist_manifest(
        playlist_id, db, base_url=_public_base_url(request), plan_id=plan_id,
    )
    return {"code": 0, "message": "ok", "data": {"manifest": manifest}, "ok": True, "manifest": manifest}
