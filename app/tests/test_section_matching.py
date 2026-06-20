from __future__ import annotations

from app.modules.dj_control.spotify_mix.section_matcher import plan_section_match_transition


def _song(song_id: str, *, key: str = "8A") -> dict:
    return {
        "id": song_id,
        "song_id": song_id,
        "bpm": 120.0,
        "camelot_key": key,
        "duration": 120.0,
        "energy": 0.6,
        "analysis": {
            "duration": 120.0,
            "phrase_map": [
                {"label": "intro", "start": 0.0, "end": 16.0, "energy": 0.35},
                {"label": "verse", "start": 16.0, "end": 48.0, "energy": 0.45},
                {"label": "chorus", "start": 48.0, "end": 80.0, "energy": 0.75},
                {"label": "outro", "start": 80.0, "end": 120.0, "energy": 0.55},
            ],
            "energy_curve": [
                {"time": 0.0, "energy": 0.35},
                {"time": 80.0, "energy": 0.55},
                {"time": 116.0, "energy": 0.45},
            ],
            "vocal_events": [{"start": 20.0, "end": 40.0, "confidence": 1.0}],
            "bass_risk_windows": [{"start": 80.0, "end": 120.0, "low_energy": 0.65}],
            "downbeats": [float(x) for x in range(0, 124, 2)],
        },
    }


def test_section_match_plan_is_rk_eq_band_executable():
    plan = plan_section_match_transition(_song("a"), _song("b", key="9A"))

    assert plan["transition_mode"] == "section_match"
    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["target"]["song_id"] == "b"
    assert plan["deck_a"]["eq"]["low"]
    assert plan["deck_b"]["eq"]["low"]
    assert plan["section_match"]["score"] > 0
    assert plan["section_match"]["a_section"]["label"] in {"outro", "chorus"}
    assert plan["section_match"]["b_section"]["label"] in {"chorus", "intro", "verse"}
    assert "vocal_density_avg" in plan["section_match"]["a_section"]
    assert "vocal_density_avg" in plan["section_match"]["b_section"]


def test_section_match_supports_auto_dj_mix_five_strategies():
    from app.modules.dj_control.eq_transition_presets import EQ_STRATEGIES, preset_for_strategy

    assert {
        "standard_blend",
        "energy_lift",
        "energy_drop",
        "tempo_compat",
        "cross_style",
    }.issubset(EQ_STRATEGIES)

    for strategy in EQ_STRATEGIES:
        preset = preset_for_strategy(strategy)
        assert preset["rk_style"] == "eq_band_mix"


def test_section_match_uses_beat_bar_when_phrase_data_missing():
    a = _song("a")
    b = _song("b")
    a["analysis"]["phrase_map"] = []

    plan = plan_section_match_transition(a, b)

    assert plan["transition_mode"] == "section_match"
    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["section_match"]["is_fallback"] is False
    assert plan["section_match"]["a_section"]["cut_point_source"] == "beat_bar"


def test_section_match_falls_back_when_no_phrase_or_beat_data():
    a = _song("a")
    b = _song("b")
    a["analysis"]["phrase_map"] = []
    b["analysis"]["phrase_map"] = []
    a["analysis"]["beat_points"] = []
    b["analysis"]["beat_points"] = []
    a["analysis"]["downbeats"] = []
    b["analysis"]["downbeats"] = []

    plan = plan_section_match_transition(a, b)

    assert plan["transition_mode"] == "section_match"
    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["section_match"]["is_fallback"] is True


def test_section_match_filters_hard_double_vocal_when_clean_pair_exists():
    a = _song("a")
    b = _song("b")
    a["analysis"]["vocal_events"] = [
        {"start": 116.0, "end": 120.0, "confidence": 1.0},
    ]
    b["analysis"]["vocal_events"] = [
        {"start": 48.0, "end": 52.0, "confidence": 1.0},
    ]

    plan = plan_section_match_transition(a, b)
    match = plan["section_match"]

    assert match["vocal_policy"]["hard_conflict_filtered"] is True
    assert not (
        match["a_section"]["vocal_density_end"] >= 0.6
        and match["b_section"]["vocal_density_start"] >= 0.6
    )
    assert "hard double vocal overlap" not in match["issues"]


