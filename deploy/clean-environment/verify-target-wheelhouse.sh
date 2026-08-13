#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <profile:jetson|rk3588> <wheelhouse> <venv>" >&2
  exit 2
fi

profile="$1"
wheelhouse="$(realpath "$2")"
venv="$(realpath -m "$3")"

case "$profile" in
  jetson|rk3588) ;;
  *) echo "unsupported profile: $profile" >&2; exit 2 ;;
esac

case "$venv" in
  /tmp/harbeat-clean-*) ;;
  *) echo "refusing to replace venv outside /tmp/harbeat-clean-*: $venv" >&2; exit 2 ;;
esac

python3 - "$wheelhouse" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

wheelhouse = Path(sys.argv[1])
manifest = json.loads((wheelhouse / "wheelhouse-manifest.json").read_text(encoding="utf-8-sig"))
artifacts = manifest.get("artifacts", [])
if len(artifacts) != 12:
    raise SystemExit(f"expected 12 artifacts, got {len(artifacts)}")
for artifact in artifacts:
    path = wheelhouse / artifact["name"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != artifact["sha256"]:
        raise SystemExit(f"sha256 mismatch: {path.name}")
print("wheelhouse sha256: 12/12")
PY

rm -rf "$venv"
python3 -m venv "$venv"
python="$venv/bin/python"

"$python" -m pip install --disable-pip-version-check --quiet \
  "numpy==1.26.4" \
  "soundfile==0.13.1" \
  "sounddevice==0.4.6" \
  "fastapi==0.116.1" \
  "httpx==0.28.1"
"$python" -m pip install --disable-pip-version-check --quiet --no-deps "$wheelhouse"/*.whl

"$python" - <<'PY'
import json
import platform

import harbeat_asset_sync
import harbeat_audio_preprocess
import harbeat_audio_runtime
import harbeat_device_runtime
import harbeat_library_catalog
import harbeat_observability
import harbeat_physical_input
import harbeat_sequence_planner
import harbeat_stem_separation
import harbeat_transition_orchestrator
import harbeat_transition_planner
import harbeat_transition_renderer

print(json.dumps({
    "python": platform.python_version(),
    "architecture": platform.machine(),
    "wheel_imports": "12/12",
}, sort_keys=True))
PY
