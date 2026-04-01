"""Music search & download API routes (Kuwo-backed, fangpi-compatible interface)."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.fangpi.service import download_fangpi_song, search_fangpi, smart_search_fangpi
from app.modules.fangpi.playlist_parser import parse_playlist_url
from app.modules.library.background_tasks import copy_analysis_from, run_analysis_and_separation
from app.modules.library.schemas import LibrarySongCreateRequest, LibrarySongData
from app.modules.library.service import create_or_replace_library_song
from app.modules.users.models import User
from app.shared.config import get_settings
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


class SearchRequest(BaseModel):
    query: str


class DownloadRequest(BaseModel):
    music_id: str
    title: str
    artist: str
    tags: list[str] = []
    energy: list[str] = []
    scenes: list[str] = []
    source: str = "fangpi"  # "fangpi" or "kuwo"


class ParsePlaylistRequest(BaseModel):
    url: str


@router.post("/search")
async def fangpi_search(payload: SearchRequest):
    """Search songs via music API (Kuwo)."""
    results = await search_fangpi(payload.query)
    return APIResponse(data={"songs": results})


@router.post("/download")
async def fangpi_download(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a song to the shared server pool and link to user's library."""
    from datetime import datetime
    from app.modules.music.schemas import UpsertSongRequest
    from app.modules.music.service import upsert_song_with_tags
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song

    settings = get_settings()
    upload_dir = os.path.abspath(settings.upload_dir)
    shared_dir = os.path.join(upload_dir, "shared")
    os.makedirs(shared_dir, exist_ok=True)

    # Check if this song already exists on the server (by platform_id or title+artist)
    existing_lib = (
        db.query(LibrarySong)
        .filter(LibrarySong.platform_id == payload.music_id)
        .first()
    )

    if existing_lib:
        # Song already downloaded — just upsert tags (accumulate) and link to this user
        catalog_song = upsert_song_with_tags(db, UpsertSongRequest(
            title=payload.title,
            artist=payload.artist,
            tags=payload.tags,
            energy=payload.energy,
            scenes=payload.scenes,
        ))

        # Check if this user already has a library entry for this song
        user_lib = (
            db.query(LibrarySong)
            .filter(LibrarySong.user_id == current_user.id, LibrarySong.platform_id == payload.music_id)
            .first()
        )
        if not user_lib:
            user_lib = LibrarySong(
                id=uuid.uuid4().hex,
                user_id=current_user.id,
                title=payload.title,
                artist=payload.artist,
                duration=existing_lib.duration or 0,
                format="mp3",
                file_size=existing_lib.file_size or 0,
                source_type="fangpi",
                source_path=existing_lib.source_path,
                platform_id=payload.music_id,
                platform_url=f"https://www.fangpi.net/music/{payload.music_id}",
                song_id=catalog_song.id,
                created_at=datetime.utcnow(),
            )
            # Copy analysis results from existing entry
            copy_analysis_from(existing_lib, user_lib)
            db.add(user_lib)
            db.commit()
            db.refresh(user_lib)
        else:
            if user_lib.song_id != catalog_song.id:
                user_lib.song_id = catalog_song.id
                db.commit()
                db.refresh(user_lib)

        return APIResponse(data=LibrarySongData.model_validate(user_lib))

    # New song — download to shared directory
    try:
        result = await download_fangpi_song(
            payload.music_id, payload.title, payload.artist, shared_dir,
            source=payload.source,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"download failed: {e}",
        )

    song_id = uuid.uuid4().hex
    song_payload = LibrarySongCreateRequest(
        id=song_id,
        user_id=current_user.id,
        title=payload.title,
        artist=payload.artist,
        duration=0,
        format="mp3",
        file_size=result["file_size"],
        source_type="fangpi",
        source_path=result["file_path"],
        platform_id=payload.music_id,
        platform_url=f"https://www.fangpi.net/music/{payload.music_id}",
        created_at=datetime.utcnow(),
    )
    song = create_or_replace_library_song(db, song_payload)

    # Create/update Song + SongTag (accumulate tags) and link
    catalog_song = upsert_song_with_tags(db, UpsertSongRequest(
        title=payload.title,
        artist=payload.artist,
        tags=payload.tags,
        energy=payload.energy,
        scenes=payload.scenes,
    ))

    lib_row = db.get(LibrarySong, song.id)
    if lib_row and lib_row.song_id != catalog_song.id:
        lib_row.song_id = catalog_song.id
        db.commit()

    # Enqueue background analysis + stem separation
    if lib_row:
        lib_row.analysis_status = "pending"
        db.commit()
    background_tasks.add_task(run_analysis_and_separation, song.id)

    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/parse-playlist")
async def parse_playlist_endpoint(payload: ParsePlaylistRequest):
    """Parse a NetEase Cloud Music or QQ Music playlist URL."""
    try:
        result = await parse_playlist_url(payload.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(data=result)


class BatchSearchItem(BaseModel):
    title: str
    artist: str


class BatchSearchRequest(BaseModel):
    songs: list[BatchSearchItem]


@router.post("/batch-search")
async def fangpi_batch_search(payload: BatchSearchRequest):
    """Search fangpi for multiple songs. Returns {results: [{title, artist, found: bool, candidates: [...]}]}."""
    results = []
    for item in payload.songs:
        candidates = await smart_search_fangpi(item.title, item.artist)
        results.append({
            "title": item.title,
            "artist": item.artist,
            "found": len(candidates) > 0,
            "candidates": candidates[:5],  # Top 5 per song
        })
    return APIResponse(data={"results": results})
