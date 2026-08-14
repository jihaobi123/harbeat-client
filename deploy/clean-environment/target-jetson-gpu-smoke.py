#!/usr/bin/env python3
import json

import demucs
import torch
import torchaudio


cuda_available = torch.cuda.is_available()
result = {
    "cuda_available": cuda_available,
    "demucs": demucs.__version__,
    "torch": torch.__version__,
    "torchaudio": torchaudio.__version__,
}

if cuda_available:
    sample = torch.ones(4, device="cuda")
    result.update({
        "cuda_device": torch.cuda.get_device_name(0),
        "cuda_sum": float(sample.sum().cpu()),
    })

print(json.dumps(result, sort_keys=True))

if not cuda_available:
    raise SystemExit("CUDA is not available")
