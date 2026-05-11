from __future__ import annotations

import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from hashlib import sha1

logger = logging.getLogger(__name__)

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.music.schemas import SongProcessRequest
from app.modules.music.service import process_song_for_styles
from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.playlists.schemas import (
    DjFxAutomationPoint,
    DjOfflineMixRequest,
    DjOfflineMixResult,
    DjMixPlanRequest,
    DjMixPlanResult,
    DjTransitionPlanItem,
    PlaylistDetailData,
    PlaylistImportRequest,
    PlaylistListData,
    PlaylistReorderRequest,
    PlaylistSongData,
    PlaylistSummaryData,
    StyleMixRequest,
    StyleMixResult,
)
from app.modules.playlists.groove_adapter import (
    library_song_to_track_metadata,
    run_groove_engine_plan,
)
from app.modules.playlists.offline_renderer import (
    OfflineRenderTrackInput,
    convert_wav_to_mp3,
    render_offline_mix,
)
from app.modules.users.service import get_user_or_404


def import_playlist(db: Session, payload: PlaylistImportRequest) -> tuple[Playlist, int]:
    get_user_or_404(db, payload.user_id)

    playlist = Playlist(
        user_id=payload.user_id,
        playlist_name=payload.playlist_name,
        source_type=payload.source_type,
    )
    db.add(playlist)
    db.flush()

    pending_analysis_count = 0

    for index, item in enumerate(payload.songs):
        song = db.query(Song).filter(Song.title == item.title, Song.artist == item.artist).first()
        if not song:
            song = Song(
                title=item.title,
                artist=item.artist,
                audio_url=str(item.audio_url) if item.audio_url else None,
                duration=item.duration,
            )
            db.add(song)
            db.flush()
            if item.bpm is not None or item.tags:
                db.add(SongTag(song_id=song.id, bpm=item.bpm, style=",".join(item.tags) if item.tags else None))
        elif (item.bpm is not None or item.tags) and song.tags is None:
            db.add(SongTag(song_id=song.id, bpm=item.bpm, style=",".join(item.tags) if item.tags else None))
        elif song.tags is not None:
            if item.bpm is not None:
                song.tags.bpm = item.bpm
            if item.tags:
                song.tags.style = ",".join(item.tags)

        relation = PlaylistSong(playlist_id=playlist.id, song_id=song.id, order_index=index)
        db.add(relation)

        if song.tags is None:
            pending_analysis_count += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"failed to import playlist: {exc}",
        ) from exc

    db.refresh(playlist)
    return playlist, pending_analysis_count


def list_playlists(db: Session, user_id: int) -> PlaylistListData:
    get_user_or_404(db, user_id)
    playlists = db.query(Playlist).filter(Playlist.user_id == user_id).order_by(Playlist.created_at.desc()).all()
    return PlaylistListData(
        playlists=[
            PlaylistSummaryData(
                id=playlist.id,
                user_id=playlist.user_id,
                playlist_name=playlist.playlist_name,
                source_type=playlist.source_type,
                song_count=len(playlist.songs),
            )
            for playlist in playlists
        ]
    )


def get_playlist_detail(db: Session, playlist_id: int) -> PlaylistDetailData:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")

    songs = (
        db.query(PlaylistSong)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.asc())
        .all()
    )

    # Build a lookup from song_id → LibrarySong analysis data
    from app.modules.library.models import LibrarySong
    song_ids = [item.song_id for item in songs]
    lib_songs = (
        db.query(LibrarySong)
        .filter(LibrarySong.song_id.in_(song_ids))
        .all()
    ) if song_ids else []
    # Map song_id → best LibrarySong (prefer one with bpm)
    lib_map: dict[int, LibrarySong] = {}
    for ls in lib_songs:
        if ls.song_id is None:
            continue
        existing = lib_map.get(ls.song_id)
        if existing is None or (existing.bpm is None and ls.bpm is not None):
            lib_map[ls.song_id] = ls

    return PlaylistDetailData(
        id=playlist.id,
        user_id=playlist.user_id,
        playlist_name=playlist.playlist_name,
        source_type=playlist.source_type,
        songs=[
            PlaylistSongData(
                song_id=item.song.id,
                library_song_id=lib_map[item.song_id].id if item.song_id in lib_map else None,
                title=item.song.title,
                artist=item.song.artist,
                audio_url=item.song.audio_url,
                duration=lib_map[item.song_id].duration if item.song_id in lib_map and lib_map[item.song_id].duration else item.song.duration,
                bpm=lib_map[item.song_id].bpm if item.song_id in lib_map else (item.song.tags.bpm if item.song.tags else None),
                replay_gain_db=_library_replay_gain_db(lib_map.get(item.song_id)),
                loudness_lufs=_library_loudness_lufs(lib_map.get(item.song_id)),
                key=lib_map[item.song_id].key if item.song_id in lib_map else None,
                energy=lib_map[item.song_id].energy if item.song_id in lib_map else None,
                format=lib_map[item.song_id].format if item.song_id in lib_map else None,
                analysis_status=lib_map[item.song_id].analysis_status if item.song_id in lib_map else None,
                tags=[part for part in (item.song.tags.style or "").split(",") if part] if item.song.tags else [],
                order_index=item.order_index,
            )
            for item in songs
        ],
    )


