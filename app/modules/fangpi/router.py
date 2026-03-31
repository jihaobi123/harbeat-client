"""Fangpi.net search & download API routes."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.fangpi.service import download_fangpi_song, search_fangpi
from app.modules.fangpi.playlist_parser import parse_playlist_url
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


class ParsePlaylistRequest(BaseModel):
    url: str


@router.post("/search")
async def fangpi_search(payload: SearchRequest):
    """Search songs on fangpi.net."""
    results = await search_fangpi(payload.query)
    return APIResponse(data={"songs": results})


@router.post("/download")
async def fangpi_download(
    payload: DownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a song from fangpi.net and add to user's library."""
    settings = get_settings()
    upload_dir = os.path.abspath(settings.upload_dir)
    user_dir = os.path.join(upload_dir, str(current_user.id))
    os.makedirs(user_dir, exist_ok=True)

    try:
        result = await download_fangpi_song(
            payload.music_id, payload.title, payload.artist, user_dir
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"download failed: {e}",
        )

    from datetime import datetime

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
    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/parse-playlist")
async def parse_playlist_endpoint(payload: ParsePlaylistRequest):
    """Parse a NetEase Cloud Music or QQ Music playlist URL."""
    try:
        result = await parse_playlist_url(payload.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(data=result)
