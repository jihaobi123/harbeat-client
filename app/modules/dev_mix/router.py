from __future__ import annotations

import math
import os
import wave
from hashlib import sha1
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.playlists.schemas import (
    DjMixPlanRequest,
    DjMixPlanResult,
    DjTransitionPlanItem,
    MixControlTimeline,
    OnlineMixSafety,
    PlaylistSongData,
)
from app.modules.playlists.service import generate_dj_mix_plan, get_playlist_detail
from app.modules.stream.router import CONTENT_TYPES, _range_response
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


class DevPlanRequest(BaseModel):
    style: str = "hiphop"
    duration_minutes: int = Field(default=10, ge=1, le=120)
    quality_mode: Literal["balanced", "hq", "fast"] = "fast"
    random_seed: int | None = None
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    candidate_window: int = Field(default=4, ge=1, le=8)
    max_tracks: int = Field(default=8, ge=2, le=32)
    song_ids: list[int] | None = None


class DevSongItem(BaseModel):
    library_song_id: str
    song_id: int
    title: str
    artist: str
    duration: float
    bpm: float | None = None
    key: str | None = None
    camelot_key: str | None = None
    energy: float | None = None
    analysis_status: str | None = None
    stream_url: str


class DevSongList(BaseModel):
    user_id: int
    songs: list[DevSongItem]


def _ensure_dev_user(db: Session) -> User:
    user = db.query(User).filter(User.username == "dev_mix").first()
    if user:
        return user
    user = User(
        username="dev_mix",
        password_hash=None,
        role="user",
        status="active",
        dance_style="hiphop",
        level="dev",
        favorite_style="hiphop",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _remap_existing_path(path: str) -> str:
    if path and os.path.isfile(path):
        return path
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    marker = "data/music-files/"
    if marker in normalized:
        rel = normalized.split(marker, 1)[1]
        root = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "data", "music-files")
        )
        candidate = os.path.normpath(os.path.join(root, rel))
        if os.path.isfile(candidate):
            return candidate
    return ""


def _audio_duration(path: str) -> float:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as fh:
                frames = fh.getnframes()
                rate = fh.getframerate() or 44100
                return max(1.0, frames / float(rate))
        except Exception:
            return 180.0
    return 180.0


def _guess_bpm(title: str) -> float | None:
    import re
    m = re.search(r"(\d{2,3})\s*bpm", title.lower())
    if m:
        return float(m.group(1))
    return None


def _guess_bpm_or_default(title: str, fallback: float = 120.0) -> float:
    """Extract BPM from filename or return a usable default.

    Real music files rarely have BPM in their names, so we return a safe
    fallback rather than None so the song isn't invisible in the library.
    The actual BPM will be filled in once the analysis pipeline runs.
    """
    bpm = _guess_bpm(title)
    return bpm if bpm is not None else fallback


def _scan_local_audio_files() -> list[str]:
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    candidates = [
        os.path.normpath(os.path.join(root, "..", "GrooveEngine", "music")),
    ]
    exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
    out: list[str] = []
    for base in candidates:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in {"stems", "node_modules", ".venv", "__pycache__", "processed", "cache"}]
            for name in filenames:
                if os.path.splitext(name)[1].lower() in exts:
                    out.append(os.path.join(dirpath, name))
    return sorted(dict.fromkeys(out))


