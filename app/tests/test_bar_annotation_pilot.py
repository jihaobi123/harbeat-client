from __future__ import annotations

import json

import pytest

from app.modules.bar_annotations.pilot import (
    PilotManifest,
    PilotManifestError,
    PilotTrackNotFound,
)


def _write_manifest(tmp_path, track_ids):
    path = tmp_path / "pilot.json"
    path.write_text(
        json.dumps(
            {
                "dataset_version": "bar-understanding-1.0.0",
                "track_ids": track_ids,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_manifest_preserves_order_and_requires_allowlisted_track(tmp_path) -> None:
    manifest = PilotManifest.load(_write_manifest(tmp_path, ["track-b", "track-a"]))

    assert manifest.track_ids == ("track-b", "track-a")
    assert manifest.require_track("track-a") == "track-a"
    with pytest.raises(PilotTrackNotFound):
        manifest.require_track("private-id")


@pytest.mark.parametrize(
    "track_ids",
    [[], ["track-a", "track-a"], ["../escape"], ["track/a"]],
)
def test_manifest_rejects_empty_duplicate_or_unsafe_ids(tmp_path, track_ids) -> None:
    with pytest.raises(PilotManifestError):
        PilotManifest.load(_write_manifest(tmp_path, track_ids))


def test_manifest_rejects_unknown_fields(tmp_path) -> None:
    path = _write_manifest(tmp_path, ["track-a"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["owner_user_id"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PilotManifestError):
        PilotManifest.load(path)
