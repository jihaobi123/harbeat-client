from types import SimpleNamespace

from app.modules.bar_annotations.songformer_sections import songformer_document
from app.modules.edm_structure.runner import EdmRuntimeResult
from app.modules.edm_structure.service import build_edm_structure_document


def song():
    return SimpleNamespace(
        id="track-edm-1",
        duration=4.0,
        beat_points=[index * 0.5 for index in range(8)],
        downbeats=[0.0, 2.0],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
    )


def probabilities(label):
    values = {
        "intro": 0.02,
        "buildup": 0.02,
        "drop": 0.02,
        "breakdown": 0.02,
        "outro": 0.01,
        "silence": 0.01,
    }
    values[label] = 0.92
    return values


def runtime():
    return EdmRuntimeResult.model_validate(
        {
            "track_id": "track-edm-1",
            "audio_path": "/data/song.wav",
            "audio_sha256": "a" * 64,
            "duration_sec": 4.0,
            "status": "ready",
            "frames": [
                {"start_sec": 0.0, "end_sec": 2.0, "probabilities": probabilities("intro")},
                {"start_sec": 2.0, "end_sec": 4.0, "probabilities": probabilities("drop")},
            ],
            "boundary_candidates": [1.9, 2.2],
            "muq_sha256": "b" * 64,
            "musicfm_sha256": "c" * 64,
            "musicfm_stats_sha256": "d" * 64,
            "edmformer_sha256": "e" * 64,
            "runtime_fingerprint": {"runner_version": "edmformer_isolated_v1"},
            "warnings": [],
            "error": None,
        }
    )


def test_service_keeps_songformer_blocks_authoritative():
    source = songformer_document(
        track_id="track-edm-1",
        audio_fingerprint="audio-fingerprint",
        runtime_fingerprint={"runner_version": "songformer_isolated_v3"},
        cache_namespace="songformer-cache-a",
        segments=[
            {"start": 0.0, "end": 2.1, "label": "intro"},
            {"start": 2.1, "end": 4.0, "label": "chorus"},
        ],
    )
    document = build_edm_structure_document(
        song(),
        runtime(),
        songformer=source,
        songformer_sidecar_sha256="f" * 64,
    )
    assert [(segment.start_bar_index, segment.end_bar_index) for segment in document.segments] == [
        (0, 1),
        (1, 2),
    ]
    assert [segment.edmformer_label_candidate for segment in document.segments] == [
        "intro",
        "drop",
    ]
    assert document.segments[0].edmformer_boundary_candidates == [1.9]
    assert document.segments[1].edmformer_boundary_candidates == [2.2]
    assert document.expanded_structure_head.model_status == "not_installed"
