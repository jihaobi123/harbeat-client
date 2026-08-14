#!/usr/bin/env python3
"""Build a read-only R1 base-environment audit from tracked manifests."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy" / "clean-environment"
OUTPUT = DEPLOY / "evidence" / "r1-base-environment-audit-20260814.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or None


def tracked_files() -> list[Path]:
    relative = [
        "profiles/rk3588.json",
        "profiles/jetson.json",
        "locks/rk3588.system-packages.lock",
        "locks/rk3588.python.lock",
        "locks/jetson.system-packages.lock",
        "locks/jetson.python.lock",
        "locks/jetson.gpu-artifacts.json",
        "locks/build-tools.lock",
        "inventory-rk.json",
        "inventory-jetson.json",
        "evidence/r1-rk-inventory-current.json",
        "evidence/r1-jetson-inventory-current.json",
        "evidence/r1-exact-system-package-locks-20260814.json",
        "evidence/r1-recovery-bundles-20260814.json",
        "evidence/r1-r2-runtime-dependency-gap-20260814.json",
        "release-manifest.json",
        "service-manifest.json",
        "acceptance-report-v0.3.0.json",
    ]
    return [DEPLOY / item for item in relative]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def main() -> int:
    files = tracked_files()
    missing = [str(path.relative_to(ROOT)) for path in files if not path.is_file()]
    checksums = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in files
        if path.is_file()
    }
    rk_profile = load_json(DEPLOY / "profiles" / "rk3588.json")
    jetson_profile = load_json(DEPLOY / "profiles" / "jetson.json")
    acceptance = load_json(DEPLOY / "acceptance-report-v0.3.0.json")
    exact_locks = load_json(DEPLOY / "evidence" / "r1-exact-system-package-locks-20260814.json")
    exact_lock_roles = exact_locks.get("roles", {})
    recovery_bundles = load_json(DEPLOY / "evidence" / "r1-recovery-bundles-20260814.json")
    dependency_gap = load_json(DEPLOY / "evidence" / "r1-r2-runtime-dependency-gap-20260814.json")
    result = {
        "schema_version": 1,
        "audit": "r1-base-environment",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": git_head(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "tracked_inputs": checksums,
        "missing_inputs": missing,
        "profiles": {
            "rk3588": {
                "platform": rk_profile.get("platform"),
                "services": sorted(rk_profile.get("services", {})),
                "hardware_gates": sorted(rk_profile.get("hardware_gates", [])),
            },
            "jetson": {
                "platform": jetson_profile.get("platform"),
                "services": sorted(jetson_profile.get("services", {})),
                "hardware_gates": sorted(jetson_profile.get("hardware_gates", [])),
            },
        },
        "inherited_evidence": {
            "module_tests": acceptance.get("passed", {}).get("module_tests"),
            "rk_base_hardware": acceptance.get("passed", {}).get("rk_base_hardware"),
            "jetson_base_hardware": acceptance.get("passed", {}).get("jetson_base_hardware"),
            "rk_python_imports": acceptance.get("passed", {}).get("rk_python_3_10_wheel_imports"),
            "jetson_python_imports": acceptance.get("passed", {}).get("jetson_python_3_10_wheel_imports"),
        },
        "exact_system_package_locks": {
            role: {
                "complete": value.get("complete", False),
                "missing": value.get("missing", []),
                "resolved_executables": [
                    {
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "sha256": item.get("sha256"),
                    }
                    for item in value.get("resolved_executables", [])
                ],
            }
            for role, value in exact_lock_roles.items()
        },
        "current_runtime_dependency_gap": dependency_gap.get("roles", {}),
        "gates": {
            "tracked_manifests_complete": not missing,
            "exact_system_package_locks_complete": bool(exact_lock_roles) and all(
                value.get("complete", False) for value in exact_lock_roles.values()
            ),
            "external_recovery_bundles_verified": recovery_bundles.get("passed", False),
            "target_clean_python_venvs_verified": all(
                value.get("clean_venv_created", False)
                for value in dependency_gap.get("roles", {}).values()
            ),
            "clean_deployment_scaffold_verified": acceptance.get("passed", {}).get("clean_root_bootstrap_stage_verify"),
            "base_image_built": False,
            "empty_device_restore": False,
            "remote_mutation_performed": False,
            "r1_passed": False,
        },
        "safety": {
            "production_services_restarted": False,
            "legacy_runtime_modified": False,
            "cleanup_authorized": False,
        },
        "next_action": "Build and restore RK/Jetson base images before authorizing runtime quarantine.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
