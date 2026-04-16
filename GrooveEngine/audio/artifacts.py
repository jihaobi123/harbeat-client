from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.datatypes import PlaylistPlan, TransitionPlan
from logic.reporting import build_candidate_search_report


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return target
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for row in rows:
        values = []
        for header in headers:
            value = str(row.get(header, ""))
            escaped = '"' + value.replace('"', '""') + '"'
            values.append(escaped)
        lines.append(",".join(values))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def export_transition_artifact(
    path: str | Path,
    *,
    track_a_title: str,
    track_b_title: str,
    plan: TransitionPlan,
    transition_summary: dict[str, Any],
    render_trace: list[dict[str, Any]],
) -> Path:
    payload = {
        "track_a": track_a_title,
        "track_b": track_b_title,
        "plan": plan.model_dump(mode="json"),
        "summary": transition_summary,
        "render_trace": render_trace,
    }
    return write_json(path, payload)


def export_playlist_artifact(
    path: str | Path,
    *,
    playlist_plan: PlaylistPlan,
    mix_result: dict[str, Any],
    transition_artifacts: list[dict[str, Any]],
) -> Path:
    payload = {
        "playlist_plan": playlist_plan.model_dump(mode="json"),
        "mix_result": mix_result,
        "transition_artifacts": transition_artifacts,
    }
    return write_json(path, payload)




def export_candidate_search_report(
    json_path: str | Path,
    csv_path: str | Path,
    *,
    title: str,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    pruning_rules: dict[str, float] | None = None,
) -> tuple[Path, Path]:
    report = build_candidate_search_report(title=title, rows=rows, metadata=metadata, pruning_rules=pruning_rules)
    write_json(json_path, report)
    write_csv(csv_path, report["rows"])
    return Path(json_path), Path(csv_path)
