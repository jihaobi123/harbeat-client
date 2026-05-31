"""Manifest API endpoints — downloadable asset blueprint for RK3588 edge."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.modules.manifest import build_song_manifest, build_playlist_manifest
from app.shared.database import get_db

router = APIRouter(prefix="/manifest", tags=["manifest"])


@router.get("/song/{song_id}")
def get_song_manifest(song_id: str, db: Session = Depends(get_db)):
    """Return standard manifest for a single song (P5 / P8 compatible)."""
    from app.modules.library.models import LibrarySong

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    from app.shared.config import get_settings
    settings = get_settings()
    base_url = f"http://localhost:{settings.app_port}"

    return {"ok": True, "manifest": build_song_manifest(song, base_url=base_url)}


@router.get("/playlist/{playlist_id}")
def get_playlist_manifest(
    playlist_id: int,
    plan_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return manifest for all tracks in a playlist (or mix plan).

    Called by Flutter app: GET /api/playlists/{id}/manifest
    """
    from app.shared.config import get_settings
    settings = get_settings()
    base_url = f"http://localhost:{settings.app_port}"

    manifest = build_playlist_manifest(
        playlist_id, db, base_url=base_url, plan_id=plan_id,
    )
    return {"ok": True, "manifest": manifest}
