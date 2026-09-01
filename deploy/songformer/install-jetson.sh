#!/usr/bin/env bash
set -euo pipefail

SONGFORMER_REVISION="139b2aa3b14bd1c6d961d0994e9fc975f1ef7fd5"
MUQ_SOURCE_REVISION="28847ea50cd31ac4b8b6a7dacc051ad7d1c7606a"
MUSICFM_REVISION="b83ebedb401bcef639b26b05c0c8bee1dc2dfe71"
TORCHVISION_VERSION="0.19.0"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

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
if ! command -v ninja >/dev/null 2>&1; then
  echo "ninja-build is required; install it with: sudo apt-get install ninja-build" >&2
  exit 67
fi

SONGFORMER_ROOT="$MODEL_ROOT/SongFormer"
MUQ_ROOT="$MODEL_ROOT/MuQ-large-msd-iter"
OVERLAY_ROOT="$RUNTIME_ROOT/songformer-packages"
WRAPPER="$RUNTIME_ROOT/songformer-python"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEMP_ROOT"' EXIT

mkdir -p "$MODEL_ROOT" "$RUNTIME_ROOT" "$OVERLAY_ROOT"

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
    echo "$name source exists without a revision marker; refusing to overwrite it" >&2
    exit 69
  fi
  mkdir -p "$target"
  local archive="$TEMP_ROOT/$name.tar.gz"
  curl -fL --retry 8 --retry-delay 3 --connect-timeout 20 \
    "https://codeload.github.com/$repository/tar.gz/$revision" \
    -o "$archive"
  tar -xzf "$archive" --strip-components=1 -C "$target"
  printf '%s\n' "$revision" > "$marker"
}

install_archive_repo "SongFormer" "ASLP-lab/SongFormer" "$SONGFORMER_REVISION" "$SONGFORMER_ROOT"
install_archive_repo "MuQ-source" "tencent-ailab/MuQ" "$MUQ_SOURCE_REVISION" "$SONGFORMER_ROOT/src/third_party/MuQ"
install_archive_repo "musicfm" "minzwon/musicfm" "$MUSICFM_REVISION" "$SONGFORMER_ROOT/src/third_party/musicfm"

# Install only the additional packages. Resolving dependencies normally would
# replace NVIDIA's Jetson CUDA torch with a generic manylinux torch wheel.
"$CORE_PYTHON" -m pip install --no-deps --target "$OVERLAY_ROOT" \
  "huggingface-hub==0.30.1" "transformers==4.51.1" \
  "tokenizers==0.21.1" "safetensors==0.5.3" "ema-pytorch==0.7.7" \
  "muq==0.1.0" "einops==0.8.1" "einx==0.3.0" \
  "x-transformers==2.4.14" "x-clip==0.14.4" "beartype==0.21.0" \
  "easydict==1.13" "nnAudio==0.3.3" "loguru==0.7.3" \
  "ftfy==6.3.1" "frozendict==2.4.6" "wcwidth==0.2.13" \
  "regex==2024.11.6" "filelock==3.18.0" "packaging==24.2" \
  "PyYAML==6.0.2" "requests==2.32.3" "tqdm==4.67.1" \
  "Pillow==11.1.0" "msaf==0.1.80" "mir_eval==0.8.2" \
  "jams==0.3.4" "pandas==2.2.3" "sortedcontainers==2.4.0" \
  "jsonschema==4.23.0" "pytz==2025.2" "python-dateutil==2.9.0.post0" \
  "tzdata==2025.2" "six==1.17.0" "attrs==25.3.0" \
  "jsonschema-specifications==2025.4.1" "referencing==0.36.2" \
  "rpds-py==0.26.0" "matplotlib==3.10.1" "contourpy==1.3.1" \
  "cycler==0.12.1" "fonttools==4.56.0" "kiwisolver==1.4.8" \
  "pyparsing==3.2.1" "vmo==0.30.5" "cvxopt==1.3.2" "wheel==0.45.1"

install -m 0755 "$(dirname "$0")/songformer-python" "$WRAPPER"

# torchvision must be built against NVIDIA's Jetson torch ABI.
VISION_SOURCE="$TEMP_ROOT/vision"
mkdir -p "$VISION_SOURCE"
curl -fL --retry 8 --retry-delay 3 --connect-timeout 20 \
  "https://codeload.github.com/pytorch/vision/tar.gz/refs/tags/v$TORCHVISION_VERSION" \
  -o "$TEMP_ROOT/vision.tar.gz"
tar -xzf "$TEMP_ROOT/vision.tar.gz" --strip-components=1 -C "$VISION_SOURCE"
(
  cd "$VISION_SOURCE"
  BUILD_VERSION="$TORCHVISION_VERSION" FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST=8.7 \
    MAX_JOBS="${MAX_JOBS:-4}" HARBEAT_CORE_PYTHON="$CORE_PYTHON" \
    "$WRAPPER" setup.py bdist_wheel
)
"$CORE_PYTHON" -m pip install --no-deps --upgrade --force-reinstall \
  --target "$OVERLAY_ROOT" "$VISION_SOURCE"/dist/torchvision-*.whl

(
  cd "$SONGFORMER_ROOT/src/SongFormer"
  HF_ENDPOINT="$HF_ENDPOINT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - <<'PY'
from utils.fetch_pretrained import download_all
download_all(use_mirror=True)
PY
  printf '%s  %s\n' \
    "df930aceac8209818556c4a656a0714c" "ckpts/MusicFM/pretrained_msd.pt" \
    "75ab2e47b093e07378f7f703bdb82c14" "ckpts/MusicFM/msd_stats.json" \
    "5a24800e12ab357744f8b47e523ba3e6" "ckpts/SongFormer.safetensors" \
    | md5sum -c -
)

HF_ENDPOINT="$HF_ENDPOINT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - "$MUQ_ROOT" <<'PY'
from pathlib import Path
import sys
from huggingface_hub import snapshot_download

target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
snapshot_download(
    repo_id="OpenMuQ/MuQ-large-msd-iter",
    local_dir=str(target),
    allow_patterns=["config.json", "model.safetensors", "README.md", ".gitattributes"],
)
PY

HF_ENDPOINT="$HF_ENDPOINT" HARBEAT_CORE_PYTHON="$CORE_PYTHON" "$WRAPPER" - "$MUQ_ROOT" <<'PY'
import json
import sys
import torch
import torchvision
import librosa
import scipy
import safetensors
import ema_pytorch
import muq
import transformers
from muq import MuQ

if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
model = MuQ.from_pretrained(sys.argv[1])
print(json.dumps({
    "status": "ready",
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device": torch.cuda.get_device_name(0),
    "torchvision": torchvision.__version__,
    "muq_parameters": sum(parameter.numel() for parameter in model.parameters()),
    "librosa": librosa.__version__,
    "scipy": scipy.__version__,
    "transformers": transformers.__version__,
}, sort_keys=True))
PY

echo "SongFormer source revision: $SONGFORMER_REVISION"
echo "MuQ source revision: $MUQ_SOURCE_REVISION"
echo "MusicFM source revision: $MUSICFM_REVISION"
echo "Runtime wrapper: $WRAPPER"
