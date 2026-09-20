from __future__ import annotations

import pytest

from app.modules.dj_control.auto_mixer.feature_analyzer import FeatureAnalyzer
from app.modules.dj_control.auto_mixer.mixing_strategies import MixingStrategyParams, generate_eq_band_envelopes
from app.modules.dj_control.auto_mixer.strategy_selector import StrategySelector
from app.modules.dj_control.spotify_mix.section_matcher import plan_section_match_transition


def test_feature_extraction_normalizes_energy_and_bands():
    features = FeatureAnalyzer.extract_features(
        {
            "bpm": 128.0,
            "energy": 75,
            "phrase_map": [
                {"label": "chorus", "start": 30, "end": 60},
                {"label": "verse", "start": 60, "end": 90},
            ],
        }
    )

    assert features["bpm"] == 128.0
    assert features["energy"] == pytest.approx(0.75)
    assert features["low_ratio"] + features["mid_ratio"] + features["high_ratio"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("features1", "features2", "expected_num", "expected_name"),
    [
        (
            {"bpm": 120, "energy": 0.6, "low_ratio": 0.35, "mid_ratio": 0.4, "high_ratio": 0.25},
            {"bpm": 122, "energy": 0.65, "low_ratio": 0.33, "mid_ratio": 0.42, "high_ratio": 0.25},
            1,
            "standard_blend",
        ),
        (
            {"bpm": 100, "energy": 0.4, "low_ratio": 0.3, "mid_ratio": 0.5, "high_ratio": 0.2},
            {"bpm": 102, "energy": 0.7, "low_ratio": 0.4, "mid_ratio": 0.4, "high_ratio": 0.2},
            2,
            "energy_lift",
        ),
        (
            {"bpm": 140, "energy": 0.8, "low_ratio": 0.4, "mid_ratio": 0.4, "high_ratio": 0.2},
            {"bpm": 138, "energy": 0.45, "low_ratio": 0.3, "mid_ratio": 0.5, "high_ratio": 0.2},
            3,
            "energy_drop",
        ),
        (
            {"bpm": 100, "energy": 0.6, "low_ratio": 0.35, "mid_ratio": 0.4, "high_ratio": 0.25},
            {"bpm": 130, "energy": 0.6, "low_ratio": 0.35, "mid_ratio": 0.4, "high_ratio": 0.25},
            4,
            "tempo_compat",
        ),
        (
            {"bpm": 120, "energy": 0.6, "low_ratio": 0.75, "mid_ratio": 0.2, "high_ratio": 0.05},
            {"bpm": 122, "energy": 0.6, "low_ratio": 0.1, "mid_ratio": 0.25, "high_ratio": 0.65},
            5,
            "cross_style",
        ),
    ],
)
def test_strategy_selector_package_decision_tree(features1, features2, expected_num, expected_name):
    strategy_num, strategy_name, _reason = StrategySelector.select(features1, features2)

    assert strategy_num == expected_num
    assert strategy_name == expected_name


def test_strategy_params_have_package_durations():
    assert [MixingStrategyParams.get_strategy_params(num)["fade_sec"] for num in range(1, 6)] == [
        16.0,
        24.0,
        28.0,
        20.0,
        32.0,
    ]


def test_envelopes_are_rk_db_curves_not_linear_ratios():
    envelopes = generate_eq_band_envelopes(5)
    low_values = [
        float(point[1])
        for deck in ("deck_a", "deck_b")
        for point in envelopes[deck]["eq"]["low"]
    ]

    assert min(low_values) <= -55.0
    assert max(low_values) <= 0.0
    assert envelopes["deck_a"]["filter"] is None
    assert envelopes["deck_b"]["filter"] is None
    assert {point[1] for point in envelopes["deck_a"]["fader"]} == {1.0}
    assert {point[1] for point in envelopes["deck_b"]["fader"]} == {1.0}


def test_strategy1_low_band_matches_auto_dj_mix_formula():
    envelopes = generate_eq_band_envelopes(1)
    a_low_db = envelopes["deck_a"]["eq"]["low"]
    b_low_db = envelopes["deck_b"]["eq"]["low"]

    def ratio(point):
        return 10 ** (float(point[1]) / 20.0)

    assert ratio(a_low_db[0]) == pytest.approx(1.0)
    assert ratio(b_low_db[0]) == pytest.approx(0.001, rel=0.02)
    mid = len(a_low_db) // 2
    assert ratio(a_low_db[mid]) > ratio(b_low_db[mid])
    assert ratio(a_low_db[-1]) == pytest.approx(0.001, rel=0.02)
    assert ratio(b_low_db[-1]) == pytest.approx(1.0)


def test_section_match_returns_auto_strategy_selection_and_package_duration():
    a = _song("a", energy=0.4)
    b = _song("b", energy=0.75)
    plan = plan_section_match_transition(a, b)

    selection = plan["auto_strategy_selection"]
    assert plan["transition_mode"] == "section_match"
    assert plan["execution_mode"] == "eq_band_mix"
    assert selection["source"] == "dj_mixer_package"
    assert selection["strategy_num"] == 2
    assert plan["strategy"] == "energy_lift"
    assert plan["fade_sec"] == pytest.approx(24.0)
    assert plan["duration_beats"] == 24
    assert plan["section_match"]["auto_strategy_selection"]["strategy_num"] == 2
    assert plan["deck_a"]["eq"]["low"][0][1] <= 0.0


def _song(song_id: str, *, energy: float = 0.6) -> dict:
    return {
        "id": song_id,
        "song_id": song_id,
        "bpm": 120.0,
        "camelot_key": "8A",
        "duration": 140.0,
        "energy": energy,
        "analysis": {
            "duration": 140.0,
            "phrase_map": [
                {"label": "intro", "start": 0.0, "end": 16.0, "energy": energy * 0.8},
                {"label": "verse", "start": 16.0, "end": 56.0, "energy": energy},
                {"label": "chorus", "start": 56.0, "end": 96.0, "energy": min(1.0, energy + 0.15)},
                {"label": "outro", "start": 96.0, "end": 140.0, "energy": energy * 0.85},
            ],
            "energy_curve": [
                {"time": 0.0, "energy": energy * 0.8},
                {"time": 56.0, "energy": energy},
                {"time": 96.0, "energy": energy * 0.85},
            ],
            "vocal_events": [],
            "bass_risk_windows": [],
            "downbeats": [float(x) for x in range(0, 144, 2)],
        },
    }
