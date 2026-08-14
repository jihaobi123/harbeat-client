#!/usr/bin/env bash
set -euo pipefail

RELEASE_ROOT="${1:-}"
STATE_ROOT="${2:-/var/lib/harbeat}"
CURRENT=/opt/harbeat/current
CYCLES=3

if [[ "$RELEASE_ROOT" != /opt/harbeat/releases/* || ! -x "$RELEASE_ROOT/venv/bin/python" ]]; then
  echo "validated release root is required" >&2
  exit 2
fi
if [[ -e "$CURRENT" && ! -L "$CURRENT" ]]; then
  echo "refusing to replace non-symlink current path" >&2
  exit 2
fi

PREVIOUS_TARGET=""
if [[ -L "$CURRENT" ]]; then
  PREVIOUS_TARGET="$(readlink "$CURRENT")"
  rm "$CURRENT"
fi

restore_previous() {
  rm -f "$CURRENT"
  if [[ -n "$PREVIOUS_TARGET" ]]; then
    ln -s "$PREVIOUS_TARGET" "$CURRENT"
  fi
}
trap restore_previous EXIT

for _cycle in $(seq 1 "$CYCLES"); do
  ln -s "$RELEASE_ROOT" "$CURRENT"
  "$CURRENT/venv/bin/python" - <<'PY'
import harbeat_audio_preprocess
import harbeat_audio_runtime
import harbeat_transition_orchestrator
import harbeat_transition_planner
import harbeat_transition_renderer
PY
  [[ "$(readlink -f "$CURRENT")" == "$(readlink -f "$RELEASE_ROOT")" ]]
  rm "$CURRENT"
  [[ ! -e "$CURRENT" ]]
done

ln -s "$RELEASE_ROOT" "$CURRENT"
mkdir -p "$STATE_ROOT"
cat > "$STATE_ROOT/activation-rollback-report.json" <<JSON
{
  "schema_version": 1,
  "release_root": "$RELEASE_ROOT",
  "cycles_passed": $CYCLES,
  "rollback_baseline": "${PREVIOUS_TARGET:-no_previous_current}",
  "current_target": "$RELEASE_ROOT",
  "services_changed": false,
  "passed": true
}
JSON
trap - EXIT
echo "activation/rollback cycles passed: $CYCLES"
