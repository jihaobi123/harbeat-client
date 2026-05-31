import os
import tempfile
import unittest
from types import SimpleNamespace

import numpy as np
import soundfile as sf

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/numba-cache")

from app.modules.library.background_tasks import apply_dj_fingerprint


class _FakeDb:
    def __init__(self):
        self.commits = 0

    def add(self, _song):
        pass

    def commit(self):
        self.commits += 1


class DjFingerprintPersistenceTests(unittest.TestCase):
    def test_apply_dj_fingerprint_persists_features_and_ranked_styles(self):
        sr = 22050
        t = np.arange(sr * 2) / sr
        audio = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "song.wav")
            sf.write(path, audio, sr)
            song = SimpleNamespace(
                source_path=path,
                duration=2.0,
                bpm=124.0,
                energy=0.75,
                beat_points=[i * 0.5 for i in range(4)],
                downbeats=[0.0],
                stems=None,
                music_features={},
                dance_styles=[],
                dance_style_scores={},
                dance_style_status="none",
            )
            db = _FakeDb()

            apply_dj_fingerprint(db, song)

        self.assertIn("dj", song.music_features)
        self.assertEqual(song.music_features["dj"]["bpm"], 124.0)
        self.assertEqual(song.dance_style_status, "ready")
        self.assertEqual(len(song.dance_styles), 7)
        self.assertEqual(set(song.dance_style_scores), {
            "breaking", "hiphop", "popping", "locking", "house", "krump", "waacking",
        })
        self.assertGreaterEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
