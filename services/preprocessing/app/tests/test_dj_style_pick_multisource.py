import unittest
from types import SimpleNamespace

from app.modules.dj_control.dance_style import (
    pick_songs_for_duration,
    score_song_multisource,
    style_pick_evidence,
)


def _song(**overrides):
    base = dict(
        id="s1",
        title="Song",
        artist="Artist",
        bpm=100.0,
        energy=0.70,
        duration=210.0,
        beat_points=[i * 0.5 for i in range(420)],
        downbeats=[i * 2.0 for i in range(105)],
        phrase_map=[],
        music_features={"dj": {
            "bpm": 100.0,
            "energy": 0.70,
            "beat_density": 2.0,
            "four_on_floor": 0.35,
            "groove_complexity": 0.08,
            "bass_dominance": 0.42,
            "sub_bass_score": 0.40,
            "brass_likely": 0.35,
            "drums_to_vocals_ratio": 1.2,
            "spectral_centroid": 1900.0,
            "spectral_contrast_mean": 22.0,
        }},
        genre_profile={},
        beat_confidence=0.80,
        tempo_stability=0.85,
        transition_windows=[{"start": 180.0, "end": 196.0}],
        intro_clean_score=0.70,
        outro_clean_score=0.75,
        stem_quality_score=0.65,
        analysis_status="completed",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class DjStylePickMultisourceTests(unittest.TestCase):
    def test_multisource_score_is_bounded_and_explainable(self):
        song = _song(genre_profile={
            "sources": {
                "discogs": {
                    "labels": ["electro", "boogie", "funk"],
                    "confidence": 0.75,
                }
            }
        })

        evidence = score_song_multisource("popping", song)

        self.assertGreaterEqual(evidence["final_pick_score"], 0.0)
        self.assertLessEqual(evidence["final_pick_score"], 1.0)
        self.assertIn("fingerprint", evidence["components"])
        self.assertIn("score", evidence["components"]["fingerprint"])
        self.assertIn("electro", evidence["matched_labels"])
        self.assertTrue(evidence["recommendation_reason"])

    def test_falls_back_when_dj_features_missing(self):
        song = _song(music_features={})

        evidence = score_song_multisource("hiphop", song)

        self.assertEqual(evidence["components"]["fingerprint"]["version"], "v1")
        self.assertGreaterEqual(evidence["final_pick_score"], 0.0)

    def test_platform_tags_raise_matching_style(self):
        plain = _song(genre_profile={})
        tagged = _song(genre_profile={
            "sources": {
                "discogs": {
                    "labels": ["disco", "funk", "vocal house"],
                    "confidence": 0.80,
                }
            }
        })

        plain_score = score_song_multisource("waacking", plain)["final_pick_score"]
        tagged_score = score_song_multisource("waacking", tagged)["final_pick_score"]

        self.assertGreater(tagged_score, plain_score)

    def test_manual_feedback_suitable_and_unsuitable(self):
        suitable = _song(genre_profile={
            "style_feedback": [
                {"style": "locking", "feedback_type": "suitable", "weight": 1.0}
            ]
        })
        unsuitable = _song(genre_profile={
            "style_feedback": [
                {"style": "locking", "feedback_type": "unsuitable", "weight": 1.0}
            ]
        })

        self.assertGreater(
            score_song_multisource("locking", suitable)["final_pick_score"],
            score_song_multisource("locking", unsuitable)["final_pick_score"],
        )

    def test_pick_songs_for_duration_keeps_duration_and_diversity_fallback(self):
        songs = [
            _song(id=f"s{i}", artist=f"Artist {i % 2}", bpm=96.0 + i, duration=120.0)
            for i in range(6)
        ]

        picks = pick_songs_for_duration(
            songs,
            style_key="hiphop",
            target_seconds=360.0,
            min_score=0.10,
        )

        self.assertGreaterEqual(sum(s.duration for s, _score, _ev in picks), 360.0)
        self.assertTrue(all("final_pick_score" in ev for _s, _score, ev in picks))

    def test_style_pick_reads_persisted_style_evidence_v1(self):
        song = _song(
            dance_style_scores={"popping": 0.91},
            genre_profile={
                "sources": {
                    "discogs": {"status": "hit", "labels": ["funk", "electro"], "confidence": 0.8}
                },
                "style_evidence_v1": {
                    "popping": {
                        "external_platform_score": 0.9,
                        "local_fingerprint_score": 0.7,
                        "manual_style_score": None,
                        "tunable_adjustment_score": 0.8,
                        "final_score": 0.91,
                        "confidence": 0.8,
                        "status": "ready",
                        "reason": ["Discogs 命中 funk / electro"],
                    }
                },
            },
        )

        evidence = style_pick_evidence("popping", song)

        self.assertEqual(evidence["version"], "style_evidence_v1")
        self.assertEqual(evidence["final_pick_score"], 0.91)
        self.assertEqual(evidence["style_evidence_status"], "ready")
        self.assertIn("discogs", evidence["external_sources"])


if __name__ == "__main__":
    unittest.main()
