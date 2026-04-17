"""Test the Essentia-integrated beat engine on Fired Up."""
import sys
sys.path.insert(0, "/app")

import numpy as np
import librosa
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://harbeat:Hb12345678@pgm-wz99am1godb1u59s3o.pg.rds.aliyuncs.com:5432/rhythm_prism"
engine = create_engine(DB_URL)
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT id, title, source_path, bpm FROM library_songs WHERE title ILIKE '%fired%' LIMIT 1"
    )).fetchone()
    print(f"Song: {row[1]}, current DB BPM: {row[3]}")
    file_path = row[2]

# Load audio
y, sr = librosa.load(file_path, sr=22050)
duration = librosa.get_duration(y=y, sr=sr)

# Run the Essentia-integrated beat engine
import logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
from app.modules.library.beat_engine import analyze_beats

result = analyze_beats(file_path, y, sr, duration)

print(f"\n{'='*50}")
print(f"RESULT")
print(f"{'='*50}")
print(f"BPM: {result.bpm}")
print(f"Confidence: {result.confidence}")
print(f"Engines used: {result.engines_used}")
print(f"Needs review: {result.needs_review}")
print(f"Raw results: {result.raw_results}")
print(f"Beat points: {len(result.beat_points)} beats")
print(f"Grid interval: {result.grid_interval:.4f}s ({60/result.grid_interval:.1f} BPM)")
print(f"Confidence details: {result.confidence_details}")

print(f"\nOnline tools say: 89-90 BPM")
if 80 <= result.bpm <= 95:
    print(f"✅ BPM {result.bpm} matches online tools")
elif 125 <= result.bpm <= 135:
    print(f"⚠️  BPM {result.bpm} - still detecting 3:2 artifact")
else:
    print(f"❓ BPM {result.bpm} - unexpected value")
