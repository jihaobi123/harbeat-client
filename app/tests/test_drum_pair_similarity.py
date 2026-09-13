from __future__ import annotations

from preprocessing.engines.drum_pair_similarity import (
    DrumPairScoreConfig,
    route_overlap_score,
    score_drum_pair,
)


def _analysis(
    *,
    kick: str = "K...K...K...K...",
    snare: str = "....S.......S...",
    hihat: str = "H.H.H.H.H.H.H.H.",
    needs_review: bool = False,
) -> dict:
    return {
        "version": "drum_transcription_consensus_v4",
        "status": "ready",
        "needs_review": needs_review,
        "detector_mode": "dedicated_model",
        "counts": {
            "kick": 32,
            "snare": 16,
            "hihat": 64,
            "bass_808": 24,
            "percussion": 8,
        },
        "pattern": {
            "resolution": 16,
            "bars_analyzed": 8,
            "dominant": {
                "kick": kick,
                "snare": snare,
                "hihat": hihat,
                "bass_808": "B...B...B...B...",
                "percussion": "........P.......",
            },
        },
        "confidence": {"overall": 0.9},
        "quality_flags": [],
    }


def test_identical_patterns_score_one() -> None:
    result = score_drum_pair("a", _analysis(), "b", _analysis())

    assert result["status"] == "ready"
    assert result["scores"]["category_overlap_score"] == 1.0
    assert result["scores"]["rhythm_landing_similarity_score"] == 1.0
    assert result["scores"]["drum_overlap_score"] == 1.0
    assert result["proposal_route"]["proposal_action"] == "continue_to_harmonic_check"
    assert result["calibration"]["selection_applied"] is False
    assert result["scope"]["style_scoring_applied"] is False
    assert result["scope"]["comparison_groups"] == [
        "kick",
        "snare_clap",
        "hihat",
        "bass_808",
        "percussion",
    ]


def test_category_absence_is_not_counted_as_a_match() -> None:
    first = _analysis()
    second = _analysis()
    second["counts"] = {
        "kick": 32,
        "snare": 0,
        "hihat": 64,
        "bass_808": 0,
        "percussion": 8,
    }

    result = score_drum_pair("a", first, "b", second)

    assert result["scores"]["category_overlap_score"] == 0.6


def test_empty_patterns_are_ignored_instead_of_rewarded() -> None:
    first = _analysis(kick="................")
    second = _analysis(kick="................")

    result = score_drum_pair("a", first, "b", second)

    assert result["evidence"]["rhythm_landing"]["kick"]["status"] == "ignored_both_absent"
    assert result["scores"]["rhythm_landing_similarity_score"] == 1.0


def test_adjacent_sixteenth_hit_gets_partial_credit() -> None:
    first = _analysis(kick="K...............")
    second = _analysis(kick=".K..............")

    tolerant = score_drum_pair("a", first, "b", second)
    strict = score_drum_pair(
        "a",
        first,
        "b",
        second,
        config=DrumPairScoreConfig(rhythm_step_tolerance=0),
    )

    assert tolerant["scores"]["rhythm_landing_similarity_score"] > strict["scores"]["rhythm_landing_similarity_score"]


def test_exact_threshold_boundaries_follow_the_proposal() -> None:
    assert route_overlap_score(0.6999)["proposal_action"] == "fx_transition_case_1"
    assert route_overlap_score(0.70)["proposal_action"] == "standard_mix"
    assert route_overlap_score(0.85)["proposal_action"] == "standard_mix"
    assert route_overlap_score(0.8501)["proposal_action"] == "continue_to_harmonic_check"


def test_missing_pattern_never_receives_a_policy_decision() -> None:
    broken = _analysis()
    broken["pattern"] = {"resolution": 16, "bars_analyzed": 0, "dominant": None}

    result = score_drum_pair("a", broken, "b", _analysis())

    assert result["status"] == "unavailable"
    assert result["scores"]["drum_overlap_score"] is None
    assert result["proposal_route"]["proposal_action"] == "manual_review"


def test_quality_flags_block_automatic_route_but_keep_raw_band() -> None:
    result = score_drum_pair(
        "a",
        _analysis(needs_review=True),
        "b",
        _analysis(),
    )

    assert result["status"] == "degraded"
    assert result["proposal_route"]["proposal_action"] == "manual_review"
    assert result["raw_threshold_route"]["proposal_action"] == "continue_to_harmonic_check"


def test_legacy_mdx_groups_are_mapped_but_missing_bass_is_explicit() -> None:
    first = _analysis()
    second = _analysis()
    for analysis in (first, second):
        analysis["counts"] = {
            "kick": 32,
            "snare": 16,
            "hihat": 64,
            "tom": 4,
            "cymbal": 2,
        }
        analysis["pattern"]["dominant"] = {
            "kick": "K...K...K...K...",
            "snare": "....S.......S...",
            "hihat": "H.H.H.H.H.H.H.H.",
        }

    result = score_drum_pair("a", first, "b", second)

    assert result["evidence"]["category"]["percussion"]["count_a"] == 6
    assert "category_group_unavailable:bass_808" in result["quality_flags"]
    assert result["proposal_route"]["proposal_action"] == "manual_review"


def test_pair_cache_is_symmetric_and_invalidates_when_analysis_changes(tmp_path) -> None:
    first = _analysis()
    second = _analysis(kick="K.......K.......")
    initial = score_drum_pair("song-a", first, "song-b", second, cache_dir=tmp_path)
    cached = score_drum_pair("song-b", second, "song-a", first, cache_dir=tmp_path)

    assert initial["cache"]["hit"] is False
    assert cached["cache"]["hit"] is True
    assert cached["cache"]["key"] == initial["cache"]["key"]
    assert cached["pair"]["songs"] == initial["pair"]["songs"]

    changed = _analysis(kick="K...............")
    invalidated = score_drum_pair("song-a", first, "song-b", changed, cache_dir=tmp_path)

    assert invalidated["cache"]["hit"] is False
    assert invalidated["cache"]["key"] != initial["cache"]["key"]
