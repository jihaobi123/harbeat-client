from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.library.schemas import LibrarySongCreateRequest, LibrarySongUpdateRequest


def list_library_songs(db: Session, user_id: int) -> list[LibrarySong]:
    return (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == user_id)
        .order_by(LibrarySong.created_at.desc())
        .all()
    )


def search_library_songs(db: Session, user_id: int, query: str) -> list[LibrarySong]:
    pattern = f"%{query}%"
    return (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            (LibrarySong.title.ilike(pattern)) | (LibrarySong.artist.ilike(pattern)),
        )
        .order_by(LibrarySong.created_at.desc())
        .limit(50)
        .all()
    )


def create_or_replace_library_song(
    db: Session,
    payload: LibrarySongCreateRequest,
) -> LibrarySong:
    song = db.get(LibrarySong, payload.id)
    if song is None:
        song = LibrarySong(id=payload.id, user_id=payload.user_id)
        db.add(song)
    elif song.user_id != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="song belongs to another user",
        )

    _apply_song_fields(song, payload.model_dump(exclude={"user_id"}))
    db.commit()
    db.refresh(song)
    return song


def update_library_song(
    db: Session,
    song_id: str,
    payload: LibrarySongUpdateRequest,
) -> LibrarySong:
    song = db.get(LibrarySong, song_id)
    if song is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="library song not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return song

    _apply_song_fields(song, updates)
    db.commit()
    db.refresh(song)
    return song


def delete_library_song(db: Session, song_id: str) -> None:
    song = db.get(LibrarySong, song_id)
    if song is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="library song not found")

    db.delete(song)
    db.commit()


def _apply_song_fields(song: LibrarySong, values: dict) -> None:
    for key, value in values.items():
        if key == "cue_points" and value is not None:
            setattr(song, key, [item.model_dump() if hasattr(item, "model_dump") else item for item in value])
            continue
        setattr(song, key, value)
