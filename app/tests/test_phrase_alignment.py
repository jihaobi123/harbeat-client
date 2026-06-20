"""Phrase alignment unit tests."""
from app.modules.dj_control.spotify_mix.phrase_alignment import (
    _find_best_entry,
    _find_nearest_bar,
    _is_section_boundary,
    _score_transition_point,
    find_transition_point,
)


class TestFindNearestBar:
    def test_empty_returns_zero(self):
        assert _find_nearest_bar([], 10.0) == 0

    def test_finds_closest(self):
        downbeats = [0.0, 4.0, 8.0, 12.0, 16.0]
        assert _find_nearest_bar(downbeats, 5.0) == 1
        assert _find_nearest_bar(downbeats, 11.0) == 3
        assert _find_nearest_bar(downbeats, 15.0) == 4


class TestSectionBoundary:
    def test_chorus_label_is_boundary(self):
        phrases = [{"start": 8.0, "label": "chorus"}]
        assert _is_section_boundary(8.0, phrases)

    def test_unrelated_label_not_boundary(self):
        phrases = [{"start": 8.0, "label": "intro_repeat"}]
        assert not _is_section_boundary(8.0, phrases)

    def test_far_from_boundary(self):
        phrases = [{"start": 8.0, "label": "chorus"}]
        assert not _is_section_boundary(20.0, phrases)


class TestScoreTransitionPoint:
    def test_eight_bar_boundary_scores_higher(self):
        s8 = _score_transition_point(32.0, [], list(range(0, 64, 4)), bar_idx=8)
        s5 = _score_transition_point(20.0, [], list(range(0, 64, 4)), bar_idx=5)
        assert s8 > s5

    def test_section_boundary_bonus(self):
        phrases = [{"start": 32.0, "label": "chorus"}]
        downbeats = list(range(0, 64, 4))
        s_section = _score_transition_point(32.0, phrases, downbeats, bar_idx=8)
        s_no_section = _score_transition_point(32.0, [], downbeats, bar_idx=8)
        assert s_section > s_no_section


class TestFindBestEntry:
    def test_uses_hot_cue_intro(self):
        analysis = {
            "dj_hot_cues": [{"type": "intro_end", "time": 16.0}],
        }
        entry = _find_best_entry(analysis)
        assert entry == 16.0

    def test_falls_back_to_first_downbeat(self):
        analysis = {"downbeats": [4.0, 8.0]}
        entry = _find_best_entry(analysis)
        assert entry == 4.0

    def test_default_zero(self):
        assert _find_best_entry({}) == 0.0


class TestFindTransitionPoint:
    def test_with_bars_aligns(self):
        track_a = {
            "downbeats": [i * 4.0 for i in range(20)],  # 0, 4, 8, ..., 76
            "phrase_map": [],
        }
        track_b = {"downbeats": [0.0, 4.0]}
        exit_t, entry_t = find_transition_point(track_a, track_b, target_point_a=33.0)
        # Should snap to a bar boundary near 33.0 (probably 32.0)
        assert exit_t in track_a["downbeats"]
        assert entry_t == 0.0

    def test_no_downbeats_returns_target(self):
        exit_t, entry_t = find_transition_point({}, {}, target_point_a=20.0)
        assert exit_t == 20.0
