"""Authenticated API for the shared, per-user Bar annotation Pilot."""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import decode_access_token
from app.modules.bar_annotations.pilot import PilotManifest, PilotTrackNotFound
from app.modules.bar_annotations.schemas import (
    AnnotationWorkspace,
    PilotTrackSummary,
    SaveAnnotationWorkspaceRequest,
)
from app.modules.bar_annotations.service import (
    AnnotationValidationError,
    build_annotation_workspace,
    save_annotation_workspace,
)
from app.modules.bar_annotations.store import AnnotationStore, RevisionConflict, TimelineConflict
from app.modules.bar_annotations.songformer_sections import SongFormerSectionStore
from app.modules.users.models import User
from app.shared.config import get_settings
from app.shared.database import get_db
from app.shared.responses import APIResponse


router = APIRouter()
DEFAULT_DATASET_VERSION = "bar-understanding-1.0.0"
STEM_NAMES = {"vocals", "drums", "bass", "other"}
CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "opus": "audio/opus",
}
CHUNK_SIZE = 1024 * 256


def get_bar_annotation_store() -> AnnotationStore:
    return AnnotationStore(get_settings().bar_annotation_dir)


def get_pilot_manifest() -> PilotManifest:
    return PilotManifest.load(get_settings().bar_annotation_pilot_manifest)


def get_songformer_section_store() -> SongFormerSectionStore:
    return SongFormerSectionStore(get_settings().songformer_section_dir)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pilot track not found")


def _library_song_model():
    from app.modules.library.models import LibrarySong

    return LibrarySong


def _db_song_model(db: Session):
    return getattr(db, "_library_song_model", None) or _library_song_model()


def _pilot_song(db: Session, manifest: PilotManifest, track_id: str) -> Any:
    try:
        manifest.require_track(track_id)
    except PilotTrackNotFound as exc:
        raise _not_found() from exc
    song = db.get(_db_song_model(db), track_id)
    if song is None:
        raise _not_found()
    return song


def _require_dataset(manifest: PilotManifest, dataset_version: str) -> None:
    if dataset_version != manifest.dataset_version:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="dataset_version does not match the public Pilot",
        )


def resolve_pilot_media_path(
    song: Any,
    manifest: PilotManifest,
    stem_name: Optional[str],
) -> str:
    try:
        manifest.require_track(str(song.id))
    except PilotTrackNotFound as exc:
        raise _not_found() from exc
    if stem_name is None:
        path = getattr(song, "source_path", "")
    else:
        if stem_name not in STEM_NAMES:
            raise _not_found()
        stems = getattr(song, "stems", None) or {}
        path = stems.get(stem_name, "")
    if not path or not os.path.isfile(path):
        raise _not_found()
    return str(path)


@router.get("/pilot/tracks", response_model=APIResponse[list[PilotTrackSummary]])
def get_pilot_tracks_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    manifest: PilotManifest = Depends(get_pilot_manifest),
):
    del current_user
    tracks: list[PilotTrackSummary] = []
    for track_id in manifest.track_ids:
        song = db.get(_db_song_model(db), track_id)
        if song is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pilot manifest references a missing song",
            )
        stems = getattr(song, "stems", None) or {}
        tracks.append(
            PilotTrackSummary(
                id=str(song.id),
                title=str(song.title),
                artist=str(song.artist),
                duration_sec=float(song.duration or 0.0),
                stems_available=[
                    name
                    for name in ("vocals", "drums", "bass", "other")
                    if stems.get(name) and os.path.isfile(stems[name])
                ],
            )
        )
    return APIResponse(data=tracks)


@router.get(
    "/tracks/{track_id}/workspace",
    response_model=APIResponse[AnnotationWorkspace],
)
def get_annotation_workspace_endpoint(
    track_id: str,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: AnnotationStore = Depends(get_bar_annotation_store),
    manifest: PilotManifest = Depends(get_pilot_manifest),
    section_store: SongFormerSectionStore = Depends(get_songformer_section_store),
):
    _require_dataset(manifest, dataset_version)
    song = _pilot_song(db, manifest, track_id)
    try:
        workspace = build_annotation_workspace(
            song,
            dataset_version,
            store,
            user_id=int(current_user.id),
            section_store=section_store,
        )
    except TimelineConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return APIResponse(data=workspace)


@router.put(
    "/tracks/{track_id}/workspace",
    response_model=APIResponse[AnnotationWorkspace],
)
def save_annotation_workspace_endpoint(
    track_id: str,
    request: SaveAnnotationWorkspaceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: AnnotationStore = Depends(get_bar_annotation_store),
    manifest: PilotManifest = Depends(get_pilot_manifest),
    section_store: SongFormerSectionStore = Depends(get_songformer_section_store),
):
    _require_dataset(manifest, request.dataset_version)
    song = _pilot_song(db, manifest, track_id)
    try:
        workspace = save_annotation_workspace(
            song,
            request,
            store,
            user_id=int(current_user.id),
            section_store=section_store,
        )
    except (RevisionConflict, TimelineConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AnnotationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return APIResponse(data=workspace)


def _iter_file(path: str, start: int, end: int):
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _range_response(path: str, file_size: int, content_type: str, request: Request):
    range_header = request.headers.get("range")
    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        return StreamingResponse(
            _iter_file(path, start, end),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
            },
        )
    return StreamingResponse(
        _iter_file(path, 0, file_size - 1),
        media_type=content_type,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
    )


def _get_media_user(request: Request, db: Session, token_param: Optional[str]) -> User:
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else token_param
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    payload = decode_access_token(token)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def _stream_pilot_media(
    track_id: str,
    stem_name: Optional[str],
    request: Request,
    token: Optional[str],
    db: Session,
    manifest: PilotManifest,
):
    _get_media_user(request, db, token)
    song = _pilot_song(db, manifest, track_id)
    path = resolve_pilot_media_path(song, manifest, stem_name)
    file_size = os.path.getsize(path)
    if stem_name is not None:
        content_type = "audio/wav"
    else:
        extension = os.path.splitext(path)[1].lstrip(".").lower()
        content_type = CONTENT_TYPES.get(extension, "application/octet-stream")
    return _range_response(path, file_size, content_type, request)


@router.get("/tracks/{track_id}/audio")
def stream_pilot_audio_endpoint(
    track_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    manifest: PilotManifest = Depends(get_pilot_manifest),
):
    return _stream_pilot_media(track_id, None, request, token, db, manifest)


@router.get("/tracks/{track_id}/stems/{stem_name}")
def stream_pilot_stem_endpoint(
    track_id: str,
    stem_name: str,
    request: Request,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    manifest: PilotManifest = Depends(get_pilot_manifest),
):
    return _stream_pilot_media(track_id, stem_name, request, token, db, manifest)
