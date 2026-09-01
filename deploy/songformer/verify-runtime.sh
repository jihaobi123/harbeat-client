#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 <songformer-root> <muq-root> <runtime-python>" >&2
  exit 64
fi

SONGFORMER_ROOT="$(realpath "$1")"
MUQ_ROOT="$(realpath "$2")"
RUNTIME_PYTHON="$(realpath "$3")"

test -f "$SONGFORMER_ROOT/src/SongFormer/ckpts/SongFormer.safetensors"
test -f "$SONGFORMER_ROOT/src/SongFormer/ckpts/MusicFM/pretrained_msd.pt"
test -f "$SONGFORMER_ROOT/src/SongFormer/ckpts/MusicFM/msd_stats.json"
test -d "$MUQ_ROOT"
test -x "$RUNTIME_PYTHON"

(
  cd "$SONGFORMER_ROOT/src/SongFormer"
  printf '%s  %s\n' \
    "df930aceac8209818556c4a656a0714c" "ckpts/MusicFM/pretrained_msd.pt" \
    "75ab2e47b093e07378f7f703bdb82c14" "ckpts/MusicFM/msd_stats.json" \
    "5a24800e12ab357744f8b47e523ba3e6" "ckpts/SongFormer.safetensors" \
    | md5sum -c -
)

"$RUNTIME_PYTHON" - "$SONGFORMER_ROOT" "$MUQ_ROOT" <<'PY'
import json
from pathlib import Path
import sys
import torch
import torchvision
import safetensors
import ema_pytorch
import muq
import transformers

source = Path(sys.argv[1])
muq_root = Path(sys.argv[2])
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available")
print(json.dumps({
    "status": "ready",
    "songformer_revision": (source / ".harbeat-revision").read_text().strip(),
    "muq_files": sum(path.is_file() for path in muq_root.rglob("*")),
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device": torch.cuda.get_device_name(0),
    "torchvision": torchvision.__version__,
    "transformers": transformers.__version__,
}, sort_keys=True))
PY
