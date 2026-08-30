from __future__ import annotations

import numpy as np

from scripts.adtof_drum_worker import GM_DRUM_FAMILIES, peaks_to_events


def test_adtof_general_midi_classes_are_preserved() -> None:
    assert GM_DRUM_FAMILIES == {
        35: "kick",
        38: "snare",
        47: "tom",
        42: "hihat",
        49: "cymbal",
    }


def test_peak_conversion_uses_model_activation_as_event_confidence() -> None:
    labels = [35, 38, 47, 42, 49]
    activations = np.zeros((1, 100, 5), dtype=float)
    activations[0, 25, 0] = 0.91
    activations[0, 50, 3] = 0.73

    result = peaks_to_events(
        {35: [0.25], 42: [0.50]},
        activations,
        labels,
        fps=100,
    )

    assert result["kick"][0]["confidence"] == 0.91
    assert result["hihat"][0]["confidence"] == 0.73
    assert result["hihat"][0]["subtype"] == "closed_hihat_or_hat_family"
    assert result["snare"] == []
