import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.modules.library.background_tasks import copy_analysis_from
from app.modules.manifest import build_song_manifest


class AnalysisManifestTests(unittest.TestCase):
    def _analysis_fields(self):
        return {
            "bpm_curve": [{"start": 0.0, "end": 8.0, "bpm": 120.0, "stability": 0.99}],
            "tempo_stability": 0.99,
            "beat_confidence": 0.98,
            "beat_confidence_details": {"tempo_stability": 0.99, "phase_consistency": 0.98},
            "beat_grid_offset": 0.1,
            "beat_grid_interval": 0.5,
            "beat_engines_used": ["librosa"],
            "beat_needs_review": False,
            "loudness_profile": {
                "integrated_lufs": -14.5,
                "peak_dbfs": -1.0,
                "replay_gain_db": 0.5,
                "clipping_risk": False,
            },
            "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.95},
            "groove_score": 0.82,
            "groove_profile": {"score": 0.82, "label": "groovy"},
            "danceability_score": 0.84,
            "dancefloor_profile": {"danceability_score": 0.84, "mood_tags": ["driving"]},
            "dj_hot_cues": [{"name": "first_drop", "time": 32.0}],
            "transition_recommendations": [{"start": 0.0, "type": "entry_point"}],
            "energy_curve": [{"start": 0.0, "end": 2.0, "energy": 0.5, "relative_energy": 1.0}],
            "transition_windows": [{
                "start": 0.0, "end": 16.0, "label": "intro", "bars": 8,
                "energy": 0.3, "mix_in_score": 0.98, "mix_out_score": 0.39,
                "clean_candidate": True,
            }],
            "stem_activity": {"vocals": 0.2, "drums": 0.8, "bass": 0.6, "other": 0.4},
            "stem_activity_windows": [{
                "start": 0.0, "end": 2.0, "vocals": 0.0, "drums": 0.8,
                "bass": 0.6, "other": 0.4,
            }],
            "stem_quality_score": 0.95,
            "stem_quality_profile": {"method": "completeness_reconstruction_proxy", "completeness": 1.0},
            "intro_is_clean": True,
            "outro_is_clean": False,
            "intro_clean_score": 0.88,
            "outro_clean_score": 0.31,
            "has_drum_loop": True,
            "music_features": {"dj": {"bpm": 120.0}},
            "dance_styles": [{"style": "house", "score": 0.9}],
            "dance_style_scores": {"house": 0.9},
            "dance_style_status": "ready",
        }

    def test_copy_analysis_preserves_dj_analysis_fields(self):
        source = SimpleNamespace(**self._analysis_fields())
        target = SimpleNamespace()

        copy_analysis_from(source, target)

        self.assertEqual(target.tempo_stability, 0.99)
        self.assertEqual(target.beat_grid_interval, 0.5)
        self.assertEqual(target.loudness_profile["replay_gain_db"], 0.5)
        self.assertEqual(target.danceability_score, 0.84)
        self.assertEqual(target.dj_hot_cues[0]["name"], "first_drop")
        self.assertTrue(target.transition_windows[0]["clean_candidate"])
        self.assertEqual(target.stem_quality_score, 0.95)
        self.assertEqual(target.stem_quality_profile["completeness"], 1.0)
        self.assertEqual(target.intro_clean_score, 0.88)
        self.assertEqual(target.dance_styles[0]["style"], "house")

    def test_manifest_includes_dj_analysis_fields(self):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            song = SimpleNamespace(
                id="song-1",
                title="Test",
                artist="Artist",
                duration=120.0,
                source_path=path,
                stems=None,
                bpm=120.0,
                key="C major",
                camelot_key="8B",
                energy=0.5,
                key_confidence=0.8,
                beat_points=[0.0, 0.5, 1.0],
                downbeats=[0.0],
                phrase_map=[],
                cue_points=[],
                analysis_status="ready",
                stem_status="none",
                **self._analysis_fields(),
            )

            manifest = build_song_manifest(song)
            analysis = manifest["analysis"]

            self.assertEqual(analysis["tempo_stability"], 0.99)
            self.assertEqual(analysis["beat_confidence"], 0.98)
            self.assertEqual(analysis["loudness_profile"]["integrated_lufs"], -14.5)
            self.assertEqual(analysis["dancefloor_profile"]["mood_tags"], ["driving"])
            self.assertEqual(analysis["dj_hot_cues"][0]["name"], "first_drop")
            self.assertEqual(analysis["bpm_curve"][0]["bpm"], 120.0)
            self.assertEqual(analysis["transition_windows"][0]["label"], "intro")
            self.assertEqual(analysis["stem_quality_score"], 0.95)
            self.assertEqual(analysis["stem_quality_profile"]["method"], "completeness_reconstruction_proxy")
            self.assertTrue(analysis["intro_is_clean"])
            self.assertEqual(analysis["intro_clean_score"], 0.88)
            self.assertEqual(manifest["qualityFlags"]["outro_clean_score"], 0.31)
            self.assertEqual(analysis["dance_style_scores"]["house"], 0.9)
            self.assertEqual(manifest["replayGainDb"], 0.5)
            self.assertFalse(manifest["qualityFlags"]["clipping_risk"])
            self.assertFalse(manifest["qualityFlags"]["beat_needs_review"])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
