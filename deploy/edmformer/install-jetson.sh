#!/usr/bin/env bash
set -euo pipefail

EDM98_REVISION="2dd942f2f9e71ffd826346828eeaba1dd3ece56a"
EDMFORMER_SHA256="1412e207645e9a71adc09777714dd251ce7805cada9bf19518d2e455a977e165"
MUSICFM_SHA256="218b483a0256ddef736267425fabb166fd97008983696bb9270def464b47bded"
MUSICFM_STATS_SHA256="c36c61ab10ca4d2e7fdfefc3fcc15205316bec276a06a47baa3641a62c546f22"
MUSICFM_TRANSFORMER_REPO="facebook/wav2vec2-conformer-rope-large-960h-ft"
MUSICFM_TRANSFORMER_REVISION="6b36ef01c6443c67ae7ed0822876d091ab50e4aa"
MUSICFM_TRANSFORMER_CONFIG_SHA256="7a63cb5706c9a37483f1973a3c226d54eb504ce15cf62cb52637019540c8a75d"
EDMFORMER_URL="https://media.githubusercontent.com/media/25ohms/EDM-98/$EDM98_REVISION/data/checkpoints/model.pt"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <model-root> <runtime-root> <core-python>" >&2
  exit 64
fi

MODEL_ROOT="$(realpath -m "$1")"
RUNTIME_ROOT="$(realpath -m "$2")"
CORE_PYTHON="$(cd "$(dirname "$3")" && pwd -P)/$(basename "$3")"
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
if [[ -z "$AVAILABLE_KB" || "$AVAILABLE_KB" -lt 3145728 ]]; then
  echo "at least 3 GiB free is required before EDMFormer installation" >&2
  exit 67
fi

EDM98_ROOT="$MODEL_ROOT/EDM-98"
SONGFORMER_ROOT="$MODEL_ROOT/SongFormer"
MUQ_ROOT="$MODEL_ROOT/MuQ-large-msd-iter"
MUSICFM_SOURCE="$SONGFORMER_ROOT/src/third_party/musicfm"
MUSICFM_MODEL="$SONGFORMER_ROOT/src/SongFormer/ckpts/MusicFM/pretrained_msd.pt"
MUSICFM_STATS="$SONGFORMER_ROOT/src/SongFormer/ckpts/MusicFM/msd_stats.json"
EDMFORMER_MODEL="$EDM98_ROOT/data/checkpoints/model.pt"
HF_CACHE_ROOT="${HARBEAT_HF_CACHE_ROOT:-$MODEL_ROOT/../cache/huggingface}"
SONGFORMER_WRAPPER="$RUNTIME_ROOT/songformer-python"
OVERLAY_ROOT="$RUNTIME_ROOT/edmformer-packages"
WRAPPER="$RUNTIME_ROOT/edmformer-python"
TEMP_ROOT="$(mktemp -d /tmp/harbeat-edmformer-install.XXXXXX)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

for prerequisite in "$SONGFORMER_ROOT" "$MUQ_ROOT" "$MUSICFM_SOURCE"; do
  if [[ ! -d "$prerequisite" ]]; then
    echo "required SongFormer asset is missing: $prerequisite" >&2
    exit 68
  fi
done
for prerequisite in "$MUSICFM_MODEL" "$MUSICFM_STATS"; do
  if [[ ! -f "$prerequisite" ]]; then
    echo "required SongFormer checkpoint is missing: $prerequisite" >&2
    exit 69
  fi
done
if [[ ! -x "$SONGFORMER_WRAPPER" ]]; then
  echo "required SongFormer runtime wrapper is missing: $SONGFORMER_WRAPPER" >&2
  exit 69
fi
printf '%s  %s\n' "$MUSICFM_SHA256" "$MUSICFM_MODEL" | sha256sum -c -
printf '%s  %s\n' "$MUSICFM_STATS_SHA256" "$MUSICFM_STATS" | sha256sum -c -