def delete_playlist(db: Session, playlist_id: int) -> None:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    db.delete(playlist)
    db.commit()


def update_playlist_song_tags(db: Session, playlist_id: int, song_id: int, tags: list[str]) -> None:
    relation = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song_id).first()
    if not relation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist song not found")

    tag = relation.song.tags
    if tag is None:
        tag = SongTag(song_id=song_id)
        db.add(tag)
    tag.style = ",".join(tags) if tags else None
    db.commit()


def create_empty_playlist(db: Session, user_id: int, name: str) -> Playlist:
    playlist = Playlist(user_id=user_id, playlist_name=name, source_type="manual")
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def add_library_songs_to_playlist(db: Session, playlist_id: int, user_id: int, library_song_ids: list[str]) -> int:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    if playlist.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")

    max_order = (
        db.query(PlaylistSong.order_index)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    added = 0
    for lib_song_id in library_song_ids:
        lib_song = db.get(LibrarySong, lib_song_id)
        if not lib_song or lib_song.user_id != user_id:
            continue

        song = db.query(Song).filter(Song.title == lib_song.title, Song.artist == lib_song.artist).first()
        if not song:
            song = Song(title=lib_song.title, artist=lib_song.artist, duration=lib_song.duration)
            db.add(song)
            db.flush()

        if lib_song.song_id != song.id:
            lib_song.song_id = song.id

        existing = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song.id).first()
        if existing:
            continue

        db.add(PlaylistSong(playlist_id=playlist_id, song_id=song.id, order_index=next_order))
        next_order += 1
        added += 1

    db.commit()
    return added


