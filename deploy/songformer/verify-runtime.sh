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
  cd "$SONGFORMER_ROOT/src/SongFormer/ckpts"
  md5sum -c md5sum.txt --ignore-missing
)

"$RUNTIME_PYTHON" - "$SONGFORMER_ROOT" "$MUQ_ROOT" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
import torch
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
    "songformer_revision": subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip(),
    "muq_files": sum(path.is_file() for path in muq_root.rglob("*")),
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "device": torch.cuda.get_device_name(0),
    "transformers": transformers.__version__,
}, sort_keys=True))
PY

