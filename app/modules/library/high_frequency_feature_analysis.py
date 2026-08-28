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
    unavailable_feature,
)


TARGET_SAMPLE_RATE = 22050


def _count(values) -> int:
    return 0 if values is None else len(values)


def _tempo_family(bpm: float | None) -> dict[str, Any]:
    if bpm is None or not np.isfinite(bpm) or bpm <= 0:
        return {
            "status": "unavailable", "half": None, "base": None, "double": None,
            "octave_relation_detected": False,
        }
    value = float(bpm)
    return {
        "status": "candidate_levels_only",
        "half": round(value / 2.0, 4),
        "base": round(value, 4),
        "double": round(value * 2.0, 4),
        # No second tempo observation is supplied to this layer, so exposing
        # candidates must not be misreported as a detected conflict.
        "octave_relation_detected": False,
    }


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
    native_arrays = {
        name: np.asarray(value, dtype=np.float32)
        for name, value in stems.items() if value is not None and len(value)
    }
    if original_audio is not None and len(original_audio):
        native_mix = np.asarray(original_audio, dtype=np.float32)
    else:
        native_lengths = [len(value) for value in native_arrays.values()]
        native_length = min(native_lengths) if native_lengths else 0
        native_mix = (
            sum(
                (value[:native_length] for value in native_arrays.values()),
                np.zeros(native_length, dtype=np.float32),
            )
            if native_length else None
        )
    arrays, analysis_sr = _resample_stems(native_arrays, sr)
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
        downbeats=downbeats,
        original_audio=mix,
        model_route=((model_evidence or {}).get("routes") or {}).get("bass_transcription"),
    )
    percussion = analyze_percussion_features(
        native_arrays.get("drums"), sr, drum_analysis=drum_analysis,
    )
    context = analyze_musical_context_features(
        vocals=arrays.get("vocals"),
        other=arrays.get("other"),
        original_audio=mix,
        sr=analysis_sr,
        key_profile=key_profile,
        native_other=native_arrays.get("other"),
        native_original_audio=native_mix,
        native_sr=sr,
        beat_points=beat_points,
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

    return {
        "version": STYLE_FEATURE_EVIDENCE_VERSION,
        "status": status,
        "needs_review": bool(flags),
        "reason": None,
        "music_context": {
            "bpm": bpm,
            "tempo_family": _tempo_family(bpm),
            "beat_count": _count(beat_points),
            "downbeat_count": _count(downbeats),
            "key_profile": dict(key_profile or {}),
            "analysis_sample_rate": analysis_sr,
            "high_frequency_sample_rate": sr,
            "sampling_strategy": "dual_rate_native_percussion_v1",
            "duration": round(duration, 4),
        },
        "feature_groups": groups,
        "analysis_modules": {
            "rhythm": rhythm,
            "bass": bass,
            "percussion": percussion,
            "musical_context": context,
        },
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