def generate_style_mix_playlist(db: Session, payload: StyleMixRequest, user_id: int) -> StyleMixResult:
    """
    练舞会话长歌单生成：
    1. 从服务器曲库按 style/bpm/energy 筛歌
    2. 累计到目标时长
    3. 对每首歌应用单曲风格处理，并返回模型选择信息
    """
    songs: list[Song] = []
    changed_library_mapping = False

    if payload.playlist_id is not None:
        playlist = db.query(Playlist).filter(Playlist.id == payload.playlist_id).first()
        if not playlist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")

        if playlist.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")

        ordered_relations = (
            db.query(PlaylistSong)
            .filter(PlaylistSong.playlist_id == payload.playlist_id)
            .order_by(PlaylistSong.order_index.asc())
            .all()
        )
        songs = [rel.song for rel in ordered_relations if rel.song is not None]
        logger.warning("[DJ-MIX] Loaded %d songs from playlist_id=%d", len(songs), payload.playlist_id)
    else:
        # Default to current user's own library-mapped songs only.
        library_rows = (
            db.query(LibrarySong)
            .filter(
                LibrarySong.user_id == user_id,
                LibrarySong.source_path.isnot(None),
                LibrarySong.source_path != "",
            )
            .order_by(LibrarySong.created_at.desc())
            .all()
        )
        seen_song_ids: set[int] = set()
        for lib_song in library_rows:
            audio_path = _remap_audio_path(lib_song.source_path or "")
            if not audio_path:
                continue

            song: Song | None = None
            if lib_song.song_id:
                song = db.get(Song, lib_song.song_id)

            if song is None:
                song = db.query(Song).filter(Song.title == lib_song.title, Song.artist == lib_song.artist).first()

            if song is None:
                song = Song(
                    title=lib_song.title,
                    artist=lib_song.artist,
                    audio_url=lib_song.source_path,
                    duration=lib_song.duration if lib_song.duration and lib_song.duration > 0 else None,
                )
                db.add(song)
                db.flush()

            if lib_song.song_id != song.id:
                lib_song.song_id = song.id
                changed_library_mapping = True

            if song.tags is None:
                db.add(
                    SongTag(
                        song_id=song.id,
                        bpm=int(lib_song.bpm) if lib_song.bpm else None,
                        style=payload.style,
                    )
                )
            elif not song.tags.style:
                song.tags.style = payload.style

            if song.id in seen_song_ids:
                continue
            seen_song_ids.add(song.id)
            songs.append(song)

    # Optional filters on top of owned playlist/library source
    if payload.bpm is not None:
        songs = [
            s for s in songs
            if s.tags and s.tags.bpm is not None and payload.bpm - 4 <= s.tags.bpm <= payload.bpm + 4
        ]
    if payload.energy is not None:
        token = payload.energy.lower()
        songs = [
            s for s in songs
            if s.tags and s.tags.energy and token in s.tags.energy.lower()
        ]

    # Soft style preference (do not hard filter when using explicit playlist).
    def _style_rank(song: Song) -> int:
        style = (song.tags.style if song.tags else "") or ""
        return 0 if payload.style.lower() in style.lower() else 1

    songs = sorted(
        songs,
        key=lambda s: (
            _style_rank(s),
            abs(((s.tags.bpm if s.tags and s.tags.bpm is not None else payload.bpm or 0) - (payload.bpm or 0)))
            if payload.bpm is not None else 0,
            -(s.created_at.timestamp() if s.created_at else 0),
        ),
    )

    if changed_library_mapping:
        db.commit()

    selected: list[tuple[Song, str, float]] = []
    total_seconds = 0
    target_seconds = max(payload.duration_minutes, 1) * 60
    rng = random.Random(payload.random_seed) if payload.random_seed is not None else random.Random()
    diversity = _clamp(float(payload.diversity), 0.0, 1.0)
    candidate_window = max(1, min(8, int(1 + round(diversity * 5.0))))
    pending_songs = list(songs)

    logger.warning("[DJ-MIX] Starting selection: %d candidate songs, target=%ds", len(pending_songs), target_seconds)

    while pending_songs and total_seconds < target_seconds:
        if diversity <= 0.001:
            song = pending_songs.pop(0)
        else:
            top = pending_songs[:candidate_window]
            top_weights = [1.0 / (idx + 1) for idx in range(len(top))]
            song = rng.choices(top, weights=top_weights, k=1)[0]
            pending_songs.remove(song)

        audio_path = _resolve_user_song_audio_path(db, song, user_id)
        if not audio_path:
            logger.warning("[DJ-MIX] SKIP song_id=%d (%s) - no audio_path. audio_url=%s", song.id, song.title, song.audio_url)
            continue

        duration = _resolve_user_song_duration_fast(db, song, user_id)
        if duration is None or duration <= 0:
            logger.warning("[DJ-MIX] SKIP song_id=%d (%s) - duration=%s", song.id, song.title, duration)
            continue

        logger.warning("[DJ-MIX] SELECTED song_id=%d (%s) audio=%s dur=%.1f", song.id, song.title, audio_path, duration)

        if song.duration is None or song.duration <= 0:
            song.duration = duration

        selected.append((song, audio_path, duration))
        total_seconds += int(duration)

    logger.warning("[DJ-MIX] Selection done: %d songs selected, total_seconds=%d", len(selected), total_seconds)

    playlist_data: list[PlaylistSongData] = []
    processed_files: dict[int, str] = {}
    meta: dict[int, dict[str, str]] = {}
    changed_song_audio = False
    selected_song_map = {song.id: song for song, _, _ in selected}
    selected_library_map = _library_context_map(db, payload.user_id, selected_song_map) if payload.user_id else {}

    # Batch mix must remain interactive. Heavy per-track DSP (Demucs + mastering)
    # is only allowed for very small HQ jobs; otherwise we use fast stream-copy fallback.
    allow_heavy_batch = (
        payload.quality_mode == "hq"
        and len(selected) <= 2
        and all((d or 0) <= 6 * 60 for _, _, d in selected)
    )
    logger.warning("[DJ-MIX] Processing selected songs, allow_heavy_batch=%s, quality_mode=%s", allow_heavy_batch, payload.quality_mode)

    for song, audio_path, duration in selected:
        if song.audio_url != audio_path:
            song.audio_url = audio_path
            changed_song_audio = True

        if allow_heavy_batch:
            one_song_result = process_song_for_styles(
                db,
                song.id,
                SongProcessRequest(
                    styles=[payload.style],
                    bpm=payload.bpm,
                    energy=payload.energy,
                    quality_mode=payload.quality_mode,
                ),
            )
            processed_path = one_song_result.processed_files.get(payload.style, "")
            style_meta = one_song_result.meta.get(payload.style)
            selected_models = style_meta.selected_models if style_meta else {}
        else:
            processed_path = ""
            selected_models = {
                "pipeline": "fast_stream_copy",
                "note": "batch_mix_interactive_mode",
            }

        if not processed_path or not os.path.isfile(processed_path):
            logger.warning("[DJ-MIX] Building processed fallback for song_id=%d, audio_path=%s", song.id, audio_path)
            processed_path = _build_processed_fallback(audio_path, song.id, payload.style, payload.quality_mode)
        if not processed_path or not os.path.isfile(processed_path):
            logger.warning("[DJ-MIX] SKIP processed: song_id=%d - processed_path=%s", song.id, processed_path)
            continue

        logger.warning("[DJ-MIX] OK processed: song_id=%d -> %s", song.id, processed_path)

        order_index = len(playlist_data)
        lib_context = selected_library_map.get(song.id)
        playlist_data.append(
            PlaylistSongData(
                song_id=song.id,
                library_song_id=next((ls.id for ls in db.query(LibrarySong).filter(LibrarySong.user_id == user_id, LibrarySong.song_id == song.id).all() if _remap_audio_path(ls.source_path or "")), None),
                title=song.title,
                artist=song.artist,
                audio_url=audio_path,
                duration=duration,
                bpm=song.tags.bpm if song.tags else None,
                replay_gain_db=_library_replay_gain_db(lib_context),
                loudness_lufs=_library_loudness_lufs(lib_context),
                tags=[part for part in (song.tags.style or "").split(",") if part] if song.tags else [],
                order_index=order_index,
            )
        )
        processed_files[song.id] = processed_path
        meta[song.id] = selected_models

    if changed_song_audio:
        db.commit()

    return StyleMixResult(playlist=playlist_data, processed_files=processed_files, meta=meta)


