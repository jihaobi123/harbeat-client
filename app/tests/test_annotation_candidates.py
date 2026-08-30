from __future__ import annotations

from types import SimpleNamespace

from app.modules.annotations.candidates import activity_state, build_candidate_bars


def _song(**overrides):
    values = {
        "id": "track-candidate-1",
        "duration": 4.0,
        "beat_points": [index * 0.5 for index in range(8)],
        "downbeats": [0.0, 2.0],
        "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.95},
        "bpm": 120.0,
        "beat_confidence": 0.94,
        "stem_activity_windows": [
            {"start": 0.0, "end": 2.0, "vocals": 0.0, "drums": 0.8, "bass": 0.4},
            {"start": 2.0, "end": 4.0, "vocals": 0.8, "drums": 0.75, "bass": 0.7},
        ],
        "energy_curve": [],
        "phrase_map": [
            {"start": 0.0, "end": 2.0, "label": "intro", "confidence": 0.82},
            {"start": 2.0, "end": 4.0, "label": "drop", "confidence": 0.76},
        ],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_activity_thresholds_fail_closed_on_missing_values() -> None:
    assert activity_state(None) == "unknown"
    assert activity_state(0.0) == "absent"
    assert activity_state(0.149) == "absent"
    assert activity_state(0.15) == "background"
    assert activity_state(0.649) == "background"
    assert activity_state(0.65) == "foreground"


def test_candidates_use_phrase_overlap_and_stem_activity() -> None:
    bars = build_candidate_bars(_song())

    assert len(bars) == 2
    assert bars[0]["start_sec"] == 0.0
    assert bars[0]["end_sec"] == 2.0
    assert bars[0]["section"]["value"] == "intro"
    assert bars[0]["section"]["source_label"] == "intro"
    assert bars[0]["section"]["confidence"] == 0.82
    assert bars[0]["elements"]["drums"]["value"] == "foreground"
    assert bars[0]["elements"]["vocal"]["value"] == "absent"
    assert bars[0]["elements"]["bass"]["value"] == "background"
    assert bars[0]["elements"]["melody"]["value"] == "unknown"


def test_candidate_transition_marks_entering_without_hiding_activity() -> None:
    bars = build_candidate_bars(_song())

    vocal = bars[1]["elements"]["vocal"]
    assert vocal["value"] == "entering"
    assert vocal["activity"] == 0.8
    assert vocal["source"] == "analysis:stem_activity:v1"
    assert bars[1]["section"]["value"] == "main"


def test_section_without_overlapping_phrase_is_unknown() -> None:
    bars = build_candidate_bars(_song(phrase_map=[]))

    assert all(bar["section"]["value"] == "unknown" for bar in bars)
