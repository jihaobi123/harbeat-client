"""Build an immutable TrackAnalysis V1 envelope from persisted analysis facts."""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.modules.library.bar_feature_adapter import (
    DEFAULT_AGGREGATION_PROVENANCE_REF,
    DEFAULT_PROVENANCE_REF,
    _available,
    _missing,
    _number,
    _probability,
    build_bar_features,
    build_canonical_timeline,
)
from app.modules.library.track_analysis_v1_validation import (
    validate_track_analysis_v1_invariants,
)


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[a-fA-F0-9]{7,64}$")


@dataclass(frozen=True)
class TrackAnalysisBuildContext:
    analysis_id: str
    revision: int
    created_at: str
    audio_sha256: str
    decoded_pcm_sha256: str
    pipeline_version: str
    preprocessing_version: str
    feature_definition_version: str
    config_sha256: str
    code_commit: str
    provenance_ref: str = DEFAULT_PROVENANCE_REF
    aggregation_provenance_ref: str = DEFAULT_AGGREGATION_PROVENANCE_REF
    method_id: str = "legacy-explicit-adapter"
    method_version: str = "1.0.0"
    license_id: str | None = None

    def __post_init__(self) -> None:
        if not self.analysis_id:
            raise ValueError("analysis_id is required")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be a positive integer")
        if (
            not self.created_at
            or "T" not in self.created_at
            or not self.created_at.endswith("Z")
        ):
            raise ValueError("created_at must be an ISO 8601 UTC timestamp ending in Z")
        try:
            timestamp = datetime.fromisoformat(self.created_at[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("created_at must be a valid ISO 8601 UTC timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise ValueError("created_at must be UTC")
        for field_name in ("audio_sha256", "decoded_pcm_sha256", "config_sha256"):
            if not SHA256_RE.fullmatch(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be a 64-character lowercase SHA-256")
        if not COMMIT_RE.fullmatch(self.code_commit):
            raise ValueError("code_commit must be a 7-64 character hexadecimal revision")
        for field_name in (
            "pipeline_version",
            "preprocessing_version",
            "feature_definition_version",
            "provenance_ref",
            "aggregation_provenance_ref",
            "method_id",
            "method_version",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} is required")
        if self.provenance_ref == self.aggregation_provenance_ref:
            raise ValueError("explicit and aggregation provenance keys must be different")


def _summary_feature(
    value: Any,
    *,
    provenance_ref: str,
    confidence: Any = None,
    unavailable: bool = False,
) -> dict[str, Any]:
    number = _number(value)
    if number is None:
        return _missing(availability="unavailable" if unavailable else "not_computed")
    return _available(round(number, 6), confidence=confidence, provenance_ref=provenance_ref)


def _meter_segments(bars: list[dict[str, Any]], provenance_ref: str) -> list[dict[str, Any]]:
    if not bars:
        return []
    meter = bars[0]["timing"]["meter"]
    if meter["availability"] != "available":
        return []
    return [
        {
            "start_bar_index": 0,
            "end_bar_index": len(bars),
            "numerator": meter["value"]["numerator"],
            "denominator": meter["value"]["denominator"],
            "confidence": meter["confidence"],
            "provenance_ref": provenance_ref,
        }
    ]


def build_track_analysis_v1(
    song: Any,
    context: TrackAnalysisBuildContext,
) -> dict[str, Any]:
    """Build TrackAnalysis V1 while keeping missing values distinct from zero."""
    track_id = str(getattr(song, "id", "") or "")
    duration = _number(getattr(song, "duration", None))
    if not track_id:
        raise ValueError("track_id is required")
    if duration is None or duration <= 0:
        raise ValueError("A positive duration is required")

    timeline = build_canonical_timeline(song)
    bars = build_bar_features(
        song,
        analysis_id=context.analysis_id,
        provenance_ref=context.provenance_ref,
        aggregation_provenance_ref=context.aggregation_provenance_ref,
        timeline=timeline,
    )
    first_bar = bars[0]
    bpm = _number(getattr(song, "bpm", None))
    bpm_feature = (
        _summary_feature(
            bpm,
            confidence=getattr(song, "bpm_confidence", None),
            provenance_ref=context.provenance_ref,
            unavailable=True,
        )
        if bpm is not None and bpm > 0
        else _missing(availability="unavailable")
    )
    energy = _number(getattr(song, "energy", None))
    energy_probability = _probability(energy)
    if energy is None:
        energy_feature = _missing()
    elif energy_probability is None:
        energy_feature = _missing(availability="invalid")
    else:
        energy_feature = _available(
            energy_probability,
            confidence=None,
            provenance_ref=context.provenance_ref,
        )

    tempo_stability_raw = _number(getattr(song, "tempo_stability", None))
    tempo_stability = _probability(tempo_stability_raw)
    if tempo_stability_raw is None:
        tempo_stability_feature = _missing()
    elif tempo_stability is None:
        tempo_stability_feature = _missing(availability="invalid")
    else:
        tempo_stability_feature = _available(
            tempo_stability,
            confidence=None,
            provenance_ref=context.provenance_ref,
        )

    missing_feature_sets = sorted(
        {
            path.split(".", 1)[0]
            for bar in bars
            for path in bar["quality"]["missing_fields"]
        }
    )
    warnings = sorted(
        {
            warning
            for bar in bars
            for warning in bar["quality"]["warnings"]
        }
    )
    status = "partial" if missing_feature_sets or warnings else "succeeded"
    result = {
        "schema_name": "harbeat.track_analysis",
        "schema_version": "1.0.0",
        "analysis_id": context.analysis_id,
        "track_id": track_id,
        "revision": context.revision,
        "status": status,
        "created_at": context.created_at,
        "audio": {
            "audio_sha256": context.audio_sha256,
            "decoded_pcm_sha256": context.decoded_pcm_sha256,
            "duration_sec": round(duration, 6),
            "canonical_sample_rate_hz": 44100,
            "canonical_channels": 2,
        },
        "pipeline": {
            "pipeline_version": context.pipeline_version,
            "preprocessing_version": context.preprocessing_version,
            "feature_definition_version": context.feature_definition_version,
            "config_sha256": context.config_sha256,
            "code_commit": context.code_commit,
        },
        "timeline": {
            "beat_times_sec": list(timeline.beat_times_sec),
            "downbeat_times_sec": list(timeline.downbeat_times_sec),
            "meter_segments": _meter_segments(bars, context.provenance_ref),
            "bar_count": len(bars),
        },
        "track_summary": {
            "bpm": bpm_feature,
            "meter": deepcopy(first_bar["timing"]["meter"]),
            "key": _missing(),
            "energy_normalized": energy_feature,
            "tempo_stability": tempo_stability_feature,
        },
        "bars": bars,
        "sections": [],
        "provenance": {
            context.provenance_ref: {
                "source_type": "explicit",
                "method_id": context.method_id,
                "method_version": context.method_version,
                "model_id": None,
                "model_sha256": None,
                "dataset_version": None,
                "calibration_version": None,
                "preprocessing_version": context.preprocessing_version,
                "config_sha256": context.config_sha256,
                "code_commit": context.code_commit,
                "computed_at": context.created_at,
                "license_id": context.license_id,
            },
            context.aggregation_provenance_ref: {
                "source_type": "derived",
                "method_id": "bar-window-overlap-mean",
                "method_version": "1.0.0",
                "model_id": None,
                "model_sha256": None,
                "dataset_version": None,
                "calibration_version": None,
                "preprocessing_version": context.preprocessing_version,
                "config_sha256": context.config_sha256,
                "code_commit": context.code_commit,
                "computed_at": context.created_at,
                "license_id": context.license_id,
            }
        },
        "quality": {
            "overall_confidence": None,
            "needs_review": status == "partial",
            "missing_feature_sets": missing_feature_sets,
            "warnings": warnings,
        },
    }
    validate_track_analysis_v1_invariants(result)
    return result
