from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from music_analysis.drum_analysis import pipeline
from music_analysis.drum_analysis.adtof_detector import (
    ADTOF_CLASS_NAMES,
    MIDI_LABELS,
    THRESHOLDS,
    _events_and_peaks,
)
from music_analysis.drum_analysis.mdx23c_separator import (
    MDX23CDrumSeparator,
    TARGET_SAMPLE_RATE,
)
from music_analysis.drum_analysis.schemas import DRUM_CLASSES


def _write_input(path: Path, *, sample_rate: int = 22050, seconds: float = 0.2) -> None:
    time = np.arange(int(sample_rate * seconds), dtype=np.float32) / sample_rate
    audio = 0.1 * np.sin(2.0 * np.pi * 110.0 * time)
    sf.write(path, audio, sample_rate)


def test_adtof_events_keep_activation_confidence() -> None:
    activations = np.zeros((1, 100, 5), dtype=np.float32)
    expected_frames = (10, 20, 30, 40, 50)
    for class_index, frame in enumerate(expected_frames):
        activations[0, frame, class_index] = 0.95

    events, peaks = _events_and_peaks(activations, THRESHOLDS, 100)

    assert set(events) == set(DRUM_CLASSES)
    for class_index, (name, frame) in enumerate(zip(ADTOF_CLASS_NAMES, expected_frames)):
        assert events[name] == [{"time": frame / 100, "confidence": 0.95}]
        assert peaks[MIDI_LABELS[class_index]] == [frame / 100]


def test_mdx_separator_normalizes_names_rate_and_channels(tmp_path, monkeypatch) -> None:
    source = tmp_path / "drums.wav"
    _write_input(source)
    calls: list[tuple[tuple[int, ...], int]] = []

    class FakeEngine:
        def separate(self, audio, sample_rate, progress):
            calls.append((audio.shape, sample_rate))
            base = np.ones_like(audio, dtype=np.float32) * 0.01
            return {
                "kick": base,
                "snare": base * 2,
                "toms": base * 3,
                "hh": base * 4,
                "ride": base * 5,
                "crash": base * 6,
            }

    monkeypatch.setattr(
        "music_analysis.drum_analysis.mdx23c_separator._load_engine",
        lambda _device, _cache: FakeEngine(),
    )
    separator = MDX23CDrumSeparator(device="cpu")
    outputs = separator.separate(source, tmp_path / "stems")

    assert tuple(outputs) == DRUM_CLASSES
    assert calls[0][0][1] == 2
    assert calls[0][1] == TARGET_SAMPLE_RATE
    for name, path in outputs.items():
        assert path.name == f"{name}.wav"
        info = sf.info(path)
        assert info.samplerate == TARGET_SAMPLE_RATE
        assert info.channels == 2


def test_mdx_cuda_oom_retries_on_cpu(tmp_path, monkeypatch) -> None:
    source = tmp_path / "drums.wav"
    _write_input(source, sample_rate=44100)
    separator = MDX23CDrumSeparator(device="cpu")
    separator.device = "cuda"
    devices: list[str] = []

    def fake_infer(audio, device):
        devices.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA out of memory")
        base = np.zeros_like(audio, dtype=np.float32)
        return {
            "kick": base,
            "snare": base,
            "toms": base,
            "hh": base,
            "ride": base,
            "crash": base,
        }

    monkeypatch.setattr(separator, "_infer", fake_infer)
    outputs = separator.separate(source, tmp_path / "stems")

    assert devices == ["cuda", "cpu"]
    assert separator.device == "cpu"
    assert set(outputs) == set(DRUM_CLASSES)


def test_pipeline_writes_contract_and_keeps_branches_independent(tmp_path, monkeypatch) -> None:
    source = tmp_path / "drums.wav"
    _write_input(source, sample_rate=44100)
    calls: list[tuple[str, Path]] = []

    class FakeSeparator:
        def __init__(self, device):
            self.device = "cpu"

        def separate(self, input_path, output_dir):
            calls.append(("separator", Path(input_path)))
            outputs = {}
            for name in DRUM_CLASSES:
                path = Path(output_dir) / f"{name}.wav"
                sf.write(path, np.zeros((32, 2), dtype=np.float32), 44100)
                outputs[name] = path
            return outputs

    class FakeDetector:
        def __init__(self, device):
            pass

        def transcribe(self, input_path, midi_path):
            calls.append(("detector", Path(input_path)))
            path = Path(midi_path)
            path.write_bytes(b"MThd")
            return {
                "events": {
                    name: ([{"time": 0.1, "confidence": 0.9}] if name == "kick" else [])
                    for name in DRUM_CLASSES
                },
                "midi_path": path,
                "device": "cpu",
                "thresholds": list(THRESHOLDS),
            }

    monkeypatch.setattr(pipeline, "MDX23CDrumSeparator", FakeSeparator)
    monkeypatch.setattr(pipeline, "ADTOFDrumDetector", FakeDetector)
    output_dir = tmp_path / "drum_analysis"

    result = pipeline.analyze_drums(str(source), str(output_dir), "cpu")

    assert calls == [("separator", source.resolve()), ("detector", source.resolve())]
    assert set(result["stems"]) == set(DRUM_CLASSES)
    assert result["events"]["kick"] == [{"time": 0.1, "confidence": 0.9}]
    events = json.loads((output_dir / "drum_events.json").read_text())
    meta = json.loads((output_dir / "analysis_meta.json").read_text())
    assert events["sample_rate"] == 44100
    assert events["fps"] == 100
    assert meta["status"] == "ready"
    assert meta["architecture"]["independent_branches"] is True


def test_pipeline_records_failure_metadata(tmp_path, monkeypatch) -> None:
    source = tmp_path / "drums.wav"
    _write_input(source)

    class FailingSeparator:
        def __init__(self, device):
            pass

        def separate(self, input_path, output_dir):
            raise RuntimeError("checkpoint download failed")

    monkeypatch.setattr(pipeline, "MDX23CDrumSeparator", FailingSeparator)
    output_dir = tmp_path / "failed"

    try:
        pipeline.analyze_drums(str(source), str(output_dir), "cpu")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected pipeline failure")

    meta = json.loads((output_dir / "analysis_meta.json").read_text())
    assert meta["status"] == "failed"
    assert meta["error"] == "checkpoint download failed"
