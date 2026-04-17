import sys, os
sys.path.insert(0, '/app')
import librosa
from app.modules.library.beat_engine import analyze_beats

songs = [
    ("/app/data/music-files/shared/不怪她 (Blame) - HARIKIRI&Bohan Phoenix&马思唯&J.Mag.mp3", "不怪她", 80),
    ("/app/data/music-files/shared/One B-Boy - Dj Pablo _ Battle of the Year.mp3", "One B-Boy - Dj Pablo", 126),
    ("/app/data/music-files/shared/It's Been A Long Time - Rakim.mp3", "It's Been A Long Time - Rakim", 89),
    ("/app/data/music-files/shared/So Many Ways - Warren G.mp3", "So Many Ways - Warren G", 95),
]

print("USER 4-SONG RETEST")
print("=" * 72)
for path, name, ref in songs:
    if not os.path.exists(path):
        print(f"{name}: FILE NOT FOUND")
        continue
    y, sr = librosa.load(path, sr=22050, mono=True)
    r = analyze_beats(path, y, sr, len(y) / sr)
    diff = r.bpm - ref
    mark = "OK" if abs(diff) <= 3 else ("CLOSE" if abs(diff) <= 8 else "OFF")
    raw = {k: round(v.get('bpm', 0), 2) for k, v in r.raw_results.items() if isinstance(v, dict)}
    print(f"{name}: final={r.bpm:.1f}, ref={ref}, diff={diff:+.1f}, conf={r.confidence:.3f}, {mark}, raw={raw}")
