"""Multi-source genre classifier: audio-feature inference + external metadata.

Architecture:
  1. Audio-feature inference (always available, no API dependency)
     Uses existing DJ features (BPM, stem activity, spectral, groove) to estimate
     primary and secondary genres with confidence scores.

  2. Spotify metadata enrichment (optional, if SPOTIPY_CLIENT_ID is configured)
     Searches by title+artist ISRC, fetches artist genres, album genres.

  3. Discogs metadata enrichment (optional, if DISCOGS_USER_TOKEN is configured)
     Searches release/master genre and style labels.

  4. Manual override via SongTag.style (always highest priority).

Genre taxonomy follows DJ-relevant categories:
  house, techno, hip-hop, drum-and-bass, pop, r-and-b, latin, rock, funk, disco,
  electronic, breaks, trance, dubstep, reggae, afrobeats, amapiano, lo-fi, ambient
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Genre BPM bands (based on DJ wiki + industry standards) ──────────────────
# (lo, hi, weight) — weight is how strongly BPM defines this genre
GENRE_BPM_BANDS: dict[str, tuple[float, float, float]] = {
    "downtempo":    (60, 95,  0.30),
    "hip-hop":      (75, 105, 0.35),
    "r-and-b":      (65, 100, 0.25),
    "reggae":       (60, 90,  0.20),
    "funk":         (90, 115, 0.20),
    "disco":        (110, 128, 0.20),
    "house":        (118, 130, 0.40),
    "techno":       (125, 145, 0.35),
    "trance":       (128, 145, 0.25),
    "breaks":       (125, 140, 0.15),
    "drum-and-bass": (160, 180, 0.45),
    "dubstep":      (135, 150, 0.30),
    "latin":        (90, 130, 0.10),
    "afrobeats":    (95, 120, 0.20),
    "amapiano":     (110, 118, 0.15),
    "pop":          (90, 130, 0.10),
    "rock":         (100, 160, 0.15),
    "electronic":   (110, 140, 0.15),
}


def _band_fit(value: float, lo: float, hi: float) -> float:
    """1.0 inside [lo,hi], linear decay to 0 outside (band-width on each side)."""
    if hi <= lo:
        return 0.0
    if lo <= value <= hi:
        return 1.0
    width = hi - lo
    if value < lo:
        return max(0.0, 1.0 - (lo - value) / width)
    return max(0.0, 1.0 - (value - hi) / width)


# ── Stem profile heuristics ──────────────────────────────────────────────────
# (vocals_bias, drums_bias, bass_bias, other_bias, weight)
# Positive bias = genre needs more of that stem
GENRE_STEM_PROFILES: dict[str, tuple[float, float, float, float, float]] = {
    "hip-hop":      (0.6,  0.3,  0.5, -0.3, 0.30),
    "r-and-b":      (0.7,  0.0,  0.3, -0.1, 0.25),
    "pop":          (0.7,  0.0,  0.2,  0.1, 0.20),
    "house":        (0.1,  0.5,  0.4,  0.0, 0.20),
    "techno":       (-0.2, 0.6,  0.4,  0.1, 0.25),
    "drum-and-bass":(-0.3, 0.7,  0.6,  0.0, 0.30),
    "dubstep":      (0.0,  0.5,  0.7,  0.2, 0.25),
    "funk":         (0.2,  0.3,  0.3,  0.3, 0.15),
    "disco":        (0.3,  0.4,  0.3,  0.2, 0.15),
    "rock":         (0.4,  0.2,  0.2,  0.3, 0.15),
    "ambient":      (0.0, -0.3, -0.3,  0.5, 0.20),
}


def _classify_from_features(
    bpm: float,
    stem_activity: dict | None,
    groove_profile: dict | None,
    dj_features: dict | None,
    energy: float,
) -> dict:
    """Infer genre from existing analysis features.

    Returns {genres: [{name, confidence, source}], primary_genre, method}.
    """
    scores: dict[str, float] = {}
    breakdowns: dict[str, dict] = {}

    groove = groove_profile or {}
    features = dj_features or {}
    stems = stem_activity or {}

    # ── Guard: truly no data → unknown ──
    has_bpm = bpm and bpm > 0
    has_stems = stems and any(float(v) > 0 for v in stems.values())
    has_features = features and any(float(v) != 0 for v in features.values()
                                    if isinstance(v, (int, float)))
    if not has_bpm and not has_stems and not has_features:
        return {
            "genres": [],
            "primary_genre": "unknown",
            "primary_confidence": 0.0,
            "method": "no_data",
        }

    # ── BPM score ──
    if has_bpm:
        for genre, (lo, hi, w) in GENRE_BPM_BANDS.items():
            fit = _band_fit(bpm, lo, hi)
            scores[genre] = scores.get(genre, 0.0) + fit * w
            breakdowns.setdefault(genre, {})["bpm_fit"] = round(fit, 3)

    # ── Stem profile score ──
    if stems:
        vocals = float(stems.get("vocals", 0))
        drums = float(stems.get("drums", 0))
        bass = float(stems.get("bass", 0))
        other = float(stems.get("other", 0))
        for genre, (vb, db, bb, ob, w) in GENRE_STEM_PROFILES.items():
            # Cosine-like similarity between stem vector and genre profile
            profile = np.array([vb, db, bb, ob])
            actual = np.array([vocals, drums, bass, other])
            profile_norm = np.linalg.norm(profile) + 1e-9
            actual_norm = np.linalg.norm(actual) + 1e-9
            sim = float(np.dot(profile / profile_norm, actual / actual_norm))
            # Rescale from [-1,1] to [0,1]
            stem_score = float(np.clip((sim + 1.0) / 2.0, 0.0, 1.0))
            scores[genre] = scores.get(genre, 0.0) + stem_score * w
            breakdowns.setdefault(genre, {})["stem_fit"] = round(stem_score, 3)
    else:
        # No stems — BPM-only genres dominate
        pass

    # ── Spectral / groove adjustments ──
    spectral_centroid = float(features.get("spectral_centroid", 2000))
    four_on_floor = float(features.get("four_on_floor", 0.5))
    sub_bass = float(features.get("sub_bass_score", 0.0))
    brass = float(features.get("brass_likely", 0.0))
    groove_score = float(groove.get("score", 0.5))

    # Bright spectral = more likely EDM / pop, darker = hip-hop / rock
    if spectral_centroid > 3000:
        for g in ("house", "techno", "trance", "pop", "disco"):
            scores[g] = scores.get(g, 0.0) + 0.12
    elif spectral_centroid < 1500:
        for g in ("hip-hop", "r-and-b", "dubstep", "rock", "reggae"):
            scores[g] = scores.get(g, 0.0) + 0.10

    # Four-on-floor = house/techno/disco/pop
    if four_on_floor > 0.6:
        for g in ("house", "techno", "disco", "trance", "pop"):
            scores[g] = scores.get(g, 0.0) + 0.15
            breakdowns.setdefault(g, {})["four_on_floor"] = round(four_on_floor, 3)

    # Sub-bass = dubstep/drum-and-bass/trap
    if sub_bass > 0.4:
        for g in ("dubstep", "drum-and-bass", "hip-hop"):
            scores[g] = scores.get(g, 0.0) + 0.15
            breakdowns.setdefault(g, {})["sub_bass"] = round(sub_bass, 3)

    # Brass = funk/disco/latin
    if brass > 0.3:
        for g in ("funk", "disco", "latin", "house"):
            scores[g] = scores.get(g, 0.0) + 0.15
            breakdowns.setdefault(g, {})["brass"] = round(brass, 3)

    # Groovy = funk/disco/house; stiff = techno
    if groove_score > 0.65:
        for g in ("funk", "disco", "house", "afrobeats", "latin"):
            scores[g] = scores.get(g, 0.0) + 0.08
    if groove.get("label") == "stiff":
        for g in ("techno", "trance"):
            scores[g] = scores.get(g, 0.0) + 0.05

    # ── Energy adjustment ──
    if energy > 0.7:
        for g in ("drum-and-bass", "dubstep", "techno", "rock"):
            scores[g] = scores.get(g, 0.0) + 0.08
    elif energy < 0.3:
        for g in ("ambient", "lo-fi", "downtempo", "r-and-b"):
            scores[g] = scores.get(g, 0.0) + 0.10

    # ── Lofi / ambient detection ──
    if stems:
        drums_v = float(stems.get("drums", 0.5))
        if drums_v < 0.2 and energy < 0.35:
            for g in ("ambient", "lo-fi"):
                scores[g] = scores.get(g, 0.0) + 0.20

    # ── Rank and select ──
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not ranked:
        return {
            "genres": [],
            "primary_genre": "unknown",
            "primary_confidence": 0.0,
            "method": "no_data",
        }

    max_score = ranked[0][1] if ranked else 1.0
    genres = []
    for name, raw_score in ranked[:5]:
        confidence = round(float(np.clip(raw_score / (max_score + 1e-9), 0.0, 1.0)), 4)
        if confidence < 0.15:
            break
        genres.append({
            "name": name,
            "confidence": confidence,
            "source": "audio_features",
            "breakdown": breakdowns.get(name, {}),
        })

    primary = genres[0] if genres else {"name": "unknown", "confidence": 0.0}
    return {
        "genres": genres,
        "primary_genre": primary["name"],
        "primary_confidence": primary["confidence"],
        "method": "audio_features",
    }


# ── Spotify enrichment (optional) ────────────────────────────────────────────


def _enrich_from_spotify(title: str, artist: str) -> dict | None:
    """Look up genre metadata from Spotify via track search.

    Returns {genres: [...], spotify_id, album_genres, artist_genres} or None.
    """
    try:
        import os
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        cid = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
        csecret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
        if not cid or not csecret:
            return None

        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(client_id=cid, client_secret=csecret)
        )
        query = f"track:{title} artist:{artist}" if artist else title
        result = sp.search(q=query, type="track", limit=3)
        items = result.get("tracks", {}).get("items", [])
        if not items:
            return None

        # Find best match (title similarity)
        best = items[0]
        spotify_id = best.get("id", "")

        # Get artist genres
        artist_ids = [a["id"] for a in best.get("artists", [])[:3] if a.get("id")]
        artist_genres: list[str] = []
        if artist_ids:
            artists_data = sp.artists(artist_ids).get("artists", [])
            genre_set: set[str] = set()
            for a in artists_data:
                for g in a.get("genres", []):
                    genre_set.add(g)
            artist_genres = sorted(genre_set)

        # Get album genres
        album_data = best.get("album", {})
        album_genres: list[str] = []
        album_id = album_data.get("id")
        if album_id:
            try:
                album = sp.album(album_id)
                album_genres = sorted(set(album.get("genres", [])))
            except Exception:
                pass

        all_genres = list(dict.fromkeys(artist_genres + album_genres))

        # Map Spotify microgenres to broad DJ genres
        dj_genres = _map_spotify_genres_to_dj(all_genres)

        return {
            "genres": dj_genres,
            "spotify_id": spotify_id,
            "spotify_genres_raw": all_genres[:10],
            "artist_genres": artist_genres,
            "album_genres": album_genres,
            "source": "spotify",
        }
    except Exception as e:
        logger.debug("[genre] Spotify enrichment failed: %s", e)
        return None


# ── Spotify → DJ genre mapping ───────────────────────────────────────────────

_SPOTIFY_TO_DJ: dict[str, str] = {
    "house": "house", "deep house": "house", "tech house": "house",
    "progressive house": "house", "tropical house": "house",
    "techno": "techno", "minimal techno": "techno", "peak time techno": "techno",
    "hip hop": "hip-hop", "rap": "hip-hop", "trap": "hip-hop",
    "drill": "hip-hop", "boom bap": "hip-hop", "east coast hip hop": "hip-hop",
    "drum and bass": "drum-and-bass", "dnb": "drum-and-bass",
    "liquid funk": "drum-and-bass", "neurofunk": "drum-and-bass",
    "dubstep": "dubstep", "brostep": "dubstep", "riddim": "dubstep",
    "pop": "pop", "dance pop": "pop", "electropop": "pop",
    "synthpop": "pop", "k-pop": "pop", "j-pop": "pop",
    "r&b": "r-and-b", "contemporary r&b": "r-and-b", "neo soul": "r-and-b",
    "alternative r&b": "r-and-b",
    "funk": "funk", "disco": "disco", "nu disco": "disco",
    "rock": "rock", "alternative rock": "rock", "indie rock": "rock",
    "punk": "rock", "metal": "rock",
    "electronic": "electronic", "edm": "electronic",
    "idm": "electronic", "downtempo": "electronic",
    "trance": "trance", "psytrance": "trance", "uplifting trance": "trance",
    "breaks": "breaks", "breakbeat": "breaks",
    "latin": "latin", "reggaeton": "latin", "salsa": "latin",
    "bachata": "latin", "dembow": "latin",
    "reggae": "reggae", "dancehall": "reggae", "dub": "reggae",
    "afrobeats": "afrobeats", "afrobeat": "afrobeats", "afro house": "afrobeats",
    "amapiano": "amapiano",
    "lo-fi": "lo-fi", "chillhop": "lo-fi", "lo-fi beats": "lo-fi",
    "ambient": "ambient",
    "jazz": "funk", "blues": "rock", "soul": "r-and-b",
    "gospel": "r-and-b", "country": "rock",
}


def _map_spotify_genres_to_dj(spotify_genres: list[str]) -> list[dict]:
    """Map Spotify's microgenre tags to broad DJ genre categories."""
    mapped: dict[str, float] = {}
    for g in spotify_genres:
        key = g.lower().strip()
        dj_genre = _SPOTIFY_TO_DJ.get(key)
        if not dj_genre:
            # Try partial match
            for spotify_k, dj_v in _SPOTIFY_TO_DJ.items():
                if spotify_k in key or key in spotify_k:
                    dj_genre = dj_v
                    break
        if dj_genre:
            mapped[dj_genre] = mapped.get(dj_genre, 0.0) + 1.0

    total = sum(mapped.values()) or 1.0
    return sorted(
        [{"name": k, "confidence": round(v / total, 3), "source": "spotify"}
         for k, v in mapped.items()],
        key=lambda x: -x["confidence"],
    )