def _song_map(db: Session, song_ids: list[int]) -> dict[int, Song]:
    if not song_ids:
        return {}
    songs = db.query(Song).filter(Song.id.in_(song_ids)).all()
    return {song.id: song for song in songs}


def _library_context_map(
    db: Session,
    user_id: int,
    songs: dict[int, Song],
) -> dict[int, LibrarySong]:
    song_ids = list(songs.keys())
    if not song_ids:
        return {}
    direct_rows = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == user_id, LibrarySong.song_id.in_(song_ids))
        .order_by(LibrarySong.created_at.desc())
        .all()
    )
    out: dict[int, LibrarySong] = {}
    for row in direct_rows:
        if row.song_id and row.song_id not in out:
            out[row.song_id] = row

    for sid, song in songs.items():
        if sid in out:
            continue
        fallback = (
            db.query(LibrarySong)
            .filter(
                LibrarySong.user_id == user_id,
                LibrarySong.title == song.title,
                LibrarySong.artist == song.artist,
            )
            .order_by(LibrarySong.created_at.desc())
            .first()
        )
        if fallback:
            out[sid] = fallback
    return out


def _run_demucs_separation(audio_path: str, timeout_sec: int = 120) -> dict[str, str] | None:
    if not audio_path or not os.path.isfile(audio_path):
        return None

    stems_base = os.path.abspath(os.path.join(os.path.dirname(audio_path), "..", "stems"))
    os.makedirs(stems_base, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    stems_dir = os.path.join(stems_base, "htdemucs", base_name)
    stem_names = ["vocals", "drums", "bass", "other"]
    if all(os.path.isfile(os.path.join(stems_dir, f"{name}.wav")) for name in stem_names):
        return {name: os.path.join(stems_dir, f"{name}.wav") for name in stem_names}

    def _invoke_demucs(source_path: str) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "demucs", "-n", "htdemucs", "--segment", "7", "-o", stems_base, source_path],
                capture_output=True,
                text=True,
                timeout=max(15, int(timeout_sec)),
                check=False,
            )
            message = f"{proc.stdout}\n{proc.stderr}".strip()
            return proc.returncode == 0, message
        except Exception as exc:
            return False, str(exc)

    _invoke_demucs(audio_path)

    # Retry path-sensitive cases with an ASCII-safe temp filename.
    if not all(os.path.isfile(os.path.join(stems_dir, f"{name}.wav")) for name in stem_names):
        safe_input_dir = os.path.join(stems_base, "_inputs")
        os.makedirs(safe_input_dir, exist_ok=True)
        ext = os.path.splitext(audio_path)[1] or ".wav"
        safe_base = f"src_{sha1(audio_path.encode('utf-8', errors='ignore')).hexdigest()[:16]}"
        safe_input = os.path.join(safe_input_dir, f"{safe_base}{ext}")
        try:
            shutil.copyfile(audio_path, safe_input)
            ok2, _ = _invoke_demucs(safe_input)
            safe_stems_dir = os.path.join(stems_base, "htdemucs", safe_base)
            if ok2 and all(os.path.isfile(os.path.join(safe_stems_dir, f"{name}.wav")) for name in stem_names):
                os.makedirs(stems_dir, exist_ok=True)
                for name in stem_names:
                    shutil.copyfile(
                        os.path.join(safe_stems_dir, f"{name}.wav"),
                        os.path.join(stems_dir, f"{name}.wav"),
                    )
        except Exception:
            return None

    if not all(os.path.isfile(os.path.join(stems_dir, f"{name}.wav")) for name in stem_names):
        return None
    return {name: os.path.join(stems_dir, f"{name}.wav") for name in stem_names}


def _separate_stems_for_library_song(song: LibrarySong, timeout_sec: int = 120) -> dict[str, str] | None:
    return _run_demucs_separation(song.source_path or "", timeout_sec=timeout_sec)


