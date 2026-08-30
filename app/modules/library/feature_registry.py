"""Canonical pre-style feature definitions and release gates.

The registry separates directly measured quantities, musically derived
relationships, and semantic identities.  A feature is not allowed to become
style-required merely because a DSP score crosses a hand-written threshold;
it must have a versioned calibration entry whose held-out metrics satisfy the
gate declared here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SemanticLevel = Literal["measurement", "derived", "semantic"]
ValidationStatus = Literal[
    "validated", "failed_validation", "provisional", "candidate_only",
    "unavailable", "deprecated",
]


@dataclass(frozen=True)
class FeatureDefinition:
    group: str
    name: str
    semantic_level: SemanticLevel
    default_status: ValidationStatus
    minimum_accuracy: float = 0.80
    minimum_precision: float = 0.80
    minimum_recall: float = 0.70
    minimum_f1: float = 0.80
    style_required_allowed: bool = False
    canonical_name: str | None = None


MEASUREMENTS = {
    "sub_bass", "bass_pitch_stability", "bass_slide", "kick_bass_alignment",
    "low_frequency_melody", "vocal_density", "syllabic_activity",
    "vocal_pitch_range", "pitch_sustain_ratio", "melodic_contour", "harmonic_complexity",
    "chord_change_activity",
}

DERIVED = {
    "four_on_floor", "backbeat_2_4", "halftime_snare_3", "jersey_club",
    "tamborzao", "dembow", "tresillo", "two_step", "drill_hat",
    "breakbeat", "swing", "afro_syncopation", "four_floor_stability",
    "timing_quantization", "drum_loop_repetition", "bass_reply_pattern",
    "bass_syncopation", "bass_staccato_ratio", "bass_riff_repetition",
    "bass_octave_pattern", "bass_kick_interlock", "continuous_high_percussion",
    "repeated_tonal_motif", "sample_texture", "brightness", "dark_timbre",
    "sampled_loop_tendency",
}

SEMANTIC = {
    "offbeat_open_hat", "drum_machine_consistency",
    "sustained_harmonic_bass_candidate", "sliding_bass_candidate",
    "low_percussive_bass_candidate", "808_timbre_candidate",
    "log_drum_candidate", "sub_808", "sliding_808", "log_drum",
    "full_snare", "wide_clap", "short_rim_snap", "short_metallic",
    "sustained_metallic", "low_pitched_drum", "mid_pitched_drum",
    "hand_drum_family", "tonal_percussion", "rap_delivery", "singing",
    "vocal_chop", "vocal_chop_repetition", "jazz_soul_harmony",
    "distortion", "lofi_texture", "electronic_production",
    "acoustic_production", "rage_synth", "rage_synth_candidate",
}

DEPRECATED_ALIASES = {
    "sub_808": "808_timbre_candidate",
    "sliding_808": "sliding_bass_candidate",
    "log_drum": "low_percussive_bass_candidate",
    "log_drum_candidate": "low_percussive_bass_candidate",
    "rage_synth": "rage_synth_candidate",
}


def definition_for(group: str, name: str) -> FeatureDefinition:
    """Return a conservative definition for every emitted feature."""
    if name == "analysis":
        return FeatureDefinition(group, name, "measurement", "unavailable")
    if name in DEPRECATED_ALIASES:
        return FeatureDefinition(
            group, name, "semantic", "deprecated", canonical_name=DEPRECATED_ALIASES[name]
        )
    if name in SEMANTIC:
        return FeatureDefinition(
            group, name, "semantic", "candidate_only", style_required_allowed=True,
        )
    if name in DERIVED:
        return FeatureDefinition(
            group, name, "derived", "provisional", style_required_allowed=True,
        )
    if name in MEASUREMENTS:
        return FeatureDefinition(
            group, name, "measurement", "provisional", style_required_allowed=True,
        )
    # Unknown output must fail closed until it is explicitly registered.
    return FeatureDefinition(group, name, "semantic", "candidate_only")
