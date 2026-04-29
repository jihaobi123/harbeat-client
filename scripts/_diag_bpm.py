"""Diagnose BPM detection for a specific song - run inside harbeat-api container."""
import sys, json
import collections, collections.abc
import numpy as np

# Python 3.12 compat patches
for _attr in ("MutableSequence", "MutableMapping", "MutableSet",
              "Mapping", "Sequence", "Iterable", "Iterator"):
    if not hasattr(collections, _attr) and hasattr(collections.abc, _attr):
        setattr(collections, _attr, getattr(collections.abc, _attr))
for _alias, _real in (("float", np.float64), ("int", np.int_),
                       ("complex", np.complex128), ("object", np.object_),
                       ("bool", np.bool_), ("str", np.str_)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _real)

import librosa
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism"

# Find the song
engine = create_engine(DB_URL)
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT id, title, source_path, bpm, beat_confidence, beat_engines_used "
        "FROM library_songs WHERE title ILIKE '%fired%' LIMIT 1"
    )).fetchone()
    if row:
        print(f"Song: id={row[0]}, title={row[1]}")
        print(f"  source_path={row[2]}")
        print(f"  db_bpm={row[3]}, confidence={row[4]}, engines={row[5]}")
        file_path = row[2]
    else:
        print("Song not found")
        sys.exit(1)

# Load audio
print("\n=== Loading audio ===")
y, sr = librosa.load(file_path, sr=22050)
duration = librosa.get_duration(y=y, sr=sr)
print(f"Duration: {duration:.1f}s, SR: {sr}")

# === Engine 1: madmom ===
print("\n=== MADMOM ===")
try:
    from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor
    beat_act = RNNBeatProcessor()(file_path)
    beats = DBNBeatTrackingProcessor(fps=100)(beat_act)
    intervals = np.diff(beats)
    madmom_bpm = 60.0 / float(np.median(intervals))
    print(f"BPM (from median interval): {madmom_bpm:.2f}")
    print(f"Beats detected: {len(beats)}")
    print(f"Interval stats: median={np.median(intervals):.4f}s, mean={np.mean(intervals):.4f}s, std={np.std(intervals):.4f}s")
    
    # Check every-other-beat (half-time)
    beats_half = beats[::2]
    if len(beats_half) > 1:
        intervals_half = np.diff(beats_half)
        bpm_half = 60.0 / float(np.median(intervals_half))
        print(f"Half-time BPM (every other beat): {bpm_half:.2f}")
    
    # Show first 10 beat intervals for pattern analysis
    print(f"First 15 intervals: {[round(float(x), 4) for x in intervals[:15]]}")
except Exception as e:
    madmom_bpm = None
    print(f"Failed: {e}")

# === Engine 2: librosa beat_track ===
print("\n=== LIBROSA beat_track ===")
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
bpm_basic = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
beat_times_lib = librosa.frames_to_time(beat_frames, sr=sr)
if len(beat_times_lib) > 1:
    lib_intervals = np.diff(beat_times_lib)
    print(f"BPM (beat_track): {bpm_basic:.2f}")
    print(f"BPM (from intervals): {60.0/np.median(lib_intervals):.2f}")
    print(f"Beats detected: {len(beat_times_lib)}")
    print(f"First 15 intervals: {[round(float(x), 4) for x in lib_intervals[:15]]}")

# Also try with different start_bpm priors
for prior in [90, 120, 130, 175]:
    t2, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=prior)
    bpm2 = float(t2) if not hasattr(t2, "__len__") else float(t2[0])
    print(f"  beat_track(start_bpm={prior}): {bpm2:.2f}")

# === Engine 3: librosa tempogram ===
print("\n=== LIBROSA tempogram ===")
tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
ac_global = np.mean(tempogram, axis=1)
freqs = librosa.tempo_frequencies(tempogram.shape[0], sr=sr)

# Top 10 tempo peaks
valid = (freqs >= 50) & (freqs <= 250)
valid_indices = np.where(valid)[0]
valid_strengths = ac_global[valid_indices]
top10 = valid_indices[np.argsort(valid_strengths)[-10:][::-1]]
print("Top 10 tempogram peaks:")
for idx in top10:
    print(f"  BPM={freqs[idx]:.1f}, strength={ac_global[idx]:.4f}")