def _ensure_scanned_library(db: Session, user_id: int, limit: int) -> None:
    existing_paths = {os.path.normcase(row.source_path or "") for row in db.query(LibrarySong).all()}
    for path in _scan_local_audio_files()[:limit]:
        if os.path.normcase(path) in existing_paths:
            continue
        # Hard guard: never allow shared/processed or shared/cache paths
        norm = path.replace("\\", "/").lower()
        if "/shared/processed/" in norm or "/shared/cache/" in norm:
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        fmt = os.path.splitext(path)[1].lstrip(".").lower() or "wav"
        duration = _audio_duration(path)
        bpm = _guess_bpm_or_default(base)
        has_real_bpm = _guess_bpm(base) is not None
        lib = LibrarySong(
            id="dev_" + sha1(path.encode("utf-8", errors="ignore")).hexdigest()[:16],
            user_id=user_id,
            song_id=None,
            title=base.replace("_", " "),
            artist="Local File",
            duration=duration,
            format=fmt,
            file_size=os.path.getsize(path),
            source_type="local_dev_scan",
            source_path=path,
            bpm=bpm,
            key=None,
            camelot_key=None,
            energy=0.5,
            analysis_status="analyzed" if has_real_bpm else "pending",
        )
        db.add(lib)
        _ensure_catalog_song(db, lib)
    db.commit()


def _library_rows(db: Session, user_id: int, limit: int) -> list[LibrarySong]:
    _ensure_scanned_library(db, user_id, limit)
    rows = (
        db.query(LibrarySong)
        .filter(LibrarySong.source_path.isnot(None), LibrarySong.source_path != "")
        .order_by(LibrarySong.analysis_status.desc(), LibrarySong.created_at.desc())
        .all()
    )
    usable: list[LibrarySong] = []
    for row in rows:
        path = _remap_existing_path(row.source_path or "")
        if not path:
            continue
        if row.source_path != path:
            row.source_path = path
        if row.user_id != user_id:
            row.user_id = user_id
        _ensure_catalog_song(db, row)
        usable.append(row)
        if len(usable) >= limit:
            break
    if usable:
        db.commit()
    return usable


def _ensure_catalog_song(db: Session, lib: LibrarySong) -> Song:
    song = db.get(Song, lib.song_id) if lib.song_id else None
    if song is None:
        song = db.query(Song).filter(Song.title == lib.title, Song.artist == lib.artist).first()
    if song is None:
        song = Song(title=lib.title, artist=lib.artist, audio_url=lib.source_path, duration=lib.duration or None)
        db.add(song)
        db.flush()
    if lib.song_id != song.id:
        lib.song_id = song.id
    if song.audio_url != lib.source_path:
        song.audio_url = lib.source_path
    if song.duration is None or song.duration <= 0:
        song.duration = lib.duration or None
    if song.tags is None:
        song.tags = SongTag(
            song_id=song.id,
            bpm=int(lib.bpm) if lib.bpm else None,
            energy=_energy_label(lib.energy),
            style="hiphop",
        )
        db.add(song.tags)
    else:
        if lib.bpm and not song.tags.bpm:
            song.tags.bpm = int(lib.bpm)
        if not song.tags.style:
            song.tags.style = "hiphop"
        if lib.energy is not None and not song.tags.energy:
            song.tags.energy = _energy_label(lib.energy)
    return song


