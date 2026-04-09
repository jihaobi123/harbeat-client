from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.modules.auth.service import decode_access_token
from app.modules.library.models import LibrarySong
from app.modules.users.models import User
from app.shared.database import get_db

router = APIRouter()

CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "opus": "audio/opus",
    "wma": "audio/x-ms-wma",
}

CHUNK_SIZE = 1024 * 256  # 256 KB


def _iter_file(path: str, start: int, end: int):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _range_response(file_path: str, file_size: int, content_type: str, request: Request):
    """Handle optional Range header and return appropriate streaming response."""
    range_header = request.headers.get("range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        content_length = end - start + 1
        return StreamingResponse(
            _iter_file(file_path, start, end),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    return StreamingResponse(
        _iter_file(file_path, 0, file_size - 1),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


def _get_user_from_request(request: Request, db: Session, token_param: str | None) -> User:
    """Extract user from Authorization header or query param token."""
    token: str | None = None

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    elif token_param:
        token = token_param

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")

    payload = decode_access_token(token)
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


@router.get("/processed/{filename}")
def stream_processed(
    filename: str,
    request: Request,
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Stream a style-processed audio file from data/music-files/shared/processed/."""
    _get_user_from_request(request, db, token)

    # Sanitize filename to prevent path traversal
    safe_name = os.path.basename(filename)
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "music-files", "shared", "processed")
    )
    file_path = os.path.normpath(os.path.join(base_dir, safe_name))
    if not file_path.startswith(base_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid filename")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="processed file not found")

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(safe_name)[1].lstrip(".").lower()
    content_type = CONTENT_TYPES.get(ext, "audio/wav")
    return _range_response(file_path, file_size, content_type, request)


@router.get("/mixes/{filename}")
def stream_mix(
    filename: str,
    request: Request,
    token: str | None = Query(None),
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Stream an offline-rendered DJ mix from data/music-files/shared/mixes/."""
    _get_user_from_request(request, db, token)

    safe_name = os.path.basename(filename)
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "music-files", "shared", "mixes")
    )
    file_path = os.path.normpath(os.path.join(base_dir, safe_name))
    if not file_path.startswith(base_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid filename")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mix file not found")

    file_size = os.path.getsize(file_path)
    ext = os.path.splitext(safe_name)[1].lstrip(".").lower()
    content_type = CONTENT_TYPES.get(ext, "audio/wav")

    if download:
        return StreamingResponse(
            _iter_file(file_path, 0, file_size - 1),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "Content-Length": str(file_size),
            },
        )

    return _range_response(file_path, file_size, content_type, request)


@router.delete("/mixes/{filename}")
def delete_mix(
    filename: str,
    request: Request,
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Delete a temporary DJ mix file after user has downloaded it."""
    _get_user_from_request(request, db, token)

    safe_name = os.path.basename(filename)
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "music-files", "shared", "mixes")
    )
    file_path = os.path.normpath(os.path.join(base_dir, safe_name))
    if not file_path.startswith(base_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid filename")
    if os.path.isfile(file_path):
        os.remove(file_path)
    return {"ok": True}


@router.get("/{song_id}")
def stream_audio(
    song_id: str,
    request: Request,
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    _get_user_from_request(request, db, token)

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")

    file_path = song.source_path
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audio file not found on disk")

    file_size = os.path.getsize(file_path)
    fmt = song.format.lower().lstrip(".")
    content_type = CONTENT_TYPES.get(fmt, "application/octet-stream")
    return _range_response(file_path, file_size, content_type, request)


@router.get("/{song_id}/stem/{stem_name}")
def stream_stem(
    song_id: str,
    stem_name: str,
    request: Request,
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Stream a separated stem audio file."""
    _get_user_from_request(request, db, token)

    if stem_name not in ("vocals", "drums", "bass", "other"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid stem name")

    song = db.get(LibrarySong, song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")

    if not song.stems or stem_name not in song.stems:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stem not available")

    file_path = song.stems[stem_name]
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stem file not found on disk")

    file_size = os.path.getsize(file_path)
    return _range_response(file_path, file_size, "audio/wav", request)
