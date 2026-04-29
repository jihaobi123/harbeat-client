"""Debug: compare activations from optimized vs original BeatNet pipeline."""
import numpy as np
import time
import logging
import sys
import os

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(message)s")

import collections, collections.abc
for _attr in ("MutableSequence", "MutableMapping", "MutableSet",
              "Mapping", "Sequence", "Iterable", "Iterator"):
    if not hasattr(collections, _attr) and hasattr(collections.abc, _attr):
        setattr(collections, _attr, getattr(collections.abc, _attr))

for _alias, _real in (("float", np.float64), ("int", np.int_),
                       ("complex", np.complex128), ("object", np.object_),
                       ("bool", np.bool_), ("str", np.str_)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _real)

import torch
import librosa
from BeatNet.log_spect import LOG_SPECT
from BeatNet.model import BDA
from BeatNet.BeatNet import BeatNet as BeatNetOriginal

test_file = "data/music-files/shared/California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3"

# --- Original BeatNet pipeline ---
print("=" * 60)
print("  ORIGINAL BeatNet Pipeline (model=1, offline, DBN)")
print("=" * 60)
t0 = time.time()
bn = BeatNetOriginal(1, mode='offline', inference_model='DBN', plot=[], thread=False, device='cuda')
preds_orig = bn.activation_extractor_online(test_file)
output_orig = bn.estimator(preds_orig)
dt = time.time() - t0
print(f"Time: {dt:.1f}s")
print(f"Activations shape: {preds_orig.shape}, dtype: {preds_orig.dtype}")
print(f"Activations min/max: {preds_orig.min():.6f} / {preds_orig.max():.6f}")
print(f"Activations mean: {preds_orig.mean(axis=0)}")
print(f"Activations sum per row (first 5): {preds_orig[:5].sum(axis=1)}")
print(f"Output: {len(output_orig)} events")
if len(output_orig) > 0:
    print(f"First 5 events: {output_orig[:5]}")

# --- Optimized pipeline ---
print("\n" + "=" * 60)
print("  OPTIMIZED Pipeline (shared features, GPU)")
print("=" * 60)

device = 'cuda'
t1 = time.time()
audio, _ = librosa.load(test_file, sr=22050)
print(f"Audio loaded: {time.time()-t1:.1f}s")

t2 = time.time()
sample_rate = 22050
hop_length = int(20 * 0.001 * sample_rate)
win_length = int(64 * 0.001 * sample_rate)
proc = LOG_SPECT(sample_rate=sample_rate, win_length=win_length,
                 hop_size=hop_length, n_bands=[24], mode='offline')
feats_raw = proc.process_audio(audio)
feats_np = feats_raw.T  # (T, F)
feats_tensor = torch.from_numpy(feats_np).unsqueeze(0).to(device)
print(f"Features: {time.time()-t2:.1f}s, shape={feats_np.shape}")

# Run model 1
import BeatNet.model as _bn_model_mod
pkg_dir = os.path.dirname(_bn_model_mod.__file__)

model = BDA(272, 150, 2, device)
weight_path = os.path.join(pkg_dir, 'models', 'model_1_weights.pt')
model.load_state_dict(torch.load(weight_path, map_location=device), strict=False)
model.eval()

with torch.no_grad():
    model.hidden = torch.zeros(2, 1, model.dim_hd, device=device)
    model.cell = torch.zeros(2, 1, model.dim_hd, device=device)
    
    # Without autocast
    preds = model(feats_tensor)[0]
    preds = model.final_pred(preds)

preds_np_opt = preds.cpu().detach().float().numpy()
activations_opt = np.transpose(preds_np_opt[:2, :])

print(f"\nActivations shape: {activations_opt.shape}, dtype: {activations_opt.dtype}")
print(f"Activations min/max: {activations_opt.min():.6f} / {activations_opt.max():.6f}")
print(f"Activations mean: {activations_opt.mean(axis=0)}")
print(f"Activations sum per row (first 5): {activations_opt[:5].sum(axis=1)}")

# Compare original vs optimized activations
if preds_orig.shape == activations_opt.shape:
    diff = np.abs(preds_orig - activations_opt)
    print(f"\nActivation difference: max={diff.max():.6f}, mean={diff.mean():.6f}")
else:
    print(f"\nShape mismatch: orig={preds_orig.shape} vs opt={activations_opt.shape}")

# Try DBN on optimized activations
from madmom.features.downbeats import DBNDownBeatTrackingProcessor
dbn = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=50)
try:
    output_opt = dbn(activations_opt)
    print(f"\nDBN output: {len(output_opt)} events")
    if len(output_opt) > 0:
        print(f"First 5 events: {output_opt[:5]}")
except Exception as exc:
    print(f"\nDBN failed: {exc}")

# Try DBN on original activations
dbn2 = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=50)
try:
    output_check = dbn2(preds_orig)
    print(f"\nDBN on original activations: {len(output_check)} events")
except Exception as exc:
    print(f"\nDBN on original activations failed: {exc}")
