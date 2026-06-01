from __future__ import annotations

import os
import shutil

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

from app.modules.library.models import LibrarySong
from app.modules.library.schemas import LibrarySongCreateRequest, LibrarySongUpdateRequest


def list_library_songs(db: Session, user_id: int) -> list[LibrarySong]:
    return (
        db.query(LibrarySong)
        .options(
            load_only(
                LibrarySong.id,
                LibrarySong.user_id,
                LibrarySong.song_id,
                LibrarySong.title,
                LibrarySong.artist,
                LibrarySong.duration,
                LibrarySong.format,
                LibrarySong.file_size,
                LibrarySong.source_type,
                LibrarySong.platform_id,
                LibrarySong.platform_url,
                LibrarySong.bpm,
                LibrarySong.key,
                LibrarySong.camelot_key,
                LibrarySong.energy,
                LibrarySong.analysis_status,
                LibrarySong.stems,
                LibrarySong.cue_points,
                LibrarySong.beat_points,
                LibrarySong.created_at,
                LibrarySong.updated_at,
            )
        )
        .filter(LibrarySong.user_id == user_id)
        .order_by(LibrarySong.created_at.desc())
        .all()
    )


def search_library_songs(db: Session, user_id: int, query: str) -> list[LibrarySong]:
    pattern = f"%{query}%"
    return (
        db.query(LibrarySong)
        .options(
            load_only(
                LibrarySong.id,
                LibrarySong.user_id,
                LibrarySong.song_id,
                LibrarySong.title,
                LibrarySong.artist,
                LibrarySong.duration,
                LibrarySong.format,
                LibrarySong.file_size,
                LibrarySong.source_type,
                LibrarySong.platform_id,
                LibrarySong.platform_url,
                LibrarySong.bpm,
                LibrarySong.key,
                LibrarySong.camelot_key,
                LibrarySong.energy,
                LibrarySong.analysis_status,
                LibrarySong.stems,
                LibrarySong.cue_points,
                LibrarySong.beat_points,
                LibrarySong.created_at,
                LibrarySong.updated_at,
            )
        )
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
        existing = _find_existing_library_song(db, payload)
        if existing is not None:
            return existing
        song = LibrarySong(id=payload.id, user_id=payload.user_id)
        db.add(song)
    elif song.user_id != payload.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="song belongs to another user",
        )

    _apply_song_fields(song, payload.model_dump(exclude={"user_id"}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _find_existing_library_song(db, payload)
        if existing is not None:
            return existing
        raise
    db.refresh(song)
    return song


def _find_existing_library_song(
    db: Session,
    payload: LibrarySongCreateRequest,
) -> LibrarySong | None:
    """Return the row that won a concurrent import race, if one exists."""
    if payload.platform_id:
        existing = (
            db.query(LibrarySong)
            .filter(
                LibrarySong.user_id == payload.user_id,
                LibrarySong.platform_id == payload.platform_id,
            )
            .order_by(LibrarySong.updated_at.desc())
            .first()
        )
        if existing is not None:
            return existing

    if payload.source_path:
        existing = (
            db.query(LibrarySong)
            .filter(
                LibrarySong.user_id == payload.user_id,
                LibrarySong.source_path == payload.source_path,
            )
            .order_by(LibrarySong.updated_at.desc())
            .first()
        )
        if existing is not None:
            return existing

    return None


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


def delete_library_song(db: Session, song_id: str, user_id: int) -> None:
    song = db.get(LibrarySong, song_id)
    if song is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="library song not found")
    if song.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your song")

    # 删除音频文件
    if song.source_path:
        try:
            if os.path.isfile(song.source_path):
                os.remove(song.source_path)
        except OSError:
            pass

    # 删除 stems 目录
    if song.stems:
        for stem_path in song.stems.values():
            try:
                if stem_path and os.path.isfile(stem_path):
                    os.remove(stem_path)
            except OSError:
                pass

    db.delete(song)
    db.commit()


def _apply_song_fields(song: LibrarySong, values: dict) -> None:
    int_bool_fields = {
        "beat_needs_review",
        "intro_is_clean",
        "outro_is_clean",
        "has_drum_loop",
    }
    for key, value in values.items():
        if key == "cue_points" and value is not None:
            setattr(song, key, [item.model_dump() if hasattr(item, "model_dump") else item for item in value])
            continue
        if key in int_bool_fields and value is not None:
            value = int(bool(value))
        setattr(song, key, value)
