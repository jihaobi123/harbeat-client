"""Duration-weight EDMFormer evidence inside canonical SongFormer Bar blocks."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from app.modules.edm_structure.schemas import EDM_LABELS, EdmSegmentCandidate


def _value(source: Any, name: str) -> Any:
    return source.get(name) if isinstance(source, Mapping) else getattr(source, name)


def _probabilities(frame: Any) -> dict[str, float]:
    raw = _value(frame, "probabilities")
    if not isinstance(raw, Mapping) or set(raw) != set(EDM_LABELS):
        raise ValueError("EDM frame must contain all six probabilities")
    values = {label: float(raw[label]) for label in EDM_LABELS}
    if any(not math.isfinite(value) or value < 0 for value in values.values()):
        raise ValueError("EDM frame probabilities must be finite and non-negative")
    total = sum(values.values())
    if total <= 0:
        raise ValueError("EDM frame probabilities cannot all be zero")
    return {label: value / total for label, value in values.items()}


def align_edm_probabilities(
    frames: Sequence[Any],
    songformer_blocks: Sequence[Any],
    *,
    boundary_candidates: Sequence[float] = (),
) -> list[EdmSegmentCandidate]:
    results: list[EdmSegmentCandidate] = []
    for block in songformer_blocks:
        start = float(_value(block, "start_time"))
        end = float(_value(block, "end_time"))
        if end <= start:
            raise ValueError("SongFormer block end must be greater than start")
        weighted = {label: 0.0 for label in EDM_LABELS}
        maxima = {label: 0.0 for label in EDM_LABELS}
        observed = 0.0
        for frame in frames:
            frame_start = float(_value(frame, "start_sec"))
            frame_end = float(_value(frame, "end_sec"))
            overlap = min(end, frame_end) - max(start, frame_start)
            if overlap <= 0:
                continue
            probabilities = _probabilities(frame)
            observed += overlap
            for label in EDM_LABELS:
                weighted[label] += probabilities[label] * overlap
                maxima[label] = max(maxima[label], probabilities[label])
        if observed <= 0:
            raise ValueError("SongFormer block has no overlapping EDMFormer evidence")
        means = {label: weighted[label] / observed for label in EDM_LABELS}
        total = sum(means.values())
        normalized = {label: round(means[label] / total, 7) for label in EDM_LABELS}
        rounding_error = 1.0 - sum(normalized.values())
        top = max(normalized, key=normalized.get)
        normalized[top] = round(normalized[top] + rounding_error, 7)
        results.append(
            EdmSegmentCandidate(
                canonical_section_id=str(_value(block, "block_id")),
                start_bar_index=int(_value(block, "start_bar_index")),
                end_bar_index=int(_value(block, "end_bar_index")),
                start_sec=start,
                end_sec=end,
                canonical_boundary_source="songformer_bar_snap_v1",
                edmformer_label_candidate=top,
                edmformer_label_probabilities=normalized,
                edmformer_label_max_probabilities={
                    label: round(maxima[label], 7) for label in EDM_LABELS
                },
                edmformer_boundary_candidates=sorted(
                    round(float(boundary), 6)
                    for boundary in boundary_candidates
                    if start < float(boundary) < end
                ),
                validation_status="unreviewed",
            )
        )
    return results

