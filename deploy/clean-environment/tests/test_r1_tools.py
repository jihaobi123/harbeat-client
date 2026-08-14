from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_exact_package_locks.py"
SPEC = importlib.util.spec_from_file_location("build_exact_package_locks", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_package_rows_indexes_multiarch_name(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps({"system_packages": "libsndfile1:arm64\t1.0.31\tarm64\n"}),
        encoding="utf-8",
    )

    rows = MODULE.package_rows(inventory)

    assert rows["libsndfile1"] == rows["libsndfile1:arm64"]
    assert rows["libsndfile1"]["package"] == "libsndfile1:arm64"


def test_resolve_does_not_substitute_an_unrequested_package() -> None:
    rows = {
        "chromium-codecs-ffmpeg-extra": {
            "package": "chromium-codecs-ffmpeg-extra",
            "version": "1",
            "architecture": "arm64",
        }
    }

    assert MODULE.resolve("ffmpeg", rows) is None
