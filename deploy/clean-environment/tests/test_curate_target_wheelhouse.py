import importlib.util
from pathlib import Path

from packaging.utils import parse_wheel_filename


SCRIPT = Path(__file__).parents[1] / "tools" / "curate_target_wheelhouse.py"
SPEC = importlib.util.spec_from_file_location("curate_target_wheelhouse", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def tags(filename: str):
    return parse_wheel_filename(filename)[3]


def test_linux_aarch64_rejects_windows_wheel() -> None:
    assert not MODULE.target_compatible(
        tags("lameenc-1.8.4-cp313-cp313-win_amd64.whl"), "cp310", "linux-aarch64"
    )


def test_linux_aarch64_accepts_cp310_arm64_wheel() -> None:
    assert MODULE.target_compatible(
        tags("lameenc-1.8.4-cp310-cp310-manylinux2014_aarch64.whl"),
        "cp310",
        "linux-aarch64",
    )


def test_linux_aarch64_accepts_universal_python3_wheel() -> None:
    assert MODULE.target_compatible(
        tags("fastapi-0.116.1-py3-none-any.whl"), "cp310", "linux-aarch64"
    )
