from scripts.evaluate_drum_transcriber import MIDI_FAMILY, merged_event_family


def test_reference_midi_taxonomy_matches_five_class_worker() -> None:
    assert MIDI_FAMILY[35] == "kick"
    assert MIDI_FAMILY[36] == "kick"
    assert MIDI_FAMILY[38] == "snare"
    assert MIDI_FAMILY[46] == "hihat"
    assert MIDI_FAMILY[47] == "tom"
    assert MIDI_FAMILY[51] == "cymbal"
    assert 33 not in MIDI_FAMILY


def test_high_percussion_merge_does_not_claim_open_hat_identity() -> None:
    result = merged_event_family(
        {"hihat": [0.5], "cymbal": [{"time": 1.0}], "snare": [0.75]},
        ("hihat", "cymbal"),
    )

    assert result == {"merged": [0.5, {"time": 1.0}]}