HF_ENDPOINT="$HF_ENDPOINT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" \
  "$SONGFORMER_WRAPPER" - "$HF_CACHE_ROOT" \
  "$MUSICFM_TRANSFORMER_REPO" "$MUSICFM_TRANSFORMER_REVISION" \
  "$MUSICFM_TRANSFORMER_CONFIG_SHA256" <<'PY'
import hashlib
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

cache_root = Path(sys.argv[1]).expanduser().resolve()
config_path = Path(hf_hub_download(
    repo_id=sys.argv[2],
    filename="config.json",
    revision=sys.argv[3],
    cache_dir=str(cache_root / "hub"),
))
actual = hashlib.sha256(config_path.read_bytes()).hexdigest()
if actual != sys.argv[4]:
    raise SystemExit(f"MusicFM transformer config checksum mismatch: {actual}")
print(f"MusicFM transformer config: {config_path}")
PY

MARKER="$EDM98_ROOT/.harbeat-revision"
if [[ -f "$MARKER" ]]; then
  if [[ "$(<"$MARKER")" != "$EDM98_REVISION" ]]; then
    echo "EDM-98 revision mismatch at $EDM98_ROOT" >&2
    exit 70
  fi
elif [[ -d "$EDM98_ROOT" ]] && [[ -n "$(find "$EDM98_ROOT" -mindepth 1 -print -quit)" ]]; then
  echo "EDM-98 source exists without a matching revision marker" >&2
  exit 71
else
  mkdir -p "$EDM98_ROOT"
  curl -fL --retry 8 --retry-delay 3 --connect-timeout 20 \
    "https://codeload.github.com/25ohms/EDM-98/tar.gz/$EDM98_REVISION" \
    -o "$TEMP_ROOT/edm98.tar.gz"
  tar -xzf "$TEMP_ROOT/edm98.tar.gz" --strip-components=1 -C "$EDM98_ROOT"
  printf '%s\n' "$EDM98_REVISION" > "$MARKER"
fi

mkdir -p "$(dirname "$EDMFORMER_MODEL")" "$OVERLAY_ROOT"
if [[ -f "$EDMFORMER_MODEL" ]]; then
  if printf '%s  %s\n' "$EDMFORMER_SHA256" "$EDMFORMER_MODEL" | sha256sum -c - >/dev/null 2>&1; then
    EDMFORMER_READY=true
  elif head -n 1 "$EDMFORMER_MODEL" | grep -qx 'version https://git-lfs.github.com/spec/v1'; then
    EDMFORMER_READY=false
  else
    echo "EDMFormer checkpoint exists with an unexpected checksum" >&2
    exit 72
  fi
else
  EDMFORMER_READY=false
fi
if [[ "$EDMFORMER_READY" != true ]]; then
  curl -fL --retry 12 --retry-delay 5 --connect-timeout 20 \
    "$EDMFORMER_URL" -o "$TEMP_ROOT/model.pt"
  printf '%s  %s\n' "$EDMFORMER_SHA256" "$TEMP_ROOT/model.pt" | sha256sum -c -
  install -m 0644 "$TEMP_ROOT/model.pt" "$EDMFORMER_MODEL"
fi

# Keep dependency resolution disabled so NVIDIA's CUDA-enabled Jetson torch is
# never replaced. The SongFormer runtime already supplies the shared ML stack.
"$CORE_PYTHON" -m pip install --no-deps --upgrade --target "$OVERLAY_ROOT" \
  "edm98==0.1.0"
install -m 0755 "$(dirname "$0")/edmformer-python" "$WRAPPER"

HARBEAT_MODEL_ROOT="$MODEL_ROOT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - <<'PY'
import edm98
import torch
from edm98.inference import pipeline

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
if ".nv" not in torch.__version__:
    raise SystemExit(f"expected NVIDIA Jetson torch, got {torch.__version__}")
print({"status": "ready", "torch": torch.__version__, "edm98": edm98.__version__})
PY

echo "EDM-98 source revision: $EDM98_REVISION"
echo "EDMFormer checkpoint: $EDMFORMER_MODEL"
echo "Reused MusicFM checkpoint: $MUSICFM_MODEL"
echo "Reused MuQ checkpoint directory: $MUQ_ROOT"
echo "Runtime wrapper: $WRAPPER"
