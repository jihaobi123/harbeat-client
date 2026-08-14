"""Standalone raw-audio analysis followed by planner-ready v2 extraction."""

from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from .base_analysis import analyze_audio_file
from .dj_structure_v2 import VERSION, analyze_song_dj_structure
from .version_gate import validate_dj_structure_v2


BASE_ANALYSIS_VERSION = "harbeat_base_analysis_v1"
_CAMELOT = re.compile(r"^(?:[1-9]|1[0-2])[AB]$")


class BaseAnalysisError(ValueError):
    """Raised when raw-audio analysis violates the clean module contract."""


def validate_base_analysis(payload: Mapping[str, Any], *, require_essentia: bool = False) -> None:
    bpm = _finite_float(payload.get("bpm"), "bpm")
    if not 20.0 <= bpm <= 300.0:
        raise BaseAnalysisError("bpm must be between 20 and 300")
    if _finite_float(payload.get("duration"), "duration") <= 0.0:
        raise BaseAnalysisError("duration must be positive")
    if not str(payload.get("key") or "").strip():
        raise BaseAnalysisError("key is missing")
    if not _CAMELOT.fullmatch(str(payload.get("camelot_key") or "")):
        raise BaseAnalysisError("camelot_key is invalid")
    for field in ("beat_points", "downbeats", "phrase_map", "energy_curve"):
        if not isinstance(payload.get(field), list) or not payload[field]:
            raise BaseAnalysisError(f"{field} must be a non-empty list")
    key_profile = payload.get("key_profile")
    if not isinstance(key_profile, Mapping):
        raise BaseAnalysisError("key_profile is missing")
    beat_engines = payload.get("beat_engines_used")
    if not isinstance(beat_engines, list) or not beat_engines:
        raise BaseAnalysisError("beat_engines_used is missing")
    if require_essentia:
        if key_profile.get("engine") != "essentia":
            raise BaseAnalysisError("Essentia key analysis was not used")
        if not any("essentia" in str(engine).casefold() for engine in beat_engines):
            raise BaseAnalysisError("Essentia rhythm analysis was not used")
        if key_profile.get("fallback_reason"):
            raise BaseAnalysisError("key analysis used a fallback")
        details = payload.get("beat_confidence_details") or {}
        if isinstance(details, Mapping) and details.get("fallback_reason"):
            raise BaseAnalysisError("rhythm analysis used a fallback")


def analyze_audio_for_planning(
    audio_path: str | Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    require_essentia: bool = False,
    base_analyzer: Callable[..., Mapping[str, Any]] = analyze_audio_file,
) -> dict[str, Any]:
    path = Path(audio_path).expanduser().resolve(strict=True)
    base = dict(base_analyzer(str(path), title=title, artist=artist))
    validate_base_analysis(base, require_essentia=require_essentia)
    analyzed_song = SimpleNamespace(
        source_path=str(path),
        duration=base["duration"],
        beat_points=base["beat_points"],
        downbeats=base["downbeats"],
        phrase_map=base["phrase_map"],
    )
    structure = analyze_song_dj_structure(analyzed_song)
    validate_dj_structure_v2(structure)
    return {
        "version": BASE_ANALYSIS_VERSION,
        "source_path": str(path),
        "analysis": base,
        VERSION: structure,
    }


def _finite_float(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BaseAnalysisError(f"{field} must be numeric") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise BaseAnalysisError(f"{field} must be finite")
    return number
