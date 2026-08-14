#!/usr/bin/env python3
"""Resolve baseline package names against read-only device inventories."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy" / "clean-environment"
EVIDENCE = DEPLOY / "evidence"


def package_rows(inventory: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    rows: dict[str, dict[str, str]] = {}
    raw = payload.get("system_packages") or ""
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, version, architecture = parts
        item = {
            "package": name,
            "version": version,
            "architecture": architecture,
        }
        rows[name] = item
        canonical_name = name.split(":", 1)[0]
        rows.setdefault(canonical_name, item)
    return rows


def requested(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def resolve(name: str, rows: dict[str, dict[str, str]]) -> dict[str, str] | None:
    candidates = [name]
    if name == "cuda-runtime":
        candidates = ["cuda-runtime-12-2", "cuda-runtime-12-1"]
    elif name == "cudnn":
        candidates = ["libcudnn8", "libcudnn9"]
    for candidate in candidates:
        if candidate in rows:
            return rows[candidate]
    return None


def build(role: str) -> dict:
    inventory_name = "rk" if role == "rk3588" else role
    inventory = EVIDENCE / f"r1-{inventory_name}-inventory-current.json"
    lock = DEPLOY / "locks" / f"{role}.system-packages.lock"
    rows = package_rows(inventory)
    payload = json.loads(inventory.read_text(encoding="utf-8"))
    executables = payload.get("executables") or {}
    resolved = []
    resolved_executables = []
    missing = []
    for name in requested(lock):
        item = resolve(name, rows)
        if item is None:
            executable = executables.get(name)
            if executable:
                resolved_executables.append({
                    "name": name,
                    "source": "device-executable",
                    **executable,
                })
            else:
                missing.append(name)
        else:
            resolved.append(item)
    return {
        "role": role,
        "inventory": str(inventory.relative_to(ROOT)),
        "requested": requested(lock),
        "resolved": resolved,
        "resolved_executables": resolved_executables,
        "missing": missing,
        "complete": not missing,
    }


def main() -> int:
    report = {
        "schema_version": 1,
        "audit": "r1-exact-system-package-locks",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roles": {role: build(role) for role in ("rk3588", "jetson")},
        "policy": "A missing baseline package blocks base-image acceptance; no fallback package is substituted.",
    }
    output = EVIDENCE / "r1-exact-system-package-locks-20260814.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["complete"] for item in report["roles"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
