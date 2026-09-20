from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.evaluate_open_drums_808 import discover_samples, repeated_sample, summarize


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.asarray([0.0, 0.5, -0.25, 0.0], dtype=np.float32), 22_050)


def test_sample_inventory_keeps_808_positive_and_other_kicks_negative(tmp_path: Path) -> None:
    _write(tmp_path / "tr-808" / "TR808WAV" / "BD" / "BD0000.WAV")
    _write(tmp_path / "tr-909" / "TR909all" / "BT0A0D0.WAV")
    _write(tmp_path / "tr-707" / "TR707WAV" / "BassDrum1.wav")
    rows = discover_samples(tmp_path)
    assert [(row["source"], row["expected"]) for row in rows] == [
        ("TR-808", True), ("TR-909", False), ("TR-707", False),
    ]


def test_repeated_sample_has_auditable_onset_grid(tmp_path: Path) -> None:
    path = tmp_path / "kick.wav"
    _write(path)
    audio, onsets = repeated_sample(path, duration_seconds=2.0, interval_seconds=0.5)
    assert len(audio) == 44_100
    assert onsets == [0.5, 1.0, 1.5]
    assert np.max(np.abs(audio)) > 0


def test_single_source_identity_audit_can_never_promote_feature() -> None:
    rows = [
        {"expected": True, "predicted": True},
        {"expected": False, "predicted": False},
    ] * 25
    result = summarize(rows)
    assert result["metrics"]["accuracy"] == 1.0
    assert result["release_gate"]["passed"] is False
    assert "single_positive_source_machine_cannot_validate_general_808_identity" in (
        result["release_gate"]["reasons"]
    )
