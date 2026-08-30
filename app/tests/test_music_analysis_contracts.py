import json
import unittest
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag

from jsonschema import FormatChecker, ValidationError
from referencing import Registry, Resource
from jsonschema.validators import validator_for


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas" / "analysis"
EXPECTED_SCHEMAS = {
    "analysis_job_v1.schema.json",
    "annotation_record_v1.schema.json",
    "bar_feature_v1.schema.json",
    "dataset_track_v1.schema.json",
    "feature_registry_entry_v1.schema.json",
    "mert_cache_manifest_v1.schema.json",
    "model_manifest_v1.schema.json",
    "track_analysis_v1.schema.json",
}
FIXTURE_DIR = REPO_ROOT / "contracts" / "fixtures" / "analysis"


def _walk_refs(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                yield child
            else:
                yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


class MusicAnalysisContractDiscoveryTests(unittest.TestCase):
    def test_v1_schema_set_is_complete_and_machine_valid(self):
        schema_paths = sorted(SCHEMA_DIR.glob("*_v1.schema.json"))
        self.assertEqual({path.name for path in schema_paths}, EXPECTED_SCHEMAS)

        schemas = [json.loads(path.read_text(encoding="utf-8")) for path in schema_paths]
        schema_ids = [schema.get("$id") for schema in schemas]

        self.assertNotIn(None, schema_ids)
        self.assertEqual(len(schema_ids), len(set(schema_ids)))
        self.assertEqual(set(schema_ids), EXPECTED_SCHEMAS)

        registry = Registry().with_resources(
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in zip(schema_ids, schemas)
        )

        for schema in schemas:
            validator_for(schema).check_schema(schema)
            resolver = registry.resolver(base_uri=schema["$id"])
            for ref in _walk_refs(schema):
                target, _fragment = urldefrag(ref)
                if target:
                    self.assertIn(
                        target,
                        schema_ids,
                        msg=f"{schema['$id']} references missing local schema {target}",
                    )
                resolver.lookup(ref)


class MusicAnalysisContractFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in SCHEMA_DIR.glob("*_v1.schema.json")
        }
        resources = [
            (schema_id, Resource.from_contents(schema))
            for schema_id, schema in cls.schemas.items()
        ]
        cls.registry = Registry().with_resources(resources)

    def _validator(self, schema_name):
        schema = self.schemas[schema_name]
        validator_class = validator_for(schema)
        return validator_class(
            schema,
            registry=self.registry,
            format_checker=FormatChecker(),
        )

    def _fixture(self, name):
        return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))

    def test_valid_bar_feature_fixture(self):
        self._validator("bar_feature_v1.schema.json").validate(
            self._fixture("bar_feature_v1.valid.json")
        )

    def test_valid_track_analysis_fixture(self):
        from app.modules.library.track_analysis_v1_validation import (
            validate_track_analysis_v1_invariants,
        )

        fixture = self._fixture("track_analysis_v1.valid.json")
        self._validator("track_analysis_v1.schema.json").validate(fixture)
        validate_track_analysis_v1_invariants(fixture)

    def test_probability_outside_unit_interval_is_rejected(self):
        bar = self._fixture("bar_feature_v1.valid.json")
        bar["structure"]["section_start_probability"]["value"] = 1.1

        with self.assertRaises(ValidationError):
            self._validator("bar_feature_v1.schema.json").validate(bar)

    def test_unavailable_feature_cannot_carry_a_numeric_value(self):
        bar = self._fixture("bar_feature_v1.valid.json")
        feature = bar["acoustic"]["energy_normalized"]
        feature.update(
            value=0.4,
            availability="unavailable",
            confidence=None,
            provenance_ref=None,
        )

        with self.assertRaises(ValidationError):
            self._validator("bar_feature_v1.schema.json").validate(bar)

    def test_real_zero_is_valid_when_feature_is_available(self):
        bar = deepcopy(self._fixture("bar_feature_v1.valid.json"))
        feature = bar["acoustic"]["energy_normalized"]
        feature.update(
            value=0.0,
            availability="available",
            confidence=0.9,
            provenance_ref="prov_explicit_v1",
        )

        self._validator("bar_feature_v1.schema.json").validate(bar)

    def test_utc_timestamp_with_offset_is_rejected(self):
        track = self._fixture("track_analysis_v1.valid.json")
        track["created_at"] = "2026-08-30T16:15:30+08:00"

        with self.assertRaises(ValidationError):
            self._validator("track_analysis_v1.schema.json").validate(track)


if __name__ == "__main__":
    unittest.main()
