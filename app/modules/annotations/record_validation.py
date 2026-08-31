"""Annotation Record V1 validation shared by API and batch exports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANNOTATION_SCHEMA_PATH = (
    PROJECT_ROOT / "schemas/music_analysis/annotation_record_v1.schema.json"
)
BAR_FEATURE_SCHEMA_PATH = ANNOTATION_SCHEMA_PATH.with_name(
    "bar_feature_v1.schema.json"
)

with ANNOTATION_SCHEMA_PATH.open("r", encoding="utf-8") as schema_handle:
    ANNOTATION_RECORD_SCHEMA = json.load(schema_handle)
with BAR_FEATURE_SCHEMA_PATH.open("r", encoding="utf-8") as schema_handle:
    BAR_FEATURE_SCHEMA = json.load(schema_handle)

ANNOTATION_RECORD_SCHEMA["$id"] = ANNOTATION_SCHEMA_PATH.resolve().as_uri()
BAR_FEATURE_SCHEMA["$id"] = BAR_FEATURE_SCHEMA_PATH.resolve().as_uri()
SCHEMA_REGISTRY = Registry().with_resource(
    BAR_FEATURE_SCHEMA["$id"],
    Resource.from_contents(BAR_FEATURE_SCHEMA),
)
ANNOTATION_RECORD_VALIDATOR = Draft202012Validator(
    ANNOTATION_RECORD_SCHEMA,
    registry=SCHEMA_REGISTRY,
    format_checker=FormatChecker(),
)


def validate_annotation_record(record: dict[str, Any]) -> None:
    ANNOTATION_RECORD_VALIDATOR.validate(record)
    if record["annotation_status"] not in {"reviewed", "adjudicated"}:
        raise ValueError("Presence export only accepts reviewed or adjudicated records")
    if record["value"] is not True:
        raise ValueError("Presence records must have value=true")