def _separate_stems_for_audio_path(audio_path: str, timeout_sec: int = 120) -> dict[str, str] | None:
    return _run_demucs_separation(audio_path, timeout_sec=timeout_sec)


def _energy_bucket(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"low", "medium", "high"}:
            return v
        if v in {"explosive", "peak"}:
            return "high"
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if n < 0.34:
            return "low"
        if n < 0.67:
            return "medium"
        return "high"
    return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _feature_float(features: dict | None, *keys: str) -> float | None:
    if not isinstance(features, dict):
        return None
    for key in keys:
        value = features.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    nested = features.get("features")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _library_replay_gain_db(lib: LibrarySong | None) -> float | None:
    if not lib:
        return None
    value = _feature_float(lib.music_features, "replay_gain_db", "replayGainDb")
    if value is not None:
        return max(-12.0, min(12.0, value))
    loudness = _library_loudness_lufs(lib)
    if loudness is None:
        return None
    return max(-8.0, min(8.0, -14.0 - loudness))


def _library_loudness_lufs(lib: LibrarySong | None) -> float | None:
    if not lib:
        return None
    return _feature_float(lib.music_features, "loudness_lufs", "integrated_lufs", "lufs")


def _ranked_pick(
    ranked_candidates: list[tuple[float, int]],
    rng: random.Random,
    diversity: float,
    candidate_window: int,
) -> int:
    if not ranked_candidates:
        raise ValueError("ranked_candidates must not be empty")

    ordered = sorted(ranked_candidates, key=lambda item: item[0], reverse=True)
    if len(ordered) == 1:
        return ordered[0][1]

    div = _clamp(float(diversity), 0.0, 1.0)
    if div <= 0.001:
        return ordered[0][1]

    window = max(1, min(int(candidate_window), len(ordered)))
    top = ordered[:window]

    # More diversity -> flatter distribution among top candidates.
    rank_decay = 0.55 + (1.35 * (1.0 - div))
    weights = [1.0 / ((idx + 1) ** rank_decay) for idx, _ in enumerate(top)]
    return rng.choices([song_id for _, song_id in top], weights=weights, k=1)[0]


def generate_dj_mix_plan(db: Session, payload: DjMixPlanRequest) -> DjMixPlanResult:
    if payload.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required")

    logger.warning("[DJ-MIX-PLAN] Starting: playlist_id=%s, style=%s, duration=%s min", payload.playlist_id, payload.style, payload.duration_minutes)
    t0 = time.time()

    style_result = generate_style_mix_playlist(
        db,
        StyleMixRequest(
            style=payload.style,
            duration_minutes=payload.duration_minutes,
            bpm=payload.bpm,
            energy=payload.energy,
            playlist_id=payload.playlist_id,
            quality_mode=payload.quality_mode,
            random_seed=payload.random_seed,
            diversity=payload.diversity,
        ),
        user_id=payload.user_id,
    )

    logger.warning("[DJ-MIX-PLAN] style_mix done in %.1fs, playlist_len=%d", time.time() - t0, len(style_result.playlist))

    playlist = style_result.playlist
    if len(playlist) < 2:
        logger.warning("[DJ-MIX-PLAN] Less than 2 songs, returning early")
        return DjMixPlanResult(
            playlist=playlist,
            processed_files=style_result.processed_files,
            meta=style_result.meta,
            transition_plan=[],
        )

    # ── Build GrooveEngine TrackMetadata for each song ────────────────
    song_ids = [track.song_id for track in playlist]
    songs = _song_map(db, song_ids)
    library_map = _library_context_map(db, payload.user_id, songs)

    track_metas = []
    for item in playlist:
        lib = library_map.get(item.song_id)
        audio_path = style_result.processed_files.get(item.song_id, "")

        meta = library_song_to_track_metadata(
            song_id=item.song_id,
            title=item.title,
            artist=item.artist or "",
            duration=item.duration or (lib.duration if lib else 180.0),
            bpm=item.bpm or (lib.bpm if lib else None),
            key=lib.key if lib else None,
            camelot_key=lib.camelot_key if lib else None,
            energy=lib.energy if lib else None,
            beat_points=list(lib.beat_points) if lib and lib.beat_points else [],
            downbeats=list(lib.downbeats) if lib and lib.downbeats else [],
            phrase_map=list(lib.phrase_map) if lib and lib.phrase_map else [],
            beat_confidence=lib.beat_confidence if lib else None,
            audio_path=audio_path,
        )
        track_metas.append(meta)

    # ── Run GrooveEngine playlist planning (11-factor scoring) ────────
    logger.warning("[DJ-MIX-PLAN] Running GrooveEngine plan with %d tracks...", len(track_metas))
    t1 = time.time()
    result = run_groove_engine_plan(
        track_metas=track_metas,
        song_playlist_data={item.song_id: item for item in playlist},
        processed_files=style_result.processed_files,
        style_meta=style_result.meta,
        energy_target=payload.energy,
    )

    # ── Two-tier context planner (optional) ──────────────────────────
    if payload.use_context_planner and payload.scene_type:
        try:
            from app.modules.playlists.dj_context_planner import DJContextPlanner, SessionContext

            context = SessionContext(
                scene_type=payload.scene_type,
                style_ratios=payload.style_ratios or {},
            )
            # Build candidates from track_metas
            candidates = [
                {
                    "track_id": str(item.song_id),
                    "bpm": item.bpm or (lib.bpm if lib else 120.0),
                    "key": lib.camelot_key if lib else "",
                    "energy": lib.energy if lib else 5.0,
                    "dominant_styles": [payload.style] if payload.style else [],
                    "distance": 0.5,
                    "song_id": item.song_id,
                }
                for item in playlist
                for lib in [library_map.get(item.song_id)]
            ]

            tp = TransitionPlanner()
            context_planner = DJContextPlanner(transition_planner=tp)
            ctx_plan = context_planner.generate_plan(
                candidates=candidates,
                context=context,
                target_length=len(playlist),
                explain=True,
            )
            # Merge context planner stage report into transition items
            if ctx_plan.get("transitions"):
                for i, tr_item in enumerate(result.transition_plan):
                    if i < len(ctx_plan["transitions"]):
                        ctx_tr = ctx_plan["transitions"][i]
                        tr_item.score = max(tr_item.score, ctx_tr.get("score", 0.0))
                        tr_item.transition_technique = ctx_tr.get("strategy", tr_item.transition_technique)

            logger.warning(
                "[DJ-MIX-PLAN] Two-tier context planner: scene=%s, ordered=%d, stages=%d",
                payload.scene_type,
                len(ctx_plan.get("ordered_tracks", [])),
                len(ctx_plan.get("stage_report", [])),
            )
        except Exception:
            logger.exception("[DJ-MIX-PLAN] Two-tier context planner failed, using GrooveEngine-only result")

    logger.warning("[DJ-MIX-PLAN] GrooveEngine done in %.1fs, final playlist=%d, transitions=%d", time.time() - t1, len(result.playlist), len(result.transition_plan))
    return result


