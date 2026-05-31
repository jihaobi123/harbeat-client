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
            "intro_is_clean": True,
            "outro_is_clean": False,
            "has_drum_loop": True,
        }

    def test_copy_analysis_preserves_dj_analysis_fields(self):
        source = SimpleNamespace(**self._analysis_fields())
        target = SimpleNamespace()

        copy_analysis_from(source, target)

        self.assertEqual(target.tempo_stability, 0.99)
        self.assertTrue(target.transition_windows[0]["clean_candidate"])
        self.assertEqual(target.stem_quality_score, 0.95)

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

            analysis = build_song_manifest(song)["analysis"]

            self.assertEqual(analysis["tempo_stability"], 0.99)
            self.assertEqual(analysis["bpm_curve"][0]["bpm"], 120.0)
            self.assertEqual(analysis["transition_windows"][0]["label"], "intro")
            self.assertEqual(analysis["stem_quality_score"], 0.95)
            self.assertTrue(analysis["intro_is_clean"])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
