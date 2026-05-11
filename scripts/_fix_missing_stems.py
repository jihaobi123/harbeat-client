"""Re-run demucs stem separation for songs missing stems.

Directly calls demucs subprocess for each song, then updates the DB.
"""
import json
import os
import subprocess
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
try:
    sys.path.insert(0, "/home/mark/harbeat")
except Exception:
    pass

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/harbeat_dev.db")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DB_URL = os.environ["DATABASE_URL"]
engine = create_engine(DB_URL)

STEM_NAMES = ["vocals", "drums", "bass", "other"]

with Session(engine) as db:
    # Find songs with no stems but completed analysis
    rows = db.execute(text("""
        SELECT id, title, artist, source_path, stems, analysis_status
        FROM library_songs
        WHERE (stems IS NULL OR stems::text = 'null' OR stems::text = '{}')
        AND source_path IS NOT NULL
        ORDER BY title
    """)).fetchall()

    print(f"Found {len(rows)} songs without stems")

    import shutil
    ffmpeg = shutil.which("ffmpeg")
    
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}, ffmpeg: {ffmpeg}")
    python_exe = sys.executable

    for i, row in enumerate(rows, 1):
        sid, title, artist, source_path, stems, status = row
        print(f"\n[{i}/{len(rows)}] {title} - {artist}")
        
        if not source_path or not os.path.isfile(source_path):
            print(f"  SKIP: source file not found: {source_path}")
            continue

        # Compute stems dir
        stems_base = os.path.join(os.path.dirname(os.path.abspath(source_path)), "..", "stems")
        stems_base = os.path.abspath(stems_base)
        os.makedirs(stems_base, exist_ok=True)
        
        base_name = os.path.splitext(os.path.basename(source_path))[0]
        stems_dir = os.path.join(stems_base, "htdemucs", base_name)

        # Check if stems already exist on disk
        if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in STEM_NAMES):
            print(f"  Stems exist on disk, updating DB only")
            stem_paths = {s: os.path.join(stems_dir, f"{s}.wav") for s in STEM_NAMES}
            db.execute(text("UPDATE library_songs SET stems = :stems WHERE id = :id"),
                       {"stems": json.dumps(stem_paths), "id": sid})
            db.commit()
            print(f"  DB updated")
            continue

        # Run demucs
        print(f"  Running demucs (device={device})...")
        try:
            result = subprocess.run(
                [python_exe, "-m", "demucs", "-n", "htdemucs", "-d", device,
                 "--segment", "7", "-o", stems_base, source_path],
                capture_output=True, text=True, timeout=1800,
            )
            if result.returncode != 0:
                stderr_tail = (result.stderr or "").strip()[-500:]
                print(f"  FAILED: exit={result.returncode}\n  {stderr_tail}")
                continue
            print(f"  demucs OK")
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        # Verify and update DB
        if all(os.path.isfile(os.path.join(stems_dir, f"{s}.wav")) for s in STEM_NAMES):
            stem_paths = {s: os.path.join(stems_dir, f"{s}.wav") for s in STEM_NAMES}
            db.execute(text("UPDATE library_songs SET stems = :stems WHERE id = :id"),
                       {"stems": json.dumps(stem_paths), "id": sid})
            db.commit()
            print(f"  DB updated with stems")

            # Convert WAV to MP3
            if ffmpeg:
                for s in STEM_NAMES:
                    wav = os.path.join(stems_dir, f"{s}.wav")
                    mp3 = os.path.join(stems_dir, f"{s}.mp3")
                    if not os.path.isfile(mp3):
                        subprocess.run([ffmpeg, "-i", wav, "-b:a", "192k", "-y", mp3],
                                       capture_output=True, timeout=120)
                print(f"  MP3 converted")
        else:
            print(f"  WARN: stems not found after demucs")

print("\nDone!")
