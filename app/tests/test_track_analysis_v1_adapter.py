import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "analysis"
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _song(**overrides):
    values = {
        "id": "track_test_1",
        "duration": 4.0,
        "beat_points": [index * 0.5 for index in range(8)],
        "downbeats": [0.0, 2.0],
        "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.9},
        "bpm": 120.0,
        "bpm_confidence": 0.94,
        "beat_confidence": 0.92,
        "tempo_stability": 0.88,
        "energy": 0.61,
        "energy_curve": [],
        "stem_activity_windows": [],
        "phrase_map": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class TrackAnalysisV1AdapterTests(unittest.TestCase):
    def _context(self):
        from app.modules.library.track_analysis_v1_adapter import TrackAnalysisBuildContext

        return TrackAnalysisBuildContext(
            analysis_id="analysis_test_1",
            revision=1,
            created_at="2026-08-30T08:15:30Z",
            audio_sha256=HASH_A,
            decoded_pcm_sha256=HASH_B,
            pipeline_version="bar-understanding-1.0.0",
            preprocessing_version="canonical-pcm-1.0.0",
            feature_definition_version="1.0.0",
            config_sha256=HASH_C,
            code_commit="7abc019",
        )

    def _build(self, song):
        from app.modules.library.track_analysis_v1_adapter import build_track_analysis_v1

        return build_track_analysis_v1(song, self._context())

    def _validator(self):
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in SCHEMA_DIR.glob("*_v1.schema.json")
        }
        registry = Registry().with_resources(
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in schemas.items()
        )
        schema = schemas["track_analysis_v1.schema.json"]
        return validator_for(schema)(
            schema,
            registry=registry,
            format_checker=FormatChecker(),
        )

    def test_builds_schema_valid_immutable_analysis_envelope(self):
        result = self._build(_song())

        self.assertEqual(result["schema_name"], "harbeat.track_analysis")
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["analysis_id"], "analysis_test_1")
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["timeline"]["bar_count"], 2)
        self.assertEqual([bar["bar_index"] for bar in result["bars"]], [0, 1])
        self.assertIn("prov_legacy_explicit_v1", result["provenance"])
        self.assertIn("prov_bar_aggregation_v1", result["provenance"])
        self.assertIsNone(result["quality"]["overall_confidence"])
        self._validator().validate(result)

    def test_missing_track_measurement_remains_null(self):
        result = self._build(_song(bpm=None, bpm_confidence=None, energy=None))

        bpm = result["track_summary"]["bpm"]
        energy = result["track_summary"]["energy_normalized"]
        self.assertIsNone(bpm["value"])
        self.assertEqual(bpm["availability"], "unavailable")
        self.assertIsNone(energy["value"])
        self.assertEqual(energy["availability"], "not_computed")

    def test_out_of_range_track_energy_is_invalid_instead_of_available_null(self):
        result = self._build(_song(energy=1.5))

        energy = result["track_summary"]["energy_normalized"]
        self.assertIsNone(energy["value"])
        self.assertEqual(energy["availability"], "invalid")

    def test_context_rejects_placeholder_or_malformed_hashes(self):
        from app.modules.library.track_analysis_v1_adapter import TrackAnalysisBuildContext

        with self.assertRaisesRegex(ValueError, "audio_sha256"):
            TrackAnalysisBuildContext(
                analysis_id="analysis_test_1",
                revision=1,
                created_at="2026-08-30T08:15:30Z",
                audio_sha256="unknown",
                decoded_pcm_sha256=HASH_B,
                pipeline_version="bar-understanding-1.0.0",
                preprocessing_version="canonical-pcm-1.0.0",
                feature_definition_version="1.0.0",
                config_sha256=HASH_C,
                code_commit="7abc019",
            )

    def test_context_rejects_colliding_provenance_keys(self):
        from app.modules.library.track_analysis_v1_adapter import TrackAnalysisBuildContext

        with self.assertRaisesRegex(ValueError, "provenance"):
            TrackAnalysisBuildContext(
                analysis_id="analysis_test_1",
                revision=1,
                created_at="2026-08-30T08:15:30Z",
                audio_sha256=HASH_A,
                decoded_pcm_sha256=HASH_B,
                pipeline_version="bar-understanding-1.0.0",
                preprocessing_version="canonical-pcm-1.0.0",
                feature_definition_version="1.0.0",
                config_sha256=HASH_C,
                code_commit="7abc019",
                provenance_ref="same_provenance",
                aggregation_provenance_ref="same_provenance",
            )

    def test_context_rejects_malformed_utc_timestamp(self):
        from app.modules.library.track_analysis_v1_adapter import TrackAnalysisBuildContext

        with self.assertRaisesRegex(ValueError, "created_at"):
            TrackAnalysisBuildContext(
                analysis_id="analysis_test_1",
                revision=1,
                created_at="garbageZ",
                audio_sha256=HASH_A,
                decoded_pcm_sha256=HASH_B,
                pipeline_version="bar-understanding-1.0.0",
                preprocessing_version="canonical-pcm-1.0.0",
                feature_definition_version="1.0.0",
                config_sha256=HASH_C,
                code_commit="7abc019",
            )

        with self.assertRaisesRegex(ValueError, "created_at"):
            TrackAnalysisBuildContext(
                analysis_id="analysis_test_1",
                revision=1,
                created_at="2026-08-30Z",
                audio_sha256=HASH_A,
                decoded_pcm_sha256=HASH_B,
                pipeline_version="bar-understanding-1.0.0",
                preprocessing_version="canonical-pcm-1.0.0",
                feature_definition_version="1.0.0",
                config_sha256=HASH_C,
                code_commit="7abc019",
            )

    def test_track_timeline_never_republishes_off_grid_raw_downbeats(self):
        result = self._build(_song(downbeats=[0.2, 2.2]))

        self.assertEqual(result["timeline"]["downbeat_times_sec"], [0.0, 2.0])
        self.assertIn("DOWNBEAT_OFF_GRID", result["quality"]["warnings"])

    def test_semantic_validator_rejects_cross_object_invariant_violations(self):
        from app.modules.library.track_analysis_v1_validation import (
            validate_track_analysis_v1_invariants,
        )

        valid = self._build(_song())
        mutations = {
            "bar_count": lambda value: value["timeline"].update(bar_count=99),
            "child_analysis_id": lambda value: value["bars"][0].update(analysis_id="other"),
            "beat_count": lambda value: value["bars"][0].update(beat_count=99),
            "bar_index": lambda value: value["bars"][1].update(bar_index=7),
            "provenance_ref": lambda value: value["bars"][0]["timing"]["bpm"].update(
                provenance_ref="missing_provenance"
            ),
            "unordered_beats": lambda value: value["timeline"].update(
                beat_times_sec=[0.5, 0.0]
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                invalid = deepcopy(valid)
                mutate(invalid)
                with self.assertRaises(ValueError):
                    validate_track_analysis_v1_invariants(invalid)

    def test_legacy_v2_module_path_remains_runnable(self):
        code = (
            "from types import SimpleNamespace; "
            "from app.modules.dj_set.track_analysis_adapter import build_track_analysis_v2; "
            "r=build_track_analysis_v2(SimpleNamespace(id='x', title='x', duration=1.0)); "
            "assert r['schema_version']=='track-analysis-v2'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
