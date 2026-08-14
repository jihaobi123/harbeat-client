from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


JETSON_SERVICES = frozenset({
    "catalog-api",
    "analysis-worker",
    "stem-worker",
    "planning-api",
    "render-worker",
})
RK_SERVICES = frozenset({
    "sync-worker",
    "edge-agent",
    "audio-engine",
    "input-daemon",
})
FORBIDDEN_MARKERS = (
    "/".join(("", "home", "cat", "cypher")),
    "/".join(("", "home", "cat", "venvs")),
    "/".join(("", "home", "mark", "harbeat")),
    "/".join(("", "home", "mark", "venvs")),
)


class AdapterConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    service: str
    profile: str
    mode: str
    state_root: Path
    asset_root: Path
    settings: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: dict[str, Any], *, expected_service: str | None = None) -> "AdapterConfig":
        if value.get("schema_version") != 1:
            raise AdapterConfigError("unsupported adapter config schema")
        service = str(value.get("service") or "").strip()
        if expected_service and service != expected_service:
            raise AdapterConfigError("adapter config service mismatch")
        if service in JETSON_SERVICES:
            expected_profile = "jetson"
        elif service in RK_SERVICES:
            expected_profile = "rk3588"
        else:
            raise AdapterConfigError(f"unknown service: {service}")
        profile = str(value.get("profile") or "").strip()
        if profile != expected_profile:
            raise AdapterConfigError(f"service {service} requires profile {expected_profile}")
        mode = str(value.get("mode") or "").strip()
        if mode != "shadow":
            raise AdapterConfigError("v0.3 adapters only permit shadow mode")
        state_root = _absolute_path(value.get("state_root"), "state_root")
        asset_root = _absolute_path(value.get("asset_root"), "asset_root")
        for path in (state_root, asset_root):
            normalized = path.as_posix()
            if any(marker in normalized for marker in FORBIDDEN_MARKERS):
                raise AdapterConfigError(f"legacy path is forbidden: {path}")
        settings = value.get("settings") or {}
        if not isinstance(settings, dict):
            raise AdapterConfigError("settings must be an object")
        required_settings = {
            "sync-worker": ("jetson_base_url", "runtime_home"),
            "edge-agent": ("sync_worker_url", "audio_socket", "runtime_home"),
            "audio-engine": ("audio_socket", "runtime_home"),
            "input-daemon": ("edge_agent_url", "audio_socket", "input_device"),
        }.get(service, ())
        missing = [name for name in required_settings if not str(settings.get(name) or "").strip()]
        if missing:
            raise AdapterConfigError(f"missing service settings: {', '.join(missing)}")
        if service == "edge-agent" and bool(settings.get("operation_executor_enabled")):
            operation_missing = [
                name for name in ("planning_api_url", "render_worker_url")
                if not str(settings.get(name) or "").strip()
            ]
            if operation_missing:
                raise AdapterConfigError(
                    f"missing operation executor settings: {', '.join(operation_missing)}"
                )
        for name in ("runtime_home",):
            if name in settings:
                runtime_path = _absolute_path(settings[name], name)
                if any(marker in runtime_path.as_posix() for marker in FORBIDDEN_MARKERS):
                    raise AdapterConfigError(f"legacy path is forbidden: {runtime_path}")
                settings[name] = str(runtime_path)
        return cls(service, profile, mode, state_root, asset_root, dict(settings))

    @classmethod
    def load(cls, path: Path, *, expected_service: str | None = None) -> "AdapterConfig":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterConfigError(f"invalid adapter config: {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise AdapterConfigError("adapter config must be an object")
        return cls.from_mapping(value, expected_service=expected_service)

    def prepare_shadow_directories(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.asset_root.mkdir(parents=True, exist_ok=True)


def _absolute_path(value: Any, name: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise AdapterConfigError(f"{name} is required")
    path = Path(raw)
    posix_absolute = PurePosixPath(raw).is_absolute()
    if not path.is_absolute() and not posix_absolute:
        raise AdapterConfigError(f"{name} must be absolute")
    return path if posix_absolute and os.name == "nt" else path.resolve()
