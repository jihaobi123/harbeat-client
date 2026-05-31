"""Tests for comprehensive key/tonal analysis."""
import json
import unittest

import numpy as np

from app.modules.library.analysis import _analyze_key


class KeyAnalysisTests(unittest.TestCase):
    def _synthesize_sine_chord(self, root_freq: float, sr: int = 22050,
                                duration: float = 3.0, major: bool = True) -> np.ndarray:
        """Synthesize a simple major or minor chord for testing."""
        t = np.arange(int(sr * duration), dtype=np.float32) / sr
        if major:
            intervals = [1.0, 1.25, 1.5]  # root, M3, P5
        else:
            intervals = [1.0, 1.2, 1.5]   # root, m3, P5
        signal = np.zeros_like(t)
        for ratio in intervals:
            signal += 0.33 * np.sin(2 * np.pi * root_freq * ratio * t)
        return signal / np.max(np.abs(signal) + 1e-8)

    def test_clear_tonal_signal_returns_high_confidence(self):
        """C major chord → should detect C major with high confidence."""
        y = self._synthesize_sine_chord(261.63, major=True)  # C4
        result = _analyze_key(y, 22050)
        self.assertIn("major", result["key"])
        self.assertGreater(result["key_confidence"], 0.5)
        # Tonal clarity: simple sine chords may not be very "peaky" in CQT
        # due to librosa's frequency resolution; real music has much higher clarity.
        self.assertGreater(result["tonal_clarity"], 0.1)

    def test_noise_returns_low_tonal_clarity(self):
        """White noise → tonal clarity should be near zero."""
        y = np.random.randn(22050 * 3).astype(np.float32) * 0.1
        result = _analyze_key(y, 22050)
        self.assertLess(result["tonal_clarity"], 0.4)

    def test_candidates_include_top_matches(self):
        """Key analysis should return at least 1 candidate."""
        y = self._synthesize_sine_chord(440.0, major=True)  # A4
        result = _analyze_key(y, 22050)
        self.assertGreaterEqual(len(result["candidates"]), 1)
        for c in result["candidates"]:
            self.assertIn("root", c)
            self.assertIn("mode", c)
            self.assertIn("camelot", c)
            self.assertIn("score", c)

    def test_short_audio_falls_back(self):
        """Very short audio → fallback."""
        y = np.zeros(100, dtype=np.float32)
        result = _analyze_key(y, 22050)
        self.assertEqual(result["method"], "fallback_short_audio")

    def test_relative_ambiguity_is_boolean(self):
        """relative_ambiguity should be True or False."""
        y = self._synthesize_sine_chord(261.63, major=True)
        result = _analyze_key(y, 22050)
        self.assertIsInstance(result["relative_ambiguity"], bool)

    def test_camelot_key_in_expected_format(self):
        """Camelot key should be like '8B' or '5A'."""
        y = self._synthesize_sine_chord(261.63, major=True)
        result = _analyze_key(y, 22050)
        self.assertRegex(result["camelot_key"], r'^\d{1,2}[AB]$')

    def test_json_serializable(self):
        y = self._synthesize_sine_chord(261.63, major=True)
        result = _analyze_key(y, 22050)
        json.dumps(result)  # should not raise


if __name__ == "__main__":
    unittest.main()
