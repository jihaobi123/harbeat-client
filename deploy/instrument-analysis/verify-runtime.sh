#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <model-root> <runtime-python> <harbeat-release>" >&2
  exit 64
fi

MODEL_ROOT="$(realpath "$1")"
RUNTIME_PYTHON="$(realpath "$2")"
RELEASE_ROOT="$(realpath "$3")"
test -x "$RUNTIME_PYTHON"
test -f "$MODEL_ROOT/ADTOF-pytorch/data/adtof_frame_rnn_pytorch_weights.pth"
test -f "$MODEL_ROOT/PANNs/Cnn14_DecisionLevelMax_mAP=0.385.pth"
test -f "$MODEL_ROOT/PANNs/class_labels_indices.csv"
test -f "$RELEASE_ROOT/experiments/run_instrument_analysis_isolated.py"

VERIFY_ROOT="$(mktemp -d /tmp/harbeat-instrument-verify.XXXXXX)"
trap 'rm -rf "$VERIFY_ROOT"' EXIT
FIXTURE="$MODEL_ROOT/ADTOF-pytorch/dev/test.wav"

HARBEAT_MODEL_ROOT="$MODEL_ROOT" "$RUNTIME_PYTHON" \
  "$RELEASE_ROOT/experiments/run_instrument_analysis_isolated.py" \
  --audio "$FIXTURE" \
  --drums-stem "$FIXTURE" \
  --output-dir "$VERIFY_ROOT" \
  --adtof-weights "$MODEL_ROOT/ADTOF-pytorch/data/adtof_frame_rnn_pytorch_weights.pth" \
  --panns-weights "$MODEL_ROOT/PANNs/Cnn14_DecisionLevelMax_mAP=0.385.pth" \
  --panns-labels "$MODEL_ROOT/PANNs/class_labels_indices.csv" \
  --adtof-source "$MODEL_ROOT/ADTOF-pytorch" \
  --panns-source "$MODEL_ROOT/PANNs-source" \
  --device cuda \
  --precision float32

"$RUNTIME_PYTHON" - "$VERIFY_ROOT/manifest.json" <<'PY'
import json
import math
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
track = manifest["tracks"][0]
assert track["models"]["adtof"]["availability"] == "available"
assert track["models"]["panns"]["availability"] == "available"
assert len(track["models"]["panns"]["labels"]) == 527
assert track["models"]["panns"]["windows"]
assert all(
    math.isfinite(score)
    for window in track["models"]["panns"]["windows"]
    for score in window["scores"]
)
assert {
    event["drum_class"] for event in track["models"]["adtof"]["events"]
}.issubset({"kick", "snare", "hihat", "tom", "cymbal"})
print(json.dumps({
    "status": "ready",
    "runtime_fingerprint": manifest["runtime_fingerprint"],
    "adtof_events": len(track["models"]["adtof"]["events"]),
    "panns_windows": len(track["models"]["panns"]["windows"]),
    "peak_cuda_bytes": {
        name: model["peak_cuda_bytes"] for name, model in track["models"].items()
    },
}, sort_keys=True))
PY