def generate_dj_offline_mix(db: Session, payload: DjOfflineMixRequest) -> DjOfflineMixResult:
    if payload.user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required")

    mix_plan = generate_dj_mix_plan(
        db,
        DjMixPlanRequest(
            style=payload.style,
            duration_minutes=payload.duration_minutes,
            bpm=payload.bpm,
            energy=payload.energy,
            playlist_id=payload.playlist_id,
            quality_mode=payload.quality_mode,
            strict_harmonic=payload.strict_harmonic,
            max_tempo_shift=payload.max_tempo_shift,
            random_seed=payload.random_seed,
            diversity=payload.diversity,
            candidate_window=payload.candidate_window,
            user_id=payload.user_id,
        ),
    )

    if not mix_plan.playlist:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no track available for offline mix")

    songs = _song_map(db, [item.song_id for item in mix_plan.playlist])
    library_map = _library_context_map(db, payload.user_id, songs)
    transition_lookup = {(item.from_song_id, item.to_song_id): item for item in mix_plan.transition_plan}

    render_track_candidates: list[dict[str, object]] = []
    warnings: list[str] = []
    library_updated = False
    missing_audio_song_ids: list[int] = []
    missing_stem_song_ids: list[int] = []
    auto_stem_failed_song_ids: list[int] = []
    auto_stem_skipped_by_limit_song_ids: list[int] = []
    auto_stem_attempts = 0
    auto_stem_limit = max(0, int(payload.max_auto_stem_tracks))
    auto_stem_timeout = max(15, int(payload.stem_separation_timeout_sec))

    for item in mix_plan.playlist:
        song = songs.get(item.song_id)
        if not song:
            continue

        audio_path = mix_plan.processed_files.get(item.song_id, "")
        if not audio_path or not os.path.isfile(audio_path):
            resolved = _resolve_user_song_audio_path(db, song, payload.user_id)
            audio_path = resolved or ""
        if not audio_path or not os.path.isfile(audio_path):
            missing_audio_song_ids.append(item.song_id)
            continue

        lib = library_map.get(item.song_id)
        stem_paths: dict[str, str] | None = None
        if payload.stem_aware and lib and lib.stems:
            existing = {
                k: v
                for k, v in lib.stems.items()
                if isinstance(k, str) and isinstance(v, str) and os.path.isfile(v)
            }
            if len(existing) >= 2:
                stem_paths = existing

        if payload.stem_aware and payload.auto_separate_stems and not stem_paths:
            if auto_stem_attempts >= auto_stem_limit:
                auto_stem_skipped_by_limit_song_ids.append(item.song_id)
                missing_stem_song_ids.append(item.song_id)
                render_track_candidates.append(
                    {
                        "song_id": item.song_id,
                        "audio_path": audio_path,
                        "stems": stem_paths,
                    }
                )
                continue

            generated: dict[str, str] | None = None
            auto_stem_attempts += 1
            if lib:
                generated = _separate_stems_for_library_song(lib, timeout_sec=auto_stem_timeout)
                if generated:
                    lib.stems = generated
                    library_updated = True
            if not generated:
                generated = _separate_stems_for_audio_path(audio_path, timeout_sec=auto_stem_timeout)

            if generated:
                stem_paths = generated
            else:
                auto_stem_failed_song_ids.append(item.song_id)

        if payload.stem_aware and not stem_paths:
            missing_stem_song_ids.append(item.song_id)

        render_track_candidates.append(
            {
                "song_id": item.song_id,
                "audio_path": audio_path,
                "stems": stem_paths,
            }
        )

    if library_updated:
        db.commit()

    if not render_track_candidates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="offline mix failed: no usable tracks")

    if missing_audio_song_ids:
        show = ",".join(str(sid) for sid in missing_audio_song_ids[:12])
        tail = f" (+{len(missing_audio_song_ids) - 12})" if len(missing_audio_song_ids) > 12 else ""
        warnings.append(
            f"{len(missing_audio_song_ids)} songs missing decodable audio and were skipped: {show}{tail}"
        )
    if payload.stem_aware and missing_stem_song_ids:
        show = ",".join(str(sid) for sid in missing_stem_song_ids[:12])
        tail = f" (+{len(missing_stem_song_ids) - 12})" if len(missing_stem_song_ids) > 12 else ""
        warnings.append(
            f"{len(missing_stem_song_ids)} songs without usable stems, fallback to normal crossfade: {show}{tail}"
        )
    if payload.stem_aware and payload.auto_separate_stems and auto_stem_failed_song_ids:
        warnings.append(
            f"auto stem separation failed for {len(auto_stem_failed_song_ids)} songs (demucs unavailable or failed)"
        )
    if payload.stem_aware and payload.auto_separate_stems and auto_stem_skipped_by_limit_song_ids:
        warnings.append(
            f"auto stem separation limit reached ({auto_stem_limit}); skipped {len(auto_stem_skipped_by_limit_song_ids)} songs"
        )

    render_tracks: list[OfflineRenderTrackInput] = []
    render_transitions: list[DjTransitionPlanItem] = []
    for i, candidate in enumerate(render_track_candidates):
        song_id = int(candidate["song_id"])  # type: ignore[arg-type]
        audio_path = str(candidate["audio_path"])
        stems = candidate.get("stems")
        entry_time = 0.0

        if i > 0:
            prev_song_id = int(render_track_candidates[i - 1]["song_id"])  # type: ignore[arg-type]
            pair_transition = transition_lookup.get((prev_song_id, song_id))
            if pair_transition and pair_transition.entry_time_sec is not None:
                entry_time = max(0.0, float(pair_transition.entry_time_sec))
            if pair_transition:
                render_transitions.append(pair_transition)

        render_tracks.append(
            OfflineRenderTrackInput(
                song_id=song_id,
                audio_path=audio_path,
                entry_time_sec=entry_time,
                stems=stems if isinstance(stems, dict) else None,
            )
        )

    safe_output_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", (payload.output_name or "final_mix")).strip("_")
    if not safe_output_name:
        safe_output_name = "final_mix"

    suffix = int(time.time())
    base_filename = f"{safe_output_name}_{payload.user_id}_{suffix}"
    out_dir = os.path.join("data", "music-files", "shared", "mixes")
    os.makedirs(out_dir, exist_ok=True)
    wav_filename = f"{base_filename}.wav"
    wav_path = os.path.join(out_dir, wav_filename)

    render_meta = render_offline_mix(
        tracks=render_tracks,
        transitions=render_transitions,
        output_wav_path=wav_path,
        sample_rate=44100,
        stem_aware=payload.stem_aware,
    )

    output_files: dict[str, str] = {"wav": wav_path.replace("\\", "/")}
    stream_files: dict[str, str] = {"wav": wav_filename}

    if payload.output_format in {"mp3", "both"}:
        mp3_filename = f"{base_filename}.mp3"
        mp3_path = os.path.join(out_dir, mp3_filename)
        ok, msg = convert_wav_to_mp3(wav_path, mp3_path)
        if ok:
            output_files["mp3"] = mp3_path.replace("\\", "/")
            stream_files["mp3"] = mp3_filename
        elif msg:
            if payload.output_format == "both":
                warnings.append("mp3 unavailable on current ffmpeg build; wav exported successfully")
            else:
                warnings.append(msg)
            if payload.output_format == "mp3":
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=msg)

    return DjOfflineMixResult(
        mix_plan=mix_plan,
        output_files=output_files,
        stream_files=stream_files,
        warnings=warnings,
        stem_rule_events=render_meta.get("stem_rule_events", []),
        sample_rate=int(render_meta.get("sample_rate", 44100)),
        duration_sec=float(render_meta.get("duration_sec", 0.0)),
    )


