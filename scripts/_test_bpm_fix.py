"""Test the BPM fix on Fired Up - should detect ~86 BPM instead of 129."""
import sys
sys.path.insert(0, "/app")

import os

import numpy as np
import librosa
from sqlalchemy import create_engine, text

# Find the song
engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///./data/harbeat_dev.db"))
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT id, title, source_path, bpm FROM library_songs WHERE lower(title) LIKE '%fired%' LIMIT 1"
    )).fetchone()
    print(f"Song: {row[1]}, current DB BPM: {row[3]}")
    file_path = row[2]

# Load audio
y, sr = librosa.load(file_path, sr=22050)
duration = librosa.get_duration(y=y, sr=sr)

# Run the fixed beat engine
from app.modules.library.beat_engine import analyze_beats

result = analyze_beats(file_path, y, sr, duration)

print(f"\n=== FIXED RESULT ===")
print(f"BPM: {result.bpm}")
print(f"Confidence: {result.confidence}")
print(f"Engines: {result.engines_used}")
print(f"Needs review: {result.needs_review}")
print(f"Raw results: {result.raw_results}")
print(f"Beat points: {len(result.beat_points)} beats")
print(f"Grid interval: {result.grid_interval:.4f}s ({60/result.grid_interval:.1f} BPM)")

expected_range = (80, 95)
if expected_range[0] <= result.bpm <= expected_range[1]:
    print(f"\n✅ BPM {result.bpm} is in expected range {expected_range} (online tools say 89-90)")
else:
    print(f"\n❌ BPM {result.bpm} is NOT in expected range {expected_range}")
