from __future__ import annotations

from app.modules.library.high_frequency_style_taxonomy import (
    FREESTYLE_CYPHER,
    PARTY_BAR,
    STYLE_DEFINITIONS,
    STYLE_GROUPS,
)


VALID_GROUP_FEATURES = {
    "rhythm_grammar": {
        "four_on_floor", "backbeat_2_4", "halftime_snare_3", "jersey_club",
        "tamborzao", "dembow", "tresillo", "two_step", "drill_hat",
        "breakbeat", "swing", "afro_syncopation",
    },
    "low_frequency": {
        "sub_bass", "bass_pitch_stability", "bass_slide", "kick_bass_alignment",
        "sub_808", "sliding_808", "log_drum",
    },
    "percussion_timbre": {
        "full_snare", "wide_clap", "short_rim_snap", "short_metallic",
        "sustained_metallic", "low_pitched_drum", "mid_pitched_drum",
        "hand_drum_family", "continuous_high_percussion", "tonal_percussion",
        "repeated_tonal_motif",
    },
    "vocal_delivery": {"rap_delivery", "singing", "vocal_chop"},
    "harmony": {"harmonic_complexity", "jazz_soul_harmony", "chord_change_activity"},
    "production": {
        "brightness", "dark_timbre", "distortion", "lofi_texture", "sample_texture",
        "electronic_production", "acoustic_production", "rage_synth",
    },
}


def test_taxonomy_contains_exactly_the_confirmed_21_styles_and_groups() -> None:
    assert len(STYLE_DEFINITIONS) == 21
    assert len(STYLE_GROUPS[FREESTYLE_CYPHER]) == 9
    assert len(STYLE_GROUPS[PARTY_BAR]) == 12
    assert set(STYLE_GROUPS[FREESTYLE_CYPHER]) | set(STYLE_GROUPS[PARTY_BAR]) == set(STYLE_DEFINITIONS)


def test_every_style_rule_has_bpm_positive_and_required_evidence() -> None:
    for style_id, rule in STYLE_DEFINITIONS.items():
        assert rule["name"], style_id
        assert rule["bpm_ranges"], style_id
        assert len(rule["positive"]) >= 5, style_id
        assert rule["required_any"], style_id
        assert rule["minimum_evidence"] >= 1


def test_all_rule_feature_paths_exist_in_the_v3_feature_contract() -> None:
    for style_id, rule in STYLE_DEFINITIONS.items():
        paths = set(rule["positive"]) | set(rule["negative"])
        paths |= {path for requirement in rule["required_any"] for path in requirement}
        for path in paths:
            group, feature = path.split(".", 1)
            assert feature in VALID_GROUP_FEATURES[group], (style_id, path)
