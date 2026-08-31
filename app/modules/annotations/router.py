"""Authenticated HTTP endpoints for Bar-level presence review."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.modules.annotations.schemas import (
    PresenceAnnotationBundle,
    PresenceReviewRequest,
)
from app.modules.annotations.service import (
    AnnotationAccessError,
    AnnotationGenerationError,
    PresenceAnnotationService,
)
from app.modules.annotations.store import (
    AnnotationNotFound,
    AnnotationStoreError,
    RevisionConflict,
)
from app.modules.auth.service import decode_access_token
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse


router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def get_annotation_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = decode_access_token(credentials.credentials)
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    return user


def get_annotation_service() -> PresenceAnnotationService:
    return PresenceAnnotationService.from_settings()


def _library_song_model():
    from app.modules.library.models import LibrarySong

    return LibrarySong


def _owned_song(db: Session, song_id: str, user_id: int):
    song = db.get(_library_song_model(), song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if int(song.user_id) != int(user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    return song


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, AnnotationNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (AnnotationAccessError,)):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, RevisionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, AnnotationGenerationError):
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    if isinstance(exc, AnnotationStoreError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get(
    "/songs/{song_id}/presence",
    response_model=APIResponse[PresenceAnnotationBundle],
)
def get_presence_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_annotation_user),
    service: PresenceAnnotationService = Depends(get_annotation_service),
):
    song = _owned_song(db, song_id, current_user.id)
    try:
        bundle = service.read(song=song, requesting_user_id=current_user.id)
    except Exception as exc:
        _raise_http(exc)
    return APIResponse(data=bundle)


@router.post(
    "/songs/{song_id}/presence/generate",
    response_model=APIResponse[PresenceAnnotationBundle],
)
def generate_presence_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_annotation_user),
    service: PresenceAnnotationService = Depends(get_annotation_service),
):
    song = _owned_song(db, song_id, current_user.id)
    try:
        bundle = service.generate_for_song(
            song=song,
            requesting_user_id=current_user.id,
        )
    except Exception as exc:
        _raise_http(exc)
    return APIResponse(data=bundle)


@router.put(
    "/songs/{song_id}/presence/review",
    response_model=APIResponse[PresenceAnnotationBundle],
)
def review_presence_endpoint(
    song_id: str,
    payload: PresenceReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_annotation_user),
    service: PresenceAnnotationService = Depends(get_annotation_service),
):
    song = _owned_song(db, song_id, current_user.id)
    try:
        bundle = service.review(
            song=song,
            requesting_user_id=current_user.id,
            payload=payload,
            actor_id=f"user:{current_user.id}",
        )
    except Exception as exc:
        _raise_http(exc)
    return APIResponse(data=bundle)


@router.post(
    "/songs/{song_id}/presence/adjudicate",
    response_model=APIResponse[PresenceAnnotationBundle],
)
def adjudicate_presence_endpoint(
    song_id: str,
    payload: PresenceReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_annotation_user),
    service: PresenceAnnotationService = Depends(get_annotation_service),
):
    song = _owned_song(db, song_id, current_user.id)
    try:
        bundle = service.adjudicate(
            song=song,
            requesting_user_id=current_user.id,
            payload=payload,
            actor_id=f"user:{current_user.id}",
        )
    except Exception as exc:
        _raise_http(exc)
    return APIResponse(data=bundle)


@router.get("/songs/{song_id}/presence/export")
def export_presence_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_annotation_user),
    service: PresenceAnnotationService = Depends(get_annotation_service),
):
    song = _owned_song(db, song_id, current_user.id)
    try:
        content = service.export(song=song, requesting_user_id=current_user.id)
    except Exception as exc:
        _raise_http(exc)
    return Response(
        content=content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{song_id}-presence.jsonl"'},
    )
