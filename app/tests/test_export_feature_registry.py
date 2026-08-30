import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema.validators import validator_for
from referencing import Registry, Resource


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = (
    REPO_ROOT
    / "experiments"
    / "traditional_vs_ml_20260829"
    / "reports"
    / "feature_selection.csv"
)
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "analysis"


class FeatureRegistryExportTests(unittest.TestCase):
    def _export(self, destination):
        from scripts.export_feature_registry_v1 import export_feature_registry

        return export_feature_registry(SOURCE_CSV, destination)

    def _validator(self):
        schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in SCHEMA_DIR.glob("*_v1.schema.json")
        }
        registry = Registry().with_resources(
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in schemas.items()
        )
        schema = schemas["feature_registry_entry_v1.schema.json"]
        return validator_for(schema)(schema, registry=registry)

    def test_export_contains_exactly_69_unique_schema_valid_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "registry.jsonl"
            entries = self._export(destination)

            self.assertEqual(len(entries), 69)
            self.assertEqual(len({entry["feature_id"] for entry in entries}), 69)
            self.assertEqual(entries, sorted(entries, key=lambda row: row["feature_id"]))

            validator = self._validator()
            for entry in entries:
                validator.validate(entry)

            on_disk = [
                json.loads(line)
                for line in destination.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(on_disk, entries)

    def test_export_preserves_metrics_and_does_not_invent_missing_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = self._export(Path(directory) / "registry.jsonl")
            by_id = {entry["feature_id"]: entry for entry in entries}

            validated = by_id["harmony.chord_change_activity"]
            self.assertEqual(validated["status"], "validated")
            self.assertEqual(validated["validation_evidence"]["selection_value"], 0.9213)
            self.assertEqual(validated["validation_evidence"]["f1"], 0.9369)
            self.assertEqual(validated["validation_evidence"]["sample_count"], 89)

            not_evaluated = by_id["harmony.harmonic_complexity"]
            self.assertIsNone(not_evaluated["validation_evidence"]["selection_value"])
            self.assertIsNone(not_evaluated["validation_evidence"]["f1"])
            self.assertIsNone(not_evaluated["validation_evidence"]["sample_count"])

    def test_export_preserves_failed_and_deprecated_states(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = self._export(Path(directory) / "registry.jsonl")
            by_id = {entry["feature_id"]: entry for entry in entries}

            self.assertEqual(
                by_id["low_frequency.808_timbre_candidate"]["status"],
                "failed_validation",
            )
            self.assertEqual(by_id["low_frequency.sub_808"]["status"], "deprecated")
            self.assertEqual(
                by_id["low_frequency.sub_808"]["canonical_feature_id"],
                "low_frequency.808_timbre_candidate",
            )

    def test_script_runs_directly_from_the_repository_root(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "registry.jsonl"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "export_feature_registry_v1.py"),
                    "--source",
                    str(SOURCE_CSV),
                    "--output",
                    str(destination),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(len(destination.read_text(encoding="utf-8").splitlines()), 69)

    def test_committed_registry_matches_a_fresh_repeatable_export(self):
        from scripts.export_feature_registry_v1 import export_feature_registry

        committed = REPO_ROOT / "contracts" / "registries" / "analysis_features_v1.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.jsonl"
            second = Path(directory) / "second.jsonl"
            export_feature_registry(SOURCE_CSV, first)
            export_feature_registry(SOURCE_CSV, second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.read_bytes(), committed.read_bytes())

    def test_exporter_rejects_ambiguous_booleans_and_non_finite_numbers(self):
        from scripts.export_feature_registry_v1 import _boolean, _optional_float

        with self.assertRaises(ValueError):
            _boolean("maybe")
        with self.assertRaises(ValueError):
            _optional_float("NaN")
        self.assertTrue(math.isfinite(_optional_float("0.5")))


if __name__ == "__main__":
    unittest.main()
