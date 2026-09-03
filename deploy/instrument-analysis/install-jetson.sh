#!/usr/bin/env bash
set -euo pipefail

ADTOF_REVISION="85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9"
PANNS_REVISION="d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4"
ADTOF_SHA256="1bc986e596ec47ba0b44916f87cd4a39f0b2bec23596df3fb5d0e87749217320"
PANNS_MD5="70539c43c18b6a289b3199c503a82c5a"
PANNS_SHA256="dd3b4043a87d4ec13df8082c0fcfee3fb5084151808e47e060987a95eabdd142"
PANNS_URL="https://zenodo.org/records/3987831/files/Cnn14_DecisionLevelMax_mAP%3D0.385.pth?download=1"

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <model-root> <runtime-root> <core-python>" >&2
  exit 64
fi

MODEL_ROOT="$(realpath -m "$1")"
RUNTIME_ROOT="$(realpath -m "$2")"
CORE_PYTHON="$(realpath -m "$3")"
for target in "$MODEL_ROOT" "$RUNTIME_ROOT"; do
  if [[ -z "$target" || "$target" == "/" || "$target" == "$HOME" ]]; then
    echo "refusing unsafe target: $target" >&2
    exit 65
  fi
done
if [[ ! -x "$CORE_PYTHON" ]]; then
  echo "core Python is not executable: $CORE_PYTHON" >&2
  exit 66
fi

mkdir -p "$MODEL_ROOT" "$RUNTIME_ROOT"
AVAILABLE_KB="$(df -Pk "$MODEL_ROOT" | awk 'NR==2 {print $4}')"
if [[ -z "$AVAILABLE_KB" || "$AVAILABLE_KB" -lt 8388608 ]]; then
  echo "at least 8 GiB free is required before instrument runtime installation" >&2
  exit 67
fi

ADTOF_ROOT="$MODEL_ROOT/ADTOF-pytorch"
PANNS_SOURCE_ROOT="$MODEL_ROOT/PANNs-source"
PANNS_MODEL_ROOT="$MODEL_ROOT/PANNs"
OVERLAY_ROOT="$RUNTIME_ROOT/instrument-analysis-packages"
WRAPPER="$RUNTIME_ROOT/instrument-analysis-python"
TEMP_ROOT="$(mktemp -d /tmp/harbeat-instrument-install.XXXXXX)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

install_archive_repo() {
  local name="$1"
  local repository="$2"
  local revision="$3"
  local target="$4"
  local marker="$target/.harbeat-revision"
  if [[ -f "$marker" ]]; then
    if [[ "$(<"$marker")" != "$revision" ]]; then
      echo "$name revision mismatch at $target" >&2
      exit 68
    fi
    return
  fi
  if [[ -d "$target" ]] && [[ -n "$(find "$target" -mindepth 1 -print -quit)" ]]; then
    echo "$name source exists without a matching revision marker" >&2
    exit 69
  fi
  mkdir -p "$target"
  local archive="$TEMP_ROOT/$name.tar.gz"
  curl -fL --retry 8 --retry-delay 3 --connect-timeout 20 \
    "https://codeload.github.com/$repository/tar.gz/$revision" -o "$archive"
  tar -xzf "$archive" --strip-components=1 -C "$target"
  printf '%s\n' "$revision" > "$marker"
}

install_archive_repo "adtof" "xavriley/ADTOF-pytorch" "$ADTOF_REVISION" "$ADTOF_ROOT"
install_archive_repo "panns" "qiuqiangkong/audioset_tagging_cnn" "$PANNS_REVISION" "$PANNS_SOURCE_ROOT"

mkdir -p "$PANNS_MODEL_ROOT" "$OVERLAY_ROOT"
ADTOF_WEIGHTS="$ADTOF_ROOT/data/adtof_frame_rnn_pytorch_weights.pth"
PANNS_WEIGHTS="$PANNS_MODEL_ROOT/Cnn14_DecisionLevelMax_mAP=0.385.pth"
PANNS_LABELS="$PANNS_MODEL_ROOT/class_labels_indices.csv"
printf '%s  %s\n' "$ADTOF_SHA256" "$ADTOF_WEIGHTS" | sha256sum -c -

if [[ -f "$PANNS_WEIGHTS" ]]; then
  printf '%s  %s\n' "$PANNS_SHA256" "$PANNS_WEIGHTS" | sha256sum -c -
else
  curl -fL --retry 12 --retry-delay 5 --connect-timeout 20 \
    "$PANNS_URL" -o "$TEMP_ROOT/panns.pth"
  printf '%s  %s\n' "$PANNS_MD5" "$TEMP_ROOT/panns.pth" | md5sum -c -
  printf '%s  %s\n' "$PANNS_SHA256" "$TEMP_ROOT/panns.pth" | sha256sum -c -
  install -m 0644 "$TEMP_ROOT/panns.pth" "$PANNS_WEIGHTS"
fi
install -m 0644 "$PANNS_SOURCE_ROOT/metadata/class_labels_indices.csv" "$PANNS_LABELS"

# Install only missing pure-Python packages. Dependency resolution is disabled
# so NVIDIA's CUDA-enabled Jetson torch cannot be replaced by a generic wheel.
"$CORE_PYTHON" -m pip install --no-deps --upgrade --target "$OVERLAY_ROOT" \
  "pretty-midi==0.2.10" "mido==1.3.3" "torchlibrosa==0.1.0"
install -m 0755 "$(dirname "$0")/instrument-analysis-python" "$WRAPPER"

HARBEAT_MODEL_ROOT="$MODEL_ROOT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - <<'PY'
import json
import torch
import librosa
import pretty_midi
import torchlibrosa

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
if ".nv" not in torch.__version__:
    raise SystemExit(f"expected NVIDIA Jetson torch, got {torch.__version__}")
print(json.dumps({
    "status": "ready",
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device": torch.cuda.get_device_name(0),
    "librosa": librosa.__version__,
    "pretty_midi": pretty_midi.__version__,
    "torchlibrosa": getattr(torchlibrosa, "__version__", "unknown"),
}, sort_keys=True))
PY

echo "ADTOF source revision: $ADTOF_REVISION"
echo "PANNs source revision: $PANNS_REVISION"
echo "Runtime wrapper: $WRAPPER"
