import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "tools" / "build_essentia_recovery_wheel.py"
SPEC = importlib.util.spec_from_file_location("build_essentia_recovery_wheel", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_digest_record_is_wheel_compatible() -> None:
    digest, size = MODULE.digest_record(b"harbeat")
    assert digest.startswith("sha256=")
    assert "=" not in digest.removeprefix("sha256=")
    assert size == "7"


def test_rejects_wrong_package_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "wrong"
    package.mkdir()
    library = tmp_path / "libessentia.so"
    library.write_bytes(b"native")
    monkeypatch.setattr(MODULE.sys, "version_info", (3, 10))
    monkeypatch.setattr(MODULE.platform, "machine", lambda: "aarch64")
    with pytest.raises(ValueError, match="unexpected"):
        MODULE.build(package, library, tmp_path / "out")
