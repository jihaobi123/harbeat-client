import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "verify_library_asset_coverage.py"
SPEC = importlib.util.spec_from_file_location("verify_library_asset_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_verifies_source_and_four_stems() -> None:
    stems = {
        role: f"/legacy/music-files/stems/song/{role}.wav"
        for role in ("vocals", "drums", "bass", "other")
    }
    index = [{"id": "song", "source_path": "/legacy/music-files/shared/song.mp3", "stems": stems}]
    assets = [{"relative_path": "shared/song.mp3"}] + [
        {"relative_path": f"stems/song/{role}.wav"}
        for role in ("vocals", "drums", "bass", "other")
    ]

    report = MODULE.verify(index, {"assets": assets})

    assert report["passed"] is True
    assert report["source_files_ready"] == 1
    assert report["declared_stem_files_ready"] == 4


def test_missing_stem_manifest_is_reported_but_does_not_hide_source_coverage() -> None:
    index = [{"id": "song", "source_path": "/legacy/music-files/shared/song.mp3", "stems": {}}]
    report = MODULE.verify(index, {"assets": [{"relative_path": "shared/song.mp3"}]})

    assert report["passed"] is True
    assert report["songs_without_stem_manifest"] == ["song"]
    assert report["declared_stem_files_expected"] == 0
