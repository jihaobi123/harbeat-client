"""Debug: test DBN with single beats_per_bar using original BeatNet activations."""
import numpy as np
import collections, collections.abc
import time, sys

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
import os

test_file = "data/music-files/shared/California Love - 2Pac _ Dr. Dre _ The D.O.C..mp3"

# Step 1: Get activations from original BeatNet
print("=== ORIGINAL BeatNet activations ===")
from BeatNet.BeatNet import BeatNet as BN
t0 = time.time()
bn = BN(1, mode='offline', inference_model='DBN', plot=[], thread=False, device='cuda')
preds = bn.activation_extractor_online(test_file)
print(f"Time: {time.time()-t0:.1f}s")
print(f"preds shape: {preds.shape}, dtype: {preds.dtype}")
print(f"preds min/max: {preds.min():.6f} / {preds.max():.6f}")
print(f"preds mean per col: {preds.mean(axis=0)}")

# Step 2: Test with single beats_per_bar
from madmom.features.downbeats import DBNDownBeatTrackingProcessor
print("\n=== DBN with beats_per_bar=[4], fps=50 ===")
dbn4 = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=50)
out = dbn4(preds)
print(f"DBN [4] events: {len(out)}")
if len(out) > 0:
    print(f"First 3: {out[:3]}")
    beats = [float(r[0]) for r in out]
    intervals = np.diff(beats)
    if len(intervals) > 0:
        bpm = 60.0 / np.median(intervals)
        print(f"Median BPM: {bpm:.1f}")

# Step 3: Now test OPTIMIZED pipeline
print("\n=== OPTIMIZED Pipeline ===")
import librosa
from BeatNet.log_spect import LOG_SPECT
from BeatNet.model import BDA

t1 = time.time()
audio, _ = librosa.load(test_file, sr=22050)
print(f"Audio load: {time.time()-t1:.1f}s")

t2 = time.time()
sr = 22050
hop = int(20 * 0.001 * sr)
win = int(64 * 0.001 * sr)
proc = LOG_SPECT(sample_rate=sr, win_length=win, hop_size=hop, n_bands=[24], mode='offline')
feats_raw = proc.process_audio(audio)
feats_np = feats_raw.T
print(f"Features: {time.time()-t2:.1f}s, shape={feats_np.shape}")

device = 'cuda'
feats_tensor = torch.from_numpy(feats_np).unsqueeze(0).to(device)

import BeatNet.model as _bn_mod
pkg_dir = os.path.dirname(_bn_mod.__file__)

model = BDA(272, 150, 2, device)
model.load_state_dict(torch.load(os.path.join(pkg_dir, 'models', 'model_1_weights.pt'),
                                  map_location=device), strict=False)
model.eval()

with torch.no_grad():
    model.hidden = torch.zeros(2, 1, model.dim_hd, device=device)
    model.cell = torch.zeros(2, 1, model.dim_hd, device=device)
    preds_opt = model(feats_tensor)[0]
    preds_opt = model.final_pred(preds_opt)

preds_opt_np = preds_opt.cpu().detach().float().numpy()
activations_opt = np.transpose(preds_opt_np[:2, :])
print(f"Opt activations shape: {activations_opt.shape}, dtype: {activations_opt.dtype}")
print(f"Opt min/max: {activations_opt.min():.6f} / {activations_opt.max():.6f}")
print(f"Opt mean per col: {activations_opt.mean(axis=0)}")

# Compare
if preds.shape == activations_opt.shape:
    diff = np.abs(preds - activations_opt)
    print(f"Diff orig vs opt: max={diff.max():.6f}, mean={diff.mean():.6f}")

print("\n=== DBN on OPTIMIZED activations ===")
dbn_opt = DBNDownBeatTrackingProcessor(beats_per_bar=[4], fps=50)
out_opt = dbn_opt(activations_opt)
print(f"DBN [4] events: {len(out_opt)}")
if len(out_opt) > 0:
    print(f"First 3: {out_opt[:3]}")
    beats = [float(r[0]) for r in out_opt]
    intervals = np.diff(beats)
    if len(intervals) > 0:
        bpm = 60.0 / np.median(intervals)
        print(f"Median BPM: {bpm:.1f}")
