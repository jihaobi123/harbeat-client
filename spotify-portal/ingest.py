import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chromadb
import librosa
import numpy as np
import spotipy
import torch
import yt_dlp
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from transformers import AutoProcessor, ClapModel


CLAP_MODEL_NAME = "laion/clap-htsat-unfused"
COLLECTION_NAME = "street_dance_tracks"
CHROMA_PATH = "./chroma_db"
MAX_SPOTIFY_RETRIES = 5
YTDLP_TIMEOUT_SECONDS = 120


logger = logging.getLogger("street-dance-ingest")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_required_env() -> None:
    load_dotenv()

    keys = [
        "SPOTIPY_CLIENT_ID",
        "SPOTIPY_CLIENT_SECRET",
    ]
    missing = [key for key in keys if not os.environ.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def parse_playlist_id(playlist_input: str) -> str:
    playlist_input = playlist_input.strip()

    url_match = re.search(r"playlist/([A-Za-z0-9]+)", playlist_input)
    if url_match:
        return url_match.group(1)

    uri_match = re.match(r"spotify:playlist:([A-Za-z0-9]+)", playlist_input)
    if uri_match:
        return uri_match.group(1)

    raw_match = re.match(r"^[A-Za-z0-9]+$", playlist_input)
    if raw_match:
        return playlist_input

    raise ValueError("Could not parse a Spotify playlist ID from the provided input.")


def create_spotify_client() -> spotipy.Spotify:
    auth_manager = SpotifyOAuth(
        client_id=os.environ.get("SPOTIPY_CLIENT_ID"),
        client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.environ.get("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope="playlist-read-private playlist-read-collaborative",
        open_browser=False,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def spotify_call_with_retry(func, *args, **kwargs):
    delay = 2.0
    for attempt in range(1, MAX_SPOTIFY_RETRIES + 1):
        try:
            return func(*args, **kwargs)
        except SpotifyException as exc:
            status_code = getattr(exc, "http_status", None)
            headers = getattr(exc, "headers", {}) or {}

            if status_code == 429 and attempt < MAX_SPOTIFY_RETRIES:
                retry_after = headers.get("Retry-After") or headers.get("retry-after")
                sleep_for = float(retry_after) if retry_after else delay
                logger.warning(
                    "Spotify rate limit hit. Retrying in %.1f seconds (attempt %s/%s).",
                    sleep_for,
                    attempt,
                    MAX_SPOTIFY_RETRIES,
                )
                time.sleep(sleep_for)
                delay *= 2
                continue

            if status_code and 500 <= status_code < 600 and attempt < MAX_SPOTIFY_RETRIES:
                logger.warning(
                    "Spotify server error %s. Retrying in %.1f seconds (attempt %s/%s).",
                    status_code,
                    delay,
                    attempt,
                    MAX_SPOTIFY_RETRIES,
                )
                time.sleep(delay)
                delay *= 2
                continue

            raise
        except Exception:
            if attempt < MAX_SPOTIFY_RETRIES:
                logger.warning(
                    "Unexpected Spotify error. Retrying in %.1f seconds (attempt %s/%s).",
                    delay,
                    attempt,
                    MAX_SPOTIFY_RETRIES,
                )
                time.sleep(delay)
                delay *= 2
                continue
            raise


def fetch_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[Dict[str, str]]:
    valid_tracks: List[Dict[str, Any]] = []

    results = spotify_call_with_retry(sp.playlist_items, playlist_id)

    while True:
        for row in results['items']:
            # Try getting 'track' first (standard API), fallback to 'item' (weird API behavior)
            track_data = row.get('track') or row.get('item')
            
            if track_data and not track_data.get('is_local') and track_data.get('id'):
                valid_tracks.append(track_data)

        if not results.get("next"):
            break

        results = spotify_call_with_retry(sp.next, results)

    normalized_tracks: List[Dict[str, str]] = []
    for track_data in valid_tracks:
        track_name = (track_data.get("name") or "").strip() or "Unknown Track"
        artist = ", ".join(
            artist_data.get("name", "").strip()
            for artist_data in track_data.get("artists", [])
            if artist_data.get("name")
        ).strip() or "Unknown Artist"
        normalized_tracks.append(
            {
                "spotify_id": str(track_data.get("id")),
                "track_name": track_name,
                "artist": artist,
            }
        )

    print(f"✅ Successfully extracted {len(valid_tracks)} tracks from the playlist.")
    return normalized_tracks


class ClapEmbedder:
    def __init__(self, model_name: str = CLAP_MODEL_NAME) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Loading CLAP model '%s' on %s.", model_name, self.device)
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = ClapModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    def embed_file(self, audio_path: Path) -> List[float]:
        audio, sample_rate = librosa.load(audio_path, sr=48000, mono=True)
        if audio.size == 0:
            raise ValueError("Audio file is empty after loading.")

        inputs = self.processor(audio=audio, sampling_rate=sample_rate, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}

        with torch.no_grad():
            # Use get_audio_features to get the 512D projection
            audio_features = self.model.get_audio_features(**inputs)
            # Flatten and convert to list of floats
            embedding = audio_features.pooler_output.cpu().numpy().flatten().tolist()
        return embedding


def compute_audio_features(audio_path: Path) -> Tuple[float, float]:
    signal, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    if signal.size == 0:
        raise ValueError("Audio file is empty after loading.")

    tempo, _ = librosa.beat.beat_track(y=signal, sr=sample_rate)
    rms = librosa.feature.rms(y=signal)
    energy = float(np.mean(rms))
    safe_tempo = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return safe_tempo, energy


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return cleaned.strip("._") or "audio"


def download_audio(track_name: str, artist: str, spotify_id: str, temp_dir: Path) -> Path:
    output_template = temp_dir / f"{sanitize_filename(spotify_id)}.%(ext)s"
    query = f"ytsearch1:{track_name} {artist} audio"

    ydl_opts: Dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": str(output_template),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": YTDLP_TIMEOUT_SECONDS,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if info is None:
            raise RuntimeError("yt-dlp returned no metadata.")

        if "entries" in info:
            entries = [entry for entry in info["entries"] if entry]
            if not entries:
                raise RuntimeError("yt-dlp search produced no downloadable entries.")
            info = entries[0]

        downloaded_path = Path(ydl.prepare_filename(info))
        if not downloaded_path.exists():
            matches = sorted(temp_dir.glob(f"{sanitize_filename(spotify_id)}.*"))
            if not matches:
                raise FileNotFoundError("Downloaded audio file could not be located.")
            downloaded_path = matches[0]

        return downloaded_path


def create_collection() -> chromadb.api.models.Collection.Collection:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def ingest_track(
    track: Dict[str, str],
    embedder: ClapEmbedder,
    collection,
) -> bool:
    temp_dir = Path(tempfile.mkdtemp(prefix="street-dance-"))
    audio_path: Optional[Path] = None

    try:
        logger.info("Processing: %s - %s", track["artist"], track["track_name"])
        audio_path = download_audio(
            track_name=track["track_name"],
            artist=track["artist"],
            spotify_id=track["spotify_id"],
            temp_dir=temp_dir,
        )

        bpm, energy = compute_audio_features(audio_path)
        embedding = embedder.embed_file(audio_path)
        flat_embedding = np.array(embedding).flatten().tolist()

        metadata = {
            "spotify_id": str(track["spotify_id"]),
            "bpm": float(bpm),
            "energy": float(energy),
            "track_name": str(track["track_name"]),
            "artist": str(track["artist"]),
        }

        collection.upsert(
            ids=[track["spotify_id"]],
            embeddings=[flat_embedding],
            metadatas=[metadata],
            documents=[f"{track['track_name']} - {track['artist']}"]
        )

        logger.info(
            "Stored track %s with bpm=%.2f energy=%.6f",
            track["spotify_id"],
            bpm,
            energy,
        )
        return True
    except Exception as exc:
        logger.exception(
            "Failed to ingest track %s (%s - %s): %s",
            track.get("spotify_id", "unknown"),
            track.get("artist", "unknown"),
            track.get("track_name", "unknown"),
            exc,
        )
        return False
    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except Exception:
                logger.warning("Could not delete temporary audio file: %s", audio_path)
        shutil.rmtree(temp_dir, ignore_errors=True)


def iter_failed_tracks(tracks: Iterable[Dict[str, str]], results: Iterable[bool]) -> List[Dict[str, str]]:
    return [track for track, success in zip(tracks, results) if not success]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest a Spotify playlist into ChromaDB using librosa features and CLAP embeddings."
    )
    parser.add_argument("playlist", help="Spotify playlist URL, URI, or playlist ID")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(verbose=args.verbose)

    try:
        load_required_env()
        playlist_id = parse_playlist_id(args.playlist)
        spotify_client = create_spotify_client()
        collection = create_collection()
        embedder = ClapEmbedder()
    except Exception as exc:
        logger.exception("Startup failed: %s", exc)
        return 1

    try:
        tracks = fetch_playlist_tracks(spotify_client, playlist_id)
    except Exception as exc:
        logger.exception("Failed to fetch playlist tracks: %s", exc)
        return 1

    if not tracks:
        logger.warning("No valid tracks found in playlist %s", playlist_id)
        return 0

    logger.info("Fetched %s tracks from playlist %s", len(tracks), playlist_id)

    results: List[bool] = []
    for track in tracks:
        success = ingest_track(
            track=track,
            embedder=embedder,
            collection=collection,
        )
        results.append(success)

    success_count = sum(results)
    failed_tracks = iter_failed_tracks(tracks, results)

    logger.info("Ingestion complete. Successful: %s | Failed: %s", success_count, len(failed_tracks))
    if failed_tracks:
        logger.warning("Failed track IDs: %s", ", ".join(track["spotify_id"] for track in failed_tracks))

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
