from pathlib import Path
from types import SimpleNamespace

from app.modules.bar_annotations.pilot import PilotManifest
from app.modules.instrument_analysis.runner import InstrumentRuntimeResult
from app.modules.instrument_analysis.store import InstrumentAnalysisStore
from scripts.generate_instrument_analysis import generate_pilot_instrument_analysis


class FakeDB:
    def __init__(self, songs):
        self.songs = {song.id: song for song in songs}

    def get(self, _model, track_id):
        return self.songs.get(track_id)


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, *, track_id, audio_path, stems):
        self.calls.append((track_id, audio_path, stems))
        audio = Path(audio_path)
        import hashlib

        audio_sha = hashlib.sha256(audio.read_bytes()).hexdigest()
        return InstrumentRuntimeResult.model_validate(
            {
                "track_id": track_id,
                "audio_path": str(audio.resolve()),
                "audio_sha256": audio_sha,
                "duration_sec": 4.0,
                "status": "ready",
                "runtime_fingerprint": {"runner_version": "test"},
                "models": {
                    "adtof": {
                        "availability": "available",
                        "checkpoint_sha256": "a" * 64,
                        "source_revision": "b" * 40,
                        "events": [
                            {"time_sec": 0.5, "drum_class": "kick", "confidence": 0.9}
                        ],
                        "windows": [],
                        "labels": [],
                        "elapsed_seconds": 1.0,
                        "peak_cuda_bytes": 10,
                        "error": None,
                    },
                    "panns": {
                        "availability": "available",
                        "checkpoint_sha256": "c" * 64,
                        "source_revision": "d" * 40,
                        "events": [],
                        "windows": [
                            {
                                "start_sec": 0.0,
                                "end_sec": 4.0,
                                "scores": [0.8],
                                "broad_scores": {"bass": 0.8, "voice": 0.2},
                            }
                        ],
                        "labels": ["Bass guitar"],
                        "elapsed_seconds": 1.0,
                        "peak_cuda_bytes": 20,
                        "error": None,
                    },
                },
                "warnings": [],
            }
        )


def song(tmp_path: Path):
    audio = tmp_path / "song.wav"
    drums = tmp_path / "drums.wav"
    audio.write_bytes(b"audio")
    drums.write_bytes(b"drums")
    return SimpleNamespace(
        id="track-1",
        title="Track",
        artist="Artist",
        source_path=str(audio),
        stems={"drums": str(drums)},
        duration=4.0,
        beat_points=[0.0, 1.0, 2.0, 3.0],
        downbeats=[0.0],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 1.0},
    )


def test_backfill_skips_matching_cache_without_overwrite(tmp_path):
    track = song(tmp_path)
    store = InstrumentAnalysisStore(tmp_path / "instrument-analysis")
    runner = FakeRunner()
    kwargs = dict(
        manifest=PilotManifest("dataset-v1", ("track-1",)),
        db=FakeDB([track]),
        runner=runner,
        store=store,
        song_model=object,
    )

    first = generate_pilot_instrument_analysis(**kwargs, overwrite=False)
    second = generate_pilot_instrument_analysis(**kwargs, overwrite=False)

    assert first["generated"] == 1
    assert second["cached"] == 1
    assert len(runner.calls) == 1


def test_output_never_uses_bar_annotation_directory():
    from app.shared.config import Settings

    settings = Settings()
    assert Path(settings.instrument_analysis_dir).resolve() != Path(
        settings.bar_annotation_dir
    ).resolve()


def test_generated_sidecar_aligns_events_and_probabilities(tmp_path):
    track = song(tmp_path)
    store = InstrumentAnalysisStore(tmp_path / "instrument-analysis")
    report = generate_pilot_instrument_analysis(
        manifest=PilotManifest("dataset-v1", ("track-1",)),
        db=FakeDB([track]),
        runner=FakeRunner(),
        store=store,
        song_model=object,
    )
    document = store.load("track-1")
    assert report["generated"] == 1
    assert document is not None
    assert document.bars[0].drum_events[0].beat_position == 1.5
    bass = next(
        item
        for item in document.bars[0].instrument_probabilities
        if item.instrument_class == "bass"
    )
    assert bass.mean_probability == 0.8
    assert document.models["panns"].deployment_status == "shadow"
