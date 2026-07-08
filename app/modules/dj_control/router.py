"""DJ Control router — exposes dance-style recommendation, energy sequencing,
mixing rules, live cut planning, and FX synthesis under /api/dj.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import User
from app.modules.dj_control import cut_strategy, dance_style, eq_transition_strategy, fx_synth, mixer_rules, sequencer, vibe_search
from app.modules.dj_control.default_mix import reference_renderer
from app.modules.dj_control.default_mix import transition_planner as default_transition_planner
from app.modules.dj_control.energy_hiphop import compute_dance_energy, get_dance_energy_profile
from app.modules.dj_control.spotify_mix.section_features import vocal_density_in_range
from app.modules.dj_control.spotify_mix.section_matcher import plan_section_match_transition
from app.modules.dj_set import service as dj_set_service
from app.modules.dj_set.set_templates import ALL_TEMPLATES, get_template
from app.modules.dj_control.schemas import (
    CutPlanRequest,
    BpmBucketItem,
    FxItem,
    FxListResponse,
    LivePoolPrepareRequest,
    LivePoolPrepareResponse,
    ScoredSong,
    SequenceEntry,
    SequenceRequest,
    SequenceResponse,
    SmartReorderRequest,
    SpotifyDecideRequest,
    SpotifyEQRequest,
    SpotifyFilterRequest,
    SpotifyVolumeRequest,
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


def _bpm_bucket_items(picks: list[tuple[LibrarySong, float, dict]]) -> list[BpmBucketItem]:
    buckets: dict[int, int] = {}
    for song, _score, _evidence in picks:
        try:
            bpm = float(song.bpm or 0.0)
        except (TypeError, ValueError):
            bpm = 0.0
        if bpm <= 0:
            continue
        lo = int(bpm // 10) * 10
        buckets[lo] = buckets.get(lo, 0) + 1
    return [
        BpmBucketItem(label=f"{lo}-{lo + 10}", min_bpm=float(lo), max_bpm=float(lo + 10), count=count)
        for lo, count in sorted(buckets.items())
    ]


def _analysis_status(song: LibrarySong) -> str:
    if getattr(song, "beat_points", None) and getattr(song, "music_features", None):
        return "completed"
    if getattr(song, "bpm", None) is not None:
        return "partial"
    return "missing"


def _analysis_completeness(song: LibrarySong) -> int:
    checks = [
        getattr(song, "bpm", None) is not None,
        bool(getattr(song, "camelot_key", None) or getattr(song, "key", None)),
        getattr(song, "energy", None) is not None,
        bool(getattr(song, "beat_points", None)),
        bool(getattr(song, "downbeats", None)),
        bool(getattr(song, "phrase_map", None)),
        bool(getattr(song, "transition_windows", None)),
        bool((getattr(song, "music_features", None) or {}).get("dj")),
    ]
    return sum(1 for item in checks if item)


def _status_rank(song: LibrarySong) -> int:
    return {"completed": 0, "partial": 1, "missing": 2}.get(_analysis_status(song), 3)


def _effective_bpm_range(payload: StylePickRequest) -> tuple[float | None, float | None]:
    bpm_min = payload.bpm_min if payload.bpm_min is not None else payload.min_bpm
    bpm_max = payload.bpm_max if payload.bpm_max is not None else payload.max_bpm
    return bpm_min, bpm_max


def _filter_and_sort_style_picks(
    picks: list[tuple[LibrarySong, float, dict]],
    *,
    bpm_min: float | None,
    bpm_max: float | None,
) -> list[tuple[LibrarySong, float, dict]]:
    filtered = list(picks)
    if bpm_min is not None and bpm_max is not None:
        filtered = [
            item
            for item in filtered
            if item[0].bpm is not None and float(item[0].bpm) >= bpm_min and float(item[0].bpm) < bpm_max
        ]
        center = (float(bpm_min) + float(bpm_max)) * 0.5
        filtered.sort(
            key=lambda item: (
                abs(float(item[0].bpm or center) - center),
                _status_rank(item[0]),
                -_analysis_completeness(item[0]),
                -float(item[1] or 0.0),
                (item[0].title or "").lower(),
            )
        )
    return filtered


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
    if payload.mode == "default":
        picks = dance_style.rank_songs_for_style(
            songs,
            style_key=payload.style,
            limit=80,
            min_score=payload.min_score,
        )
        buckets = _bpm_bucket_items(picks)
        bpm_min, bpm_max = _effective_bpm_range(payload)
        picks = _filter_and_sort_style_picks(
            picks,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
        )
    else:
        target_seconds = float(payload.target_duration_sec or 600.0)
        picks = dance_style.pick_songs_for_duration(
            songs,
            style_key=payload.style,
            target_seconds=target_seconds,
            min_score=payload.min_score,
        )
        buckets = []
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
                camelot_key=s.camelot_key,
                duration=s.duration,
                score=score,
                energy=(s.energy if s.energy is not None else None),
                analysis_status=_analysis_status(s),
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
        bpm_buckets=buckets,
    ))


@router.get("/styles/{style}/bpm-buckets")
def style_bpm_buckets_endpoint(
    style: str,
    min_score: float = 0.35,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if style not in dance_style.STYLE_PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown style: {style}")
    songs = db.query(LibrarySong).filter(LibrarySong.user_id == current_user.id).all()
    picks = dance_style.rank_songs_for_style(
        songs,
        style_key=style,
        limit=500,
        min_score=min_score,
    )
    return APIResponse(data={
        "style": style,
        "bpm_buckets": _bpm_bucket_items(picks),
    })


@router.get("/styles/{style}/candidates")
def style_candidates_endpoint(
    style: str,
    min_bpm: float,
    max_bpm: float,
    min_score: float = 0.35,
    limit: int = 80,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if style not in dance_style.STYLE_PROFILES:
        raise HTTPException(status_code=400, detail=f"unknown style: {style}")
    songs = db.query(LibrarySong).filter(LibrarySong.user_id == current_user.id).all()
    picks = dance_style.rank_songs_for_style(
        songs,
        style_key=style,
        limit=500,
        min_score=min_score,
    )
    picks = _filter_and_sort_style_picks(picks, bpm_min=min_bpm, bpm_max=max_bpm)[: max(1, min(limit, 200))]
    return APIResponse(data={
        "style": style,
        "bpm_bucket": f"{int(min_bpm)}-{int(max_bpm)}",
        "songs": [
            {
                "song_id": s.id,
                "title": s.title,
                "artist": s.artist,
                "bpm": s.bpm,
                "camelot_key": s.camelot_key,
                "energy": s.energy,
                "duration": s.duration,
                "analysis_status": _analysis_status(s),
                "analysis_completeness": _analysis_completeness(s),
                "score": score,
            }
            for s, score, _evidence in picks
        ],
    })


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
    seq_result = sequencer.sequence_songs_with_details(ordered_songs, preset=payload.preset)
    seq = seq_result["sequence"]
    return APIResponse(data=SequenceResponse(
        preset=payload.preset,
        sequence=[SequenceEntry(**e) for e in seq],
        ordering_mode=seq_result.get("ordering_mode"),
        pair_scores=seq_result.get("pair_scores") or [],
        pair_breakdowns=seq_result.get("pair_breakdowns") or [],
        default_mix_debug=seq_result.get("default_mix_debug") or {},
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


def _public_base_url(request: Request) -> str:
    from app.shared.config import get_settings
    import os

    settings = get_settings()
    configured = (
        getattr(settings, "public_asset_base_url", None)
        or os.environ.get("PUBLIC_ASSET_BASE_URL", "")
    ).strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}".rstrip("/") if host else ""


@router.get("/default/render/{pair_id}")
def stream_default_render(pair_id: str):
    path = reference_renderer.pair_dir(pair_id) / "transition_render.wav"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="default transition render not found")
    return FileResponse(str(path), media_type="audio/wav", filename="transition_render.wav")


@router.get("/default/render/{pair_id}/meta")
def stream_default_render_meta(pair_id: str):
    path = reference_renderer.pair_dir(pair_id) / "transition_render.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="default transition render meta not found")
    return FileResponse(str(path), media_type="application/json", filename="transition_render.json")


def _song_for_section_match(song: LibrarySong) -> dict:
    loudness_profile = getattr(song, "loudness_profile", None) or {}
    music_features = getattr(song, "music_features", None) or {}
    analysis = {
        "duration": float(song.duration or 0.0),
        "phrase_map": getattr(song, "phrase_map", None) or [],
        "transition_windows": getattr(song, "transition_windows", None) or [],
        "energy_curve": getattr(song, "energy_curve", None) or [],
        "vocal_events": getattr(song, "vocal_events", None) or [],
        "bass_risk_windows": getattr(song, "bass_risk_windows", None) or [],
        "stem_activity_windows": getattr(song, "stem_activity_windows", None) or [],
        "beat_points": getattr(song, "beat_points", None) or [],
        "downbeats": getattr(song, "downbeats", None) or [],
        "beatgrid": {"downbeats": getattr(song, "downbeats", None) or []},
        "bpm_curve": getattr(song, "bpm_curve", None) or [],
    }
    return {
        "id": song.id,
        "song_id": song.id,
        "source_path": song.source_path,
        "bpm": float(song.bpm or music_features.get("bpm") or 120.0),
        "camelot_key": song.camelot_key or "8A",
        "duration": float(song.duration or 0.0),
        "energy": float(song.energy if song.energy is not None else 0.5),
        "loudness": float(loudness_profile.get("integrated_lufs", -14.0)),
        "music_features": music_features,
        "genre_profile": getattr(song, "genre_profile", None) or {},
        "analysis": analysis,
    }


def _override_would_create_double_vocal(
    transition: dict,
    *,
    current: LibrarySong,
    target: LibrarySong,
    entry_sec: float,
) -> dict:
    fade_sec = float(transition.get("fade_sec") or transition.get("duration_sec") or 6.0)
    from_at = float(transition.get("from_at_sec") or transition.get("start_in_prev") or 0.0)
    current_duration = float(current.duration or 0.0)
    target_duration = float(target.duration or 0.0)
    from_end = min(current_duration, from_at + fade_sec) if current_duration > from_at else from_at + fade_sec
    to_end = min(target_duration, entry_sec + fade_sec) if target_duration > entry_sec else entry_sec + fade_sec
    a_vocal = vocal_density_in_range(getattr(current, "vocal_events", None) or [], from_at, from_end)
    b_vocal = vocal_density_in_range(getattr(target, "vocal_events", None) or [], entry_sec, to_end)
    both = min(a_vocal, b_vocal)
    return {
        "double_vocal": bool(both >= 0.25 or (a_vocal >= 0.60 and b_vocal >= 0.60)),
        "from_window": [round(from_at, 3), round(from_end, 3)],
        "to_window": [round(entry_sec, 3), round(to_end, 3)],
        "a_vocal": round(a_vocal, 3),
        "b_vocal": round(b_vocal, 3),
        "both_vocal": round(both, 3),
    }


def _attach_prepared_section_transition(
    plan: dict,
    *,
    current: LibrarySong,
    target: LibrarySong | None,
    cursor_sec: float,
) -> dict:
    if target is None:
        return plan
    prepared = dict(plan)
    transition = plan_section_match_transition(
        _song_for_section_match(current),
        _song_for_section_match(target),
        cursor_sec=cursor_sec,
    )
    selected = prepared.get("selected_song")
    if isinstance(selected, dict) and selected.get("entry_start_sec") is not None:
        entry = round(float(selected.get("entry_start_sec") or 0.0), 3)
        vocal_check = _override_would_create_double_vocal(
            transition,
            current=current,
            target=target,
            entry_sec=entry,
        )
        override = {
            "entry_start_sec": entry,
            "entry_label": selected.get("entry_label"),
            "segment_energy_score": selected.get("segment_energy_score"),
            "vocal_check": vocal_check,
        }
        if vocal_check["double_vocal"]:
            override["applied"] = False
            override["reason"] = "rejected_double_vocal_overlap"
        else:
            transition["to_at_sec"] = entry
            transition["start_in_next"] = entry
            target_spec = dict(transition.get("target") or {})
            target_spec["song_id"] = target.id
            target_spec["start_cue_sec"] = entry
            transition["target"] = target_spec
            override["applied"] = True
        transition["energy_entry_override"] = override
    prepared["prepared_transition"] = transition
    prepared["prepared_for_current_song_id"] = current.id
    prepared["prepared_target_song_id"] = target.id
    prepared.setdefault("reason", []).append("Jetson prepared v3.2 section_match transition with current vocal_events.")
    return prepared


@router.post("/transitions/plan")
def plan_transition_endpoint(
    payload: TransitionPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prev = db.get(LibrarySong, payload.prev_song_id)
    nxt = db.get(LibrarySong, payload.next_song_id)
    if not prev or not nxt or prev.user_id != current_user.id or nxt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song(s) not found")
    if payload.transition_mode == "default_mix":
        compatibility_bridge = (
            (payload.eq_mix_user_mode or "").lower() in {"bridge", "compat", "phase0"}
            or payload.rule_key == "default_mix_bridge"
        )
        spec = default_transition_planner.plan_default_transition(
            prev,
            nxt,
            cursor_sec=payload.cursor_sec,
            compatibility_bridge=compatibility_bridge,
        )
        if not compatibility_bridge:
            try:
                render_meta = reference_renderer.ensure_reference_render(prev, nxt, spec)
            except reference_renderer.DefaultRenderError as exc:
                raise HTTPException(status_code=503, detail=f"default render unavailable: {exc}") from exc
            spec = default_transition_planner.attach_render_resources(
                spec,
                render_meta=render_meta,
                base_url=_public_base_url(request),
            )
    elif payload.transition_mode == "section_match":
        spec = plan_section_match_transition(
            _song_for_section_match(prev),
            _song_for_section_match(nxt),
            cursor_sec=payload.cursor_sec,
            user_strategy=(
                payload.eq_mix_user_mode
                if payload.eq_mix_user_mode and payload.eq_mix_user_mode != "auto"
                else None
            ),
        )
    elif payload.transition_mode == "eq_band_mix":
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
    if payload.apply_phrase_alignment and payload.transition_mode not in {"section_match", "default_mix"}:
        from app.modules.dj_control.spotify_mix.phrase_alignment import find_transition_point

        prev_analysis = {
            "phrase_map": getattr(prev, "phrase_map", []) or [],
            "downbeats": getattr(prev, "downbeats", []) or [],
            "dj_hot_cues": getattr(prev, "dj_hot_cues", []) or [],
        }
        next_analysis = {
            "phrase_map": getattr(nxt, "phrase_map", []) or [],
            "downbeats": getattr(nxt, "downbeats", []) or [],
            "dj_hot_cues": getattr(nxt, "dj_hot_cues", []) or [],
            "stems": getattr(nxt, "stems", {}) or {},
            "vocal_events": getattr(nxt, "vocal_events", []) or [],
        }
        exit_at, entry_at = find_transition_point(
            prev_analysis,
            next_analysis,
            float(spec.get("from_at_sec", payload.cursor_sec) or payload.cursor_sec),
        )
        spec["from_at_sec"] = round(float(exit_at), 3)
        spec["to_at_sec"] = round(float(entry_at), 3)
        spec["start_in_prev"] = spec["from_at_sec"]
        spec["start_in_next"] = spec["to_at_sec"]
        spec["phrase_alignment"] = {"applied": True, "exit_at_sec": spec["from_at_sec"], "entry_at_sec": spec["to_at_sec"]}
    if payload.mix_preset and payload.transition_mode == "default_mix":
        spec["mix_preset_ignored"] = payload.mix_preset
        spec.setdefault("reason", []).append(
            "mix_preset ignored because default_mix owns cut points, duration and reference render."
        )
    elif payload.mix_preset and payload.transition_mode != "section_match":
        from app.modules.dj_control.transition import enrich_transition_plan_with_mix_effects

        try:
            spec = enrich_transition_plan_with_mix_effects(spec, prev, nxt, payload.mix_preset)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif payload.mix_preset and payload.transition_mode == "section_match":
        spec["mix_preset_ignored"] = payload.mix_preset
        spec.setdefault("reason", []).append(
            "mix_preset ignored because v3.2 section_match owns duration/style."
        )
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
        selected = plan.get("selected_song") if isinstance(plan, dict) else None
        target_song = db.get(LibrarySong, selected.get("song_id")) if isinstance(selected, dict) and selected.get("song_id") else None
        return APIResponse(data=_attach_prepared_section_transition(
            plan,
            current=current,
            target=target_song if target_song and target_song.user_id == current_user.id else None,
            cursor_sec=payload.cursor_sec,
        ))

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
        selected = plan.get("selected_song") if isinstance(plan, dict) else None
        target_song = db.get(LibrarySong, selected.get("song_id")) if isinstance(selected, dict) and selected.get("song_id") else None
        return APIResponse(data=_attach_prepared_section_transition(
            plan,
            current=current,
            target=target_song if target_song and target_song.user_id == current_user.id else None,
            cursor_sec=payload.cursor_sec,
        ))

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
    target_song = db.get(LibrarySong, plan.get("next_song_id")) if plan.get("next_song_id") else None
    return APIResponse(data=_attach_prepared_section_transition(
        plan,
        current=current,
        target=target_song if target_song and target_song.user_id == current_user.id else None,
        cursor_sec=payload.cursor_sec,
    ))


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


# --------------------------------------------------------------------------- #
# HarBeat Mix Effects API
# --------------------------------------------------------------------------- #
@router.get("/mix_effects/presets")
def mix_effect_presets_endpoint():
    from app.modules.dj_control.transition import mix_effect_presets

    return APIResponse(data=mix_effect_presets())


@router.post("/mix_effects/decide")
def mix_effect_decide_endpoint(
    payload: SpotifyDecideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.dj_control.transition import decide_mix_preset
    prev = db.get(LibrarySong, payload.prev_song_id)
    nxt = db.get(LibrarySong, payload.next_song_id)
    if not prev or not nxt or prev.user_id != current_user.id or nxt.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="song(s) not found")
    try:
        decision = decide_mix_preset(prev, nxt, payload.user_preference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(data=decision)


@router.post("/mix_effects/smart_reorder")
def mix_effect_smart_reorder_endpoint(
    payload: SmartReorderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.modules.dj_control.transition import smart_reorder
    songs_by_id = {
        s.id: s for s in db.query(LibrarySong)
        .filter(LibrarySong.user_id == current_user.id)
        .filter(LibrarySong.id.in_(payload.song_ids))
        .all()
    }
    ordered = [songs_by_id[sid] for sid in payload.song_ids if sid in songs_by_id]
    if len(ordered) < 2:
        raise HTTPException(status_code=400, detail="need >=2 songs")
    reordered = smart_reorder(ordered, payload.bpm_tolerance, payload.prefer_energy_flow)
    return APIResponse(data={"song_ids": [s.id for s in reordered]})


@router.post("/mix_effects/eq_curve")
def mix_effect_eq_curve_endpoint(payload: SpotifyEQRequest):
    from app.modules.dj_control.transition import generate_eq_curve
    try:
        curve = generate_eq_curve(payload.eq_type, payload.duration_beats, payload.bpm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(data=curve)


@router.post("/mix_effects/filter_curve")
def mix_effect_filter_curve_endpoint(payload: SpotifyFilterRequest):
    from app.modules.dj_control.transition import generate_filter_curve
    try:
        curve = generate_filter_curve(payload.filter_type, payload.duration_beats, payload.bpm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(data=curve)


@router.post("/mix_effects/volume_curve")
def mix_effect_volume_curve_endpoint(payload: SpotifyVolumeRequest):
    from app.modules.dj_control.transition import generate_volume_curve
    try:
        curve = generate_volume_curve(payload.curve_type, payload.duration_beats, payload.bpm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(data=curve)
