from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
from sqlalchemy import select

from app.db import SessionLocal
from app.models.track import Track

MUSIC_ROOT = Path("./music_library")
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler templates
MAJOR_TEMPLATE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_TEMPLATE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_MODE_TO_CAMELOT = {
    ("C", "major"): "8B",
    ("C#", "major"): "3B",
    ("D", "major"): "10B",
    ("D#", "major"): "5B",
    ("E", "major"): "12B",
    ("F", "major"): "7B",
    ("F#", "major"): "2B",
    ("G", "major"): "9B",
    ("G#", "major"): "4B",
    ("A", "major"): "11B",
    ("A#", "major"): "6B",
    ("B", "major"): "1B",
    ("C", "minor"): "5A",
    ("C#", "minor"): "12A",
    ("D", "minor"): "7A",
    ("D#", "minor"): "2A",
    ("E", "minor"): "9A",
    ("F", "minor"): "4A",
    ("F#", "minor"): "11A",
    ("G", "minor"): "6A",
    ("G#", "minor"): "1A",
    ("A", "minor"): "8A",
    ("A#", "minor"): "3A",
    ("B", "minor"): "10A",
}


def parse_artist_title(file_path: Path) -> tuple[str, str]:
    stem = file_path.stem
    if " - " not in stem:
        return "Unknown Artist", stem.strip()

    artist, title = stem.split(" - ", 1)
    return artist.strip(), title.strip()


def normalize_energy(rms: np.ndarray) -> float:
    # 把平均 RMS 压缩到 0-1，适配舞曲能量比较
    raw = float(np.mean(rms))
    scaled = np.tanh(raw * 8.0)
    return float(np.clip(scaled, 0.0, 1.0))


def infer_key_and_mode(chromagram: np.ndarray) -> tuple[str, str, str]:
    chroma_profile = np.mean(chromagram, axis=1)
    if np.sum(chroma_profile) == 0:
        return "C", "major", "8B"

    chroma_profile = chroma_profile / (np.linalg.norm(chroma_profile) + 1e-9)

    best_score = -1e9
    best_note = "C"
    best_mode = "major"

    for idx, note in enumerate(NOTE_NAMES):
        major_rot = np.roll(MAJOR_TEMPLATE, idx)
        minor_rot = np.roll(MINOR_TEMPLATE, idx)

        major_rot = major_rot / (np.linalg.norm(major_rot) + 1e-9)
        minor_rot = minor_rot / (np.linalg.norm(minor_rot) + 1e-9)

        major_score = float(np.dot(chroma_profile, major_rot))
        minor_score = float(np.dot(chroma_profile, minor_rot))

        if major_score > best_score:
            best_score = major_score
            best_note = note
            best_mode = "major"

        if minor_score > best_score:
            best_score = minor_score
            best_note = note
            best_mode = "minor"

    camelot = NOTE_MODE_TO_CAMELOT[(best_note, best_mode)]
    return best_note, best_mode, camelot


def analyze_audio(file_path: Path) -> dict:
    y, sr = librosa.load(file_path.as_posix(), sr=22050)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo)

    rms = librosa.feature.rms(y=y)[0]
    energy = normalize_energy(rms)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    root_note, mode, camelot_key = infer_key_and_mode(chroma)

    return {
        "bpm": bpm,
        "energy": energy,
        "camelot_key": camelot_key,
        "root_note": root_note,
        "mode": mode,
    }


def collect_audio_files(root: Path) -> list[tuple[str, Path]]:
    if not root.exists():
        return []

    items: list[tuple[str, Path]] = []
    for genre_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for fp in sorted(genre_dir.iterdir()):
            if fp.suffix.lower() in AUDIO_EXTS:
                items.append((genre_dir.name, fp))
    return items


def is_duplicate(db, title: str, artist: str) -> bool:
    rows = db.scalars(select(Track).where(Track.title == title)).all()
    artist_key = artist.strip().lower()

    for row in rows:
        tags = row.genre_tags or {}
        existing_artist = str(tags.get("artist", "")).strip().lower()
        if existing_artist == artist_key:
            return True

    return False


def seed_local_audio() -> None:
    file_items = collect_audio_files(MUSIC_ROOT)
    total = len(file_items)

    if total == 0:
        print("⚠️ 未找到音频文件，请检查 ./music_library 目录")
        return

    print(f"🎧 开始本地音频分析，共 {total} 首")

    inserted = 0
    skipped = 0
    failed = 0

    with SessionLocal() as db:
        for idx, (genre, file_path) in enumerate(file_items, start=1):
            progress = f"[{idx:02d}/{total:02d}]"
            artist, title = parse_artist_title(file_path)

            if is_duplicate(db, title, artist):
                print(f"{progress} [{genre}] 跳过重复: {artist} - {title}")
                skipped += 1
                continue

            try:
                features = analyze_audio(file_path)
                genre_tags = {
                    "styles": [genre],
                    "artist": artist,
                    "source": "local_audio_analyzer",
                    "root_note": features["root_note"],
                    "mode": features["mode"],
                    "file_path": str(file_path),
                }

                payload = {
                    "title": title,
                    "bpm": features["bpm"],
                    "camelot_key": features["camelot_key"],
                    "energy": features["energy"],
                    "genre_tags": genre_tags,
                    "embedding": np.random.rand(128).astype(float).tolist(),
                }

                if hasattr(Track, "artist"):
                    payload["artist"] = artist

                db.add(Track(**payload))
                db.commit()
                inserted += 1

                print(
                    f"{progress} [{genre}] 分析完成: {artist} - {title} | "
                    f"BPM: {features['bpm']:.1f} | Key: {features['camelot_key']} | "
                    f"Energy: {features['energy']:.2f}"
                )
            except Exception as exc:
                db.rollback()
                failed += 1
                print(f"{progress} [{genre}] 失败: {artist} - {title} | 错误: {exc}")

    print("\n📊 本地分析入库完成")
    print(f"   新增: {inserted}")
    print(f"   跳过: {skipped}")
    print(f"   失败: {failed}")


if __name__ == "__main__":
    seed_local_audio()
