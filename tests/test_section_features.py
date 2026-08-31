from app.modules.dj_control.spotify_mix.section_features import (
    ROLE_OUTRO,
    enumerate_outro_sections,
    extract_section_features,
)
from app.modules.library.analysis import _build_transition_windows


def test_extract_features_prefers_new_label_layers() -> None:
    feature = extract_section_features(
        {
            "start": 10.0,
            "end": 18.0,
            "label": "legacy-wrong-label",
            "structure_label_candidate": "pre-chorus",
            "mix_roles": ["transition", "buildup"],
            "mix_role_scores": {"transition": 1.0, "buildup": 0.7},
        },
        {"energy_curve": [], "downbeats": [10.0, 18.0]},
        role=ROLE_OUTRO,
    )

    assert feature["label"] == "pre-chorus"
    assert feature["structure_label_candidate"] == "pre-chorus"
    assert feature["mix_roles"] == ["transition", "buildup"]
    assert feature["mix_role_scores"] == {"transition": 1.0, "buildup": 0.7}


def test_legacy_inst_is_normalized_for_existing_consumers() -> None:
    feature = extract_section_features(
        {"start": 0.0, "end": 8.0, "label": "inst"},
        {},
    )

    assert feature["label"] == "instrumental"
    assert feature["mix_roles"] == []


def test_transition_role_is_an_explicit_outro_candidate() -> None:
    analysis = {
        "duration": 100.0,
        "phrase_map": [
            {"start": 0.0, "end": 30.0, "label": "intro"},
            {"start": 30.0, "end": 55.0, "label": "verse"},
            {
                "start": 55.0,
                "end": 70.0,
                "structure_label_candidate": "pre-chorus",
                "label": "pre-chorus",
                "mix_roles": ["transition", "buildup"],
            },
            {"start": 70.0, "end": 100.0, "label": "chorus"},
        ],
    }

    candidates = enumerate_outro_sections(analysis)
    transition = next(item for item in candidates if item["label"] == "pre-chorus")

    assert "transition_role" in transition["priority_reason"]


def test_core_transition_windows_use_mix_roles_without_relabelling_structure() -> None:
    windows = _build_transition_windows([
        {
            "start": 8.0,
            "end": 16.0,
            "label": "pre-chorus",
            "mix_roles": ["transition", "buildup"],
            "energy": 0.5,
            "bars": 8,
        }
    ])

    assert windows[0]["label"] == "pre-chorus"
    assert windows[0]["mix_roles"] == ["transition", "buildup"]
    assert windows[0]["mix_out_score"] > 0.7
