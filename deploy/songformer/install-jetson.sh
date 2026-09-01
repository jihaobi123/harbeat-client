#!/usr/bin/env bash
set -euo pipefail

SONGFORMER_REVISION="139b2aa3b14bd1c6d961d0994e9fc975f1ef7fd5"

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <model-root> <runtime-root> <core-python>" >&2
  exit 64
fi

MODEL_ROOT="$(realpath -m "$1")"
RUNTIME_ROOT="$(realpath -m "$2")"
CORE_PYTHON="$(realpath "$3")"

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

SONGFORMER_ROOT="$MODEL_ROOT/SongFormer"
MUQ_ROOT="$MODEL_ROOT/MuQ-MuLan-large"
OVERLAY_ROOT="$RUNTIME_ROOT/songformer-packages"
WRAPPER="$RUNTIME_ROOT/songformer-python"

mkdir -p "$MODEL_ROOT" "$RUNTIME_ROOT" "$OVERLAY_ROOT"

if [[ -d "$SONGFORMER_ROOT/.git" ]]; then
  if ! git -C "$SONGFORMER_ROOT" diff --quiet || ! git -C "$SONGFORMER_ROOT" diff --cached --quiet; then
    echo "SongFormer source tree is dirty; refusing to overwrite it" >&2
    exit 67
  fi
  git -C "$SONGFORMER_ROOT" fetch --depth 1 origin "$SONGFORMER_REVISION"
else
  git clone --filter=blob:none --no-checkout https://github.com/ASLP-lab/SongFormer.git "$SONGFORMER_ROOT"
  git -C "$SONGFORMER_ROOT" fetch --depth 1 origin "$SONGFORMER_REVISION"
fi
git -C "$SONGFORMER_ROOT" checkout --detach "$SONGFORMER_REVISION"
git -C "$SONGFORMER_ROOT" submodule update --init --recursive --depth 1

"$CORE_PYTHON" -m pip install --target "$OVERLAY_ROOT" \
  "huggingface-hub==0.30.1" \
  "transformers==4.51.1" \
  "tokenizers==0.21.1" \
  "safetensors==0.5.3" \
  "ema-pytorch==0.7.7" \
  "muq==0.1.0" \
  "einops==0.8.1" \
  "einx==0.3.0" \
  "x-transformers==2.4.14" \
  "x-clip==0.14.4" \
  "beartype==0.21.0"

install -m 0755 "$(dirname "$0")/songformer-python" "$WRAPPER"

HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" "$SONGFORMER_ROOT/src/SongFormer/utils/fetch_pretrained.py"
(
  cd "$SONGFORMER_ROOT/src/SongFormer/ckpts"
  md5sum -c md5sum.txt --ignore-missing
)

HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - "$MUQ_ROOT" <<'PY'
from pathlib import Path
import sys
from huggingface_hub import snapshot_download

target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
snapshot_download(
    repo_id="OpenMuQ/MuQ-MuLan-large",
    local_dir=str(target),
    local_dir_use_symlinks=False,
)
PY

HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - <<'PY'
import json
import torch
import librosa
import scipy
import safetensors
import ema_pytorch
import muq
import transformers

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
print(json.dumps({
    "status": "ready",
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device": torch.cuda.get_device_name(0),
    "librosa": librosa.__version__,
    "scipy": scipy.__version__,
    "transformers": transformers.__version__,
}, sort_keys=True))
PY

echo "SongFormer source revision: $(git -C "$SONGFORMER_ROOT" rev-parse HEAD)"
echo "Runtime wrapper: $WRAPPER"
