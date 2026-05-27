"""DJ Control router — exposes dance-style recommendation, energy sequencing,
mixing rules, live cut planning, and FX synthesis under /api/dj.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import User
from app.modules.dj_control import cut_strategy, dance_style, fx_synth, mixer_rules, sequencer, vibe_search
from app.modules.dj_control.energy_hiphop import compute_dance_energy
from app.modules.dj_control.schemas import (
    CutPlanRequest,
    FxItem,
    FxListResponse,
    ScoredSong,
    SequenceEntry,
    SequenceRequest,
    SequenceResponse,
    StyleListResponse,
    StylePickRequest,
    StylePickResponse,
    TransitionPlanRequest,
)
from app.modules.library.models import LibrarySong
from app.shared.database import get_db
from app.shared.responses import APIResponse


router = APIRouter()


# --------------------------------------------------------------------------- #
# Dance styles
# --------------------------------------------------------------------------- #
@router.get("/styles", response_model=APIResponse[StyleListResponse])
def list_styles_endpoint():
    return APIResponse(data=StyleListResponse(styles=dance_style.list_styles()))


@router.post("/styles/pick", response_model=APIResponse[StylePickResponse])
def pick_by_style_endpoint(
    payload: StylePickRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.style not in dance_style.STYLE_PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown style: {payload.style}")
    songs = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .all()
    )
    picks = dance_style.pick_songs_for_duration(
        songs,
        style_key=payload.style,
        target_seconds=payload.target_duration_sec,
        min_score=payload.min_score,
    )
    achieved = sum(float(s.duration or 0) for s, _ in picks)
    return APIResponse(data=StylePickResponse(
        style=payload.style,
        target_duration_sec=payload.target_duration_sec,
        achieved_duration_sec=achieved,
        songs=[
            ScoredSong(
                song_id=s.id,
                title=s.title,
                artist=s.artist,
                bpm=s.bpm,
                duration=s.duration,
                score=score,
                energy=(s.energy if s.energy is not None else None),
            )
            for s, score in picks
        ],
    ))


# --------------------------------------------------------------------------- #
# Energy-based sequencing
# --------------------------------------------------------------------------- #
@router.get("/sequence/presets")
def list_sequence_presets():
    return APIResponse(data={
        "presets": sequencer.PRESETS,
        "meta": sequencer.list_presets(),
    })


@router.post("/sequence", response_model=APIResponse[SequenceResponse])
def sequence_endpoint(
    payload: SequenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.preset not in sequencer.PRESETS:
        raise HTTPException(status_code=400, detail=f"unknown preset: {payload.preset}")
    songs_by_id = {
        s.id: s
        for s in db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .filter(LibrarySong.id.in_(payload.song_ids))
        .all()
    }
    ordered_songs = [songs_by_id[sid] for sid in payload.song_ids if sid in songs_by_id]
    if not ordered_songs:
        raise HTTPException(status_code=400, detail="no matching songs")
    seq = sequencer.sequence_songs(ordered_songs, preset=payload.preset)
    return APIResponse(data=SequenceResponse(
        preset=payload.preset,
        sequence=[SequenceEntry(**e) for e in seq],
    ))


@router.get("/songs/{song_id}/energy")
def energy_breakdown_endpoint(
    song_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    song = db.get(LibrarySong, song_id)
    if not song or song.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song not found")
    eb = compute_dance_energy(song)
    return APIResponse(data=eb.as_dict())


# --------------------------------------------------------------------------- #
# Mixing rules
# --------------------------------------------------------------------------- #
@router.get("/transitions/rules")
def list_transition_rules_endpoint():
    return APIResponse(data=mixer_rules.list_transition_rules())


@router.post("/transitions/plan")
def plan_transition_endpoint(
    payload: TransitionPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prev = db.get(LibrarySong, payload.prev_song_id)
    nxt = db.get(LibrarySong, payload.next_song_id)
    if not prev or not nxt or prev.user_id != current_user.id or nxt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song(s) not found")
    spec = mixer_rules.build_transition_spec(prev, nxt, payload.cursor_sec, payload.rule_key)
    return APIResponse(data=spec)


# --------------------------------------------------------------------------- #
# Live cut strategies
# --------------------------------------------------------------------------- #
@router.post("/cut/plan")
def plan_cut_endpoint(
    payload: CutPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.strategy not in ("fast_cut", "energy_up_cut", "energy_down_cut"):
        raise HTTPException(status_code=400, detail=f"unknown strategy: {payload.strategy}")
    current = db.get(LibrarySong, payload.current_song_id)
    if not current or current.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="current song not found")
    all_ids = set(payload.queue_song_ids) | set(payload.pool_song_ids)
    songs_by_id = {
        s.id: s
        for s in db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .filter(LibrarySong.id.in_(all_ids))
        .all()
    } if all_ids else {}
    queue = [songs_by_id[sid] for sid in payload.queue_song_ids if sid in songs_by_id]
    pool = [songs_by_id[sid] for sid in payload.pool_song_ids if sid in songs_by_id]
    plan = cut_strategy.plan_cut(
        strategy=payload.strategy,
        current_song=current,
        cursor_sec=payload.cursor_sec,
        queue=queue,
        current_index=payload.current_index,
        pool=pool,
        max_wait_sec=payload.max_wait_sec,
    )
    return APIResponse(data=plan)


# --------------------------------------------------------------------------- #
# Vibe search — free-form text → ranked songs
# --------------------------------------------------------------------------- #
from pydantic import BaseModel


class VibeSearchRequest(BaseModel):
    query: str
    target_duration_sec: float | None = None
    fill_duration: bool = False
    limit: int = 50


@router.post("/vibe/search")
def vibe_search_endpoint(
    payload: VibeSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    songs = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .all()
    )
    matches = vibe_search.score_songs(songs, payload.query)
    if payload.fill_duration and payload.target_duration_sec:
        matches = vibe_search.fill_to_duration(matches, payload.target_duration_sec)
    else:
        matches = matches[: max(1, payload.limit)]
    total_dur = sum(float(m.song.duration or 0) for m in matches)
    return APIResponse(data={
        "query": payload.query,
        "total_duration_sec": total_dur,
        "songs": [
            {
                "song_id": m.song.id,
                "title": m.song.title,
                "artist": m.song.artist,
                "bpm": m.song.bpm,
                "duration": m.song.duration,
                "energy": m.song.energy,
                "score": round(m.score, 3),
                "matched": m.matched,
            }
            for m in matches
        ],
    })


# --------------------------------------------------------------------------- #
# FX synthesis
# --------------------------------------------------------------------------- #
@router.get("/fx", response_model=APIResponse[FxListResponse])
def list_fx_endpoint():
    return APIResponse(data=FxListResponse(fx=[FxItem(**f) for f in fx_synth.list_fx()]))


@router.get("/fx/{fx_key}.wav")
def render_fx_endpoint(fx_key: str, duration: float | None = None):
    if fx_key not in fx_synth.FX_CATALOG:
        raise HTTPException(status_code=404, detail="unknown fx")
    try:
        wav_bytes = fx_synth.render_to_wav_bytes(fx_key, duration=duration)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"render failed: {e}")
    return Response(content=wav_bytes, media_type="audio/wav")
