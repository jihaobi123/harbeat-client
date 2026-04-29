"""End-to-end offline render smoke checks for GrooveEngine."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.storage import MetadataStorage
from audio.offline_renderer import OfflineDualDeckRenderer
from logic.brain import TransitionPlanner


FIXTURES_DIR = ROOT / "fixtures"
SAMPLE_RATE = 44100


def _load(name: str):
    return MetadataStorage.load(FIXTURES_DIR / name)


def _sine_track(seconds: float, frequency: float) -> np.ndarray:
    timeline = np.arange(int(seconds * SAMPLE_RATE), dtype=np.float32) / SAMPLE_RATE
    mono = 0.16 * np.sin(2.0 * np.pi * frequency * timeline)
    return np.column_stack([mono, mono]).astype(np.float32)


def test_offline_renderer_stabilizes_output() -> None:
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    plan = TransitionPlanner().plan(track_a, track_b)
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, block_size=1024)

    audio_a = _sine_track(track_a.duration_seconds, 110.0)
    audio_b = _sine_track(track_b.duration_seconds, 220.0)
    result = renderer.render_transition(audio_a, track_a, track_a.title, plan, audio_b, track_b, track_b.title)

    peak = float(np.max(np.abs(result.audio)))
    assert result.audio.ndim == 2
    assert result.audio.shape[1] == 2
    assert peak <= 0.981
    assert result.transition_summary["render_output_gain"] > 0.0
    assert "render_peak_db" in result.transition_summary
    assert "render_headroom_db" in result.transition_summary
    assert len(result.transition_summary["notes"]) >= 2


if __name__ == "__main__":
    test_offline_renderer_stabilizes_output()
    print("offline renderer smoke checks passed")


def test_offline_renderer_summary_exposes_sync_alignment_fields() -> None:
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    plan = TransitionPlanner().plan(track_a, track_b)
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, block_size=1024)

    audio_a = _sine_track(track_a.duration_seconds, 110.0)
    audio_b = _sine_track(track_b.duration_seconds, 220.0)
    result = renderer.render_transition(audio_a, track_a, track_a.title, plan, audio_b, track_b, track_b.title)

    summary = result.transition_summary
    assert "render_anchor_delta_beats" in summary
    assert "render_phase_offset_applied" in summary
    assert "render_effective_phase_correction_beats" in summary
    assert "render_phase_error_estimate" in summary
    assert "render_drift_risk" in summary
    assert "render_long_blend_safe" in summary
    assert "render_long_overlap_safe" in summary
    assert "render_recommended_max_overlap_beats" in summary
    assert "render_sync_warning_count" in summary


def test_offline_renderer_summary_exposes_objective_metrics() -> None:
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    plan = TransitionPlanner().plan(track_a, track_b)
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, block_size=1024)

    audio_a = _sine_track(track_a.duration_seconds, 110.0)
    audio_b = _sine_track(track_b.duration_seconds, 220.0)
    result = renderer.render_transition(audio_a, track_a, track_a.title, plan, audio_b, track_b, track_b.title)

    summary = result.transition_summary
    expected_fields = [
        "peak_db",
        "rms_db",
        "headroom_db",
        "loudness_delta_db",
        "low_band_conflict",
        "bass_overlap_indicator",
        "transient_loss_indicator",
        "groove_softening_indicator",
        "vocal_overlap_risk",
    ]
    for field in expected_fields:
        assert field in summary, f"missing {field}"
        assert isinstance(summary[field], float)

    assert summary["peak_db"] <= 0.0
    assert summary["headroom_db"] >= 0.0
    for field in [
        "low_band_conflict",
        "bass_overlap_indicator",
        "transient_loss_indicator",
        "groove_softening_indicator",
        "vocal_overlap_risk",
    ]:
        assert 0.0 <= summary[field] <= 1.0
    assert -60.0 <= summary["loudness_delta_db"] <= 60.0


def test_offline_renderer_metrics_support_render_validation_scoring() -> None:
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    plan = TransitionPlanner().plan(track_a, track_b)
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, block_size=1024)

    audio_a = _sine_track(track_a.duration_seconds, 110.0)
    audio_b = _sine_track(track_b.duration_seconds, 220.0)
    result = renderer.render_transition(audio_a, track_a, track_a.title, plan, audio_b, track_b, track_b.title)

    summary = result.transition_summary
    assert isinstance(summary["low_band_conflict"], float)
    assert isinstance(summary["transient_loss_indicator"], float)
    assert isinstance(summary["groove_softening_indicator"], float)
    assert isinstance(summary["vocal_overlap_risk"], float)
