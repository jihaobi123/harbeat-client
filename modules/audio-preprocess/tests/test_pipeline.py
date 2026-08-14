from pathlib import Path

import pytest

from harbeat_audio_preprocess.pipeline import BaseAnalysisError, validate_base_analysis


def valid_payload() -> dict:
    return {
        "bpm": 120.0,
        "duration": 180.0,
        "key": "C major",
        "camelot_key": "8B",
        "beat_points": [0.0, 0.5, 1.0, 1.5],
        "downbeats": [0.0],
        "phrase_map": [{"start": 0.0, "end": 16.0}],
        "energy_curve": [{"start": 0.0, "end": 4.0, "energy": 0.5}],
        "key_profile": {"engine": "essentia", "fallback_reason": None},
        "beat_engines_used": ["essentia_rhythmextractor2013"],
        "beat_confidence_details": {},
    }


def test_accepts_complete_essentia_payload() -> None:
    validate_base_analysis(valid_payload(), require_essentia=True)


def test_rejects_fallback_when_essentia_is_required() -> None:
    payload = valid_payload()
    payload["key_profile"] = {"engine": "librosa_chroma_fallback", "fallback_reason": "missing"}
    with pytest.raises(BaseAnalysisError, match="Essentia key"):
        validate_base_analysis(payload, require_essentia=True)


def test_rejects_missing_planner_fields() -> None:
    payload = valid_payload()
    payload["phrase_map"] = []
    with pytest.raises(BaseAnalysisError, match="phrase_map"):
        validate_base_analysis(payload)