# Current code's tempogram BPM
valid2 = (freqs >= 60) & (freqs <= 200)
ac_valid = ac_global.copy()
ac_valid[~valid2] = 0
peak_idx = np.argmax(ac_valid)
bpm_tempogram = float(freqs[peak_idx])
print(f"\nCurrent code picks: BPM={bpm_tempogram:.2f} (strength={ac_global[peak_idx]:.4f})")

# Restricted range analysis
for lo, hi, label in [(60, 100, "60-100"), (100, 145, "100-145"), (145, 200, "145-200")]:
    mask = (freqs >= lo) & (freqs <= hi)
    if np.any(mask):
        ac_range = ac_global.copy()
        ac_range[~mask] = 0
        pk = np.argmax(ac_range)
        print(f"  Best in {label}: BPM={freqs[pk]:.1f}, strength={ac_global[pk]:.4f}")

# === Engine 4: librosa.beat.tempo (newer API) ===
print("\n=== LIBROSA tempo() ===")
try:
    # Try newer API
    t_arr = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)
    print(f"tempo(aggregate=None): unique values = {sorted(set([round(float(x), 1) for x in t_arr]))[:10]}")
    t_med = float(np.median(t_arr))
    t_mean = float(np.mean(t_arr))
    print(f"  median={t_med:.1f}, mean={t_mean:.1f}")
    
    # With different priors
    for prior in [90, 120, 130, 175]:
        t_p = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, start_bpm=prior)
        bp = float(t_p) if not hasattr(t_p, "__len__") else float(t_p[0])
        print(f"  tempo(start_bpm={prior}): {bp:.1f}")
except Exception as e:
    print(f"tempo() failed: {e}")

# === Onset strength autocorrelation (raw) ===
print("\n=== Onset autocorrelation ===")
ac = np.correlate(onset_env, onset_env, mode='full')
ac = ac[len(ac)//2:]  # positive lags only
# Convert lag to BPM: lag (in frames) * hop_length / sr = time in seconds
hop_length = 512
max_lag_bpm60 = int(60 * sr / (hop_length * 60))  # lag for 60 BPM
min_lag_bpm200 = int(60 * sr / (hop_length * 200))  # lag for 200 BPM
ac_range = ac[min_lag_bpm200:max_lag_bpm60]
lag_indices = np.arange(min_lag_bpm200, max_lag_bpm60)
bpm_values = 60.0 * sr / (hop_length * lag_indices)

# Find top peaks
from scipy.signal import find_peaks
try:
    peaks, props = find_peaks(ac_range, distance=3, prominence=0.01*np.max(ac_range))
    peak_bpms = bpm_values[peaks]
    peak_strengths = ac_range[peaks]
    sorted_idx = np.argsort(peak_strengths)[::-1][:10]
    print("Top autocorrelation peaks:")
    for i in sorted_idx:
        print(f"  BPM={peak_bpms[i]:.1f}, strength={peak_strengths[i]:.1f}")
except ImportError:
    # No scipy, manual peak finding
    top_idx = np.argsort(ac_range)[::-1][:10]
    print("Top autocorrelation values:")
    for i in top_idx:
        print(f"  BPM={bpm_values[i]:.1f}, strength={ac_range[i]:.1f}")

# === Summary ===
print("\n" + "="*50)
print("SUMMARY")
print("="*50)
if madmom_bpm: print(f"madmom:           {madmom_bpm:.1f} BPM")
print(f"librosa beat_track: {bpm_basic:.1f} BPM")
print(f"librosa tempogram:  {bpm_tempogram:.1f} BPM")
print(f"\nOnline tools say:   89-90 BPM")
print(f"Our system detected: 129.2 BPM")

# Ratio analysis
if madmom_bpm:
    print(f"\n129.2 / 90 = {129.2/90:.4f} (not 2:1={2:.4f}, 3:2={1.5:.4f}, 4:3={4/3:.4f})")
    print(f"90 * 3/2 = {90*1.5:.1f}")
    print(f"129.2 * 2/3 = {129.2*2/3:.1f}")
    print(f"90 * 2 = {90*2:.1f}")
    print(f"129.2 / 2 = {129.2/2:.1f}")
