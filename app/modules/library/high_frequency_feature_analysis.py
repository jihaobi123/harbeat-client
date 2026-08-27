"""Orchestrate style-ready music features without emitting style labels."""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np

from app.modules.library.bass_feature_analysis import analyze_bass_features
from app.modules.library.musical_context_feature_analysis import analyze_musical_context_features
from app.modules.library.percussion_feature_analysis import analyze_percussion_features
from app.modules.library.rhythm_feature_analysis import analyze_rhythm_features
from app.modules.library.style_feature_evidence import (
    STYLE_FEATURE_EVIDENCE_VERSION,
    to_v2_feature,
    unavailable_feature,
)


TARGET_SAMPLE_RATE = 22050


def _legacy_group(group: dict[str, dict]) -> dict[str, dict]:
    return {name: to_v2_feature(feature) for name, feature in group.items()}


def _count(values) -> int:
    return 0 if values is None else len(values)


def empty_high_frequency_features(reason: str = "required_audio_unavailable") -> dict[str, Any]:
    feature = unavailable_feature(
        reason,
        sources=["demucs_stems"],
        analysis_method="high_frequency_feature_pipeline_v1",
    )
    groups = {
        "rhythm_grammar": {"analysis": feature},
        "low_frequency": {"analysis": feature},
        "percussion_timbre": {"analysis": feature},
        "vocal_delivery": {"analysis": feature},
        "harmony": {"analysis": feature},
        "production": {"analysis": feature},
    }
    return {
        "version": STYLE_FEATURE_EVIDENCE_VERSION,
        "status": "unavailable",
        "needs_review": True,
        "reason": reason,
        "music_context": {},
        "feature_groups": groups,
        "analysis_modules": {},
        "rhythm_grammar": _legacy_group(groups["rhythm_grammar"]),
        "low_frequency": _legacy_group(groups["low_frequency"]),
        "percussion_timbre": _legacy_group(groups["percussion_timbre"]),
        "sonic_profile": {},
        "confidence": {"overall": 0.0},
        "quality_flags": [reason],
        "selected_models": [],
        "model_evidence": {"status": "unavailable", "routes": {}},
    }


def _resample_stems(stems: dict[str, np.ndarray], sr: int) -> tuple[dict[str, np.ndarray], int]:
    arrays = {
        name: np.asarray(value, dtype=np.float32)
        for name, value in stems.items() if value is not None and len(value)
    }
    if sr == TARGET_SAMPLE_RATE:
        return arrays, sr
    return ({
        name: librosa.resample(value, orig_sr=sr, target_sr=TARGET_SAMPLE_RATE)
        for name, value in arrays.items()
    }, TARGET_SAMPLE_RATE)


def analyze_high_frequency_features(
    stems: dict[str, np.ndarray] | None,
    sr: int,
    *,
    bpm: float | None = None,
    beat_points=None,
    downbeats=None,
    drum_analysis: dict | None = None,
    key_profile: dict | None = None,
    original_audio: np.ndarray | None = None,
    model_evidence: dict | None = None,
) -> dict[str, Any]:
    stems = stems or {}
    if sr <= 0 or not any(value is not None and len(value) for value in stems.values()):
        return empty_high_frequency_features()
    duration = max(len(value) for value in stems.values() if value is not None and len(value)) / sr
    arrays, analysis_sr = _resample_stems(stems, sr)
    if original_audio is not None and len(original_audio):
        mix = np.asarray(original_audio, dtype=np.float32)
        if sr != analysis_sr:
            mix = librosa.resample(mix, orig_sr=sr, target_sr=analysis_sr)
    else:
        lengths = [len(value) for value in arrays.values()]
        length = min(lengths) if lengths else 0
        mix = sum((value[:length] for value in arrays.values()), np.zeros(length, dtype=np.float32)) if length else None

    rhythm = analyze_rhythm_features(
        drum_analysis,
        bpm=bpm,
        beat_points=beat_points,
        downbeats=downbeats,
        duration=duration,
    )
    bass = analyze_bass_features(
        arrays.get("bass"), arrays.get("drums"), analysis_sr,
        drum_analysis=drum_analysis,
        beat_points=beat_points,
        original_audio=mix,
    )
    percussion = analyze_percussion_features(
        arrays.get("drums"), analysis_sr, drum_analysis=drum_analysis,
    )
    context = analyze_musical_context_features(
        vocals=arrays.get("vocals"),
        other=arrays.get("other"),
        original_audio=mix,
        sr=analysis_sr,
        key_profile=key_profile,
    )
    groups = {
        "rhythm_grammar": rhythm["features"],
        "low_frequency": bass["features"],
        "percussion_timbre": percussion["features"],
        "vocal_delivery": context["vocal_delivery"],
        "harmony": context["harmony"],
        "production": context["production"],
    }
    module_confidences = [
        float(rhythm.get("confidence", 0.0) or 0.0),
        float(bass.get("confidence", 0.0) or 0.0),
        float(percussion.get("confidence", 0.0) or 0.0),
        float((context.get("confidence") or {}).get("overall", 0.0) or 0.0),
    ]
    available_confidences = [value for value in module_confidences if value > 0]
    overall = float(np.mean(available_confidences)) if available_confidences else 0.0
    flags = list(dict.fromkeys(
        list(rhythm.get("quality_flags") or [])
        + list(bass.get("quality_flags") or [])
        + list(percussion.get("quality_flags") or [])
        + list(context.get("quality_flags") or [])
    ))
    selected_models = [
        str(route.get("engine"))
        for route in ((model_evidence or {}).get("routes") or {}).values()
        if route.get("status") == "ready" and route.get("engine")
    ]
    if not selected_models:
        flags.append("mature_models_unavailable_using_dsp_fallbacks")
    unavailable_modules = sum(value == 0 for value in module_confidences)
    status = "ready" if overall >= 0.55 and unavailable_modules == 0 else "degraded"

    # Old callers can continue reading the four legacy groups while new style
    # analysis consumes feature_groups with explicit availability semantics.
    legacy_sonic = {
        **_legacy_group(groups["harmony"]),
        **_legacy_group(groups["production"]),
    }
    return {
        "version": STYLE_FEATURE_EVIDENCE_VERSION,
        "status": status,
        "needs_review": bool(flags),
        "reason": None,
        "music_context": {
            "bpm": bpm,
            "beat_count": _count(beat_points),
            "downbeat_count": _count(downbeats),
            "key_profile": dict(key_profile or {}),
            "analysis_sample_rate": analysis_sr,
            "duration": round(duration, 4),
        },
        "feature_groups": groups,
        "analysis_modules": {
            "rhythm": rhythm,
            "bass": bass,
            "percussion": percussion,
            "musical_context": context,
        },
        "rhythm_grammar": _legacy_group(groups["rhythm_grammar"]),
        "low_frequency": _legacy_group(groups["low_frequency"]),
        "percussion_timbre": _legacy_group(groups["percussion_timbre"]),
        "sonic_profile": legacy_sonic,
        "confidence": {
            "overall": round(overall, 4),
            "rhythm": round(module_confidences[0], 4),
            "low_frequency": round(module_confidences[1], 4),
            "percussion": round(module_confidences[2], 4),
            "musical_context": round(module_confidences[3], 4),
        },
        "quality_flags": list(dict.fromkeys(flags)),
        "selected_models": list(dict.fromkeys(selected_models)),
        "model_evidence": model_evidence or {"status": "unavailable", "routes": {}},
    }