def test_section_match_understands_legacy_enter_exit_vocal_markers():
    from app.modules.dj_control.spotify_mix.section_features import extract_section_features

    analysis = _song("legacy")["analysis"]
    analysis["vocal_events"] = [
        {"time": 80.0, "type": "enter", "confidence": 1.0, "vocal_level": 0.8},
        {"time": 120.0, "type": "exit", "confidence": 1.0, "vocal_level": 0.0},
    ]

    features = extract_section_features(
        {"label": "outro", "start": 80.0, "end": 120.0, "energy": 0.55},
        analysis,
        role="outro",
    )

    assert features["vocal_density_end"] >= 0.9
    assert features["vocal_density_avg"] >= 0.9


def test_section_match_prefers_clean_mid_late_exit_over_song_tail():
    a = _song("a")
    b = _song("b")
    a["duration"] = 180.0
    a["analysis"]["duration"] = 180.0
    a["analysis"]["phrase_map"] = [
        {"label": "intro", "start": 0.0, "end": 24.0, "energy": 0.35},
        {"label": "verse", "start": 24.0, "end": 64.0, "energy": 0.45},
        {"label": "chorus", "start": 64.0, "end": 96.0, "energy": 0.75},
        {"label": "verse", "start": 96.0, "end": 136.0, "energy": 0.50},
        {"label": "outro", "start": 136.0, "end": 180.0, "energy": 0.55},
    ]
    a["analysis"]["energy_curve"] = [
        {"time": 64.0, "energy": 0.75},
        {"time": 83.0, "energy": 0.65},
        {"time": 162.0, "energy": 0.45},
    ]
    a["analysis"]["vocal_events"] = [
        {"start": 150.0, "end": 178.0, "confidence": 1.0},
    ]
    a["analysis"]["downbeats"] = [float(x) for x in range(0, 184, 2)]

    plan = plan_section_match_transition(a, b)
    match = plan["section_match"]

    assert match["a_section"]["cut_point_source"] == "beat_bar"
    assert plan["from_at_sec"] < 140.0
    assert match["compatibility_breakdown"]["actual_max_vocal"] < 0.25
    assert "exit point is very late in the song" not in match["issues"]


def test_section_match_penalizes_actual_mix_window_vocals():
    a = _song("a")
    b = _song("b")
    a["analysis"]["vocal_events"] = [
        {"start": 100.0, "end": 110.0, "confidence": 1.0},
    ]
    b["analysis"]["vocal_events"] = [
        {"start": 50.0, "end": 56.0, "confidence": 1.0},
    ]

    plan = plan_section_match_transition(a, b)
    breakdown = plan["section_match"]["compatibility_breakdown"]

    assert "actual_a_vocal" in breakdown
    assert "actual_b_vocal" in breakdown
    assert not breakdown["actual_hard_vocal_conflict"]


def test_section_match_allows_one_sided_vocal_in_actual_mix_window():
    a = _song("a")
    b = _song("b")
    a["analysis"]["vocal_events"] = [
        {"start": 100.0, "end": 110.0, "confidence": 1.0},
    ]
    b["analysis"]["vocal_events"] = []

    plan = plan_section_match_transition(a, b)
    breakdown = plan["section_match"]["compatibility_breakdown"]

    assert breakdown["actual_max_vocal"] >= 0.25
    assert breakdown["actual_both_vocal"] == 0.0
    assert breakdown["actual_one_sided_vocal_allowed"] is True
    assert breakdown["actual_hard_vocal_conflict"] is False


def test_section_match_filters_actual_double_vocal_when_safer_pair_exists():
    a = _song("a")
    b = _song("b")
    a["analysis"]["vocal_events"] = [
        {"start": 104.0, "end": 110.0, "confidence": 1.0},
    ]
    b["analysis"]["vocal_events"] = [
        {"start": 48.0, "end": 56.0, "confidence": 1.0},
    ]

    plan = plan_section_match_transition(a, b)
    breakdown = plan["section_match"]["compatibility_breakdown"]

    assert breakdown["actual_both_vocal"] < 0.25
    assert breakdown["actual_hard_vocal_conflict"] is False


