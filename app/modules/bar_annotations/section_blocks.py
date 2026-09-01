"""Convert SongFormer time boundaries into canonical Bar annotation blocks."""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json

from app.modules.bar_annotations.schemas import SectionAnnotationBlock
from app.modules.bar_annotations.songformer_sections import SongFormerSectionDocument
from app.modules.library.bar_feature_adapter import CanonicalTimeline


SNAP_SOURCE = "songformer_bar_snap_v1"
TIME_EPSILON_SEC = 1e-6


def _runtime_fingerprint(document: SongFormerSectionDocument) -> str:
    encoded = json.dumps(
        document.runtime_fingerprint,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _block_id(
    *,
    track_id: str,
    start_bar_index: int,
    end_bar_index: int,
    cache_namespace: str | None,
    runtime_fingerprint: str,
) -> str:
    payload = {
        "track_id": track_id,
        "start_bar_index": start_bar_index,
        "end_bar_index": end_bar_index,
        "cache_namespace": cache_namespace,
        "runtime_fingerprint": runtime_fingerprint,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sfb-" + sha256(encoded).hexdigest()[:20]


def _threshold(timeline: CanonicalTimeline, edge_index: int) -> float:
    if edge_index >= len(timeline.intervals):
        interval = timeline.intervals[-1]
    else:
        interval = timeline.intervals[edge_index]
    local_bar_duration = interval.end_sec - interval.start_sec
    return min(1.5, 0.35 * local_bar_duration)


def build_section_blocks(
    *,
    track_id: str,
    timeline: CanonicalTimeline,
    document: SongFormerSectionDocument,
) -> list[SectionAnnotationBlock]:
    """Snap model boundaries to Bars without changing model or human evidence."""

    if document.status != "ready" or not document.segments or not timeline.intervals:
        return []
    if document.track_id != track_id:
        raise ValueError("SongFormer document track_id does not match the timeline track")

    edges = [float(interval.start_sec) for interval in timeline.intervals]
    edges.append(float(timeline.intervals[-1].end_sec))
    raw_boundaries = [float(document.segments[0].start)]
    raw_boundaries.extend(float(segment.end) for segment in document.segments)

    snapped_edges = [0]
    for boundary in raw_boundaries[1:-1]:
        snapped_edges.append(
            min(range(len(edges)), key=lambda index: abs(edges[index] - boundary))
        )
    snapped_edges.append(len(edges) - 1)

    boundary_groups: dict[int, list[int]] = defaultdict(list)
    for boundary_index, edge_index in enumerate(snapped_edges):
        boundary_groups[edge_index].append(boundary_index)
    unique_edges = sorted(boundary_groups)
    runtime_fingerprint = _runtime_fingerprint(document)

    blocks: list[SectionAnnotationBlock] = []
    for start_edge, end_edge in zip(unique_edges, unique_edges[1:]):
        if end_edge <= start_edge:
            continue
        start_group = boundary_groups[start_edge]
        end_group = boundary_groups[end_edge]
        raw_start = min(raw_boundaries[index] for index in start_group)
        raw_end = max(raw_boundaries[index] for index in end_group)
        if raw_end <= raw_start:
            continue
        start_time = edges[start_edge]
        end_time = edges[end_edge]
        start_error = abs(start_time - raw_start)
        end_error = abs(end_time - raw_end)
        suppressed = max(0, len(start_group) - 1) + max(0, len(end_group) - 1)
        source_indexes = [
            index
            for index, segment in enumerate(document.segments)
            if segment.end > start_time + TIME_EPSILON_SEC
            and segment.start < end_time - TIME_EPSILON_SEC
        ]
        blocks.append(
            SectionAnnotationBlock(
                block_id=_block_id(
                    track_id=track_id,
                    start_bar_index=start_edge,
                    end_bar_index=end_edge,
                    cache_namespace=document.cache_namespace,
                    runtime_fingerprint=runtime_fingerprint,
                ),
                start_bar_index=start_edge,
                end_bar_index=end_edge,
                start_time=round(start_time, 6),
                end_time=round(end_time, 6),
                raw_start_time=round(raw_start, 6),
                raw_end_time=round(raw_end, 6),
                start_snap_error_sec=round(start_error, 6),
                end_snap_error_sec=round(end_error, 6),
                source=SNAP_SOURCE,
                source_segment_indexes=source_indexes,
                needs_review=(
                    suppressed > 0
                    or start_error > _threshold(timeline, start_edge)
                    or end_error > _threshold(timeline, max(0, end_edge - 1))
                ),
                suppressed_boundary_count=suppressed,
                model_runtime_fingerprint=runtime_fingerprint,
            )
        )
    return blocks
