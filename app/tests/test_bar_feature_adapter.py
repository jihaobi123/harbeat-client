import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema.validators import validator_for
from referencing import Registry, Resource


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "analysis"


def _song(**overrides):
    values = {
        "id": "track_test_1",
        "duration": 5.0,
        "beat_points": [index * 0.5 for index in range(10)],
        "downbeats": [0.0, 2.0, 4.0],
        "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.9},
        "bpm": 120.0,
        "bpm_confidence": 0.94,
        "beat_confidence": 0.92,
        "energy_curve": [],
        "stem_activity_windows": [],
        "phrase_map": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class BarFeatureAdapterTests(unittest.TestCase):
    def _build(self, song):
        from app.modules.library.bar_feature_adapter import build_bar_features

        return build_bar_features(song, analysis_id="analysis_test_1")

    def _validator(self):
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in SCHEMA_DIR.glob("*_v1.schema.json")
        }
        registry = Registry().with_resources(
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in schemas.items()
        )
        schema = schemas["bar_feature_v1.schema.json"]
        return validator_for(schema)(schema, registry=registry)

    def test_downbeats_create_half_open_bars_and_partial_tail(self):
        bars = self._build(_song())

        self.assertEqual([bar["start_sec"] for bar in bars], [0.0, 2.0, 4.0])
        self.assertEqual([bar["end_sec"] for bar in bars], [2.0, 4.0, 5.0])
        self.assertEqual([bar["beat_count"] for bar in bars], [4, 4, 2])
        self.assertEqual([bar["is_partial"] for bar in bars], [False, False, True])
        self.assertEqual([bar["bar_index"] for bar in bars], [0, 1, 2])

    def test_falls_back_to_meter_sized_beat_groups_without_downbeats(self):
        song = _song(
            duration=4.2,
            beat_points=[index * 0.5 for index in range(9)],
            downbeats=[],
        )
        bars = self._build(song)

        self.assertEqual([bar["start_sec"] for bar in bars], [0.0, 2.0, 4.0])
        self.assertEqual([bar["end_sec"] for bar in bars], [2.0, 4.0, 4.2])
        self.assertEqual([bar["beat_count"] for bar in bars], [4, 4, 1])
        self.assertIn("DOWNBEATS_UNAVAILABLE", bars[0]["quality"]["warnings"])
        self.assertTrue(bars[0]["quality"]["needs_review"])

    def test_sparse_downbeats_are_completed_from_meter_sized_beat_groups(self):
        song = _song(
            duration=8.0,
            beat_points=[index * 0.5 for index in range(16)],
            downbeats=[0.0, 4.0],
        )
        bars = self._build(song)

        self.assertEqual([bar["start_sec"] for bar in bars], [0.0, 2.0, 4.0, 6.0])
        self.assertEqual([bar["beat_count"] for bar in bars], [4, 4, 4, 4])
        self.assertIn("DOWNBEATS_INTERPOLATED", bars[0]["quality"]["warnings"])
        self.assertTrue(bars[0]["quality"]["needs_review"])

    def test_inconsistent_downbeat_cadence_falls_back_and_marks_timeline_suspect(self):
        song = _song(
            duration=6.0,
            beat_points=[index * 0.5 for index in range(12)],
            downbeats=[0.0, 2.5],
        )
        bars = self._build(song)

        self.assertEqual([bar["start_sec"] for bar in bars], [0.0, 2.0, 4.0])
        self.assertIn("DOWNBEAT_CADENCE_INVALID", bars[0]["quality"]["warnings"])
        self.assertIn("TIMELINE_SUSPECT", bars[0]["quality"]["warnings"])

    def test_window_overlap_preserves_real_zero_activity(self):
        song = _song(
            stem_activity_windows=[
                {"start": 0.0, "end": 1.0, "vocals": 0.0, "drums": 0.8, "bass": 0.4},
                {"start": 1.0, "end": 2.0, "vocals": 0.0, "drums": 0.6, "bass": 0.2},
            ],
            energy_curve=[
                {"start": 0.0, "end": 1.0, "energy": 0.2},
                {"start": 1.0, "end": 2.0, "energy": 0.6},
            ],
        )
        bar = self._build(song)[0]

        vocal = bar["elements"]["vocal"]
        self.assertEqual(vocal["activity"]["value"], 0.0)
        self.assertEqual(vocal["activity"]["availability"], "available")
        self.assertIsNone(vocal["state"]["value"])
        self.assertEqual(vocal["state"]["availability"], "not_computed")
        self.assertAlmostEqual(bar["elements"]["drums"]["activity"]["value"], 0.7)
        self.assertAlmostEqual(bar["acoustic"]["energy_normalized"]["value"], 0.4)

    def test_fragmentary_window_does_not_become_full_bar_measurement(self):
        song = _song(
            stem_activity_windows=[
                {"start": 0.0, "end": 0.1, "vocals": 0.7},
            ]
        )
        bar = self._build(song)[0]

        activity = bar["elements"]["vocal"]["activity"]
        self.assertIsNone(activity["value"])
        self.assertEqual(activity["availability"], "invalid")
        self.assertIn("STEM_ACTIVITY_PARTIAL_COVERAGE", bar["quality"]["warnings"])

    def test_out_of_range_window_value_is_invalid_instead_of_clamped(self):
        song = _song(
            energy_curve=[
                {"start": 0.0, "end": 2.0, "energy": 1.5},
            ]
        )
        bar = self._build(song)[0]

        feature = bar["acoustic"]["energy_normalized"]
        self.assertIsNone(feature["value"])
        self.assertEqual(feature["availability"], "invalid")
        self.assertIn("ENERGY_INVALID_WINDOW", bar["quality"]["warnings"])

    def test_overlapping_windows_are_averaged_without_double_counting_time(self):
        song = _song(
            energy_curve=[
                {"start": 0.0, "end": 2.0, "energy": 0.2},
                {"start": 1.0, "end": 2.0, "energy": 0.6},
            ]
        )
        bar = self._build(song)[0]

        self.assertAlmostEqual(bar["acoustic"]["energy_normalized"]["value"], 0.3)

    def test_beat_confidence_is_not_reused_as_downbeat_confidence(self):
        bar = self._build(_song(beat_confidence=0.99))[0]

        downbeat = bar["timing"]["downbeat_confidence"]
        self.assertIsNone(downbeat["value"])
        self.assertEqual(downbeat["availability"], "not_computed")

    def test_missing_window_data_is_not_computed_instead_of_zero(self):
        bar = self._build(_song())[0]

        self.assertIsNone(bar["elements"]["vocal"]["activity"]["value"])
        self.assertEqual(
            bar["elements"]["vocal"]["activity"]["availability"],
            "not_computed",
        )
        self.assertIsNone(bar["acoustic"]["energy_normalized"]["value"])

    def test_every_emitted_bar_is_schema_valid(self):
        bars = self._build(_song())
        validator = self._validator()

        for bar in bars:
            validator.validate(bar)

    def test_missing_beat_grid_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "beat grid"):
            self._build(_song(beat_points=[], downbeats=[]))


if __name__ == "__main__":
    unittest.main()
