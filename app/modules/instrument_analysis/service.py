"""Build validated Bar-aligned sidecars from isolated runtime evidence."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.modules.bar_annotations.service import timeline_fingerprint
from app.modules.instrument_analysis.alignment import (
    aggregate_probability_windows,
    align_drum_event,
)
from app.modules.instrument_analysis.runner import InstrumentRuntimeResult
from app.modules.instrument_analysis.schemas import (
    DRUM_CLASSES,
    DrumSummary,
    InstrumentAnalysisDocument,
    InstrumentBarAnalysis,
    InstrumentProbability,
    ModelEvidence,
)
from app.modules.library.bar_feature_adapter import build_canonical_timeline


def _model_evidence(model_id: str, result: Any) -> ModelEvidence:
    return ModelEvidence(
        model_id=model_id,
        model_version="upstream-pinned",
        deployment_status="shadow",
        availability=result.availability,
        checkpoint_sha256=result.checkpoint_sha256,
        source_revision=result.source_revision,
        license_status="review_required",
        error=result.error,
    )


def build_instrument_analysis_document(
    song: Any, runtime: InstrumentRuntimeResult
) -> InstrumentAnalysisDocument:
    timeline = build_canonical_timeline(song)
    if abs(runtime.duration_sec - timeline.duration_sec) > 0.05:
        raise ValueError("runtime duration does not match the canonical timeline")

    models = {
        "adtof": _model_evidence("xavriley/ADTOF-pytorch", runtime.models["adtof"]),
        "panns": _model_evidence(
            "qiuqiangkong/PANNs-Cnn14-DecisionLevelMax", runtime.models["panns"]
        ),
    }
    if runtime.status == "failed":
        return InstrumentAnalysisDocument(
            track_id=str(song.id),
            status="failed",
            duration_sec=timeline.duration_sec,
            audio_sha256=runtime.audio_sha256,
            timeline_fingerprint=timeline_fingerprint(timeline),
            taxonomy_version="instrument_taxonomy@0.1.0",
            runtime_fingerprint=runtime.runtime_fingerprint,
            models=models,
            bars=[],
            warnings=list(runtime.warnings),
        )

    events_by_bar: dict[int, list[Any]] = defaultdict(list)
    ignored_unaligned_events = 0
    for raw_event in runtime.models["adtof"].events:
        try:
            event = align_drum_event(raw_event, timeline)
        except ValueError as exc:
            if str(exc) != "drum event is outside the canonical timeline":
                raise
            ignored_unaligned_events += 1
            continue
        events_by_bar[event.bar_index].append(event)

    raw_windows = runtime.models["panns"].windows
    bars: list[InstrumentBarAnalysis] = []
    for bar_index, interval in enumerate(timeline.intervals):
        drum_events = sorted(
            events_by_bar.get(bar_index, []), key=lambda event: event.time_sec
        )
        counts = {name: 0 for name in DRUM_CLASSES}
        for event in drum_events:
            counts[event.drum_class] += 1
        duration = interval.end_sec - interval.start_sec

        available_classes = sorted(
            {
                instrument_class
                for window in raw_windows
                if isinstance(window, dict)
                for instrument_class in (window.get("broad_scores") or {})
            }
        )
        probabilities: list[InstrumentProbability] = []
        for instrument_class in available_classes:
            windows = [
                {
                    "start_sec": window.get("start_sec"),
                    "end_sec": window.get("end_sec"),
                    "probability": (window.get("broad_scores") or {}).get(
                        instrument_class
                    ),
                }
                for window in raw_windows
                if instrument_class in (window.get("broad_scores") or {})
            ]
            aggregate = aggregate_probability_windows(windows=windows, bar=interval)
            probabilities.append(
                InstrumentProbability(
                    instrument_class=instrument_class,
                    mean_probability=aggregate.mean_probability,
                    max_probability=aggregate.max_probability,
                    active_coverage=aggregate.active_coverage,
                )
            )
        bars.append(
            InstrumentBarAnalysis(
                bar_index=bar_index,
                start_sec=interval.start_sec,
                end_sec=interval.end_sec,
                drum_events=drum_events,
                drum_summary=DrumSummary(
                    event_counts=counts,
                    density_per_sec=round(len(drum_events) / duration, 6),
                ),
                instrument_probabilities=probabilities,
                validation_status="unreviewed",
            )
        )

    warnings = list(runtime.warnings) + list(timeline.warnings)
    if ignored_unaligned_events:
        warnings.append("UNALIGNED_DRUM_EVENTS_IGNORED")

    return InstrumentAnalysisDocument(
        track_id=str(song.id),
        status=runtime.status,
        duration_sec=timeline.duration_sec,
        audio_sha256=runtime.audio_sha256,
        timeline_fingerprint=timeline_fingerprint(timeline),
        taxonomy_version="instrument_taxonomy@0.1.0",
        runtime_fingerprint=runtime.runtime_fingerprint,
        models=models,
        bars=bars,
        warnings=warnings,
    )
