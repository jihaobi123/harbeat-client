#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 4 ]]; then
  echo "usage: $0 <model-root> <runtime-python> <harbeat-release> <pilot-audio>" >&2
  exit 64
fi

MODEL_ROOT="$(realpath "$1")"
RUNTIME_PYTHON="$(realpath "$2")"
RELEASE_ROOT="$(realpath "$3")"
PILOT_AUDIO="$(realpath "$4")"
RUNTIME_ROOT="$(dirname "$RUNTIME_PYTHON")"
test -x "$RUNTIME_PYTHON"
test -f "$PILOT_AUDIO"
test -f "$MODEL_ROOT/EDM-98/data/checkpoints/model.pt"
test -f "$RELEASE_ROOT/experiments/run_edmformer_isolated.py"

bash "$RELEASE_ROOT/deploy/songformer/verify-runtime.sh" \
  "$MODEL_ROOT/SongFormer" \
  "$MODEL_ROOT/MuQ-large-msd-iter" \
  "$RUNTIME_ROOT/songformer-python"

VERIFY_ROOT="$(mktemp -d /tmp/harbeat-edmformer-verify.XXXXXX)"
trap 'rm -rf "$VERIFY_ROOT"' EXIT
HARBEAT_MODEL_ROOT="$MODEL_ROOT" "$RUNTIME_PYTHON" \
  "$RELEASE_ROOT/experiments/run_edmformer_isolated.py" \
  --audio "$PILOT_AUDIO" \
  --output-dir "$VERIFY_ROOT" \
  --edm98-root "$MODEL_ROOT/EDM-98" \
  --checkpoint "$MODEL_ROOT/EDM-98/data/checkpoints/model.pt" \
  --config "$MODEL_ROOT/EDM-98/configs/edmformer.yaml" \
  --musicfm-source "$MODEL_ROOT/SongFormer/src/third_party/musicfm" \
  --musicfm-model "$MODEL_ROOT/SongFormer/src/SongFormer/ckpts/MusicFM/pretrained_msd.pt" \
  --musicfm-stats "$MODEL_ROOT/SongFormer/src/SongFormer/ckpts/MusicFM/msd_stats.json" \
  --muq-model "$MODEL_ROOT/MuQ-large-msd-iter" \
  --hf-cache-dir "/opt/harbeat/cache/huggingface" \
  --device cuda

"$RUNTIME_PYTHON" - "$VERIFY_ROOT/manifest.json" <<'PY'
import json
import math
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
track = manifest["tracks"][0]
assert track["status"] == "ready"
assert track["frames"]
labels = {"intro", "buildup", "drop", "breakdown", "outro", "silence"}
for frame in track["frames"]:
    probabilities = frame["probabilities"]
    assert set(probabilities) == labels
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities.values())
    assert abs(sum(probabilities.values()) - 1.0) <= 1e-5
assert all(len(track[name]) == 64 for name in (
    "audio_sha256", "muq_sha256", "musicfm_sha256",
    "musicfm_stats_sha256", "edmformer_sha256",
))
fingerprint = manifest["runtime_fingerprint"]
assert fingerprint["device"] == "cuda"
assert fingerprint["peak_cuda_bytes"] > 0
print(json.dumps({
    "status": "ready",
    "frames": len(track["frames"]),
    "boundary_candidates": len(track["boundary_candidates"]),
    "runtime_fingerprint": fingerprint,
}, sort_keys=True))
PY

AVAILABLE_KB="$(df -Pk "$MODEL_ROOT" | awk 'NR==2 {print $4}')"
if [[ -z "$AVAILABLE_KB" || "$AVAILABLE_KB" -lt 8388608 ]]; then
  echo "verification finished but less than 8 GiB remains free" >&2
  exit 73
fi
echo "free space after verification: $((AVAILABLE_KB / 1024)) MiB"
