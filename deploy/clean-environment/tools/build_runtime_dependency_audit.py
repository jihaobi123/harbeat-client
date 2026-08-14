#!/usr/bin/env python3
"""Compare clean Python locks with system Python without accepting system state."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy" / "clean-environment"
EVIDENCE = DEPLOY / "evidence"


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def freeze_rows(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, str] = {}
    for line in str(payload.get("python_packages") or "").splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        rows[normalize(name)] = version.strip()
    return rows


def lock_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("python=="):
            continue
        name, version = line.split("==", 1)
        rows[normalize(name)] = version
    return rows


def audit(role: str) -> dict:
    inventory_role = "rk" if role == "rk3588" else role
    inventory = EVIDENCE / f"r1-{inventory_role}-inventory-current.json"
    installed = freeze_rows(inventory)
    requested = lock_rows(DEPLOY / "locks" / f"{role}.python.lock")
    missing = sorted(name for name in requested if name not in installed)
    mismatched = {
        name: {"installed": installed[name], "locked": version}
        for name, version in requested.items()
        if name in installed and installed[name] != version
    }
    return {
        "role": role,
        "locked": requested,
        "system_python_missing": missing,
        "system_python_version_mismatch": mismatched,
        "system_python_matches_lock": not missing and not mismatched,
        "clean_venv_created": False,
        "policy": "System Python is evidence only and is never accepted as the clean service environment.",
    }


def main() -> int:
    report = {
        "schema_version": 1,
        "audit": "r1-r2-runtime-dependency-gap",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roles": {role: audit(role) for role in ("rk3588", "jetson")},
        "module_wheelhouse": {
            "uri": "external://harbeat-device-backups/20260814/wheelhouse-r3",
            "module_wheels": 12,
            "verified_on_target_python_3_10": False,
        },
        "r2_target_runtime_ready": False,
        "cleanup_authorized": False,
    }
    output = EVIDENCE / "r1-r2-runtime-dependency-gap-20260814.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