# ── Public API ────────────────────────────────────────────────────────────────


_DISCOGS_TO_DJ: dict[str, str] = {
    "electronic": "electronic",
    "hip hop": "hip-hop",
    "funk / soul": "funk",
    "funk": "funk",
    "soul": "r-and-b",
    "pop": "pop",
    "rock": "rock",
    "reggae": "reggae",
    "latin": "latin",
    "jazz": "funk",
    "house": "house",
    "deep house": "house",
    "tech house": "house",
    "progressive house": "house",
    "acid house": "house",
    "techno": "techno",
    "minimal techno": "techno",
    "detroit techno": "techno",
    "trance": "trance",
    "progressive trance": "trance",
    "psy-trance": "trance",
    "breakbeat": "breaks",
    "breaks": "breaks",
    "drum n bass": "drum-and-bass",
    "drum and bass": "drum-and-bass",
    "jungle": "drum-and-bass",
    "liquid funk": "drum-and-bass",
    "dubstep": "dubstep",
    "grime": "dubstep",
    "uk garage": "breaks",
    "2-step": "breaks",
    "downtempo": "downtempo",
    "trip hop": "downtempo",
    "ambient": "ambient",
    "idm": "electronic",
    "electro": "electronic",
    "disco": "disco",
    "nu-disco": "disco",
    "boogie": "funk",
    "conscious": "hip-hop",
    "gangsta": "hip-hop",
    "boom bap": "hip-hop",
    "trap": "hip-hop",
    "drill": "hip-hop",
    "rnb/swing": "r-and-b",
    "contemporary r&b": "r-and-b",
    "dancehall": "reggae",
    "dub": "reggae",
    "reggaeton": "latin",
    "salsa": "latin",
    "afrobeat": "afrobeats",
    "afrobeats": "afrobeats",
    "afro house": "afrobeats",
    "amapiano": "amapiano",
    "lo-fi": "lo-fi",
}


