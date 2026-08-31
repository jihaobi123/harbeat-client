from types import SimpleNamespace

import pytest

from app.modules.dj_set.section_energy import (
    _tension_section,
    _vocal_density_section,
    compute_section_energy_map,
)


def test_instrumental_and_legacy_inst_have_the_same_vocal_density() -> None:
    instrumental = _vocal_density_section("instrumental", [], 0.0, 8.0)
    legacy = _vocal_density_section("inst", [], 0.0, 8.0)
    role_driven = _vocal_density_section(
        "unknown", [], 0.0, 8.0, mix_roles=["instrumental_focus"]
    )

    assert instrumental == legacy == role_driven == 0.15


def test_pre_chorus_mix_roles_raise_transition_tension() -> None:
    baseline = _tension_section("verse", [], 8.0, 16.0, 120.0)
    transition = _tension_section(
        "pre-chorus",
        [],
        8.0,
        16.0,
        120.0,
        mix_roles=["transition", "buildup"],
    )

    assert transition > baseline


def test_energy_map_prefers_structure_candidate_and_preserves_mix_roles() -> None:
    song = SimpleNamespace(
        duration=16.0,
        bpm=120.0,
        energy=0.6,
        phrase_map=[
            {
                "start": 0.0,
                "end": 8.0,
                "label": "legacy-wrong-label",
                "structure_label_candidate": "pre-chorus",
                "mix_roles": ["transition", "buildup"],
            },
            {"start": 8.0, "end": 16.0, "label": "inst"},
        ],
        cue_points=[],
        downbeats=[0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0],
        beat_points=[index * 0.5 for index in range(32)],
    )

    sections = compute_section_energy_map(song)

    assert sections[0].label == "pre-chorus"
    assert sections[0].mix_roles == ("transition", "buildup")
    assert sections[1].label == "instrumental"
    assert sections[0].section_vocal_density == pytest.approx(0.7)
