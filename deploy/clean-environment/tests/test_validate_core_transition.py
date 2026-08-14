import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "validate_core_transition.py"
SPEC = importlib.util.spec_from_file_location("validate_core_transition", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_resolve_asset_path_rebases_legacy_path(tmp_path: Path) -> None:
    target = tmp_path / "shared" / "song.mp3"
    target.parent.mkdir()
    target.write_bytes(b"audio")

    assert MODULE.resolve_asset_path(
        "/legacy/location/music-files/shared/song.mp3", tmp_path
    ) == target
