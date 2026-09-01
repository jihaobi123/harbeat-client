"""Build SongFormer-aligned EDMFormer Shadow sidecars."""
from __future__ import annotations

from typing import Any

from app.modules.bar_annotations.section_blocks import build_section_blocks
from app.modules.bar_annotations.service import timeline_fingerprint
from app.modules.bar_annotations.songformer_sections import SongFormerSectionDocument
from app.modules.edm_structure.alignment import align_edm_probabilities
from app.modules.edm_structure.runner import EdmRuntimeResult
from app.modules.edm_structure.schemas import EdmStructureAnalysisDocument
from app.modules.library.bar_feature_adapter import build_canonical_timeline


def build_edm_structure_document(
    song: Any,
    runtime: EdmRuntimeResult,
    *,
    songformer: SongFormerSectionDocument,
    songformer_sidecar_sha256: str,
) -> EdmStructureAnalysisDocument:
    timeline = build_canonical_timeline(song)
    if str(song.id) != runtime.track_id or songformer.track_id != str(song.id):
        raise ValueError("EDM runtime, SongFormer sidecar and track must match")
    if abs(runtime.duration_sec - timeline.duration_sec) > 0.05:
        raise ValueError("EDM runtime duration does not match the canonical timeline")
    blocks = build_section_blocks(
        track_id=str(song.id), timeline=timeline, document=songformer
    )
    if not blocks:
        raise ValueError("ready SongFormer sidecar produced no canonical blocks")

    if runtime.status == "failed":
        segments = []
    else:
        segments = align_edm_probabilities(
            runtime.frames,
            blocks,
            boundary_candidates=runtime.boundary_candidates,
        )
    return EdmStructureAnalysisDocument(
        track_id=str(song.id),
        status=runtime.status,
        duration_sec=timeline.duration_sec,
        audio_sha256=runtime.audio_sha256,
        timeline_fingerprint=timeline_fingerprint(timeline),
        songformer_sidecar_sha256=songformer_sidecar_sha256,
        muq_sha256=runtime.muq_sha256,
        musicfm_sha256=runtime.musicfm_sha256,
        musicfm_stats_sha256=runtime.musicfm_stats_sha256,
        edmformer_sha256=runtime.edmformer_sha256,
        deployment_status="shadow",
        runtime_fingerprint=runtime.runtime_fingerprint,
        segments=segments,
        warnings=sorted(set(runtime.warnings).union(timeline.warnings)),
        error=runtime.error,
    )