def reorder_playlist_songs(
    db: Session,
    playlist_id: int,
    user_id: int,
    payload: PlaylistReorderRequest,
) -> None:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    if playlist.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")

    relations = db.query(PlaylistSong).filter(PlaylistSong.playlist_id == playlist_id).all()
    relation_by_song_id = {relation.song_id: relation for relation in relations}

    if len(payload.songs) != len(relations):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reorder payload must include every playlist song",
        )

    incoming_song_ids = {item.song_id for item in payload.songs}
    existing_song_ids = set(relation_by_song_id.keys())
    if incoming_song_ids != existing_song_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reorder payload song ids do not match playlist songs",
        )

    used_indexes = set()
    for item in payload.songs:
        if item.order_index in used_indexes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="duplicate order_index in reorder payload",
            )
        used_indexes.add(item.order_index)
        relation_by_song_id[item.song_id].order_index = item.order_index

    db.commit()


def _remap_audio_path(path: str) -> str | None:
    """Remap legacy Docker paths (/app/...) to the current working directory."""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    if path.startswith("/app/"):
        remapped = os.path.join(os.getcwd(), path[len("/app/"):])
        if os.path.isfile(remapped):
            return remapped
    return None


def _resolve_user_song_audio_path(db: Session, song: Song, user_id: int) -> str | None:
    resolved = _remap_audio_path(song.audio_url or "")
    if resolved:
        return resolved

    by_song_id = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.song_id == song.id,
            LibrarySong.source_path.isnot(None),
            LibrarySong.source_path != "",
        )
        .order_by(LibrarySong.created_at.desc())
        .all()
    )
    for item in by_song_id:
        resolved = _remap_audio_path(item.source_path or "")
        if resolved:
            return resolved

    by_title_artist = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.title == song.title,
            LibrarySong.artist == song.artist,
            LibrarySong.source_path.isnot(None),
            LibrarySong.source_path != "",
        )
        .order_by(LibrarySong.created_at.desc())
        .all()
    )
    for item in by_title_artist:
        resolved = _remap_audio_path(item.source_path or "")
        if resolved:
            return resolved

    return None


