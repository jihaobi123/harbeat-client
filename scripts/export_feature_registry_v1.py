"""Export the historical 69-feature report into the V1 contract registry."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.modules.library.feature_registry import definition_for
from jsonschema.validators import validator_for
from referencing import Registry, Resource


DEFAULT_SOURCE = (
    REPO_ROOT
    / "experiments"
    / "traditional_vs_ml_20260829"
    / "reports"
    / "feature_selection.csv"
)
DEFAULT_DESTINATION = REPO_ROOT / "contracts" / "registries" / "analysis_features_v1.jsonl"
EXPECTED_HEADERS = (
    "feature",
    "validation_mode",
    "selection_metric",
    "selection_value",
    "f1",
    "sample_count",
    "calibration_status",
    "main_accuracy_gt_0_50",
    "sensitivity_accuracy_and_f1_gt_0_50",
)

DISPLAY_NAMES_ZH = {
    "chord_change_activity": "和弦变化活动度",
    "harmonic_complexity": "和声复杂度",
    "jazz_soul_harmony": "爵士与灵魂乐和声",
    "808_timbre_candidate": "808 音色候选",
    "bass_kick_interlock": "贝斯与底鼓咬合",
    "bass_octave_pattern": "贝斯八度型",
    "bass_pitch_stability": "贝斯音高稳定度",
    "bass_reply_pattern": "贝斯应答型",
    "bass_riff_repetition": "贝斯乐句重复度",
    "bass_slide": "贝斯滑音",
    "bass_staccato_ratio": "贝斯断奏比例",
    "bass_syncopation": "贝斯切分度",
    "kick_bass_alignment": "底鼓与贝斯对齐度",
    "log_drum": "Log Drum（旧名）",
    "log_drum_candidate": "Log Drum 候选（旧名）",
    "low_frequency_melody": "低频旋律性",
    "low_percussive_bass_candidate": "低音高打击型贝斯候选",
    "sliding_808": "滑音 808（旧名）",
    "sliding_bass_candidate": "滑音贝斯候选",
    "sub_808": "Sub 808（旧名）",
    "sub_bass": "超低频贝斯",
    "sustained_harmonic_bass_candidate": "持续谐波贝斯候选",
    "continuous_high_percussion": "连续高频打击乐",
    "full_snare": "饱满军鼓",
    "hand_drum_family": "手鼓家族",
    "low_pitched_drum": "低音高鼓",
    "mid_pitched_drum": "中音高鼓",
    "repeated_tonal_motif": "重复音高型动机",
    "short_metallic": "短促金属打击",
    "short_rim_snap": "短促边击或指响",
    "sustained_metallic": "持续金属打击",
    "tonal_percussion": "有音高打击乐",
    "wide_clap": "宽立体声拍手",
    "acoustic_production": "原声制作倾向",
    "brightness": "明亮度",
    "dark_timbre": "暗色音色",
    "distortion": "失真度",
    "electronic_production": "电子制作倾向",
    "lofi_texture": "Lo-fi 质感",
    "rage_synth": "Rage 合成器（旧名）",
    "rage_synth_candidate": "Rage 合成器候选",
    "sample_texture": "采样质感",
    "sampled_loop_tendency": "采样循环倾向",
    "afro_syncopation": "非洲律动切分",
    "backbeat_2_4": "第二、四拍反拍重音",
    "breakbeat": "碎拍律动",
    "dembow": "Dembow 律动",
    "drill_hat": "Drill 踩镲型",
    "drum_loop_repetition": "鼓循环重复度",
    "drum_machine_consistency": "鼓机一致性",
    "four_floor_stability": "四踩稳定度",
    "four_on_floor": "四踩律动",
    "halftime_snare_3": "半拍第三拍军鼓",
    "jersey_club": "Jersey Club 律动",
    "offbeat_open_hat": "反拍开镲",
    "swing": "摇摆度",
    "tamborzao": "Tamborzão 律动",
    "timing_quantization": "节奏量化度",
    "tresillo": "Tresillo 律动",
    "two_step": "Two-step 律动",
    "melodic_contour": "人声旋律轮廓",
    "pitch_sustain_ratio": "人声音高持续比例",
    "rap_delivery": "说唱演唱法",
    "singing": "歌唱演唱法",
    "syllabic_activity": "音节活动度",
    "vocal_chop": "人声切片",
    "vocal_chop_repetition": "人声切片重复度",
    "vocal_density": "人声密度",
    "vocal_pitch_range": "人声音域"
}

SOURCE_POLICIES = {
    "measurement": ["explicit"],
    "derived": ["explicit", "rule", "derived"],
    "semantic": ["explicit", "rule", "trained_head", "manual"],
}


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Expected a finite number, got {value!r}")
    return result


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    result = int(value)
    if result < 0:
        raise ValueError(f"Expected a non-negative integer, got {value!r}")
    return result


def _boolean(value: str | None) -> bool:
    normalized = str(value).strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Expected True or False, got {value!r}")
    return normalized == "true"


def _registry_validator():
    schema_dir = REPO_ROOT / "contracts" / "schemas" / "analysis"
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in schema_dir.glob("*_v1.schema.json")
    }
    registry = Registry().with_resources(
        (schema_id, Resource.from_contents(schema))
        for schema_id, schema in schemas.items()
    )
    schema = schemas["feature_registry_entry_v1.schema.json"]
    return validator_for(schema)(schema, registry=registry)


def _semantic_definition(feature_id: str, display_name: str, semantic_level: str) -> str:
    if semantic_level == "measurement":
        method = "直接音频测量"
    elif semantic_level == "derived":
        method = "由时序或频谱测量按版本化规则派生"
    else:
        method = "需要人工标签确认的音乐语义候选"
    return (
        f"{display_name}（{feature_id}）的 0–1 历史分析分数，属于{method}。"
        "本 0.1.0 条目用于无损迁移历史证据；正例、反例和边界案例须在标签指南中另行冻结。"
    )


def _source_artifact(source_path: Path) -> str:
    try:
        return source_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return source_path.name


def _entry_from_row(row: dict[str, str], source_path: Path) -> dict[str, Any]:
    feature_id = row["feature"].strip()
    group, name = feature_id.split(".", 1)
    definition = definition_for(group, name)
    calibration_status = row["calibration_status"].strip()
    if calibration_status not in {
        "validated",
        "failed_validation",
        "no_heldout_accuracy_record",
    }:
        raise ValueError(f"Unsupported calibration_status: {calibration_status!r}")
    validation_mode = row["validation_mode"].strip() or None
    if validation_mode not in {None, "binary", "continuous"}:
        raise ValueError(f"Unsupported validation_mode: {validation_mode!r}")
    if calibration_status in {"validated", "failed_validation"}:
        status = calibration_status
    else:
        status = definition.default_status

    display_name = DISPLAY_NAMES_ZH[name]
    canonical_feature_id = (
        f"{group}.{definition.canonical_name}"
        if definition.canonical_name
        else None
    )
    selection_metric = row["selection_metric"].strip() or None

    return {
        "schema_name": "harbeat.feature_registry_entry",
        "schema_version": "1.0.0",
        "feature_id": feature_id,
        "definition_version": "0.1.0",
        "display_name_zh": display_name,
        "semantic_level": definition.semantic_level,
        "canonical_feature_id": canonical_feature_id,
        "json_path": feature_id,
        "granularity": "track",
        "dtype": "number",
        "unit": "normalized_score",
        "allowed_values_or_range": {"minimum": 0.0, "maximum": 1.0},
        "semantic_definition": _semantic_definition(
            feature_id, display_name, definition.semantic_level
        ),
        "source_policy": SOURCE_POLICIES[definition.semantic_level],
        "dependencies": [],
        "missing_policy": "null",
        "consumers": ["training", "evaluation"],
        "validation_metric": selection_metric or "not_evaluated",
        "production_threshold": None,
        "validation_evidence": {
            "source_artifact": _source_artifact(source_path),
            "calibration_status": calibration_status,
            "validation_mode": validation_mode,
            "selection_metric": selection_metric,
            "selection_value": _optional_float(row["selection_value"]),
            "f1": _optional_float(row["f1"]),
            "sample_count": _optional_int(row["sample_count"]),
            "main_accuracy_gt_0_50": _boolean(row["main_accuracy_gt_0_50"]),
            "sensitivity_accuracy_and_f1_gt_0_50": _boolean(
                row["sensitivity_accuracy_and_f1_gt_0_50"]
            ),
        },
        "status": status,
        "owner": "workflow-b-label-and-model",
        "license_id": None,
    }


def export_feature_registry(source_path: Path, destination: Path) -> list[dict[str, Any]]:
    source_path = Path(source_path)
    destination = Path(destination)
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_HEADERS:
            raise ValueError(
                f"Unexpected feature report headers: {reader.fieldnames!r}; "
                f"expected {EXPECTED_HEADERS!r}"
            )
        rows = list(reader)

    entries = sorted(
        (_entry_from_row(row, source_path) for row in rows),
        key=lambda entry: entry["feature_id"],
    )
    if len(entries) != 69 or len({entry["feature_id"] for entry in entries}) != 69:
        raise ValueError("Historical feature report must contain exactly 69 unique features")
    missing_names = {
        entry["feature_id"].split(".", 1)[1]
        for entry in entries
        if entry["feature_id"].split(".", 1)[1] not in DISPLAY_NAMES_ZH
    }
    if missing_names:
        raise ValueError(f"Missing Chinese display names: {sorted(missing_names)}")

    validator = _registry_validator()
    for entry in entries:
        validator.validate(entry)

    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(entry, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        for entry in entries
    )
    destination.write_text(content, encoding="utf-8")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    entries = export_feature_registry(args.source, args.output)
    print(f"Exported {len(entries)} feature definitions to {args.output}")


if __name__ == "__main__":
    main()
