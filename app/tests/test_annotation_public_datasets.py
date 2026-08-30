from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.annotations.public_datasets import (
    convert_raveform_track,
    map_raveform_section_label,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "fixtures"
    / "analysis"
    / "raveform_track.valid.json"
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Intro", "intro"),
        ("Ambient-Intro", "intro"),
        ("Build-up", "build"),
        ("Buildup", "build"),
        ("Drop 2", "main"),
        ("Cooldown", "main"),
        ("Bridge", "main"),
        ("Breakdown", "breakdown"),
        ("Ambient Breakdown", "breakdown"),
        ("Outro", "outro"),
        ("Ambient-Outro", "outro"),
    ],
)
def test_maps_raveform_edm_functions_to_v1(source: str, expected: str) -> None:
    assert map_raveform_section_label(source) == expected


def test_unknown_public_label_fails_closed() -> None:
    assert map_raveform_section_label("mystery") == "unknown"
    assert map_raveform_section_label("") == "unknown"


def test_raveform_track_conversion_emits_candidate_records() -> None:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))

    records = convert_raveform_track(
        source,
        dataset_version="raveform-import-1.0.0",
        created_at="2026-08-30T09:00:00Z",
    )

    assert len(records) == 4
    assert records[0]["annotation_status"] == "candidate"
    assert records[0]["task_id"] == "structure.section_label"
    assert records[0]["value"] == "intro"
    assert records[0]["start_sec"] == 0.0
    assert records[0]["end_sec"] == 8.0
    assert records[0]["start_bar_index"] is None
    assert records[0]["candidate_source"].startswith("dataset:raveform:fixture-1")
    assert "Ambient-Intro" in records[0]["candidate_source"]
    assert records[-1]["end_sec"] == 32.0


def test_raveform_conversion_rejects_missing_track_or_section_boundaries() -> None:
    with pytest.raises(ValueError):
        convert_raveform_track({"sections": [{"label": "Intro"}]}, "dataset-1")