def _energy_label(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "medium"
    return "high"


def _song_item(row: LibrarySong) -> DevSongItem:
    return DevSongItem(
        library_song_id=row.id,
        song_id=int(row.song_id or 0),
        title=row.title,
        artist=row.artist,
        duration=float(row.duration or 0),
        bpm=row.bpm,
        key=row.key,
        camelot_key=row.camelot_key,
        energy=row.energy,
        analysis_status=row.analysis_status,
        stream_url=f"/api/dev/songs/{row.id}/stream",
    )



def _camelot_distance(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 6
    try:
        na, ma = int(a[:-1]), a[-1]
        nb, mb = int(b[:-1]), b[-1]
    except Exception:
        return 6
    if na == nb and ma == mb:
        return 0
    ring = min(abs(na - nb), 12 - abs(na - nb))
    if ma != mb:
        ring += 1
    return min(6, ring)


def _real_music_rows(db: Session, user_id: int, limit: int) -> list[LibrarySong]:
    _ensure_scanned_library(db, user_id, max(limit, 32))
    marker = os.path.normcase(os.path.normpath(r"D:\harbeat\GrooveEngine\music"))
    rows = db.query(LibrarySong).filter(LibrarySong.source_path.isnot(None), LibrarySong.source_path != "").all()
    usable = []
    for row in rows:
        path = _remap_existing_path(row.source_path or "")
        if not path:
            continue
        if not os.path.normcase(os.path.normpath(path)).startswith(marker):
            continue
        if row.user_id != user_id:
            row.user_id = user_id
        _ensure_catalog_song(db, row)
        if row.song_id and row.duration and row.duration > 2:
            usable.append(row)
    usable.sort(key=lambda r: (float(r.bpm or 0), _camelot_distance("8A", r.camelot_key)))
    db.commit()
    return usable[:limit]


def _mixtape_order(rows: list[LibrarySong]) -> list[LibrarySong]:
    if len(rows) <= 2:
        return rows
    remaining = sorted(rows, key=lambda r: float(r.bpm or 0))
    ordered = [remaining.pop(0)]
    while remaining:
        cur = ordered[-1]
        cur_bpm = float(cur.bpm or 120)
        def score(row: LibrarySong) -> float:
            bpm = float(row.bpm or 120)
            tempo = abs(math.log2(max(bpm, 1) / max(cur_bpm, 1))) * 100.0
            harmonic = _camelot_distance(cur.camelot_key, row.camelot_key) * 4.0
            energy = abs(float(cur.energy or 0.5) - float(row.energy or 0.5)) * 8.0
            return tempo + harmonic + energy
        nxt = min(remaining, key=score)
        remaining.remove(nxt)
        ordered.append(nxt)
    return ordered


def _nearest_grid_time(times: list[float], target: float, duration: float, lower: float = 0.0) -> float:
    valid = [float(t) for t in times if lower <= float(t) <= duration - 1.0]
    if not valid:
        return max(lower, min(target, duration - 1.0))
    return min(valid, key=lambda t: abs(t - target))


def _choose_exit_time(row: LibrarySong) -> float:
    """Pick the auto-transition exit point 5-8s before the track ends."""
    duration = float(row.duration or 180.0)
    phrase_candidates: list[float] = []
    for phrase in row.phrase_map or []:
        end = float(phrase.get("end", 0) or 0)
        label = str(phrase.get("label", "")).lower()
        # Prefer phrase ends within 4-16s of the track end
        if duration - 16.0 <= end <= duration - 3.0 and label not in {"intro"}:
            phrase_candidates.append(end)
    # Target: 6.5s before end (middle of 5-8s window)
    target = max(8.0, duration - 6.5)
    if phrase_candidates:
        target = min(phrase_candidates, key=lambda t: abs(t - target))
    grid = list(row.downbeats or row.beat_points or [])
    return round(_nearest_grid_time(grid, target, duration, lower=max(8.0, duration - 16.0)), 3)


def _choose_entry_time(row: LibrarySong) -> float:
    duration = float(row.duration or 180.0)
    preferred: list[float] = []
    for phrase in row.phrase_map or []:
        start = float(phrase.get("start", 0) or 0)
        label = str(phrase.get("label", "")).lower()
        if 0 <= start <= min(24.0, duration * 0.2) and label in {"intro", "verse", "drop", "buildup"}:
            preferred.append(start)
    target = preferred[0] if preferred else 0.0
    grid = list(row.downbeats or row.beat_points or [])
    return round(_nearest_grid_time(grid, target, duration, lower=0.0), 3)


def _smooth_crossfade_sec(from_row: LibrarySong, to_row: LibrarySong) -> float:
    a = float(from_row.bpm or 120)
    b = float(to_row.bpm or 120)
    tempo_delta = abs(math.log2(max(a, 1) / max(b, 1)))
    key_dist = _camelot_distance(from_row.camelot_key, to_row.camelot_key)
    if tempo_delta <= 0.045 and key_dist <= 2:
        return 8.0
    if tempo_delta <= 0.08 and key_dist <= 4:
        return 7.0
    if tempo_delta <= 0.14:
        return 6.0
    return 5.0


def _playlist_item(row: LibrarySong, index: int) -> PlaylistSongData:
    return PlaylistSongData(
        song_id=int(row.song_id or 0),
        library_song_id=row.id,
        title=row.title,
        artist=row.artist,
        audio_url=row.source_path,
        duration=float(row.duration or 0),
        bpm=row.bpm,
        key=row.key,
        energy=row.energy,
        format=row.format,
        analysis_status=row.analysis_status,
        tags=["pop", "hiphop"],
        order_index=index,
    )


def _build_mixtape_plan(rows: list[LibrarySong]) -> DjMixPlanResult:
    ordered = _mixtape_order(rows)
    playlist = [_playlist_item(row, idx) for idx, row in enumerate(ordered)]
    transitions: list[DjTransitionPlanItem] = []
    for idx in range(len(ordered) - 1):
        a = ordered[idx]
        b = ordered[idx + 1]
        crossfade = _smooth_crossfade_sec(a, b)
        exit_time = _choose_exit_time(a)
        entry_time = _choose_entry_time(b)
        from_bpm = float(a.bpm or 120)
        to_bpm = float(b.bpm or 120)
        raw_rate = from_bpm / to_bpm if to_bpm > 0 else 1.0
        rate = max(0.96, min(1.04, raw_rate))
        beat_a = 60.0 / from_bpm if from_bpm > 0 else 0.5
        beat_b = 60.0 / to_bpm if to_bpm > 0 else 0.5
        item = DjTransitionPlanItem(
            from_song_id=int(a.song_id or 0),
            to_song_id=int(b.song_id or 0),
            entry_beat=1,
            exit_beat=1,
            entry_time_sec=entry_time,
            exit_time_sec=exit_time,
            from_beat_interval_sec=round(beat_a, 4),
            to_beat_interval_sec=round(beat_b, 4),
            phase_anchor_sec=round(max(0.0, exit_time - crossfade), 3),
            crossfade_sec=round(crossfade, 3),
            tempo_ratio=round(rate, 4),
            key_relation="smooth" if _camelot_distance(a.camelot_key, b.camelot_key) <= 2 else "managed",
            transition_technique="clean_blend",
            energy_target="medium",
            fx_automation=[],
            score=round(1.0 / (1.0 + abs(raw_rate - 1.0) * 4.0 + _camelot_distance(a.camelot_key, b.camelot_key) * 0.25), 4),
        )
        transitions.append(item)
    return _attach_online_timeline(DjMixPlanResult(
        playlist=playlist,
        processed_files={},
        meta={int(row.song_id or 0): {"pipeline": "online_stream", "note": "real_music_mixtape"} for row in ordered},
        transition_plan=transitions,
    ))

def _attach_online_timeline(plan: DjMixPlanResult) -> DjMixPlanResult:
    by_song = {item.song_id: item for item in plan.playlist}
    for idx, tr in enumerate(plan.transition_plan):
        from_track = by_song.get(tr.from_song_id)
        to_track = by_song.get(tr.to_song_id)
        if not from_track or not to_track:
            continue
        crossfade = max(4.0, min(10.0, float(tr.crossfade_sec or 6.5)))
        from_duration = float(from_track.duration or 180.0)
        start_at = tr.exit_time_sec if tr.exit_time_sec is not None else max(0.0, from_duration - crossfade - 2.0)
        start_at = max(0.0, min(start_at, max(0.0, from_duration - crossfade)))
        entry = max(0.0, float(tr.entry_time_sec or 0.0))
        rate = max(0.85, min(1.15, float(tr.tempo_ratio or 1.0)))
        tr.online_mix_safety = OnlineMixSafety(
            online_mix_safe=True,
            recommended_mode="normal_crossfade",
            fallback_mode="short_fade",
            min_prepare_sec=8.0,
            preload_before_sec=8.0,
            reasons=[],
        )
        tr.mix_control_timeline = MixControlTimeline(
            transition_id=f"dev-transition-{idx}",
            mode="normal_crossfade",
            start_at_from_time_sec=round(start_at, 3),
            duration_sec=round(crossfade, 3),
            events=[
                {"type": "deck_load", "deck": "B", "time_sec": -8.0, "song_id": tr.to_song_id, "position_sec": entry},
                {"type": "param_set", "deck": "A", "time_sec": -0.02, "param": "gain", "value": 1.0},
                {"type": "param_set", "deck": "B", "time_sec": -0.02, "param": "gain", "value": 0.0},
                {"type": "deck_play", "deck": "B", "time_sec": 0.0, "position_sec": entry, "playback_rate": rate, "key_lock": False},
                {"type": "param_ramp", "deck": "A", "time_sec": 0.0, "duration_sec": crossfade, "param": "gain", "from": 1.0, "to": 0.0, "curve": "equal_power_out"},
                {"type": "param_ramp", "deck": "B", "time_sec": 0.0, "duration_sec": crossfade, "param": "gain", "from": 0.0, "to": 1.0, "curve": "equal_power_in"},
                {"type": "param_ramp", "deck": "A", "time_sec": 0.0, "duration_sec": crossfade, "param": "low_eq", "from": 1.0, "to": 0.35, "curve": "ease_in_out"},
                {"type": "param_ramp", "deck": "B", "time_sec": 0.0, "duration_sec": crossfade, "param": "low_eq", "from": 0.45, "to": 1.0, "curve": "ease_in_out"},
                {"type": "param_ramp", "deck": "A", "time_sec": 0.0, "duration_sec": crossfade, "param": "highpass_hz", "from": 20.0, "to": 220.0, "curve": "ease_in_out"},
                {"type": "param_ramp", "deck": "B", "time_sec": 0.0, "duration_sec": crossfade, "param": "lowpass_hz", "from": 8000.0, "to": 20000.0, "curve": "ease_in_out"},
                {"type": "deck_stop", "deck": "A", "time_sec": crossfade + 0.1},
            ],
        )
    return plan


@router.get("/songs", response_model=APIResponse[DevSongList])
def list_dev_songs(limit: int = Query(24, ge=2, le=100), db: Session = Depends(get_db)):
    user = _ensure_dev_user(db)
    rows = _real_music_rows(db, user.id, limit)
    return APIResponse(data=DevSongList(user_id=user.id, songs=[_song_item(row) for row in rows if row.song_id]))


@router.post("/mix-plan", response_model=APIResponse[DjMixPlanResult])
def generate_dev_mix_plan(payload: DevPlanRequest, db: Session = Depends(get_db)):
    user = _ensure_dev_user(db)
    rows = _real_music_rows(db, user.id, max(payload.max_tracks, 2))
    if len(rows) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="need at least 2 analyzed GrooveEngine music songs")

    if payload.song_ids:
        id_set = {int(sid) for sid in payload.song_ids[: payload.max_tracks]}
        rows = [row for row in rows if row.song_id in id_set]
        if len(rows) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selected song_ids must map to at least 2 analyzed GrooveEngine music songs")

    plan = _build_mixtape_plan(rows[: payload.max_tracks])
    return APIResponse(data=plan)


@router.get("/songs/{library_song_id}/stream")
def stream_dev_song(library_song_id: str, request: Request, db: Session = Depends(get_db)):
    song = db.get(LibrarySong, library_song_id)
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="song not found")
    file_path = _remap_existing_path(song.source_path or "")
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="audio file not found on disk")
    file_size = os.path.getsize(file_path)
    fmt = (song.format or os.path.splitext(file_path)[1].lstrip(".")).lower().lstrip(".")
    content_type = CONTENT_TYPES.get(fmt, "application/octet-stream")
    return _range_response(file_path, file_size, content_type, request)