def test_energy_entry_override_rejects_double_vocal_window():
    from types import SimpleNamespace

    from app.modules.dj_control.router import _override_would_create_double_vocal

    current = SimpleNamespace(
        duration=120.0,
        vocal_events=[{"start": 80.0, "end": 90.0, "confidence": 1.0}],
    )
    target = SimpleNamespace(
        duration=120.0,
        vocal_events=[{"start": 32.0, "end": 40.0, "confidence": 1.0}],
    )
    transition = {"from_at_sec": 82.0, "fade_sec": 6.0}

    check = _override_would_create_double_vocal(
        transition,
        current=current,
        target=target,
        entry_sec=32.0,
    )

    assert check["double_vocal"] is True
    assert check["both_vocal"] >= 0.25


def test_section_match_does_not_use_legacy_filter_sweep_strategy():
    plan = plan_section_match_transition(_song("a", key="1A"), _song("b", key="8B"))

    assert plan["strategy"] != "filter_sweep"
    assert plan["rule_key"] != "section_match:filter_sweep"


def test_section_match_filter_override_maps_to_energy_lift():
    plan = plan_section_match_transition(_song("a"), _song("b"), user_strategy="filter")

    assert plan["strategy"] == "energy_lift"


def test_frequency_mix_prefers_stem_transition_windows_for_cut_points():
    a = _song("a")
    b = _song("b")
    a["analysis"]["transition_windows"] = [
        {
            "label": "breakdown",
            "start": 70.0,
            "end": 78.0,
            "energy": 0.35,
            "mix_out_score": 0.95,
            "mix_in_score": 0.25,
            "stem_tags": ["vocal_free", "drum_heavy"],
            "stem_snapshot": {"vocals": 0.05, "drums": 0.8, "bass": 0.2, "other": 0.4},
        }
    ]
    a["analysis"]["stem_activity_windows"] = [
        {"start": 70.0, "end": 78.0, "vocals": 0.05, "drums": 0.8, "bass": 0.2, "other": 0.4}
    ]
    b["analysis"]["transition_windows"] = [
        {
            "label": "intro",
            "start": 8.0,
            "end": 16.0,
            "energy": 0.45,
            "mix_in_score": 0.9,
            "mix_out_score": 0.2,
            "stem_tags": ["vocal_free", "drum_heavy"],
            "stem_snapshot": {"vocals": 0.04, "drums": 0.7, "bass": 0.25, "other": 0.4},
        }
    ]
    b["analysis"]["stem_activity_windows"] = [
        {"start": 8.0, "end": 16.0, "vocals": 0.04, "drums": 0.7, "bass": 0.25, "other": 0.4}
    ]

    plan = plan_section_match_transition(a, b)

    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["from_at_sec"] == 70.0
    assert plan["to_at_sec"] == 8.0
    assert plan["section_match"]["a_section"]["cut_point_source"] == "stem_transition_windows"
    assert plan["section_match"]["b_section"]["cut_point_source"] == "stem_transition_windows"
    assert plan["section_match"]["cut_point_policy"]["stem_audio_required"] is False


def test_frequency_mix_uses_beat_bar_fallback_when_stems_missing():
    a = _song("a")
    b = _song("b")
    a["analysis"]["phrase_map"] = []
    b["analysis"]["phrase_map"] = []
    a["analysis"]["transition_windows"] = []
    b["analysis"]["transition_windows"] = []
    a["analysis"]["beat_points"] = [float(x) for x in range(0, 124, 2)]
    b["analysis"]["beat_points"] = [float(x) for x in range(0, 64, 2)]
    a["analysis"]["downbeats"] = [float(x) for x in range(0, 124, 8)]
    b["analysis"]["downbeats"] = [float(x) for x in range(0, 64, 8)]

    plan = plan_section_match_transition(a, b)

    assert plan["transition_mode"] == "section_match"
    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["section_match"]["is_fallback"] is False
    assert plan["section_match"]["a_section"]["cut_point_source"] == "beat_bar"
    assert plan["section_match"]["b_section"]["cut_point_source"] == "beat_bar"
    assert plan["auto_strategy_selection"]["source"] == "dj_mixer_package"


def test_frequency_mix_uses_beat_bar_even_when_phrase_map_exists_without_stems():
    plan = plan_section_match_transition(_song("a"), _song("b"))

    assert plan["execution_mode"] == "eq_band_mix"
    assert plan["section_match"]["a_section"]["cut_point_source"] == "beat_bar"
    assert plan["section_match"]["b_section"]["cut_point_source"] == "beat_bar"
    assert plan["section_match"]["cut_point_policy"]["stem_audio_required"] is False
