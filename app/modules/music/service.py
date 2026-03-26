from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.music.models import SongCue
from app.modules.music.schemas import CueCreateRequest, SongData, SongTagUpdateRequest
from app.modules.playlists.models import Song, SongTag
from app.modules.users.service import get_user_or_404


def _split_style_tags(style_value: str | None) -> list[str]:
    if not style_value:
        return []
    return [item.strip() for item in style_value.split(",") if item.strip()]


def serialize_song(song: Song) -> SongData:
    tag = song.tags
    return SongData(
        id=song.id,
        title=song.title,
        artist=song.artist,
        audio_url=song.audio_url,
        duration=song.duration,
        bpm=tag.bpm if tag else None,
        energy=tag.energy if tag else None,
        style=tag.style if tag else None,
        vocal_type=tag.vocal_type if tag else None,
        era_tag=tag.era_tag if tag else None,
        groove_tag=tag.groove_tag if tag else None,
        difficulty_fit=tag.difficulty_fit if tag else None,
        tags=_split_style_tags(tag.style if tag else None),
    )


def list_songs(db: Session) -> list[SongData]:
    songs = db.query(Song).order_by(Song.created_at.desc()).all()
    return [serialize_song(song) for song in songs]


def get_song_or_404(db: Session, song_id: int) -> Song:
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    return song


def update_song_tags(db: Session, song_id: int, payload: SongTagUpdateRequest) -> SongData:
    song = get_song_or_404(db, song_id)
    tag = song.tags
    if tag is None:
        tag = SongTag(song_id=song.id)
        db.add(tag)
        db.flush()

    values = payload.model_dump()
    if values["tags"]:
        values["style"] = ",".join(values["tags"])

    for key in ("bpm", "energy", "style", "vocal_type", "era_tag", "groove_tag", "difficulty_fit"):
        if values.get(key) is not None:
            setattr(tag, key, values[key])

    db.commit()
    db.refresh(song)
    return serialize_song(song)


def create_cue(db: Session, payload: CueCreateRequest) -> CueData:
    get_user_or_404(db, payload.user_id)
    get_song_or_404(db, payload.song_id)
    cue = SongCue(**payload.model_dump())
    db.add(cue)
    db.commit()
    db.refresh(cue)
    return CueData(
        id=cue.id,
        cue_type=cue.cue_type,
        start_time=cue.start_time,
        end_time=cue.end_time,
        label=cue.label,
    )


def list_cues(db: Session, song_id: int, user_id: int) -> list[CueData]:
    get_user_or_404(db, user_id)
    get_song_or_404(db, song_id)
    cues = (
        db.query(SongCue)
        .filter(SongCue.song_id == song_id, SongCue.user_id == user_id)
        .order_by(SongCue.start_time.asc())
        .all()
    )
    return [
        CueData(
            id=cue.id,
            cue_type=cue.cue_type,
            start_time=cue.start_time,
            end_time=cue.end_time,
            label=cue.label,
        )
        for cue in cues
    ]
