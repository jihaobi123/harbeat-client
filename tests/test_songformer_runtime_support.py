import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import torch

from experiments.run_songformer_isolated import embedding_chunks
from experiments.songformer_runtime_support import (
    aggregate_segment_label_evidence,
    attach_segment_label_evidence,
    audio_content_key,
    build_cache_namespace,
    fingerprint_model_path,
    sha256_file_cached,
    source_revision,
)


LABELS = {
    0: "intro",
    1: "verse",
    2: "chorus",
    3: "bridge",
    4: "inst",
    5: "outro",
    6: "silence",
    26: "pre-chorus",
}


def test_aggregate_segment_label_evidence_keeps_all_allowed_classes() -> None:
    logits = np.full((3, 27), -10.0, dtype=np.float64)
    logits[0, 0] = 4.0
    logits[0, 1] = 1.0
    logits[1, 0] = 3.0
    logits[1, 1] = 2.0
    logits[2, 1] = 4.0
    logits[2, 2] = 1.0

    evidence = aggregate_segment_label_evidence(
        logits,
        segments=[{"start": 0.0, "end": 2.0, "label": "intro"}],
        frame_rate=1.0,
        allowed_label_ids=list(LABELS),
        id_to_label=LABELS,
    )

    probabilities = evidence[0]["label_probabilities"]
    assert list(probabilities) == list(LABELS.values())
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert probabilities["intro"] > probabilities["verse"]
    assert evidence[0]["label_confidence"] == pytest.approx(max(probabilities.values()))
    ranked = sorted(probabilities.values(), reverse=True)
    assert evidence[0]["label_margin"] == pytest.approx(ranked[0] - ranked[1])


def test_evidence_uses_final_segment_boundaries_and_clips_empty_windows() -> None:
    logits = np.full((4, 27), -20.0, dtype=np.float64)
    logits[:2, 0] = 8.0
    logits[2:, 2] = 8.0
    segments = [
        {"start": 0.0, "end": 2.0, "label": "intro"},
        {"start": 2.0, "end": 4.0, "label": "chorus"},
        {"start": 9.0, "end": 10.0, "label": "outro"},
    ]

    attached = attach_segment_label_evidence(
        segments,
        function_logits=logits,
        frame_rate=1.0,
        allowed_label_ids=list(LABELS),
        id_to_label=LABELS,
    )

    assert attached[0]["label_probabilities"]["intro"] > 0.99
    assert attached[1]["label_probabilities"]["chorus"] > 0.99
    assert attached[2]["label_probabilities"]["chorus"] > 0.99
    assert segments[0].get("label_probabilities") is None


def test_long_song_embedding_chunks_round_trip_cached_offsets() -> None:
    payload = {
        "global": torch.arange(18, dtype=torch.float32).reshape(1, 6, 3),
        "local": torch.arange(18, dtype=torch.float32).reshape(1, 6, 3),
        "chunk_lengths": [4, 2],
    }

    chunks = embedding_chunks(payload)

    assert [chunk["global"].shape[1] for chunk in chunks] == [4, 2]
    assert torch.equal(
        torch.cat([chunk["global"] for chunk in chunks], dim=1),
        payload["global"],
    )


def test_masked_disallowed_logits_may_be_negative_infinity() -> None:
    logits = np.full((2, 128), -np.inf, dtype=np.float64)
    for label_id in LABELS:
        logits[:, label_id] = 0.0
    logits[:, 2] = 4.0

    evidence = aggregate_segment_label_evidence(
        logits,
        segments=[{"start": 0.0, "end": 1.0, "label": "chorus"}],
        frame_rate=2.0,
        allowed_label_ids=list(LABELS),
        id_to_label=LABELS,
    )

    assert evidence[0]["label_probabilities"]["chorus"] > 0.85


def test_rounded_adjacent_boundaries_do_not_share_a_frame() -> None:
    frame_rate = 8.333
    logits = np.full((20, 27), -20.0, dtype=np.float64)
    logits[:10, 0] = 8.0
    logits[10:, 2] = 8.0
    segments = [
        {"start": 0.0, "end": 1.2, "label": "intro"},
        {"start": 1.2, "end": 2.4, "label": "chorus"},
    ]

    evidence = aggregate_segment_label_evidence(
        logits,
        segments=segments,
        frame_rate=frame_rate,
        allowed_label_ids=list(LABELS),
        id_to_label=LABELS,
    )

    assert evidence[0]["label_probabilities"]["intro"] > 0.99
    assert evidence[1]["label_probabilities"]["chorus"] > 0.99


