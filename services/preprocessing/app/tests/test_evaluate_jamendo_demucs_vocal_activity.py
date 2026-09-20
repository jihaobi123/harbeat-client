from __future__ import annotations

import numpy as np

from scripts.evaluate_jamendo_demucs_vocal_activity import (
    labels_at_times,
    legacy_activity,
)


def test_labels_at_times_respects_manual_boundaries() -> None:
    labels = labels_at_times(
        np.asarray([0.0, 0.9, 1.0, 1.9, 2.0]),
        [(0.0, 1.0, False), (1.0, 2.0, True)],
    )
    assert labels.tolist() == [False, False, True, True, False]


def test_legacy_activity_reproduces_relative_rms_gate() -> None:
    audio = np.zeros(22_050 * 2, dtype=np.float32)
    audio[22_050:] = 0.5
    active, gate = legacy_activity(audio)
    assert gate > 0
    assert np.mean(active[: len(active) // 3]) < 0.1
    assert np.mean(active[-len(active) // 3 :]) > 0.9
