"""Background tasks for automatic audio analysis and stem separation on import."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)

ANALYSIS_STAGE_KEYS = ("core", "stem_separation", "feature_analysis", "style_analysis")
REQUIRED_CORE_ANALYSIS_VERSION = "songformer_sections_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_analysis_stage(
    song,
    stage: str,
    status: str,
    *,
    error: str | None = None,
) -> None:
    """Persist one pipeline transition inside the song's unified feature payload."""
    if stage not in ANALYSIS_STAGE_KEYS:
        raise ValueError(f"unknown analysis stage: {stage}")

    music_features = dict(getattr(song, "music_features", {}) or {})
    pipeline = dict(music_features.get("analysis_pipeline", {}) or {})
    stages = dict(pipeline.get("stages", {}) or {})
    stage_state = dict(stages.get(stage, {}) or {})
    now = _utc_now()
    stage_state["status"] = status
    stage_state["updated_at"] = now
    if status == "running":
        stage_state["started_at"] = now
        stage_state.pop("finished_at", None)
    elif status in {"completed", "error", "blocked"}:
        stage_state["finished_at"] = now
    if error:
        stage_state["error"] = str(error)[:1000]
    else:
        stage_state.pop("error", None)
    stages[stage] = stage_state
    pipeline.update({
        "version": "song_analysis_pipeline_v1",
        "current_stage": stage if status == "running" else pipeline.get("current_stage"),
        "stages": stages,
        "updated_at": now,
    })
    music_features["analysis_pipeline"] = pipeline
    song.music_features = music_features


def set_analysis_pipeline_status(song, status: str) -> None:
    music_features = dict(getattr(song, "music_features", {}) or {})
    pipeline = dict(music_features.get("analysis_pipeline", {}) or {})
    pipeline.update({
        "version": "song_analysis_pipeline_v1",
        "status": status,
        "current_stage": None if status in {"pending", "completed", "partial", "error"} else pipeline.get("current_stage"),
        "updated_at": _utc_now(),
    })
    music_features["analysis_pipeline"] = pipeline
    song.music_features = music_features
    song.analysis_status = status


def queue_song_analysis(song) -> None:
    """Mark a song as queued before dispatching the background worker."""
    for stage in ANALYSIS_STAGE_KEYS:
        update_analysis_stage(song, stage, "pending")
    set_analysis_pipeline_status(song, "pending")


def _commit_stage(db, song) -> None:
    db.add(song)
    db.commit()


def _int_bool(value: object) -> int:
    """Normalize boolean-like values for legacy integer columns."""
    return 1 if bool(value) else 0


def apply_dancefloor_profile(song) -> None:
    """Refresh danceability and mood metadata from the best available features."""
    from app.modules.library.analysis import _analyze_dancefloor_profile

    features = (getattr(song, "music_features", {}) or {}).get("dj", {})
    profile = _analyze_dancefloor_profile(
        bpm=float(getattr(song, "bpm", 0.0) or 0.0),
        energy=float(getattr(song, "energy", 0.0) or 0.0),
        groove=getattr(song, "groove_profile", {}) or {},
        stem_activity=getattr(song, "stem_activity", {}) or {},
        spectral_centroid=features.get("spectral_centroid"),
        phrase_map=getattr(song, "phrase_map", []) or [],
    )
    song.danceability_score = profile["danceability_score"]
    song.dancefloor_profile = profile


def apply_stem_analysis(song, *, classify_styles: bool = True) -> None:
    """Persist planner-ready analysis for already separated stem files.

    Includes: stem activity windows, vocal events, bass risk windows,
    and stem-aware transition window enhancement.
    """
    from app.modules.library.analysis import (
        _compute_bass_risk_windows,
        _detect_vocal_events,
        _enhance_transition_windows,
    )
    from app.modules.library.stem_analysis import analyze_stem_files

    existing_vocal_events = list(getattr(song, "vocal_events", None) or [])
    result = analyze_stem_files(
        song.stems,
        original_path=song.source_path,
        bpm=float(getattr(song, "bpm", 0.0) or 0.0),
        beat_points=list(getattr(song, "beat_points", None) or []),
        downbeats=list(getattr(song, "downbeats", None) or []),
        key_profile=dict(getattr(song, "key_profile", None) or {}),
    )
    song.stem_activity = result["stem_activity"]
    song.stem_activity_windows = result["stem_activity_windows"]
    song.stem_quality_score = result["stem_quality_score"]
    song.stem_quality_profile = result["stem_quality_profile"]
    song.drum_analysis = result["drum_analysis"]
    music_features = dict(getattr(song, "music_features", {}) or {})
    music_features["pre_style_features"] = result.get("feature_analysis", {})
    song.music_features = music_features
    if classify_styles:
        apply_high_frequency_style_analysis(song, result.get("feature_analysis", {}))
    song.intro_is_clean = _int_bool(result["intro_is_clean"])
    song.outro_is_clean = _int_bool(result["outro_is_clean"])
    song.intro_clean_score = result["intro_clean_score"]
    song.outro_clean_score = result["outro_clean_score"]
    song.has_drum_loop = _int_bool(result["has_drum_loop"])

    # ── Stem-dependent extended analysis ───────────────────────────
    windows = result.get("stem_activity_windows", [])

    # Vocal enter/exit events from stem activity curve
    if existing_vocal_events:
        song.vocal_events = existing_vocal_events
    else:
        try:
            song.vocal_events = _detect_vocal_events(windows)
        except Exception:
            song.vocal_events = []

    # Bass risk per window
    try:
        song.bass_risk_windows = _compute_bass_risk_windows(windows)
    except Exception:
        song.bass_risk_windows = []

    # Enhance transition windows with stem data
    tw = getattr(song, "transition_windows", None) or []
    try:
        enhanced = _enhance_transition_windows(list(tw), windows)
        song.transition_windows = enhanced
    except Exception:
        pass  # keep original label-based windows
    apply_dancefloor_profile(song)


