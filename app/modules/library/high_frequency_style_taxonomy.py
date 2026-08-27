"""Executable music rules for the 21 high-frequency styles.

Groups describe product use-cases only.  Every style is scored in parallel;
the classifier does not first force a track into one of the two groups.
"""
from __future__ import annotations

from typing import Any


STYLE_TAXONOMY_VERSION = "high_frequency_styles_v3"
FREESTYLE_CYPHER = "freestyle_cypher"
PARTY_BAR = "party_bar"


def _style(
    name: str,
    group: str,
    bpm_ranges: list[tuple[float, float]],
    positive: dict[str, float],
    *,
    negative: dict[str, float] | None = None,
    required_any: list[list[str]] | None = None,
    minimum_evidence: int = 3,
) -> dict[str, Any]:
    return {
        "name": name,
        "group": group,
        "bpm_ranges": [list(value) for value in bpm_ranges],
        "positive": positive,
        "negative": negative or {},
        "required_any": required_any or [],
        "minimum_evidence": minimum_evidence,
    }


STYLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "boombap": _style("Boombap", FREESTYLE_CYPHER, [(75, 105)], {
        "rhythm_grammar.backbeat_2_4": 1.5,
        "rhythm_grammar.swing": 0.8,
        "production.sample_texture": 1.2,
        "production.lofi_texture": 1.0,
        "production.acoustic_production": 0.5,
        "vocal_delivery.rap_delivery": 0.7,
    }, negative={"rhythm_grammar.four_on_floor": 0.8, "low_frequency.sliding_bass_candidate": 0.6},
        required_any=[["rhythm_grammar.backbeat_2_4"], ["production.sample_texture", "production.lofi_texture"]]),
    "trap": _style("Trap", FREESTYLE_CYPHER, [(65, 88), (130, 176)], {
        "rhythm_grammar.halftime_snare_3": 1.2,
        "low_frequency.sustained_harmonic_bass_candidate": 1.1,
        "low_frequency.808_timbre_candidate": 0.3,
        "rhythm_grammar.drill_hat": 0.35,
        "low_frequency.bass_slide": 0.25,
        "percussion_timbre.short_metallic": 1.0,
        "vocal_delivery.rap_delivery": 0.6,
    }, negative={"rhythm_grammar.four_on_floor": 0.8},
        required_any=[["rhythm_grammar.halftime_snare_3"], ["low_frequency.sustained_harmonic_bass_candidate", "low_frequency.sub_bass"]]),
    "funk": _style("Funk", FREESTYLE_CYPHER, [(90, 122)], {
        "rhythm_grammar.backbeat_2_4": 1.0,
        "rhythm_grammar.breakbeat": 0.8,
        "rhythm_grammar.swing": 0.6,
        "percussion_timbre.hand_drum_family": 0.5,
        "low_frequency.kick_bass_alignment": 0.9,
        "low_frequency.low_frequency_melody": 1.0,
        "low_frequency.bass_reply_pattern": 0.7,
        "production.acoustic_production": 0.8,
        "harmony.chord_change_activity": 0.5,
    }, required_any=[
        ["rhythm_grammar.backbeat_2_4", "rhythm_grammar.breakbeat"],
        ["low_frequency.low_frequency_melody", "low_frequency.bass_reply_pattern", "low_frequency.kick_bass_alignment"],
    ]),
    "breakbeat": _style("Breakbeat", FREESTYLE_CYPHER, [(90, 145)], {
        "rhythm_grammar.breakbeat": 1.7,
        "rhythm_grammar.backbeat_2_4": 0.7,
        "production.sample_texture": 0.8,
        "percussion_timbre.full_snare": 0.5,
        "rhythm_grammar.swing": 0.4,
    }, negative={"rhythm_grammar.four_on_floor": 1.0},
        required_any=[["rhythm_grammar.breakbeat"]]),
    "soul_neo_soul": _style("Soul/Neo-Soul", FREESTYLE_CYPHER, [(65, 108)], {
        "vocal_delivery.singing": 1.2,
        "harmony.jazz_soul_harmony": 1.4,
        "harmony.harmonic_complexity": 0.8,
        "rhythm_grammar.swing": 0.7,
        "production.acoustic_production": 0.7,
        "production.dark_timbre": 0.3,
    }, required_any=[["vocal_delivery.singing"], ["harmony.jazz_soul_harmony"]]),
    "jazz_hiphop": _style("Jazz-HipHop", FREESTYLE_CYPHER, [(72, 112)], {
        "rhythm_grammar.backbeat_2_4": 0.8,
        "rhythm_grammar.swing": 0.8,
        "harmony.jazz_soul_harmony": 1.5,
        "harmony.harmonic_complexity": 0.8,
        "production.sample_texture": 0.9,
        "production.lofi_texture": 0.5,
    }, negative={"rhythm_grammar.four_on_floor": 0.5},
        required_any=[["harmony.jazz_soul_harmony"], ["production.sample_texture"]]),
    "afro_afrobeats": _style("Afro/Afrobeats", FREESTYLE_CYPHER, [(90, 122)], {
        "rhythm_grammar.afro_syncopation": 1.5,
        "percussion_timbre.continuous_high_percussion": 0.9,
        "percussion_timbre.hand_drum_family": 1.0,
        "rhythm_grammar.tresillo": 0.6,
        "vocal_delivery.singing": 0.5,
        "production.acoustic_production": 0.4,
    }, negative={"rhythm_grammar.four_on_floor": 0.5, "rhythm_grammar.dembow": 0.4},
        required_any=[["rhythm_grammar.afro_syncopation"], ["percussion_timbre.hand_drum_family", "percussion_timbre.continuous_high_percussion"]]),
    "house": _style("House", FREESTYLE_CYPHER, [(115, 133)], {
        "rhythm_grammar.four_on_floor": 1.8,
        "rhythm_grammar.backbeat_2_4": 0.6,
        "percussion_timbre.sustained_metallic": 0.8,
        "production.electronic_production": 1.1,
        "production.brightness": 0.5,
    }, negative={"rhythm_grammar.halftime_snare_3": 0.3},
        required_any=[["rhythm_grammar.four_on_floor"], ["production.electronic_production"]]),
    "grime_uk_hiphop": _style("Grime/UK Hip-Hop", FREESTYLE_CYPHER, [(65, 75), (130, 145)], {
        "vocal_delivery.rap_delivery": 1.0,
        "rhythm_grammar.backbeat_2_4": 0.7,
        "rhythm_grammar.halftime_snare_3": 0.7,
        "production.electronic_production": 0.9,
        "production.dark_timbre": 0.8,
        "production.distortion": 0.4,
    }, negative={"rhythm_grammar.four_on_floor": 0.6},
        required_any=[["vocal_delivery.rap_delivery"], ["production.electronic_production"]]),
    "rnb": _style("R&B", PARTY_BAR, [(60, 108)], {
        "vocal_delivery.singing": 1.5,
        "harmony.jazz_soul_harmony": 0.9,
        "rhythm_grammar.swing": 0.7,
        "rhythm_grammar.backbeat_2_4": 0.6,
        "rhythm_grammar.halftime_snare_3": 0.4,
        "production.acoustic_production": 0.4,
    }, negative={"production.rage_synth_candidate": 0.7}, required_any=[["vocal_delivery.singing"]]),
    "disco": _style("Disco", PARTY_BAR, [(105, 132)], {
        "rhythm_grammar.four_on_floor": 1.5,
        "rhythm_grammar.backbeat_2_4": 0.7,
        "percussion_timbre.sustained_metallic": 0.8,
        "production.acoustic_production": 0.35,
        "production.brightness": 0.6,
        "low_frequency.kick_bass_alignment": 0.5,
        "low_frequency.low_frequency_melody": 0.8,
        "harmony.chord_change_activity": 0.7,
    }, negative={"production.dark_timbre": 0.5},
        required_any=[
            ["rhythm_grammar.four_on_floor"],
            [
                "percussion_timbre.sustained_metallic",
                "low_frequency.low_frequency_melody",
                "harmony.chord_change_activity",
            ],
        ]),
    "jersey_club": _style("Jersey Club", PARTY_BAR, [(130, 152)], {
        "rhythm_grammar.jersey_club": 1.9,
        "vocal_delivery.vocal_chop_repetition": 1.0,
        "percussion_timbre.short_metallic": 0.5,
        "production.electronic_production": 0.8,
        "low_frequency.sub_bass": 0.5,
    }, negative={"rhythm_grammar.four_on_floor": 0.5}, required_any=[["rhythm_grammar.jersey_club"]]),
    "drill": _style("Drill", PARTY_BAR, [(65, 76), (130, 152)], {
        "rhythm_grammar.halftime_snare_3": 1.0,
        "rhythm_grammar.drill_hat": 1.3,
        "low_frequency.bass_slide": 1.0,
        "low_frequency.sliding_bass_candidate": 0.7,
        "low_frequency.808_timbre_candidate": 0.2,
        "production.dark_timbre": 0.8,
        "vocal_delivery.rap_delivery": 0.5,
    }, negative={"rhythm_grammar.four_on_floor": 0.9},
        required_any=[["rhythm_grammar.drill_hat"], ["low_frequency.bass_slide", "low_frequency.sliding_bass_candidate"]]),
    "amapiano": _style("Amapiano", PARTY_BAR, [(106, 116)], {
        "low_frequency.bass_reply_pattern": 1.2,
        "low_frequency.low_percussive_bass_candidate": 0.8,
        "low_frequency.low_frequency_melody": 0.5,
        "rhythm_grammar.afro_syncopation": 0.9,
        "percussion_timbre.continuous_high_percussion": 0.7,
        "percussion_timbre.hand_drum_family": 0.6,
        "harmony.jazz_soul_harmony": 0.5,
        "vocal_delivery.singing": 0.4,
    }, negative={"rhythm_grammar.dembow": 0.5},
        required_any=[["rhythm_grammar.afro_syncopation"], ["low_frequency.bass_reply_pattern", "low_frequency.low_percussive_bass_candidate"]]),
    "moombahton": _style("Moombahton", PARTY_BAR, [(95, 116)], {
        "rhythm_grammar.dembow": 1.4,
        "rhythm_grammar.four_on_floor": 0.8,
        "percussion_timbre.hand_drum_family": 0.7,
        "percussion_timbre.sustained_metallic": 0.5,
        "production.electronic_production": 1.0,
    }, required_any=[["rhythm_grammar.dembow"], ["production.electronic_production"]]),
    "dancehall": _style("Dancehall", PARTY_BAR, [(80, 112)], {
        "rhythm_grammar.dembow": 1.6,
        "rhythm_grammar.tresillo": 0.8,
        "percussion_timbre.hand_drum_family": 0.8,
        "vocal_delivery.singing": 0.4,
        "production.acoustic_production": 0.4,
    }, negative={"rhythm_grammar.four_on_floor": 0.8}, required_any=[["rhythm_grammar.dembow"]]),
    "baile_funk": _style("Baile Funk", PARTY_BAR, [(125, 152)], {
        "rhythm_grammar.tamborzao": 1.9,
        "percussion_timbre.tonal_percussion": 0.8,
        "percussion_timbre.repeated_tonal_motif": 0.7,
        "production.distortion": 0.8,
        "vocal_delivery.rap_delivery": 0.5,
    }, negative={"rhythm_grammar.dembow": 0.4}, required_any=[["rhythm_grammar.tamborzao"]]),
    "memphis_trap": _style("Memphis Trap", PARTY_BAR, [(60, 82), (120, 164)], {
        "rhythm_grammar.halftime_snare_3": 1.0,
        "low_frequency.sustained_harmonic_bass_candidate": 0.8,
        "low_frequency.808_timbre_candidate": 0.2,
        "percussion_timbre.tonal_percussion": 0.9,
        "percussion_timbre.repeated_tonal_motif": 1.0,
        "production.lofi_texture": 0.7,
        "production.dark_timbre": 0.6,
        "vocal_delivery.rap_delivery": 0.5,
    }, negative={"rhythm_grammar.four_on_floor": 0.6},
        required_any=[["rhythm_grammar.halftime_snare_3", "low_frequency.sustained_harmonic_bass_candidate"], ["percussion_timbre.repeated_tonal_motif"]]),
    "rage": _style("Rage", PARTY_BAR, [(70, 88), (140, 176)], {
        "low_frequency.sustained_harmonic_bass_candidate": 0.8,
        "low_frequency.808_timbre_candidate": 0.2,
        "production.rage_synth_candidate": 1.4,
        "production.distortion": 0.9,
        "production.brightness": 0.7,
        "production.electronic_production": 0.8,
        "vocal_delivery.rap_delivery": 0.4,
    }, required_any=[["production.rage_synth_candidate", "production.electronic_production"], ["low_frequency.sustained_harmonic_bass_candidate", "low_frequency.sub_bass"]]),
    "uk_garage": _style("UK Garage", PARTY_BAR, [(125, 142)], {
        "rhythm_grammar.two_step": 1.7,
        "rhythm_grammar.swing": 1.0,
        "rhythm_grammar.backbeat_2_4": 0.7,
        "low_frequency.sub_bass": 0.7,
        "vocal_delivery.vocal_chop_repetition": 0.5,
        "vocal_delivery.singing": 0.4,
        "production.electronic_production": 0.7,
    }, negative={"rhythm_grammar.four_on_floor": 0.7}, required_any=[["rhythm_grammar.two_step"]]),
    "trap_soul": _style("Trap-Soul", PARTY_BAR, [(60, 88), (120, 176)], {
        "rhythm_grammar.halftime_snare_3": 1.2,
        "low_frequency.sustained_harmonic_bass_candidate": 0.35,
        "low_frequency.808_timbre_candidate": 0.9,
        "vocal_delivery.singing": 1.4,
        "harmony.jazz_soul_harmony": 0.8,
        "production.dark_timbre": 0.5,
        "rhythm_grammar.swing": 0.3,
    }, negative={"production.rage_synth_candidate": 0.6, "rhythm_grammar.four_on_floor": 1.0},
        required_any=[
            ["vocal_delivery.singing"],
            ["rhythm_grammar.halftime_snare_3"],
            ["low_frequency.808_timbre_candidate", "production.dark_timbre"],
        ]),
}


STYLE_IDS = tuple(STYLE_DEFINITIONS)
STYLE_GROUPS = {
    FREESTYLE_CYPHER: tuple(style_id for style_id, rule in STYLE_DEFINITIONS.items() if rule["group"] == FREESTYLE_CYPHER),
    PARTY_BAR: tuple(style_id for style_id, rule in STYLE_DEFINITIONS.items() if rule["group"] == PARTY_BAR),
}
