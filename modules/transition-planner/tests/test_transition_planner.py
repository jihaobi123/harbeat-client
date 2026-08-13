from types import SimpleNamespace
import unittest

from harbeat_transition_planner import (
    plan_default_transition,
    plan_fast_cut_transition,
    plan_target_energy_transition,
    plan_target_style_transition,
)


SOURCE = "dj_structure_precomputed_window_v2"


def song(song_id, *, bpm=100.0, energy=0.5, duration=180.0):
    beat = 60.0 / bpm
    beats = [round(i * beat, 3) for i in range(int(duration / beat))]
    return SimpleNamespace(
        id=song_id,
        title=song_id,
        artist="test",
        bpm=bpm,
        camelot_key="9A",
        key="9A",
        energy=energy,
        duration=duration,
        beat_points=beats,
        downbeats=beats[::4],
        phrase_map=[
            {"start": 0.0, "end": 32.0, "label": "intro"},
            {"start": 32.0, "end": 96.0, "label": "verse"},
            {"start": 128.0, "end": 160.0, "label": "outro"},
        ],
        transition_windows=[
            {"start": 128.0, "end": 144.0, "mix_score": 0.8, "entry_start_sec": 8.0, "entry_score": 0.8}
        ],
        energy_curve=[{"time": i * 8.0, "energy": energy} for i in range(int(duration / 8))],
        stem_activity_windows=[],
        vocal_events=[],
        music_features={"dj": {"low_ratio": 0.4, "mid_ratio": 0.32, "high_ratio": 0.28}},
        genre_profile={"vocal_density": 0.28},
        loudness_profile={},
        source_path="",
    )


def add_v2(prev, nxt, *, exits=(14.0,), entries=(12.0,)):
    prev.music_features = {"dj_structure_v2": {
        "version": "dj_structure_v2",
        "track1_exit_candidates": [
            {"time": t, "score": 0.9, "tail_rms": 0.72, "local_rms": 0.72,
             "vocal_sparsity": 0.86, "drum_strength": 0.82,
             "immediate_punch": 0.74, "handoff_readiness": 0.88,
             "audio_feature_source": SOURCE} for t in exits],
    }}
    nxt.music_features = {"dj_structure_v2": {
        "version": "dj_structure_v2",
        "track2_entry_candidates": [
            {"time": t, "score": 0.9, "entry_rms": 0.72, "local_rms": 0.72,
             "vocal_sparsity": 0.88, "vocal_entry_sparsity": 0.88,
             "drum_strength": 0.84, "drum_entry_strength": 0.84,
             "immediate_punch": 0.78, "immediate_entry_punch": 0.78,
             "handoff_readiness": 0.88, "audio_feature_source": SOURCE} for t in entries],
    }}


class TransitionPlannerTests(unittest.TestCase):
    def test_default_plan_is_renderer_neutral(self):
        plan = plan_default_transition(song("a"), song("b"))
        self.assertEqual(plan["transition_mode"], "default_mix")
        self.assertEqual(plan["execution_mode"], "default_render_playback")
        self.assertIn("default_mix", plan)
        self.assertIsNone(plan["transition_render_url"])

    def test_fast_cut_uses_v2_candidate_inside_live_window(self):
        prev, nxt = song("a"), song("b")
        add_v2(prev, nxt, exits=(14.0, 22.0))
        plan = plan_fast_cut_transition(prev, nxt, cursor_sec=10.0, min_exit_sec=13.0, max_exit_sec=18.0, fade_sec=6.0)
        self.assertEqual(plan["playback_mode"], "fast_cut")
        self.assertEqual(plan["default_mix"]["audio_feature_source"], SOURCE)
        self.assertTrue(13.0 <= plan["from_at_sec"] <= 18.0)
        self.assertTrue(plan["default_mix"]["exit_candidate"]["fast_cut_window_used"])

    def test_fast_cut_rejects_missing_v2_data(self):
        with self.assertRaises(ValueError):
            plan_fast_cut_transition(song("a"), song("b"), cursor_sec=10.0, min_exit_sec=13.0, max_exit_sec=18.0)

    def test_energy_and_style_keep_shared_transition_shape(self):
        prev, nxt = song("a", energy=0.7), song("b", energy=0.65)
        add_v2(prev, nxt, exits=(32.0,), entries=(32.0,))
        energy = plan_target_energy_transition(prev, nxt, cursor_sec=24.0, target_min=60.0, target_max=70.0)
        style = plan_target_style_transition(prev, nxt, cursor_sec=24.0, target_style="popping", target_style_score=0.86, style_contrast_score=0.62)
        for plan, mode in ((energy, "target_energy_cut"), (style, "target_style_cut")):
            self.assertEqual(plan["execution_mode"], "default_render_playback")
            self.assertEqual(plan["playback_mode"], mode)
            self.assertTrue(plan["override_next_transition"])
            self.assertIn("entry_candidate", plan["default_mix"])
            self.assertIn("alignment", plan["default_mix"])


if __name__ == "__main__":
    unittest.main()
