"""Authenticated API for the assisted Bar annotation workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.modules.annotations.schemas import (
    AnnotationWorkspace,
    SaveAnnotationWorkspaceRequest,
)
from app.modules.annotations.service import (
    AnnotationValidationError,
    build_annotation_workspace,
    save_annotation_workspace,
)
from app.modules.annotations.store import AnnotationStore, RevisionConflict, TimelineConflict
from app.modules.auth.dependencies import get_current_user
from app.modules.library.models import LibrarySong
from app.modules.users.models import User
from app.shared.config import get_settings
from app.shared.database import get_db
from app.shared.responses import APIResponse


router = APIRouter()
DEFAULT_DATASET_VERSION = "bar-understanding-1.0.0"


def get_annotation_store() -> AnnotationStore:
    return AnnotationStore(get_settings().annotation_dir)


def _get_owned_song(db: Session, track_id: str, user_id: int) -> LibrarySong:
    song = db.get(LibrarySong, track_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    if song.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")
    return song


@router.get(
    "/tracks/{track_id}/workspace",
    response_model=APIResponse[AnnotationWorkspace],
)
def get_annotation_workspace_endpoint(
    track_id: str,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    store: AnnotationStore = Depends(get_annotation_store),
):
    song = _get_owned_song(db, track_id, current_user.id)
    try:
        workspace = build_annotation_workspace(song, dataset_version, store)
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
    store: AnnotationStore = Depends(get_annotation_store),
):
    song = _get_owned_song(db, track_id, current_user.id)
    try:
        workspace = save_annotation_workspace(
            song,
            request,
            store,
            annotator_id=f"user:{current_user.id}",
        )
    except (RevisionConflict, TimelineConflict) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AnnotationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return APIResponse(data=workspace)
