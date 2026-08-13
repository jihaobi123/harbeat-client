#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <stage-root> <venv>" >&2
  exit 2
fi

stage_root="$(realpath "$1")"
venv="$(realpath "$2")"
case "$stage_root" in /tmp/harbeat-stagec-*) ;; *) echo "unsafe stage root" >&2; exit 2 ;; esac
case "$venv" in /tmp/harbeat-clean-*) ;; *) echo "unsafe venv" >&2; exit 2 ;; esac

services=(sync-worker edge-agent audio-engine input-daemon)
ports=(19100 19000 19001 19002)
pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

curl --silent --fail --max-time 3 http://127.0.0.1:9000/health >/tmp/harbeat-stagec-legacy-edge-before.json
curl --silent --fail --max-time 3 http://127.0.0.1:9100/status >/tmp/harbeat-stagec-legacy-sync-before.json

export PYTHONPATH="$stage_root"
for index in "${!services[@]}"; do
  service="${services[$index]}"
  port="${ports[$index]}"
  "$venv/bin/python" -m adapters.main \
    --service "$service" \
    --config "$stage_root/config/$service.json" \
    --host 127.0.0.1 \
    --port "$port" \
    >"/tmp/harbeat-stagec-$service.log" 2>&1 &
  pids+=("$!")
done

for index in "${!services[@]}"; do
  service="${services[$index]}"
  port="${ports[$index]}"
  ready=0
  for _attempt in $(seq 1 40); do
    if curl --silent --fail --max-time 2 "http://127.0.0.1:$port/health" >"/tmp/harbeat-stagec-$service-health.json" 2>/dev/null; then
      ready=1
      break
    fi
    sleep 0.2
  done
  if [[ "$ready" -ne 1 ]]; then
    echo "health failed: $service" >&2
    cat "/tmp/harbeat-stagec-$service.log" >&2 || true
    exit 1
  fi
  "$venv/bin/python" - "$service" "/tmp/harbeat-stagec-$service-health.json" <<'PY'
import json
import sys
from pathlib import Path

service = sys.argv[1]
payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if payload.get("ok") is not True or payload.get("service") != service:
    raise SystemExit(f"invalid health payload: {service}: {payload}")
if payload.get("mode") != "shadow" or payload.get("production_ready") is not False:
    raise SystemExit(f"invalid shadow gate: {service}: {payload}")
if service == "audio-engine" and payload.get("audio_ready") is not True:
    raise SystemExit(f"shadow audio socket is not ready: {payload}")
print(json.dumps(payload, sort_keys=True))
PY
done

curl --silent --fail --max-time 3 http://127.0.0.1:9000/health >/tmp/harbeat-stagec-legacy-edge-after.json
curl --silent --fail --max-time 3 http://127.0.0.1:9100/status >/tmp/harbeat-stagec-legacy-sync-after.json
