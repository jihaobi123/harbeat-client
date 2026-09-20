"""Music search & download API routes (Kuwo-backed, fangpi-compatible interface)."""
from __future__ import annotations

import asyncio
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

    # --- Cross-user dedup: check if ANY user already downloaded this song ---
    # Strategy: check by platform_id, then by title+artist in Song catalog,
    #           then by title+artist in LibrarySong (case-insensitive).
    existing_lib = (
        db.query(LibrarySong)
        .filter(LibrarySong.platform_id == payload.music_id)
        .first()
    )
    if not existing_lib:
        # Check via the Song catalog table (cross-platform canonical record)
        from sqlalchemy import func
        catalog_match = (
            db.query(Song)
            .filter(
                func.lower(Song.title) == payload.title.lower().strip(),
                func.lower(Song.artist) == payload.artist.lower().strip(),
            )
            .first()
        )
        if catalog_match:
            # Find any LibrarySong linked to this catalog song that has a file
            existing_lib = (
                db.query(LibrarySong)
                .filter(
                    LibrarySong.song_id == catalog_match.id,
                    LibrarySong.source_path.isnot(None),
                )
                .first()
            )
    if not existing_lib:
        # Fallback: case-insensitive title+artist on LibrarySong itself
        from sqlalchemy import func
        existing_lib = (
            db.query(LibrarySong)
            .filter(
                func.lower(LibrarySong.title) == payload.title.lower().strip(),
                func.lower(LibrarySong.artist) == payload.artist.lower().strip(),
                LibrarySong.source_path.isnot(None),
            )
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
            from sqlalchemy import func as sa_func
            user_lib = (
                db.query(LibrarySong)
                .filter(
                    LibrarySong.user_id == current_user.id,
                    sa_func.lower(LibrarySong.title) == payload.title.lower().strip(),
                    sa_func.lower(LibrarySong.artist) == payload.artist.lower().strip(),
                )
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
    """Search fangpi for multiple songs (concurrent).

    Uses a bounded semaphore so we don't overload the upstream Kuwo/fangpi API.
    With 8-way concurrency a 30-song playlist now resolves in ~5-15s instead
    of the prior 60-300s serial worst case (which made the mobile importer
    look stuck at "0%").
    """
    sem = asyncio.Semaphore(8)

    async def _search_one(item: BatchSearchItem) -> dict:
        async with sem:
            try:
                # Hard cap per-song so a single hung upstream can't stall the
                # whole batch. smart_search_fangpi internally has 12s timeouts
                # × up to 3 strategies = ~36s; cap at 18s and accept fewer
                # candidates over a hung connection.
                candidates = await asyncio.wait_for(
                    smart_search_fangpi(item.title, item.artist),
                    timeout=18.0,
                )
            except asyncio.TimeoutError:
                candidates = []
            except Exception:
                candidates = []
        return {
            "title": item.title,
            "artist": item.artist,
            "found": len(candidates) > 0,
            "candidates": candidates[:5],
        }

    results = await asyncio.gather(*[_search_one(it) for it in payload.songs])
    return APIResponse(data={"results": results})
