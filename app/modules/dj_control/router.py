"""DJ Control router — exposes dance-style recommendation, energy sequencing,
mixing rules, live cut planning, and FX synthesis under /api/dj.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import User
from app.modules.dj_control import cut_strategy, dance_style, eq_transition_strategy, fx_synth, mixer_rules, sequencer, vibe_search
from app.modules.dj_control.energy_hiphop import compute_dance_energy, get_dance_energy_profile
from app.modules.dj_set import service as dj_set_service
from app.modules.dj_set.set_templates import ALL_TEMPLATES, get_template
from app.modules.dj_control.schemas import (
    CutPlanRequest,
    FxItem,
    FxListResponse,
    LivePoolPrepareRequest,
    LivePoolPrepareResponse,
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
    achieved = sum(float(s.duration or 0) for s, _score, _evidence in picks)
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
                score_breakdown=dance_style._component_score_breakdown(evidence),
                confidence=evidence.get("confidence"),
                matched_labels=evidence.get("matched_labels", []),
                recommendation_reason=evidence.get("recommendation_reason", []),
                final_pick_score=evidence.get("final_pick_score"),
                style_evidence_status=evidence.get("style_evidence_status"),
                external_sources=evidence.get("external_sources", {}),
                reason=evidence.get("recommendation_reason", []),
            )
            for s, score, evidence in picks
        ],
    ))


# --------------------------------------------------------------------------- #
# Energy-based sequencing
# --------------------------------------------------------------------------- #
ENERGY_BUCKETS = [
    {"key": "cold", "label_zh": "冷场", "color": "#3B82F6", "lo": 0.0, "hi": 0.35},
    {"key": "warm", "label_zh": "热身", "color": "#22C55E", "lo": 0.35, "hi": 0.50},
    {"key": "mid", "label_zh": "稳定", "color": "#F59E0B", "lo": 0.50, "hi": 0.68},
    {"key": "high", "label_zh": "高能", "color": "#EF4444", "lo": 0.68, "hi": 0.84},
    {"key": "peak", "label_zh": "爆点", "color": "#A855F7", "lo": 0.84, "hi": 1.01},
]


def _energy_bucket(total: float) -> dict:
    value = max(0.0, min(1.0, float(total or 0.0)))
    for bucket in ENERGY_BUCKETS:
        if value >= bucket["lo"] and value < bucket["hi"]:
            return bucket
    return ENERGY_BUCKETS[-1]


@router.get("/energy/buckets")
def list_energy_buckets_endpoint():
    return APIResponse(data={"buckets": ENERGY_BUCKETS})


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
    style: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    song = db.get(LibrarySong, song_id)
    if not song or song.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song not found")
    eb = compute_dance_energy(song)
    profile = get_dance_energy_profile(song)
    data = eb.as_dict()
    bucket = _energy_bucket(data["total"])
    data.update({
        "bucket": bucket["key"],
        "bucket_label_zh": bucket["label_zh"],
        "bucket_color": bucket["color"],
        "bpm": song.bpm,
        "style_used": style or "generic",
        "factors": {
            "kick": data["kick_punch"],
            "snare": data["snare_crack"],
            "groove": data["groove_tightness"],
            "low_mid": data["low_mid_density"],
            "vocal": data["vocal_urgency"],
            "tempo": data["tempo_factor"],
        },
        "explain_zh": f"{bucket['label_zh']}能量，适合接在相邻能量段。",
        "dance_energy_score": profile["dance_energy_score"],
        "energy_bucket_10": profile["bucket"],
        "energy_profile": profile,
    })
    return APIResponse(data=data)


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
    if payload.transition_mode == "eq_band_mix":
        spec = eq_transition_strategy.plan_eq_band_mix_transition(
            prev,
            nxt,
            cursor_sec=payload.cursor_sec,
            rule_key=payload.rule_key,
            eq_mix_user_mode=payload.eq_mix_user_mode,
            target_style=payload.target_style,
        )
    else:
        spec = mixer_rules.build_transition_spec(prev, nxt, payload.cursor_sec, payload.rule_key)
    return APIResponse(data=spec)


# --------------------------------------------------------------------------- #
# Live cut strategies
# --------------------------------------------------------------------------- #
@router.post("/live/pool/prepare", response_model=APIResponse[LivePoolPrepareResponse])
def prepare_live_pool_endpoint(
    payload: LivePoolPrepareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    active = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .filter(LibrarySong.id.in_(payload.active_queue_song_ids))
        .all()
    )
    by_id = {song.id: song for song in active}
    ordered_active = [by_id[sid] for sid in payload.active_queue_song_ids if sid in by_id]
    library_songs = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .all()
    )
    result = cut_strategy.prepare_live_pool(
        active_queue=ordered_active,
        library_songs=library_songs,
        style=payload.style,
        target_reserve_per_bucket=payload.target_reserve_per_bucket,
        include_buckets=payload.include_buckets,
        exclude_song_ids=set(payload.exclude_song_ids),
        target_style_reserve_per_style=payload.target_style_reserve_per_style,
        include_styles=payload.include_styles,
    )
    return APIResponse(data=LivePoolPrepareResponse(**result))


@router.post("/cut/plan")
def plan_cut_endpoint(
    payload: CutPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    intent = payload.intent or payload.strategy
    if intent == "target_energy_bucket":
        current = db.get(LibrarySong, payload.current_song_id)
        if not current or current.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="current song not found")
        target = payload.target_energy_bucket or {}
        try:
            target_min = float(target.get("min"))
            target_max = float(target.get("max"))
        except (TypeError, ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="target_energy_bucket.min/max required")
        active_ids = payload.active_queue_song_ids or payload.queue_song_ids
        reserve_ids = payload.reserve_pool_song_ids or payload.pool_song_ids
        all_ids = set(active_ids) | set(reserve_ids)
        songs_by_id = {
            s.id: s
            for s in db.query(LibrarySong)
            .filter(LibrarySong.user_id == current_user.id)
            .filter(LibrarySong.id.in_(all_ids))
            .all()
        } if all_ids else {}
        active = [songs_by_id[sid] for sid in active_ids if sid in songs_by_id]
        reserve = [songs_by_id[sid] for sid in reserve_ids if sid in songs_by_id]
        plan = cut_strategy.plan_target_energy_cut(
            current_song=current,
            cursor_sec=payload.cursor_sec,
            active_queue=active,
            reserve_pool=reserve,
            target_min=target_min,
            target_max=target_max,
            current_style=payload.current_style,
            played_song_ids=set(payload.played_song_ids),
            blocked_song_ids=set(payload.blocked_song_ids),
            exclude_song_ids=set(payload.exclude_song_ids),
            cached_song_ids=set(payload.cached_song_ids),
            syncing_song_ids=set(payload.syncing_song_ids),
            prefer_cached=payload.prefer_cached,
            max_wait_sec=payload.max_wait_sec,
        )
        return APIResponse(data=plan)

    if intent == "target_dance_style":
        current = db.get(LibrarySong, payload.current_song_id)
        if not current or current.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="current song not found")
        if not payload.target_style:
            raise HTTPException(status_code=400, detail="target_style required for target_dance_style intent")

        active_ids = payload.active_queue_song_ids or payload.queue_song_ids
        style_reserve_ids = payload.style_reserve_pool_song_ids
        all_ids = set(active_ids) | set(style_reserve_ids)
        songs_by_id = {
            s.id: s
            for s in db.query(LibrarySong)
            .filter(LibrarySong.user_id == current_user.id)
            .filter(LibrarySong.id.in_(all_ids))
            .all()
        } if all_ids else {}
        active = [songs_by_id[sid] for sid in active_ids if sid in songs_by_id]
        style_reserve = [songs_by_id[sid] for sid in style_reserve_ids if sid in songs_by_id]
        plan = cut_strategy.plan_target_style_cut(
            current_song=current,
            cursor_sec=payload.cursor_sec,
            target_style=payload.target_style,
            active_queue=active,
            style_reserve_pool=style_reserve,
            current_style=payload.current_style,
            played_song_ids=set(payload.played_song_ids),
            blocked_song_ids=set(payload.blocked_song_ids),
            exclude_song_ids=set(payload.exclude_song_ids),
            cached_song_ids=set(payload.cached_song_ids),
            syncing_song_ids=set(payload.syncing_song_ids),
            prefer_cached=payload.prefer_cached,
            max_wait_sec=payload.max_wait_sec,
        )
        return APIResponse(data=plan)

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


# --------------------------------------------------------------------------- #
# Step 11 — DJ Set generation pipeline
#
#   POST /set/generate         5 candidate sets from selected songs
#   GET  /set/{set_id}         retrieve a previously generated set
#   POST /transition/preview   pairwise edge + plan preview (no full set)
#   POST /set/{set_id}/preview render single-transition WAV stub (placeholder)
# --------------------------------------------------------------------------- #
import secrets as _secrets
import time as _time

_SET_CACHE: dict[str, dict] = {}
_SET_CACHE_MAX = 32


class SetGenerateRequest(BaseModel):
    song_ids: list[str]
    template_names: list[str] | None = None
    beam_width: int = 12
    drop_failed: bool = True


class TransitionPreviewRequest(BaseModel):
    prev_song_id: str
    next_song_id: str


def _cache_set(payload: dict) -> str:
    set_id = _secrets.token_urlsafe(8)
    payload = {**payload, "set_id": set_id, "created_at": _time.time()}
    _SET_CACHE[set_id] = payload
    if len(_SET_CACHE) > _SET_CACHE_MAX:
        oldest = min(_SET_CACHE.items(), key=lambda kv: kv[1]["created_at"])[0]
        _SET_CACHE.pop(oldest, None)
    return set_id


@router.post("/set/generate")
def set_generate_endpoint(
    payload: SetGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.song_ids:
        raise HTTPException(status_code=400, detail="song_ids required")
    songs_by_id = {
        s.id: s
        for s in db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .filter(LibrarySong.id.in_(payload.song_ids))
        .all()
    }
    ordered = [songs_by_id[sid] for sid in payload.song_ids if sid in songs_by_id]
    if len(ordered) < 2:
        raise HTTPException(status_code=400, detail="need ≥2 songs to build a set")

    templates = None
    if payload.template_names:
        templates = []
        for name in payload.template_names:
            tpl = get_template(name)
            if tpl is None:
                raise HTTPException(status_code=400, detail=f"unknown template: {name}")
            templates.append(tpl)

    result = dj_set_service.generate_dj_sets(
        ordered,
        templates=templates,
        beam_width=payload.beam_width,
        drop_failed=payload.drop_failed,
    )
    set_ids: list[str] = []
    for s in result.get("sets", []):
        sid = _cache_set({"set": s, "user_id": current_user.id})
        s["set_id"] = sid
        set_ids.append(sid)
    return APIResponse(data={
        **result,
        "set_ids": set_ids,
        "count": len(result.get("sets", [])),
    })


@router.get("/set/{set_id}")
def set_get_endpoint(
    set_id: str,
    current_user: User = Depends(get_current_user),
):
    entry = _SET_CACHE.get(set_id)
    if not entry or entry.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="set not found")
    return APIResponse(data=entry["set"])


@router.post("/transition/preview")
def transition_preview_endpoint(
    payload: TransitionPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prev = db.get(LibrarySong, payload.prev_song_id)
    nxt = db.get(LibrarySong, payload.next_song_id)
    if not prev or not nxt or prev.user_id != current_user.id or nxt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song(s) not found")
    return APIResponse(data=dj_set_service.preview_transition(prev, nxt))


@router.post("/set/{set_id}/preview")
def set_preview_endpoint(
    set_id: str,
    current_user: User = Depends(get_current_user),
):
    """Stub — returns the cached plan; real-time render is mobile/RK's job."""
    entry = _SET_CACHE.get(set_id)
    if not entry or entry.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="set not found")
    return APIResponse(data={
        "set_id": set_id,
        "render_supported": False,
        "set": entry["set"],
        "hint": "前端 / RK 端按 plan.actions 自行 render",
    })
