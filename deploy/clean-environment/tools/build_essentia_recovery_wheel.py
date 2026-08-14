#!/usr/bin/env python3
"""Package the deployed ARM64 Essentia build without retaining its old venv."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile


DIST = "essentia"
VERSION = "2.1b6.dev0"
TAG = "cp310-cp310-linux_aarch64"
DIST_INFO = f"{DIST}-{VERSION}.dist-info"
LOADER = b"""# HarBeat clean-release native loader.\nfrom pathlib import Path as _HarBeatPath\nimport ctypes as _harbeat_ctypes\n_harbeat_ctypes.CDLL(str(_HarBeatPath(__file__).with_name(\"libessentia.so\")), mode=_harbeat_ctypes.RTLD_GLOBAL)\ndel _HarBeatPath, _harbeat_ctypes\n"""


def digest_record(data: bytes) -> tuple[str, str]:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def build(
    package_root: Path,
    native_library: Path,
    output_dir: Path,
    *,
    patchelf: Path | None = None,
) -> Path:
    if sys.version_info[:2] != (3, 10) or platform.machine() not in {"aarch64", "arm64"}:
        raise RuntimeError("Essentia recovery wheel must be built with CPython 3.10 on ARM64")
    package_root = package_root.resolve(strict=True)
    native_library = native_library.resolve(strict=True)
    if package_root.name != "essentia" or native_library.name != "libessentia.so":
        raise ValueError("unexpected Essentia package or native library path")
    patchelf_path = str(patchelf or shutil.which("patchelf") or "")
    if not patchelf_path or not Path(patchelf_path).is_file():
        raise RuntimeError("patchelf is required to isolate the bundled native library")
    output_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = output_dir / f"{DIST}-{VERSION}-{TAG}.whl"
    files: dict[str, bytes] = {}
    extension_name = "_essentia.cpython-310-aarch64-linux-gnu.so"
    with tempfile.TemporaryDirectory(prefix="harbeat-essentia-") as temporary:
        patched_extension = Path(temporary) / extension_name
        patched_library = Path(temporary) / "libessentia.so"
        shutil.copy2(package_root / extension_name, patched_extension)
        shutil.copy2(native_library, patched_library)
        subprocess.run([patchelf_path, "--set-rpath", "$ORIGIN", str(patched_extension)], check=True)
        subprocess.run([patchelf_path, "--set-soname", "libessentia.so", str(patched_library)], check=True)
        patched_extension_bytes = patched_extension.read_bytes()
        patched_library_bytes = patched_library.read_bytes()
    for source in sorted(package_root.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative = source.relative_to(package_root).as_posix()
        data = source.read_bytes()
        if relative == extension_name:
            data = patched_extension_bytes
        if relative == "__init__.py":
            data = LOADER + b"\n" + data
        files[f"essentia/{relative}"] = data
    files["essentia/libessentia.so"] = patched_library_bytes
    files[f"{DIST_INFO}/METADATA"] = (
        "Metadata-Version: 2.1\n"
        "Name: essentia\n"
        f"Version: {VERSION}\n"
        "Summary: Frozen HarBeat ARM64 Essentia runtime\n"
        "Requires-Python: >=3.10,<3.11\n"
        "Requires-Dist: six==1.17.0\n"
    ).encode()
    files[f"{DIST_INFO}/WHEEL"] = (
        "Wheel-Version: 1.0\n"
        "Generator: harbeat-build-essentia-recovery-wheel\n"
        "Root-Is-Purelib: false\n"
        f"Tag: {TAG}\n"
    ).encode()
    files[f"{DIST_INFO}/top_level.txt"] = b"essentia\n"
    rows = []
    for name, data in files.items():
        digest, size = digest_record(data)
        rows.append((name, digest, size))
    record_name = f"{DIST_INFO}/RECORD"
    rows.append((record_name, "", ""))
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows(rows)
    files[record_name] = record.getvalue().encode()
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return wheel_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_root", type=Path)
    parser.add_argument("native_library", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--patchelf", type=Path)
    args = parser.parse_args()
    wheel = build(args.package_root, args.native_library, args.output_dir, patchelf=args.patchelf)
    print(f"{wheel} sha256={hashlib.sha256(wheel.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