def apply_high_frequency_style_analysis(song, feature_analysis: dict | None = None) -> dict:
    """Classify and persist the 21 music styles without touching DJ styles."""
    from app.modules.library.high_frequency_style_classifier import classify_high_frequency_styles

    music_features = dict(getattr(song, "music_features", {}) or {})
    features = feature_analysis or music_features.get("pre_style_features") or {}
    result = classify_high_frequency_styles(features)
    music_features["high_frequency_styles"] = result
    song.music_features = music_features
    return result


def apply_dj_fingerprint(db, song) -> None:
    """Persist explainable DJ fingerprint features and ranked dance styles."""
    from app.modules.dj_control.dance_style import persist_multisource_style_evidence
    from app.modules.library.dj_feature_extractor import extract_dj_features

    features = extract_dj_features(song)
    music_features = dict(getattr(song, "music_features", {}) or {})
    music_features["dj"] = features
    song.music_features = music_features
    apply_dancefloor_profile(song)

    persist_multisource_style_evidence(song)
    db.add(song)
    db.commit()


def run_analysis_and_separation(song_id: str) -> None:
    """Run and durably persist the full per-song analysis pipeline."""
    db = SessionLocal()
    try:
        from app.modules.library.models import LibrarySong

        song = db.get(LibrarySong, song_id)
        if not song:
            logger.warning("[bg-analysis] song %s not found", song_id)
            return
        if not song.source_path or not os.path.isfile(song.source_path):
            logger.warning("[bg-analysis] song %s not found or no file", song_id)
            update_analysis_stage(song, "core", "error", error="audio file not found")
            update_analysis_stage(song, "stem_separation", "blocked", error="audio file is required")
            update_analysis_stage(song, "feature_analysis", "blocked", error="stem separation is required")
            update_analysis_stage(song, "style_analysis", "blocked", error="feature analysis is required")
            set_analysis_pipeline_status(song, "error")
            _commit_stage(db, song)
            return

        # Phase 1: BPM / Key / Energy / Beat & Cue points.
        core_ready = bool(
            song.bpm is not None
            and song.key
            and song.beat_points
            and song.cue_points
            and song.transition_windows
            and (
                (getattr(song, "beat_confidence_details", {}) or {}).get(
                    "core_analysis_version"
                )
                == REQUIRED_CORE_ANALYSIS_VERSION
            )
        )
        if core_ready:
            update_analysis_stage(song, "core", "completed")
            _commit_stage(db, song)
            logger.info(
                "[bg-analysis] skipping Phase 1 for %s (core analysis ready: BPM=%s Key=%s)",
                song_id,
                song.bpm,
                song.key,
            )
        else:
            update_analysis_stage(song, "core", "running")
            set_analysis_pipeline_status(song, "core_analyzing")
            _commit_stage(db, song)
            try:
                from app.modules.library.analysis import analyze_audio_file

                result = analyze_audio_file(song.source_path)
                if os.getenv("ENABLE_GPU_VOCAL_DETECTION", "false").lower() == "true":
                    try:
                        from app.modules.library.analysis_vocal_patch_gpu import patch_analysis_result_with_vocals

                        force_refresh = os.getenv("FORCE_REFRESH_VOCAL", "false").lower() == "true"
                        fast_mode = os.getenv("VOCAL_DETECTION_FAST", "true").lower() == "true"
                        if force_refresh or not result.get("vocal_events"):
                            result = patch_analysis_result_with_vocals(
                                result,
                                song.source_path,
                                use_gpu=True,
                                fast_mode=fast_mode,
                            )
                            logger.info(
                                "[bg-analysis] GPU vocal detection done for %s: %d events",
                                song_id,
                                len(result.get("vocal_events", [])),
                            )
                    except Exception as exc:
                        logger.warning("[bg-analysis] GPU vocal detection failed for %s: %s", song_id, exc)
                song.bpm = result["bpm"]
                song.duration = result["duration"]
                song.key = result.get("key")
                song.camelot_key = result.get("camelot_key")
                song.energy = result.get("energy")
                song.beat_points = result.get("beat_points", [])
                song.bpm_curve = result.get("bpm_curve", [])
                song.tempo_stability = result.get("tempo_stability")
                song.beat_confidence = result.get("beat_confidence")
                song.beat_confidence_details = result.get("beat_confidence_details", {})
                song.beat_grid_offset = result.get("beat_grid_offset")
                song.beat_grid_interval = result.get("beat_grid_interval")
                song.beat_engines_used = result.get("beat_engines_used", [])
                song.beat_needs_review = int(result.get("beat_needs_review", False))
                song.energy_curve = result.get("energy_curve", [])
                song.loudness_profile = result.get("loudness_profile", {})
                song.time_signature = result.get("time_signature", {})
                groove = result.get("groove", {})
                song.groove_score = groove.get("score") if groove else None
                song.groove_profile = groove if groove else {}
                song.danceability_score = result.get("danceability_score")
                song.dancefloor_profile = result.get("dancefloor_profile", {})
                song.dj_hot_cues = result.get("dj_hot_cues", [])
                song.vocal_events = result.get("vocal_events", [])
                song.bass_risk_windows = result.get("bass_risk_windows", [])
                song.transition_windows = result.get("transition_windows", [])
                song.transition_recommendations = result.get("transition_recommendations", [])
                song.downbeats = result.get("downbeats", [])
                song.phrase_map = result.get("phrase_map", [])
                music_features = dict(getattr(song, "music_features", {}) or {})
                music_features["section_analysis"] = result.get("section_analysis", {})
                song.music_features = music_features
                song.key_confidence = result.get("key_confidence")
                song.key_profile = result.get("key_profile", {})
                raw_cues = result.get("cue_points", [])
                song.cue_points = [
                    {
                        "id": f"cue-{song_id}-{i}",
                        "time": c["time"],
                        "end": c.get("end"),
                        "label": c["label"],
                        "raw_label": c.get("raw_label"),
                        "color": c["color"],
                        "source": c.get("source"),
                    }
                    for i, c in enumerate(raw_cues)
                ]
                update_analysis_stage(song, "core", "completed")
                _commit_stage(db, song)
                logger.info("[bg-analysis] analysis done for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
            except Exception as exc:
                logger.exception("[bg-analysis] analysis failed for %s", song_id)
                db.rollback()
                song = db.get(LibrarySong, song_id)
                update_analysis_stage(song, "core", "error", error=str(exc))
                _commit_stage(db, song)

        # Phase 2: Stem separation. Store paths immediately when it succeeds.
        stems_ready = False
        update_analysis_stage(song, "stem_separation", "running")
        set_analysis_pipeline_status(song, "stem_separating")
        _commit_stage(db, song)
        try:
            stems_base = os.path.join(os.path.dirname(os.path.abspath(song.source_path)), "..", "stems")
            stems_base = os.path.abspath(stems_base)
            os.makedirs(stems_base, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(song.source_path))[0]
            stems_dir = os.path.join(stems_base, "htdemucs", base_name)
            stem_names = ["vocals", "drums", "bass", "other"]

            # Skip if already separated
            if not all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
                python_exe = sys.executable
                logger.info("[bg-analysis] starting demucs for %s", song_id)
                result = subprocess.run(
                    [
                        python_exe, "-m", "demucs",
                        "-n", "htdemucs",
                        "--segment", "7",   # limit RAM: process 7s chunks (htdemucs max ~7.8)
                        "-o", stems_base,
                        song.source_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=True,
                )
                logger.info("[bg-analysis] demucs finished for %s", song_id)

            if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in stem_names):
                song.stems = {s: os.path.join(stems_dir, f"{s}.wav") for s in stem_names}
                stems_ready = True
                update_analysis_stage(song, "stem_separation", "completed")
                _commit_stage(db, song)
                logger.info("[bg-analysis] stems separated for %s", song_id)
            else:
                raise FileNotFoundError("stem files were not produced by demucs")
        except Exception as exc:
            logger.exception("[bg-analysis] stem separation failed for %s (non-fatal)", song_id)
            db.rollback()
            song = db.get(LibrarySong, song_id)
            update_analysis_stage(song, "stem_separation", "error", error=str(exc))
            update_analysis_stage(song, "feature_analysis", "blocked", error="stem separation is required")
            update_analysis_stage(song, "style_analysis", "blocked", error="feature analysis is required")
            _commit_stage(db, song)

        # Phase 3: Stem-aware time/frequency feature analysis.
        if stems_ready:
            update_analysis_stage(song, "feature_analysis", "running")
            set_analysis_pipeline_status(song, "feature_analyzing")
            _commit_stage(db, song)
            try:
                apply_stem_analysis(song, classify_styles=False)
                update_analysis_stage(song, "feature_analysis", "completed")
                _commit_stage(db, song)
                logger.info("[bg-analysis] feature analysis ready for %s", song_id)
            except Exception as exc:
                logger.exception("[bg-analysis] feature analysis failed for %s (non-fatal)", song_id)
                db.rollback()
                song = db.get(LibrarySong, song_id)
                update_analysis_stage(song, "feature_analysis", "error", error=str(exc))
                update_analysis_stage(song, "style_analysis", "blocked", error="feature analysis is required")
                _commit_stage(db, song)

        # Phase 4: Explainable 21-style classification from persisted features.
        feature_status = (
            (song.music_features or {})
            .get("analysis_pipeline", {})
            .get("stages", {})
            .get("feature_analysis", {})
            .get("status")
        )
        if feature_status == "completed":
            update_analysis_stage(song, "style_analysis", "running")
            set_analysis_pipeline_status(song, "style_analyzing")
            _commit_stage(db, song)
            try:
                apply_high_frequency_style_analysis(song)
                update_analysis_stage(song, "style_analysis", "completed")
                _commit_stage(db, song)
                logger.info("[bg-analysis] 21-style analysis ready for %s", song_id)
            except Exception as exc:
                logger.exception("[bg-analysis] style analysis failed for %s (non-fatal)", song_id)
                db.rollback()
                song = db.get(LibrarySong, song_id)
                update_analysis_stage(song, "style_analysis", "error", error=str(exc))
                _commit_stage(db, song)

        # Optional downstream DJ fingerprint. Required stages above are already durable.
        try:
            apply_dj_fingerprint(db, song)
            logger.info("[bg-analysis] DJ fingerprint ready for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] DJ fingerprint failed for %s (non-fatal)", song_id)
            db.rollback()

        # Optional external metadata enrichment.
        try:
            from app.modules.library.external_metadata import run_enrich_song_external_metadata

            run_enrich_song_external_metadata(db, song, force=False)
            logger.info("[bg-analysis] external style evidence ready for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] external style evidence failed for %s (non-fatal)", song_id)
            db.rollback()

        song = db.get(LibrarySong, song_id)
        stages = (song.music_features or {}).get("analysis_pipeline", {}).get("stages", {})
        stage_statuses = [stages.get(name, {}).get("status") for name in ANALYSIS_STAGE_KEYS]
        if all(value == "completed" for value in stage_statuses):
            final_status = "completed"
        elif any(value == "completed" for value in stage_statuses):
            final_status = "partial"
        else:
            final_status = "error"
        set_analysis_pipeline_status(song, final_status)
        _commit_stage(db, song)
    except Exception as exc:
        logger.exception("[bg-analysis] unexpected error for %s", song_id)
        db.rollback()
        try:
            from app.modules.library.models import LibrarySong

            song = db.get(LibrarySong, song_id)
            if song is not None:
                set_analysis_pipeline_status(song, "error")
                music_features = dict(song.music_features or {})
                pipeline = dict(music_features.get("analysis_pipeline", {}) or {})
                pipeline["error"] = str(exc)[:1000]
                music_features["analysis_pipeline"] = pipeline
                song.music_features = music_features
                _commit_stage(db, song)
        except Exception:
            db.rollback()
    finally:
        db.close()


def copy_analysis_from(source: object, target: object) -> None:
    """Copy analysis results from an existing LibrarySong to a new one."""
    for field in ("bpm", "duration", "key", "camelot_key", "energy",
                  "beat_points", "bpm_curve", "tempo_stability", "beat_confidence",
                  "beat_confidence_details", "beat_grid_offset", "beat_grid_interval",
                  "beat_engines_used", "beat_needs_review", "energy_curve", "loudness_profile",
                  "key_profile", "time_signature", "groove_score", "groove_profile",
                  "danceability_score", "dancefloor_profile", "dj_hot_cues",
                  "vocal_events", "bass_risk_windows",
                  "transition_windows", "transition_recommendations",
                  "downbeats", "phrase_map", "key_confidence",
                  "stem_activity", "stem_activity_windows", "stem_quality_score", "stem_quality_profile", "drum_analysis",
                  "intro_is_clean", "outro_is_clean", "intro_clean_score", "outro_clean_score",
                  "has_drum_loop",
                  "music_features", "dance_styles", "dance_style_scores", "dance_style_status",
                  "genre_profile", "cue_points", "stems", "analysis_status"):
        val = getattr(source, field, None)
        if val is not None:
            setattr(target, field, val)
