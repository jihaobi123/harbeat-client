"""Quick test: Essentia BPM detection on Fired Up."""
import essentia.standard as es
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism"
engine = create_engine(DB_URL)
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT title, source_path FROM library_songs WHERE title ILIKE '%fired%' LIMIT 1"
    )).fetchone()
    print(f"Song: {row[0]}, path: {row[1]}")
    file_path = row[1]

# Load audio
loader = es.MonoLoader(filename=file_path, sampleRate=44100)
audio = loader()
print(f"Audio loaded: {len(audio)} samples, {len(audio)/44100:.1f}s")

# Method 1: RhythmExtractor2013 (the main one used by those websites)
print("\n=== RhythmExtractor2013 ===")
rhythm = es.RhythmExtractor2013(method="multifeature")
bpm, beats, confidence, _, intervals = rhythm(audio)
print(f"BPM: {bpm:.2f}")
print(f"Confidence: {confidence:.4f}")
print(f"Beats: {len(beats)}")
print(f"Beat intervals distribution: {len(intervals)}")

# Method 2: PercivalBpmEstimator
print("\n=== PercivalBpmEstimator ===")
percival = es.PercivalBpmEstimator()
bpm2 = percival(audio)
print(f"BPM: {bpm2:.2f}")

# Method 3: BeatTrackerMultiFeature
print("\n=== BeatTrackerMultiFeature ===")
bt = es.BeatTrackerMultiFeature()
beats3, conf3 = bt(audio)
if len(beats3) > 1:
    import numpy as np
    intervals3 = np.diff(beats3)
    bpm3 = 60.0 / float(np.median(intervals3))
    print(f"BPM (from beats): {bpm3:.2f}")
    print(f"Confidence: {conf3:.4f}")
    print(f"Beats: {len(beats3)}")

# Method 4: BeatTrackerDegara
print("\n=== BeatTrackerDegara ===")
bt2 = es.BeatTrackerDegara()
beats4 = bt2(audio)
if len(beats4) > 1:
    import numpy as np
    intervals4 = np.diff(beats4)
    bpm4 = 60.0 / float(np.median(intervals4))
    print(f"BPM (from beats): {bpm4:.2f}")
    print(f"Beats: {len(beats4)}")

# Method 5: LoopBpmEstimator
print("\n=== LoopBpmEstimator ===")
try:
    loop = es.LoopBpmEstimator()
    bpm5 = loop(audio)
    print(f"BPM: {bpm5:.2f}")
except:
    print("Not available")

# Key detection too
print("\n=== Key Detection ===")
key_extractor = es.KeyExtractor()
key, scale, strength = key_extractor(audio)
print(f"Key: {key} {scale} (strength: {strength:.4f})")

print("\n" + "="*50)
print("SUMMARY")
print("="*50)
print(f"RhythmExtractor2013:   {bpm:.1f} BPM (confidence: {confidence:.3f})")
print(f"PercivalBpmEstimator:  {bpm2:.1f} BPM")
print(f"BeatTrackerMulti:      {bpm3:.1f} BPM" if 'bpm3' in dir() else "BeatTrackerMulti: N/A")
print(f"BeatTrackerDegara:     {bpm4:.1f} BPM" if 'bpm4' in dir() else "BeatTrackerDegara: N/A")
print(f"\nOnline tools say:      89-90 BPM")
print(f"Our old detection:     129.2 BPM")
