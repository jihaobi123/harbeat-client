#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <profile> <release-root> <internal-wheelhouse> <third-party-wheelhouse>" >&2
  exit 2
fi

PROFILE="$1"
RELEASE_ROOT="$2"
INTERNAL_WHEELHOUSE="$3"
THIRD_PARTY_WHEELHOUSE="$4"

case "$PROFILE" in
  jetson|rk3588) ;;
  *) echo "unsupported profile: $PROFILE" >&2; exit 2 ;;
esac

if [[ "$RELEASE_ROOT" != /opt/harbeat/releases/* ]]; then
  echo "release root must be below /opt/harbeat/releases" >&2
  exit 2
fi
if [[ ! -d "$RELEASE_ROOT" || -n "$(find "$RELEASE_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "release root must exist and be empty: $RELEASE_ROOT" >&2
  exit 2
fi

mapfile -t INTERNAL_WHEELS < <(find "$INTERNAL_WHEELHOUSE" -maxdepth 1 -type f -name '*.whl' -print | sort)
mapfile -t THIRD_PARTY_WHEELS < <(find "$THIRD_PARTY_WHEELHOUSE" -maxdepth 1 -type f -name '*.whl' -print | sort)
if [[ ${#INTERNAL_WHEELS[@]} -ne 12 ]]; then
  echo "expected 12 internal wheels, found ${#INTERNAL_WHEELS[@]}" >&2
  exit 3
fi
if [[ ${#THIRD_PARTY_WHEELS[@]} -eq 0 ]]; then
  echo "third-party wheelhouse is empty" >&2
  exit 3
fi
if [[ ! -f "$INTERNAL_WHEELHOUSE/wheelhouse-manifest.json" ]]; then
  echo "internal wheelhouse manifest is missing" >&2
  exit 3
fi
if [[ ! -f "$THIRD_PARTY_WHEELHOUSE/wheelhouse-manifest.json" ]]; then
  echo "third-party wheelhouse manifest is missing" >&2
  exit 3
fi
if printf '%s\n' "${THIRD_PARTY_WHEELS[@]}" | grep -Eiq 'win_|x86_64|cp31[1-9]'; then
  echo "third-party wheelhouse contains an incompatible artifact" >&2
  exit 3
fi

python3 -m venv "$RELEASE_ROOT/venv"
PYTHON="$RELEASE_ROOT/venv/bin/python"
PIP="$RELEASE_ROOT/venv/bin/pip"

"$PIP" install --disable-pip-version-check --no-index --no-deps "${THIRD_PARTY_WHEELS[@]}"
"$PIP" install --disable-pip-version-check --no-index --no-deps "${INTERNAL_WHEELS[@]}"
"$PIP" check

# The immutable wheel manifests preserve provenance. pip's direct_url files
# would otherwise bind the installed release metadata to the disposable
# staging directory used during installation.
find "$RELEASE_ROOT/venv" -type f -path '*.dist-info/direct_url.json' -delete

"$PYTHON" - <<'PY'
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
print("12 wheel imports ok")
PY

mkdir -p "$RELEASE_ROOT/manifests"
cp "$INTERNAL_WHEELHOUSE/wheelhouse-manifest.json" "$RELEASE_ROOT/manifests/internal-wheelhouse.json"
cp "$THIRD_PARTY_WHEELHOUSE/wheelhouse-manifest.json" "$RELEASE_ROOT/manifests/third-party-wheelhouse.json"
"$PYTHON" - "$PROFILE" "$RELEASE_ROOT" "${#INTERNAL_WHEELS[@]}" "${#THIRD_PARTY_WHEELS[@]}" <<'PY'
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

profile, root, internal_count, third_party_count = sys.argv[1:]
receipt = {
    "schema_version": 1,
    "installed_at": datetime.now(timezone.utc).isoformat(),
    "profile": profile,
    "release_root": root,
    "python": platform.python_version(),
    "architecture": platform.machine(),
    "internal_wheels": int(internal_count),
    "third_party_wheels": int(third_party_count),
    "pip_check": "passed",
    "wheel_imports": "12/12",
    "provenance": "sha256_wheelhouse_manifests",
    "production_ready": False,
}
Path(root, "install-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, sort_keys=True))
PY
