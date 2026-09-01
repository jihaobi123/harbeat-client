from pathlib import Path
from types import SimpleNamespace

from app.modules.bar_annotations.songformer_sections import (
    SongFormerSectionStore,
    songformer_document,
)
from app.modules.edm_structure.runner import EdmRuntimeResult
from app.modules.edm_structure.store import EdmStructureStore
from scripts.generate_edm_structure_analysis import generate_pilot_edm_structure


def song(audio_path: Path):
    return SimpleNamespace(
        id="track-1",
        source_path=str(audio_path),
        duration=4.0,
        beat_points=[index * 0.5 for index in range(8)],
        downbeats=[0.0, 2.0],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
    )


def runtime_result(audio_path: Path):
    base = {
        "intro": 0.92,
        "buildup": 0.02,
        "drop": 0.02,
        "breakdown": 0.02,
        "outro": 0.01,
        "silence": 0.01,
    }
    return EdmRuntimeResult.model_validate(
        {
            "track_id": "track-1",
            "audio_path": str(audio_path),
            "audio_sha256": __import__("hashlib").sha256(audio_path.read_bytes()).hexdigest(),
            "duration_sec": 4.0,
            "status": "ready",
            "frames": [{"start_sec": 0.0, "end_sec": 4.0, "probabilities": base}],
            "boundary_candidates": [2.0],
            "muq_sha256": "b" * 64,
            "musicfm_sha256": "c" * 64,
            "musicfm_stats_sha256": "d" * 64,
            "edmformer_sha256": "e" * 64,
            "runtime_fingerprint": {"runner_version": "edmformer_isolated_v1"},
            "warnings": [],
            "error": None,
        }
    )


class FakeDb:
    def __init__(self, item):
        self.item = item

    def get(self, _model, track_id):
        return self.item if track_id == self.item.id else None


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, **_kwargs):
        self.calls += 1
        return self.result


def test_generator_requires_songformer_and_reuses_matching_cache(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    item = song(audio)
    section_store = SongFormerSectionStore(tmp_path / "songformer")
    section_store.save(
        songformer_document(
            track_id="track-1",
            audio_fingerprint="songformer-audio",
            runtime_fingerprint={"runner_version": "songformer_isolated_v3"},
            segments=[
                {"start": 0.0, "end": 2.0, "label": "intro"},
                {"start": 2.0, "end": 4.0, "label": "verse"},
            ],
        )
    )
    runner = FakeRunner(runtime_result(audio.resolve()))
    manifest = SimpleNamespace(dataset_version="pilot-v1", track_ids=["track-1"])
    store = EdmStructureStore(tmp_path / "edm")

    first = generate_pilot_edm_structure(
        manifest=manifest,
        db=FakeDb(item),
        runner=runner,
        store=store,
        section_store=section_store,
        song_model=object,
    )
    second = generate_pilot_edm_structure(
        manifest=manifest,
        db=FakeDb(item),
        runner=runner,
        store=store,
        section_store=section_store,
        song_model=object,
    )
    assert first["generated"] == 1
    assert second["cached"] == 1
    assert runner.calls == 1
    assert len(store.load("track-1").segments) == 2


def test_generator_does_not_run_without_songformer(tmp_path):
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"audio")
    runner = FakeRunner(runtime_result(audio.resolve()))
    report = generate_pilot_edm_structure(
        manifest=SimpleNamespace(dataset_version="pilot-v1", track_ids=["track-1"]),
        db=FakeDb(song(audio)),
        runner=runner,
        store=EdmStructureStore(tmp_path / "edm"),
        section_store=SongFormerSectionStore(tmp_path / "missing"),
        song_model=object,
    )
    assert report["failed"] == 1
    assert "SongFormer" in report["tracks"][0]["error"]
    assert runner.calls == 0
