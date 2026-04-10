import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
import librosa
import numpy as np
import torch
import yt_dlp
from transformers import AutoProcessor, ClapModel

from services.config import CHROMA_PATH, CLAP_MODEL_NAME, DEFAULT_COLLECTION


logger = logging.getLogger("fre-ingest")
YTDLP_TIMEOUT_SECONDS = 120


class ClapEmbedder:
    def __init__(self, model_name: str = CLAP_MODEL_NAME) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = ClapModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    def embed_file(self, audio_path: Path) -> List[float]:
        audio, sample_rate = librosa.load(audio_path, sr=48000, mono=True)
        inputs = self.processor(audio=audio, sampling_rate=sample_rate, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with torch.no_grad():
            audio_features = self.model.get_audio_features(**inputs)
            if hasattr(audio_features, "pooler_output") and audio_features.pooler_output is not None:
                embedding = audio_features.pooler_output.cpu().numpy().flatten().tolist()
            else:
                embedding = audio_features.cpu().numpy().flatten().tolist()
        return embedding


_embedder: Optional[ClapEmbedder] = None


def get_embedder() -> ClapEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = ClapEmbedder()
    return _embedder


def create_collection(collection_name: str = DEFAULT_COLLECTION):
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(name=collection_name)


def list_collections() -> List[str]:
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return [collection.name for collection in client.list_collections()]


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return cleaned.strip("._") or "audio"


def compute_audio_features(audio_path: Path):
    signal, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=signal, sr=sample_rate)
    rms = librosa.feature.rms(y=signal)
    energy = float(np.mean(rms))
    safe_tempo = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return safe_tempo, energy


def download_audio(track_name: str, artist: str, spotify_id: str, temp_dir: Path) -> Path:
    output_template = temp_dir / f"{sanitize_filename(spotify_id)}.%(ext)s"
    query = f"ytsearch1:{track_name} {artist} audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_template),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": YTDLP_TIMEOUT_SECONDS,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if "entries" in info:
            entries = [entry for entry in info["entries"] if entry]
            info = entries[0]
        downloaded_path = Path(ydl.prepare_filename(info))
        if not downloaded_path.exists():
            matches = sorted(temp_dir.glob(f"{sanitize_filename(spotify_id)}.*"))
            downloaded_path = matches[0]
        return downloaded_path


def normalize_spotify_track(track: dict) -> Dict[str, str]:
    artists = ", ".join(
        (artist or {}).get("name", "").strip()
        for artist in track.get("artists", [])
        if (artist or {}).get("name")
    ).strip() or "Unknown Artist"
    return {
        "spotify_id": str(track.get("id") or track.get("spotify_id") or ""),
        "track_name": str(track.get("name") or track.get("track_name") or "Unknown Track"),
        "artist": artists if artists else str(track.get("artist") or "Unknown Artist"),
    }


def ingest_track(track: Dict[str, str], collection_name: str = DEFAULT_COLLECTION) -> Dict[str, object]:
    collection = create_collection(collection_name)
    embedder = get_embedder()
    temp_dir = Path(tempfile.mkdtemp(prefix="fre-"))
    audio_path: Optional[Path] = None

    try:
        audio_path = download_audio(
            track_name=track["track_name"],
            artist=track["artist"],
            spotify_id=track["spotify_id"],
            temp_dir=temp_dir,
        )
        bpm, energy = compute_audio_features(audio_path)
        embedding = np.array(embedder.embed_file(audio_path)).flatten().tolist()
        metadata = {
            "spotify_id": str(track["spotify_id"]),
            "track_name": str(track["track_name"]),
            "artist": str(track["artist"]),
            "bpm": float(bpm),
            "energy": float(energy),
            "collection": collection_name,
        }
        collection.upsert(
            ids=[track["spotify_id"]],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[f"{track['track_name']} - {track['artist']}"]
        )
        return {"success": True, "metadata": metadata}
    except Exception as exc:
        return {"success": False, "error": str(exc), "track": track}
    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                pass
        shutil.rmtree(temp_dir, ignore_errors=True)


def ingest_tracks(tracks: List[dict], collection_name: str = DEFAULT_COLLECTION):
    results = []
    for row in tracks:
        normalized = normalize_spotify_track(row)
        if normalized["spotify_id"]:
            results.append(ingest_track(normalized, collection_name=collection_name))
    return results
