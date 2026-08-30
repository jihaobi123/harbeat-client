from __future__ import annotations

import pytest

from app.modules.annotations.public_datasets import map_raveform_section_label


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