def _map_discogs_labels_to_dj(labels: list[str]) -> list[dict]:
    """Map Discogs release genre/style labels into our broad DJ taxonomy."""
    mapped: dict[str, float] = {}
    raw_count = 0
    for label in labels:
        key = str(label or "").lower().strip()
        if not key:
            continue
        raw_count += 1
        dj_genre = _DISCOGS_TO_DJ.get(key)
        if not dj_genre:
            for discogs_k, dj_v in _DISCOGS_TO_DJ.items():
                if discogs_k in key or key in discogs_k:
                    dj_genre = dj_v
                    break
        if dj_genre:
            mapped[dj_genre] = mapped.get(dj_genre, 0.0) + 1.0

    total = sum(mapped.values()) or 1.0
    coverage = min(1.0, total / max(raw_count, 1))
    return sorted(
        [
            {
                "name": name,
                "confidence": round((score / total) * (0.65 + 0.20 * coverage), 3),
                "source": "discogs",
            }
            for name, score in mapped.items()
        ],
        key=lambda x: -x["confidence"],
    )


def _discogs_headers() -> dict[str, str]:
    user_agent = os.getenv(
        "DISCOGS_USER_AGENT",
        "HarBeat/1.0 +https://github.com/jihaobi123/harbeat-client",
    ).strip()
    headers = {"User-Agent": user_agent}
    token = os.getenv("DISCOGS_USER_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    return headers


def _enrich_from_discogs(title: str, artist: str) -> dict | None:
    """Look up Discogs release/master metadata.

    Discogs tags are broad and release-level, so this is used as enrichment
    instead of a replacement for audio analysis.
    """
    if not title:
        return None
    token = os.getenv("DISCOGS_USER_TOKEN", "").strip()
    if not token:
        return None
    try:
        import httpx

        params = {
            "type": "release",
            "track": title,
            "per_page": "3",
            "page": "1",
        }
        if artist:
            params["artist"] = artist

        raw_labels: list[str] = []
        release_ids: list[int] = []
        with httpx.Client(timeout=8.0, headers=_discogs_headers()) as client:
            resp = client.get("https://api.discogs.com/database/search", params=params)
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if not results:
                return None

            for item in results[:3]:
                release_id = item.get("id")
                if isinstance(release_id, int):
                    release_ids.append(release_id)
                for key in ("genre", "style"):
                    vals = item.get(key) or []
                    if isinstance(vals, str):
                        raw_labels.append(vals)
                    elif isinstance(vals, list):
                        raw_labels.extend(str(v) for v in vals if v)

            if release_ids:
                detail = client.get(f"https://api.discogs.com/releases/{release_ids[0]}")
                if detail.status_code == 200:
                    release = detail.json()
                    for key in ("genres", "styles"):
                        vals = release.get(key) or []
                        if isinstance(vals, str):
                            raw_labels.append(vals)
                        elif isinstance(vals, list):
                            raw_labels.extend(str(v) for v in vals if v)

        raw_labels = list(dict.fromkeys(raw_labels))
        mapped = _map_discogs_labels_to_dj(raw_labels)
        if not mapped:
            return None
        return {
            "genres": mapped,
            "discogs_id": release_ids[0] if release_ids else None,
            "discogs_labels_raw": raw_labels[:16],
            "source": "discogs",
        }
    except Exception as e:
        logger.debug("[genre] Discogs enrichment failed: %s", e)
        return None


def _merge_external_and_audio(audio_result: dict, external_results: list[dict]) -> dict | None:
    external_genres: list[dict] = []
    seen: set[str] = set()
    metadata: dict[str, Any] = {}
    sources: list[str] = []

    for result in external_results:
        source = result.get("source")
        if source:
            sources.append(str(source))
        for genre in result.get("genres") or []:
            name = genre.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            external_genres.append(dict(genre))
        if source == "spotify":
            metadata["spotify_id"] = result.get("spotify_id")
            metadata["spotify_genres_raw"] = result.get("spotify_genres_raw", [])
        elif source == "discogs":
            metadata["discogs_id"] = result.get("discogs_id")
            metadata["discogs_labels_raw"] = result.get("discogs_labels_raw", [])

    if not external_genres:
        return None

    merged = list(external_genres)
    external_names = {g["name"] for g in external_genres}
    for genre in audio_result.get("genres", []):
        if genre["name"] not in external_names:
            merged.append({**genre, "confidence": round(genre["confidence"] * 0.7, 4)})
    merged.sort(key=lambda g: -g["confidence"])
    primary = merged[0]
    return {
        "genres": merged[:5],
        "primary_genre": primary["name"],
        "primary_confidence": primary["confidence"],
        "method": "_".join(sources + ["audio", "merged"]),
        **{k: v for k, v in metadata.items() if v not in (None, [], {})},
    }


def classify_genre(
    *,
    bpm: float | None = None,
    stem_activity: dict | None = None,
    groove_profile: dict | None = None,
    dj_features: dict | None = None,
    energy: float | None = None,
    title: str = "",
    artist: str = "",
    manual_style: str | None = None,
) -> dict:
    """Multi-source genre classification.

    Priority: manual_style > external metadata > audio features.
    """
    # ── 0. Manual override ──
    if manual_style and manual_style.strip():
        return {
            "genres": [{"name": manual_style.strip(), "confidence": 1.0,
                        "source": "manual"}],
            "primary_genre": manual_style.strip(),
            "primary_confidence": 1.0,
            "method": "manual",
        }

    # ── 1. Audio-feature inference ──
    audio_result = _classify_from_features(
        bpm=bpm or 0.0,
        stem_activity=stem_activity,
        groove_profile=groove_profile,
        dj_features=dj_features,
        energy=energy or 0.5,
    )

    # ── 2. Spotify enrichment ──
    external_results = []
    spotify_result = None
    if title:
        spotify_result = _enrich_from_spotify(title, artist)
        if spotify_result and spotify_result.get("genres"):
            external_results.append(spotify_result)
        discogs_result = _enrich_from_discogs(title, artist)
        if discogs_result and discogs_result.get("genres"):
            external_results.append(discogs_result)

    # ── 3. Merge ──
    merged = _merge_external_and_audio(audio_result, external_results)
    if merged:
        return merged

    if spotify_result and spotify_result.get("genres"):
        spotify_genres = spotify_result["genres"]
        # Merge: Spotify genres first, then audio genres that don't overlap
        spotify_names = {g["name"] for g in spotify_genres}
        merged = list(spotify_genres)
        for g in audio_result.get("genres", []):
            if g["name"] not in spotify_names:
                merged.append({**g, "confidence": round(g["confidence"] * 0.7, 4)})
        merged.sort(key=lambda g: -g["confidence"])

        primary = spotify_genres[0] if spotify_genres else merged[0]
        return {
            "genres": merged[:5],
            "primary_genre": primary["name"],
            "primary_confidence": primary["confidence"],
            "method": "spotify_audio_merged",
            "spotify_id": spotify_result.get("spotify_id"),
            "spotify_genres_raw": spotify_result.get("spotify_genres_raw", []),
        }

    # ── 4. Fallback: audio-only ──
    return audio_result
