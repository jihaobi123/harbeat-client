"""Strict gate between preprocessing and runtime planners."""

from __future__ import annotations

import math
from typing import Any, Mapping


class AnalysisGateError(ValueError):
  pass


def validate_dj_structure_v2(payload: Mapping[str, Any]) -> None:
  if payload.get("version") != "dj_structure_v2":
    raise AnalysisGateError("unsupported DJ structure version")
  if payload.get("source") not in {None, "harbeat_dj_structure_analysis_v2"}:
    raise AnalysisGateError("unexpected DJ structure source")
  for key, expected_type in (
    ("track1_exit_candidates", "track1_exit_candidate"),
    ("track2_entry_candidates", "track2_entry_candidate"),
  ):
    rows = payload.get(key)
    if not isinstance(rows, list) or not rows:
      raise AnalysisGateError(f"{key} is missing")
    for row in rows:
      if not isinstance(row, Mapping):
        raise AnalysisGateError(f"{key} contains non-object candidate")
      if row.get("type") != expected_type:
        raise AnalysisGateError(f"{key} contains wrong candidate type")
      if row.get("audio_feature_source") != "dj_structure_precomputed_window_v2":
        raise AnalysisGateError(f"{key} contains wrong feature source")
      for field in ("time", "score"):
        value = row.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
          raise AnalysisGateError(f"{key}.{field} must be finite")
      if float(row["time"]) < 0:
        raise AnalysisGateError(f"{key}.time must be non-negative")
