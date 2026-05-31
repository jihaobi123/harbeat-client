"""Background tasks for automatic audio analysis and stem separation on import."""
from __future__ import annotations

import logging
import os
import subprocess
import sys

from app.shared.database import SessionLocal

logger = logging.getLogger(__name__)


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


def apply_stem_analysis(song) -> None:
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

    result = analyze_stem_files(song.stems, original_path=song.source_path)
    song.stem_activity = result["stem_activity"]
    song.stem_activity_windows = result["stem_activity_windows"]
    song.stem_quality_score = result["stem_quality_score"]
    song.stem_quality_profile = result["stem_quality_profile"]
    song.intro_is_clean = result["intro_is_clean"]
    song.outro_is_clean = result["outro_is_clean"]
    song.intro_clean_score = result["intro_clean_score"]
    song.outro_clean_score = result["outro_clean_score"]
    song.has_drum_loop = result["has_drum_loop"]

    # ── Stem-dependent extended analysis ───────────────────────────
    windows = result.get("stem_activity_windows", [])

    # Vocal enter/exit events from stem activity curve
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


def apply_dj_fingerprint(db, song) -> None:
    """Persist explainable DJ fingerprint features and ranked dance styles."""
    from app.modules.dj_control.dance_style import STYLE_PROFILES, score_song_combined
    from app.modules.library.dj_feature_extractor import extract_dj_features

    features = extract_dj_features(song)
    music_features = dict(getattr(song, "music_features", {}) or {})
    music_features["dj"] = features
    song.music_features = music_features
    apply_dancefloor_profile(song)

    ranked = []
    scores = {}
    for style_key in STYLE_PROFILES:
        score, source, breakdown = score_song_combined(song, style_key)
        scores[style_key] = round(score, 4)
        ranked.append({
            "style": style_key,
            "score": round(score, 4),
            "source": source,
            "breakdown": breakdown,
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    song.dance_styles = ranked
    song.dance_style_scores = scores
    song.dance_style_status = "ready"
    db.add(song)
    db.commit()


def run_analysis_and_separation(song_id: str) -> None:
    """Run BPM/key analysis + demucs stem separation in background.

    Called automatically after a song is downloaded.
    Creates its own DB session since this runs outside the request lifecycle.
    """
    db = SessionLocal()
    try:
        from app.modules.library.models import LibrarySong

        song = db.get(LibrarySong, song_id)
        if not song or not song.source_path or not os.path.isfile(song.source_path):
            logger.warning("[bg-analysis] song %s not found or no file", song_id)
            return

        # --- Phase 1: BPM / Key / Energy / Beat & Cue points ---
        # Skip if already analyzed (e.g. retrying after interrupted stem separation)
        if song.bpm is not None and song.key is not None:
            logger.info("[bg-analysis] skipping Phase 1 for %s (already has BPM=%s Key=%s)", song_id, song.bpm, song.key)
        else:
            song.analysis_status = "analyzing"
            db.commit()

            try:
                from app.modules.library.analysis import analyze_audio_file

                result = analyze_audio_file(song.source_path)
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
                song.key_confidence = result.get("key_confidence")
                song.key_profile = result.get("key_profile", {})
                raw_cues = result.get("cue_points", [])
                song.cue_points = [
                    {"id": f"cue-{song_id}-{i}", "time": c["time"], "label": c["label"], "color": c["color"]}
                    for i, c in enumerate(raw_cues)
                ]
                db.commit()
                logger.info("[bg-analysis] analysis done for %s: BPM=%s Key=%s", song_id, song.bpm, song.key)
            except Exception:
                logger.exception("[bg-analysis] analysis failed for %s", song_id)
                song.analysis_status = "error"
                db.commit()

        # --- Phase 2: Stem separation (demucs) ---
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
                apply_stem_analysis(song)
                logger.info("[bg-analysis] stems separated for %s", song_id)
            else:
                logger.warning("[bg-analysis] stem files not found after demucs for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] stem separation failed for %s (non-fatal)", song_id)

        try:
            apply_dj_fingerprint(db, song)
            logger.info("[bg-analysis] DJ fingerprint ready for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] DJ fingerprint failed for %s (non-fatal)", song_id)

        # --- Phase 5: Genre classification ---
        try:
            _apply_genre_classification(db, song)
            logger.info("[bg-analysis] genre classification ready for %s", song_id)
        except Exception:
            logger.exception("[bg-analysis] genre classification failed for %s (non-fatal)", song_id)

        # Mark completed regardless of stem separation outcome
        song.analysis_status = "completed"
        db.commit()
    except Exception:
        logger.exception("[bg-analysis] unexpected error for %s", song_id)
    finally:
        db.close()


def _apply_genre_classification(db, song) -> None:
    """Classify genre from audio features + Spotify metadata."""
    from app.modules.library.genre_classifier import classify_genre

    manual_style = None
    try:
        from app.modules.playlists.models import SongTag
        tag = db.query(SongTag).filter(SongTag.song_id == song.song_id).first()
        if tag and tag.style:
            manual_style = tag.style
    except Exception:
        pass

    result = classify_genre(
        bpm=song.bpm,
        stem_activity=getattr(song, "stem_activity", None),
        groove_profile=getattr(song, "groove_profile", None),
        dj_features=(getattr(song, "music_features", {}) or {}).get("dj"),
        energy=song.energy,
        title=song.title,
        artist=song.artist,
        manual_style=manual_style,
    )
    song.genre_profile = result
    db.add(song)
    db.commit()


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
                  "stem_activity", "stem_activity_windows", "stem_quality_score", "stem_quality_profile",
                  "intro_is_clean", "outro_is_clean", "intro_clean_score", "outro_clean_score",
                  "has_drum_loop",
                  "music_features", "dance_styles", "dance_style_scores", "dance_style_status",
                  "genre_profile", "cue_points", "stems", "analysis_status"):
        val = getattr(source, field, None)
        if val is not None:
            setattr(target, field, val)