def test_cache_namespace_changes_for_every_runtime_input() -> None:
    base = {
        "runner_version": "songformer_isolated_v2",
        "label_contract_version": "songformer_label_contract_v2",
        "songformer_source_revision": "git-a",
        "songformer_checkpoint_sha256": "sf-a",
        "musicfm_checkpoint_sha256": "music-a",
        "musicfm_stats_sha256": "stats-a",
        "muq_model_sha256": "muq-a",
        "dataset_id": "SongForm-HX-8Class:5",
        "sample_rate": 24_000,
        "encoder_layer": 10,
        "precision": "float32",
        "frame_rate": 8.333,
    }
    baseline = build_cache_namespace(base)

    replacements = {
        "runner_version": "songformer_isolated_v3",
        "label_contract_version": "songformer_label_contract_v3",
        "songformer_source_revision": "git-b",
        "songformer_checkpoint_sha256": "sf-b",
        "musicfm_checkpoint_sha256": "music-b",
        "musicfm_stats_sha256": "stats-b",
        "muq_model_sha256": "muq-b",
        "dataset_id": "another-dataset",
        "sample_rate": 48_000,
        "encoder_layer": 11,
        "precision": "float16",
        "frame_rate": 10.0,
    }
    for key, value in replacements.items():
        changed = dict(base)
        changed[key] = value
        assert build_cache_namespace(changed) != baseline, key


def test_sha256_file_cache_is_scoped_by_path_size_and_mtime(tmp_path: Path) -> None:
    model = tmp_path / "checkpoint.bin"
    manifest = tmp_path / "hashes.json"
    model.write_bytes(b"model-a")
    first_stat = model.stat()
    first = sha256_file_cached(model, manifest)

    model.write_bytes(b"model-b")
    os.utime(model, ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns))
    assert sha256_file_cached(model, manifest) == first

    os.utime(model, ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns + 1_000_000))
    second = sha256_file_cached(model, manifest)
    assert second != first

    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert str(model.resolve()) in saved["files"]


def test_audio_content_key_detects_same_size_same_mtime_replacement(tmp_path: Path) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio-content-a")
    original = audio.stat()
    first = audio_content_key(audio)

    audio.write_bytes(b"audio-content-b")
    os.utime(audio, ns=(original.st_atime_ns, original.st_mtime_ns))
    second = audio_content_key(audio)

    assert second != first


def test_directory_model_fingerprint_changes_when_weight_changes(tmp_path: Path) -> None:
    model_dir = tmp_path / "muq"
    model_dir.mkdir()
    (model_dir / "config.json").write_text('{"model":"muq"}', encoding="utf-8")
    weights = model_dir / "model.safetensors"
    weights.write_bytes(b"weights-a")
    (model_dir / "README.md").write_text("ignored documentation", encoding="utf-8")
    manifest = tmp_path / "hashes.json"

    first = fingerprint_model_path(model_dir, manifest)
    weights.write_bytes(b"weights-b")
    second = fingerprint_model_path(model_dir, manifest)

    assert first != second


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_source_revision_changes_for_uncommitted_third_party_edits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "songformer-src"
    songformer = source / "src" / "SongFormer"
    third_party = source / "src" / "third_party" / "musicfm"
    songformer.mkdir(parents=True)
    third_party.mkdir(parents=True)
    (songformer / "model.py").write_text("MODEL = 1\n", encoding="utf-8")
    module = third_party / "encoder.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "add", "src"], check=True)
    subprocess.run(
        [
            "git", "-C", str(source),
            "-c", "user.name=HarBeat Test",
            "-c", "user.email=harbeat-test@example.invalid",
            "commit", "-q", "-m", "initial",
        ],
        check=True,
    )
    manifest = tmp_path / "hashes.json"
    clean = source_revision(source, manifest)

    original = module.stat()
    module.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(module, ns=(original.st_atime_ns, original.st_mtime_ns))
    dirty = source_revision(source, manifest)

    assert dirty != clean
    assert "+dirty-tree-sha256:" in dirty
