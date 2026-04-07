import unittest

from app.modules.playlists.transition_planner import (
    TrackFeature,
    build_fx_automation,
    camelot_relation,
    harmonic_compatible,
    plan_phrase_transition,
    score_transition,
)


class TransitionPlannerTests(unittest.TestCase):
    def test_camelot_relation_cases(self):
        self.assertEqual(camelot_relation('8A', '8A'), 'same-key')
        self.assertEqual(camelot_relation('8A', '8B'), 'relative')
        self.assertEqual(camelot_relation('8A', '9A'), 'neighbor')
        self.assertEqual(camelot_relation('8A', '2B'), 'clash')
        self.assertEqual(camelot_relation(None, '8A'), 'unknown')

    def test_harmonic_compatible_respects_strict(self):
        self.assertFalse(harmonic_compatible('8A', '2B', strict=True))
        self.assertTrue(harmonic_compatible('8A', '2B', strict=False))
        self.assertTrue(harmonic_compatible('8A', '9A', strict=True))

    def test_score_transition_prefers_better_match(self):
        good_from = TrackFeature(song_id=1, bpm=120.0, camelot_key='8A', duration=220.0)
        good_to = TrackFeature(song_id=2, bpm=122.0, camelot_key='8B', duration=210.0)
        bad_to = TrackFeature(song_id=3, bpm=160.0, camelot_key='2B', duration=80.0)

        good_score, good_ratio, _ = score_transition(
            from_track=good_from,
            to_track=good_to,
            from_energy='medium',
            to_energy='high',
            strict_harmonic=True,
            max_tempo_shift=0.10,
            crossfade_sec=8.0,
        )
        bad_score, bad_ratio, _ = score_transition(
            from_track=good_from,
            to_track=bad_to,
            from_energy='medium',
            to_energy='low',
            strict_harmonic=True,
            max_tempo_shift=0.10,
            crossfade_sec=8.0,
        )

        self.assertGreater(good_score, bad_score)
        self.assertAlmostEqual(good_ratio, 1.0166666667, places=3)
        self.assertAlmostEqual(bad_ratio, 1.3333333333, places=3)

    def test_build_fx_automation_shape(self):
        points = build_fx_automation(crossfade_sec=6.0, energy_target='high')
        self.assertEqual(len(points), 6)
        self.assertEqual(points[0]['time_sec'], 0.0)
        self.assertEqual(points[0]['target'], 'from')
        self.assertEqual(points[-1]['time_sec'], 6.0)
        self.assertEqual(points[-1]['target'], 'to')

    def test_plan_phrase_transition_prefers_outro_zone(self):
        from_track = TrackFeature(song_id=1, bpm=124.0, camelot_key='8A', duration=240.0)
        to_track = TrackFeature(song_id=2, bpm=124.0, camelot_key='8B', duration=220.0)
        beat_points = [i * (60.0 / 124.0) for i in range(600)]
        cue_points = [
            {"time": 0.0, "label": "Intro"},
            {"time": 60.0, "label": "Verse"},
            {"time": 180.0, "label": "Outro"},
        ]
        plan = plan_phrase_transition(
            from_track=from_track,
            to_track=to_track,
            crossfade_sec=6.0,
            from_beat_points=beat_points,
            to_beat_points=beat_points,
            from_cue_points=cue_points,
        )
        self.assertGreaterEqual(plan.exit_time_sec, 170.0)
        self.assertGreater(plan.from_beat_interval_sec, 0.0)
        self.assertGreater(plan.to_beat_interval_sec, 0.0)
        self.assertIn(plan.technique, {'eq_bass_swap', 'phrase_crossfade', 'echo_style_cross'})


if __name__ == '__main__':
    unittest.main()
