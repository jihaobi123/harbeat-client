from __future__ import annotations

import os

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.music.model_selection import pick_model_bundle, pick_style_engine
from app.modules.music.audio_processor import process_audio_for_style
from app.modules.music.models import SongCue
from app.modules.music.schemas import (
    CueCreateRequest,
    CueData,
    SongData,
    SongProcessRequest,
    SongProcessResult,
    SongProcessStyleMeta,
    SongTagUpdateRequest,
    UpsertSongRequest,
)
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


def search_songs(db: Session, query: str) -> list[SongData]:
    pattern = f"%{query}%"
    songs = (
        db.query(Song)
        .filter((Song.title.ilike(pattern)) | (Song.artist.ilike(pattern)))
        .order_by(Song.created_at.desc())
        .limit(50)
        .all()
    )
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


def upsert_song_with_tags(db: Session, payload: UpsertSongRequest) -> SongData:
    song = db.query(Song).filter(Song.title == payload.title, Song.artist == payload.artist).first()
    if song is None:
        song = Song(title=payload.title, artist=payload.artist)
        db.add(song)
        db.flush()

    tag = song.tags
    if tag is None:
        tag = SongTag(song_id=song.id)
        db.add(tag)
        db.flush()

    if payload.tags:
        existing_styles = {t.strip() for t in (tag.style or "").split(",") if t.strip()}
        existing_styles.update(payload.tags)
        tag.style = ",".join(sorted(existing_styles))
    if payload.energy:
        existing_energy = {e.strip() for e in (tag.energy or "").split(",") if e.strip()}
        existing_energy.update(payload.energy)
        tag.energy = ",".join(sorted(existing_energy))
    if payload.scenes:
        existing_scenes = {s.strip() for s in (tag.groove_tag or "").split(",") if s.strip()}
        existing_scenes.update(payload.scenes)
        tag.groove_tag = ",".join(sorted(existing_scenes))
    if payload.bpm is not None:
        tag.bpm = payload.bpm

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


def process_song_for_styles(db: Session, song_id: int, payload: SongProcessRequest) -> SongProcessResult:
    """
    对单曲生成多风格街舞成品（当前为成熟模型选择+管线路由层）。
    实际推理可在此处替换为 Demucs/Essentia/RAVE/FFmpeg 调用。
    """
    song = get_song_or_404(db, song_id)

    requested_styles = payload.styles or _split_style_tags(song.tags.style if song.tags else None)
    if not requested_styles:
        requested_styles = ["hiphop"]

    processed_files: dict[str, str] = {}
    meta: dict[str, SongProcessStyleMeta] = {}

    base_bundle = pick_model_bundle(payload.quality_mode)

    for style in requested_styles:
        selected_models = {
            "stem_separator": base_bundle.stem_separator,
            "beat_tracker": base_bundle.beat_tracker,
            "key_detector": base_bundle.key_detector,
            "time_stretch": base_bundle.time_stretch,
            "transition_mixer": base_bundle.transition_mixer,
            "mastering": base_bundle.mastering,
            "style_engine": pick_style_engine(style, payload.quality_mode),
        }

        output_path = f"data/music-files/shared/processed/{song_id}_{style}_{payload.quality_mode}.wav"
        note = "model bundle selected; fallback path generated"
        try:
            if os.path.isfile(output_path):
                note = "cached: already processed"
                payload_bpm = payload.bpm
            elif song.audio_url:
                process_meta = process_audio_for_style(
                    input_path=song.audio_url,
                    output_path=output_path,
                    style=style,
                    target_bpm=payload.bpm,
                    target_energy=payload.energy,
                )
                note = "processed with librosa-based dance pipeline"
                if process_meta.get("target_bpm") and payload.bpm is None:
                    payload_bpm = int(process_meta["target_bpm"])
                else:
                    payload_bpm = payload.bpm
            else:
                payload_bpm = payload.bpm
        except Exception as exc:
            payload_bpm = payload.bpm
            note = f"processing skipped: {exc}"

        processed_files[style] = output_path
        meta[style] = SongProcessStyleMeta(
            selected_models=selected_models,
            bpm=payload_bpm,
            energy=payload.energy,
            note=note,
        )

    return SongProcessResult(song_id=song_id, processed_files=processed_files, meta=meta)
