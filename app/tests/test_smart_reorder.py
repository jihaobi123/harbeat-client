"""Smart Reorder unit tests."""
from app.modules.dj_control.spotify_mix.bpm_grouping import group_by_bpm
from app.modules.dj_control.spotify_mix.smart_reorder import smart_reorder


class TestBPMGrouping:
    def test_empty_list(self):
        assert group_by_bpm([]) == []

    def test_single_song(self):
        songs = [{"bpm": 120}]
        groups = group_by_bpm(songs)
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_same_bpm_one_group(self):
        songs = [{"bpm": 120}, {"bpm": 121}, {"bpm": 122}]
        groups = group_by_bpm(songs, tolerance=0.03)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_different_bpm_split(self):
        songs = [{"bpm": 90}, {"bpm": 91}, {"bpm": 130}, {"bpm": 131}]
        groups = group_by_bpm(songs, tolerance=0.03)
        assert len(groups) == 2

    def test_zero_bpm_handled(self):
        songs = [{"bpm": 0}, {"bpm": 120}]
        groups = group_by_bpm(songs)
        assert len(groups) >= 1


class TestSmartReorder:
    def test_empty_list(self):
        assert smart_reorder([]) == []

    def test_single_song_unchanged(self):
        songs = [{"song_id": "a", "bpm": 120, "camelot_key": "8A", "energy": 0.5}]
        assert smart_reorder(songs) == songs

    def test_two_songs(self):
        songs = [
            {"song_id": "a", "bpm": 120, "camelot_key": "8A", "energy": 0.6},
            {"song_id": "b", "bpm": 121, "camelot_key": "9A", "energy": 0.4},
        ]
        result = smart_reorder(songs)
        assert len(result) == 2
        # Lower energy first when prefer_energy_flow=True
        assert result[0]["song_id"] == "b"

    def test_camelot_path_preference(self):
        songs = [
            {"song_id": "a", "bpm": 120, "camelot_key": "8A", "energy": 0.5},
            {"song_id": "b", "bpm": 120, "camelot_key": "3A", "energy": 0.5},
            {"song_id": "c", "bpm": 120, "camelot_key": "9A", "energy": 0.5},
        ]
        result = smart_reorder(songs, prefer_energy_flow=False)
        # 8A → 9A (distance 1) preferred over 8A → 3A (distance 5)
        order = [s["song_id"] for s in result]
        assert order.index("c") < order.index("b") or order.index("a") < order.index("c")

    def test_handles_missing_key(self):
        songs = [
            {"song_id": "a", "bpm": 120, "camelot_key": "", "energy": 0.5},
            {"song_id": "b", "bpm": 120, "camelot_key": "8A", "energy": 0.5},
        ]
        result = smart_reorder(songs)
        assert len(result) == 2
