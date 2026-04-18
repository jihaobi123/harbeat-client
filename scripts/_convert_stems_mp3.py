"""Convert existing WAV stems to MP3 for faster streaming.

Usage (on Jetson):
  cd /home/mark/harbeat
  python scripts/_convert_stems_mp3.py

WAV ~43MB per stem → MP3 ~4MB (192kbps), ~10x smaller.
"""
import os
import shutil
import subprocess
import sys

# Auto-detect stem root: prefer env var, then common locations
_CANDIDATES = [
    os.environ.get("STEMS_ROOT", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "music-files", "stems", "htdemucs"),
    "/mnt/nas/harbeat/music-files/stems/htdemucs",
    os.path.expanduser("~/harbeat/data/music-files/stems/htdemucs"),
]
STEMS_ROOT = ""
for _c in _CANDIDATES:
    _c = os.path.abspath(_c) if _c else ""
    if _c and os.path.isdir(_c):
        STEMS_ROOT = _c
        break
STEM_NAMES = ["vocals", "drums", "bass", "other"]


def main():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ERROR: ffmpeg not found in PATH")
        sys.exit(1)

    if not os.path.isdir(STEMS_ROOT):
        print(f"ERROR: stems dir not found: {STEMS_ROOT}")
        sys.exit(1)

    songs = sorted(os.listdir(STEMS_ROOT))
    total = len(songs)
    converted = 0
    skipped = 0
    failed = 0

    print(f"Found {total} songs in {STEMS_ROOT}")

    for i, song_dir in enumerate(songs, 1):
        song_path = os.path.join(STEMS_ROOT, song_dir)
        if not os.path.isdir(song_path):
            continue

        for stem in STEM_NAMES:
            wav_path = os.path.join(song_path, f"{stem}.wav")
            mp3_path = os.path.join(song_path, f"{stem}.mp3")

            if os.path.isfile(mp3_path):
                skipped += 1
                continue

            if not os.path.isfile(wav_path):
                continue

            try:
                result = subprocess.run(
                    [ffmpeg, "-i", wav_path, "-b:a", "192k", "-y", mp3_path],
                    capture_output=True, timeout=120,
                )
                if result.returncode == 0 and os.path.isfile(mp3_path):
                    wav_size = os.path.getsize(wav_path) / (1024 * 1024)
                    mp3_size = os.path.getsize(mp3_path) / (1024 * 1024)
                    converted += 1
                else:
                    failed += 1
                    print(f"  FAIL: {song_dir}/{stem} rc={result.returncode}")
            except Exception as e:
                failed += 1
                print(f"  ERROR: {song_dir}/{stem}: {e}")

        if i % 10 == 0 or i == total:
            print(f"  [{i}/{total}] converted={converted} skipped={skipped} failed={failed}")

    print(f"\nDone: converted={converted} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