def _resolve_user_song_duration(db: Session, song: Song, user_id: int, audio_path: str) -> float | None:
    if song.duration and song.duration > 0:
        return float(song.duration)

    by_song_id = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.song_id == song.id,
            LibrarySong.duration.isnot(None),
            LibrarySong.duration > 0,
        )
        .order_by(LibrarySong.created_at.desc())
        .first()
    )
    if by_song_id and by_song_id.duration and by_song_id.duration > 0:
        return float(by_song_id.duration)

    by_title_artist = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.title == song.title,
            LibrarySong.artist == song.artist,
            LibrarySong.duration.isnot(None),
            LibrarySong.duration > 0,
        )
        .order_by(LibrarySong.created_at.desc())
        .first()
    )
    if by_title_artist and by_title_artist.duration and by_title_artist.duration > 0:
        return float(by_title_artist.duration)

    try:
        import librosa  # type: ignore

        guessed = float(librosa.get_duration(path=audio_path))
        if guessed > 0:
            return guessed
    except Exception:
        pass

    return None


def _resolve_user_song_duration_fast(db: Session, song: Song, user_id: int) -> float:
    if song.duration and song.duration > 0:
        return float(song.duration)
    by_song_id = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.song_id == song.id,
            LibrarySong.duration.isnot(None),
            LibrarySong.duration > 0,
        )
        .order_by(LibrarySong.created_at.desc())
        .first()
    )
    if by_song_id and by_song_id.duration and by_song_id.duration > 0:
        return float(by_song_id.duration)

    by_title_artist = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == user_id,
            LibrarySong.title == song.title,
            LibrarySong.artist == song.artist,
            LibrarySong.duration.isnot(None),
            LibrarySong.duration > 0,
        )
        .order_by(LibrarySong.created_at.desc())
        .first()
    )
    if by_title_artist and by_title_artist.duration and by_title_artist.duration > 0:
        return float(by_title_artist.duration)
    # Interactive fallback: avoid expensive file probing.
    return 180.0


def _build_processed_fallback(audio_path: str, song_id: int, style: str, quality_mode: str) -> str | None:
    """Return the original audio path directly — no file copying.

    Previously this copied audio into shared/processed/ which created duplicate
    files that were then picked up by the dev scanner as spurious library entries
    (e.g. "13 hiphop fast raw"). The caller already has access to the source
    file and the processed/ cache is unused during online playback.
    """
    if not audio_path or not os.path.isfile(audio_path):
        return None
    return audio_path.replace("\\", "/")
