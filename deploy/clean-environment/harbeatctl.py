#!/usr/bin/env python3
"""Safe, old-environment-independent HarBeat deployment controller."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


MODULE_ROOT = Path(__file__).resolve().parents[2] / "modules"
DEPLOY_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = DEPLOY_ROOT / "release-manifest.json"
SERVICE_MANIFEST_PATH = DEPLOY_ROOT / "service-manifest.json"
FORBIDDEN_MARKERS = (
    "/home/cat/cypher",
    "/home/cat/venvs",
    "/home/mark/harbeat",
    "/home/mark/venvs",
)
SCAN_SUFFIXES = {".py", ".toml", ".yaml", ".yml", ".sh", ".service"}
SCAN_EXCLUDED_NAMES = {"harbeatctl.py"}


class DeploymentError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DeploymentError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest() -> dict[str, Any]:
    value = load_json(MANIFEST_PATH)
    if value.get("schema_version") != 1:
        raise DeploymentError("unsupported release manifest schema")
    if value.get("production_ready") is not False:
        raise DeploymentError("clean core release cannot be marked production-ready")
    if value.get("cleanup_authorized") is not False:
        raise DeploymentError("cleanup must remain unauthorized before device acceptance")
    return value


def module_ids() -> set[str]:
    return {path.name for path in MODULE_ROOT.iterdir() if path.is_dir() and (path / "MODULE.yaml").exists()}


def validate() -> dict[str, Any]:
    value = manifest()
    expected = set(value["python_modules"]) | set(value["dart_modules"])
    actual = module_ids()
    if expected != actual:
        raise DeploymentError(f"module registry mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    service_manifest = load_json(SERVICE_MANIFEST_PATH)
    if service_manifest.get("schema_version") != 1:
        raise DeploymentError("unsupported service manifest schema")
    if service_manifest.get("production_ready") is not False or service_manifest.get("adapter_mode") != "shadow":
        raise DeploymentError("clean core service adapters must remain shadow-only")
    registered_services = service_manifest.get("services")
    if not isinstance(registered_services, dict):
        raise DeploymentError("service manifest is missing services")
    for profile_name in ("rk3588", "jetson"):
        profile = load_json(DEPLOY_ROOT / "profiles" / f"{profile_name}.json")
        if profile.get("profile") != profile_name or profile.get("schema_version") != 1:
            raise DeploymentError(f"invalid profile: {profile_name}")
        expected_services = set(profile.get("services") or {})
        actual_services = {
            name for name, spec in registered_services.items()
            if isinstance(spec, dict) and spec.get("profile") == profile_name
        }
        if expected_services != actual_services:
            raise DeploymentError(
                f"service registry mismatch for {profile_name}: "
                f"expected={sorted(expected_services)} actual={sorted(actual_services)}"
            )
    common = load_json(DEPLOY_ROOT / "config" / "common.example.json")
    if common.get("schema_version") != 1:
        raise DeploymentError("invalid common configuration")
    text_files = scan_paths(list(DEPLOY_ROOT.rglob("*")) + list(MODULE_ROOT.rglob("*")))
    violations: list[str] = []
    for path in text_files:
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                violations.append(f"{path}: {marker}")
    if violations:
        raise DeploymentError("legacy path references found:\n" + "\n".join(violations))
    return {
        "release": value["release"],
        "module_count": len(expected),
        "python_module_count": len(value["python_modules"]),
        "dart_module_count": len(value["dart_modules"]),
        "production_ready": False,
        "cleanup_authorized": False,
    }


def scan_paths(paths: list[Path]) -> list[Path]:
    return [
        path
        for path in paths
        if path.is_file()
        and path.name not in SCAN_EXCLUDED_NAMES
        and path.suffix.casefold() in SCAN_SUFFIXES
        and "provenance-" not in path.name
    ]


def root_path(raw: str | None) -> Path:
    return Path(raw or os.environ.get("HARBEAT_ROOT", ".")).resolve()


def layout(root: Path) -> dict[str, Path]:
    return {
        "releases": root / "opt" / "harbeat" / "releases",
        "current": root / "opt" / "harbeat" / "current",
        "config": root / "etc" / "harbeat",
        "state": root / "var" / "lib" / "harbeat",
        "logs": root / "var" / "log" / "harbeat",
        "assets": root / "srv" / "harbeat-assets",
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bootstrap(args: argparse.Namespace) -> dict[str, Any]:
    result = validate()
    paths = layout(root_path(args.root))
    for key, path in paths.items():
        if key == "current":
            continue
        path.mkdir(parents=True, exist_ok=True)
    (paths["config"] / "secrets").mkdir(parents=True, exist_ok=True)
    common = load_json(DEPLOY_ROOT / "config" / "common.example.json")
    write_json(paths["config"] / "common.json", common)
    write_json(paths["config"] / "release-manifest.json", manifest())
    return {"action": "bootstrap", "root": str(root_path(args.root)), **result}


def copy_release(destination: Path, release: str) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    def ignore_build_artifacts(directory: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in {"build", "dist"} or name.endswith(".egg-info") or name == "__pycache__":
                ignored.add(name)
        return ignored

    shutil.copytree(MODULE_ROOT, destination / "modules", ignore=ignore_build_artifacts)
    clean_deploy = DEPLOY_ROOT
    shutil.copytree(clean_deploy, destination / "deploy" / "clean-environment")
    test_script = MODULE_ROOT.parent / "scripts" / "test_functional_modules.ps1"
    if test_script.exists():
        (destination / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(test_script, destination / "scripts" / test_script.name)
    release_manifest = dict(manifest())
    release_manifest["release"] = release
    write_json(destination / "release-manifest.json", release_manifest)


def stage(args: argparse.Namespace) -> dict[str, Any]:
    result = validate()
    root = root_path(args.root)
    paths = layout(root)
    paths["releases"].mkdir(parents=True, exist_ok=True)
    release = args.release or manifest()["release"]
    target = paths["releases"] / release
    if target.exists():
        raise DeploymentError(f"release already exists: {target}")
    with tempfile.TemporaryDirectory(dir=paths["releases"], prefix=f".{release}.") as tmp:
        copy_release(Path(tmp) / "payload", release)
        os.replace(Path(tmp) / "payload", target)
    return {**result, "action": "stage", "release": release, "path": str(target)}


def verify(args: argparse.Namespace) -> dict[str, Any]:
    result = validate()
    root = root_path(args.root)
    paths = layout(root)
    release = args.release or manifest()["release"]
    target = paths["releases"] / release
    if not target.is_dir():
        raise DeploymentError(f"release not staged: {target}")
    release_manifest = load_json(target / "release-manifest.json")
    expected_manifest = dict(manifest())
    expected_manifest["release"] = release
    if release_manifest != expected_manifest:
        raise DeploymentError("staged release manifest does not match source manifest")
    forbidden = []
    for path in scan_paths(list(target.rglob("*"))):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                forbidden.append(f"{path}: {marker}")
    if forbidden:
        raise DeploymentError("staged release contains legacy references:\n" + "\n".join(forbidden))
    result["release"] = release
    return {"action": "verify", "path": str(target), **result}


def activate(args: argparse.Namespace) -> dict[str, Any]:
    verified = verify(args)
    root = root_path(args.root)
    paths = layout(root)
    target = paths["releases"] / (args.release or manifest()["release"])
    current = paths["current"]
    previous = current.with_name("previous")
    if current.exists() or current.is_symlink():
        if previous.exists() or previous.is_symlink():
            previous.unlink() if previous.is_symlink() else shutil.rmtree(previous)
        current.rename(previous)
    try:
        current.symlink_to(target, target_is_directory=True)
    except OSError:
        shutil.copytree(target, current)
    write_json(paths["config"] / "active-release.json", {"release": target.name, "path": str(target)})
    return {**verified, "action": "activate", "active": str(target), "previous": str(previous)}


def rollback(args: argparse.Namespace) -> dict[str, Any]:
    root = root_path(args.root)
    paths = layout(root)
    previous = paths["current"].with_name("previous")
    current = paths["current"]
    if not previous.exists() and not previous.is_symlink():
        raise DeploymentError("no previous release is available")
    if current.exists() or current.is_symlink():
        failed = current.with_name("failed-current")
        if failed.exists() or failed.is_symlink():
            failed.unlink() if failed.is_symlink() else shutil.rmtree(failed)
        current.rename(failed)
    previous.rename(current)
    write_json(paths["config"] / "active-release.json", {"release": current.resolve().name, "path": str(current.resolve()), "rolled_back": True})
    return {"action": "rollback", "active": str(current.resolve())}


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    result = validate()
    root = root_path(args.root)
    paths = layout(root)
    active = paths["current"].resolve() if paths["current"].exists() else None
    return {
        "action": "doctor",
        "root": str(root),
        "directories": {name: path.exists() for name, path in paths.items()},
        "active_release": str(active) if active else None,
        **result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harbeatctl")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "bootstrap", "stage", "verify", "activate", "rollback", "doctor"):
        command = sub.add_parser(name)
        if name in {"bootstrap", "stage", "verify", "activate", "rollback", "doctor"}:
            command.add_argument("--root")
        if name in {"stage", "verify", "activate"}:
            command.add_argument("--release")
    args = parser.parse_args(argv)
    handlers = {"validate": lambda: validate(), "bootstrap": lambda: bootstrap(args), "stage": lambda: stage(args), "verify": lambda: verify(args), "activate": lambda: activate(args), "rollback": lambda: rollback(args), "doctor": lambda: doctor(args)}
    try:
        print(json.dumps(handlers[args.command](), ensure_ascii=False, indent=2))
    except DeploymentError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
