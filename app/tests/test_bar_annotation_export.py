from __future__ import annotations

import json

from app.modules.bar_annotations.schemas import AnnotationRecord
from app.modules.bar_annotations.store import AnnotationStore
from scripts.export_bar_annotation_pilot import export_bar_annotation_pilot


DATASET = "bar-understanding-1.0.0"


def _record(user_id: int, value: str) -> AnnotationRecord:
    return AnnotationRecord(
        annotation_id=f"ann-track-1-user-{user_id}",
        dataset_version=DATASET,
        track_id="track-1",
        task_id="structure.section_label",
        granularity="section",
        start_sec=0.0,
        end_sec=2.0,
        start_bar_index=0,
        end_bar_index=1,
        value=value,
        annotator_id=f"user:{user_id}",
        annotation_status="annotated",
        annotator_confidence=0.9,
        candidate_source="analysis:phrase_map:v1",
        created_at="2026-08-31T09:00:00Z",
    )


def test_export_preserves_two_annotators_and_reports_malformed_files(tmp_path) -> None:
    root = tmp_path / "annotations"
    store = AnnotationStore(root)
    for user_id, value in ((11, "intro"), (12, "main")):
        store.save(
            DATASET,
            user_id,
            "track-1",
            0,
            "timeline-a",
            [_record(user_id, value)],
            f"user:{user_id}",
        )
    malformed = root / DATASET / "users" / "13" / "broken.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("{not-json", encoding="utf-8")
    output = tmp_path / "pilot.jsonl"
    report_path = tmp_path / "report.json"

    report = export_bar_annotation_pilot(
        root=root,
        dataset_version=DATASET,
        output_path=output,
        report_path=report_path,
        expected_track_ids=["track-1", "track-2"],
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert {row["annotator_id"] for row in rows} == {"user:11", "user:12"}
    assert report["annotators_total"] == 2
    assert report["tracks_total"] == 1
    assert report["records_exported"] == 2
    assert report["annotators_by_track"] == {"track-1": ["user:11", "user:12"]}
    assert report["completion_by_annotator"]["user:11"] == {
        "tracks_completed": 1,
        "tracks_expected": 2,
    }
    assert report["parse_errors"][0]["path"].endswith("broken.json")
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
