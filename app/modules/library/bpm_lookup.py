"""Online BPM / key lookup via free music data sources.

Strategy (all free, no API key required for songbpm):
1. Spotify search → find track → get standardized artist/title slugs
2. songbpm.com scrape → parse BPM and key from HTML (Spotify-backed data)
3. Direct URL guess on songbpm.com if Spotify search unavailable
4. Deezer API fallback (may be blocked in China)

songbpm.com uses Spotify's audio analysis data (which they cached before
the audio_features endpoint was deprecated in Nov 2024).
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

NOTE_MODE_TO_CAMELOT = {
    ("C", "major"): "8B", ("C#", "major"): "3B", ("D", "major"): "10B",
    ("D#", "major"): "5B", ("E", "major"): "12B", ("F", "major"): "7B",
    ("F#", "major"): "2B", ("G", "major"): "9B", ("G#", "major"): "4B",
    ("A", "major"): "11B", ("A#", "major"): "6B", ("B", "major"): "1B",
    ("C", "minor"): "5A", ("C#", "minor"): "12A", ("D", "minor"): "7A",
    ("D#", "minor"): "2A", ("E", "minor"): "9A", ("F", "minor"): "4A",
    ("F#", "minor"): "11A", ("G", "minor"): "6A", ("G#", "minor"): "1A",
    ("A", "minor"): "8A", ("A#", "minor"): "3A", ("B", "minor"): "10A",
}

_HTTP_TIMEOUT = 8  # seconds
_deezer_available = True  # auto-set to False after first timeout


# ── Utilities ─────────────────────────────────────────────────────────────


def _clean_search_term(text: str) -> str:
    """Remove common filename noise for better search matching."""
    text = re.sub(r'\.\w{2,4}$', '', text)
    text = text.replace('_', ' ')
    text = re.sub(
        r'\s*[\(\[][^)\]]*(?:official|video|audio|lyric|remix|feat|explicit|clean|remaster)[^)\]]*[\)\]]',
        '', text, flags=re.IGNORECASE,
    )
    return text.strip()


def _slugify(text: str) -> str:
    """Convert text to URL slug (songbpm.com style)."""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().strip()
    # Remove non-word chars except spaces and hyphens
    text = re.sub(r'[^\w\s-]', '', text)
    # Replace whitespace/underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text


def _http_get(url: str, accept: str = "text/html") -> Optional[str]:
    """Simple HTTP GET with timeout."""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36",
        "Accept": accept,
    })
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as e:
        logger.debug("HTTP GET %s failed: %s", url, e)
        return None


def _http_get_json(url: str) -> Optional[dict]:
    """HTTP GET returning parsed JSON."""
    body = _http_get(url, accept="application/json")
    if body:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass
    return None


# ── songbpm.com scraper ──────────────────────────────────────────────────


def _parse_songbpm_html(html: str) -> Optional[dict]:
    """Extract BPM and key from songbpm.com HTML.

    The page renders BPM prominently (e.g. "91 BPM") and key/mode info
    in the meta description and structured text.
    """
    # BPM: first occurrence of "N BPM" is the primary BPM
    bpm_matches = re.findall(r'(\d+)\s*BPM', html)
    if not bpm_matches:
        return None

    bpm = int(bpm_matches[0])
    # Second match is usually the double/half-time variant
    alt_bpm = int(bpm_matches[1]) if len(bpm_matches) > 1 else None

    # Key: "a C key and a major mode" in meta description
    key_str = None
    camelot_key = None
    key_match = re.search(
        r'a\s+([A-G][#♯b♭]?)\s+key\s+and\s+a\s+(major|minor)\s+mode',
        html, re.IGNORECASE,
    )
    if key_match:
        note = key_match.group(1).replace('♯', '#').replace('♭', 'b')
        mode = key_match.group(2).lower()
        key_str = f"{note} {mode}"
        camelot_key = NOTE_MODE_TO_CAMELOT.get((note, mode))

    # Duration: "N minutes and N seconds"
    dur_match = re.search(r'(\d+)\s+minutes?\s+and\s+(\d+)\s+seconds?', html)
    duration_s = None
    if dur_match:
        duration_s = int(dur_match.group(1)) * 60 + int(dur_match.group(2))

    return {
        "bpm": bpm,
        "alt_bpm": alt_bpm,
        "key": key_str,
        "camelot_key": camelot_key,
        "duration_s": duration_s,
    }


def _songbpm_direct(artist_slug: str, title_slug: str) -> Optional[dict]:
    """Fetch BPM from songbpm.com using constructed URL."""
    url = f"https://songbpm.com/@{artist_slug}/{title_slug}"
    html = _http_get(url)
    if not html:
        return None

    parsed = _parse_songbpm_html(html)
    if not parsed or not parsed.get("bpm"):
        return None

    parsed["source"] = "songbpm"
    parsed["url"] = url
    logger.info("songbpm.com: BPM=%d key=%s (%s)", parsed["bpm"], parsed.get("key"), url)
    return parsed


# ── Spotify search (for better slug matching) ────────────────────────────


def _spotify_search(title: str, artist: str) -> Optional[dict]:
    """Search Spotify to get standardized track/artist info.

    Uses spotipy if available and configured.
    Returns dict with name, artist, artist_slug, title_slug, spotify_id.
    """
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        return None

    client_id = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None

    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            )
        )

        # Structured search first
        query = f"track:{title} artist:{artist}"
        results = sp.search(q=query, type="track", limit=3, market="US")
        tracks = results.get("tracks", {}).get("items", [])

        if not tracks:
            # Broader fallback
            query = f"{title} {artist}"
            results = sp.search(q=query, type="track", limit=3, market="US")
            tracks = results.get("tracks", {}).get("items", [])

        if not tracks:
            return None

        track = tracks[0]
        sp_artist = track["artists"][0]["name"] if track.get("artists") else artist
        sp_title = track.get("name", title)

        return {
            "name": sp_title,
            "artist": sp_artist,
            "artist_slug": _slugify(sp_artist),
            "title_slug": _slugify(sp_title),
            "spotify_id": track.get("id"),
            "duration_ms": track.get("duration_ms"),
        }
    except Exception as e:
        logger.debug("Spotify search failed: %s", e)
        return None


# ── Deezer API (fallback, may be blocked in China) ───────────────────────


def _deezer_lookup(title: str, artist: str, file_duration: float = 0) -> Optional[dict]:
    """Look up BPM from Deezer API (free, no auth). Auto-skips after first timeout."""
    global _deezer_available
    if not _deezer_available:
        return None

    title_clean = _clean_search_term(title)
    artist_clean = _clean_search_term(artist)

    query = f'artist:"{artist_clean}" track:"{title_clean}"'
    url = f"https://api.deezer.com/search?q={quote_plus(query)}&limit=3"
    data = _http_get_json(url)

    if data is None:
        # Connection failed (likely blocked in China) — disable for rest of session
        logger.info("Deezer API unreachable, disabling Deezer lookup for this session")
        _deezer_available = False
        return None

    if not data.get("data"):
        query = f"{title_clean} {artist_clean}"
        url = f"https://api.deezer.com/search?q={quote_plus(query)}&limit=3"
        data = _http_get_json(url)

    tracks = (data or {}).get("data", [])
    if not tracks:
        return None

    track = tracks[0]
    track_id = track["id"]

    detail = _http_get_json(f"https://api.deezer.com/track/{track_id}")
    if not detail:
        return None

    bpm = float(detail.get("bpm", 0))
    if bpm <= 0:
        return None

    return {
        "bpm": round(bpm, 1),
        "key": None,
        "camelot_key": None,
        "source": "deezer",
        "deezer_id": track_id,
    }


# ── Main lookup function ─────────────────────────────────────────────────


def lookup_track_info(
    title: str,
    artist: str,
    file_duration: float = 0,
) -> Optional[dict]:
    """Look up track BPM/key from online sources.

    Strategy:
    1. Use Spotify search to get standardized artist/title names
    2. Scrape songbpm.com with the Spotify-derived URL slugs
    3. If Spotify unavailable, try direct URL guess from input title/artist
    4. If songbpm.com fails, try Deezer API (may be blocked in China)

    Args:
        title: Song title (can be filename-style).
        artist: Artist name.
        file_duration: File duration in seconds (for match validation).

    Returns:
        dict with bpm, key, camelot_key, source, etc.
        None if not found → caller should use local analysis.
    """
    if not title and not artist:
        return None

    title_clean = _clean_search_term(title)
    artist_clean = _clean_search_term(artist)

    # ── Step 1: Spotify search for standardized names ─────────────
    sp_info = _spotify_search(title_clean, artist_clean)

    # ── Step 2: songbpm.com with Spotify-derived slugs ────────────
    if sp_info:
        result = _songbpm_direct(sp_info["artist_slug"], sp_info["title_slug"])
        if result and result.get("bpm"):
            result["spotify_id"] = sp_info.get("spotify_id")
            result["matched_name"] = f"{sp_info['artist']} - {sp_info['name']}"

            # Validate duration if available
            if file_duration > 0 and sp_info.get("duration_ms"):
                sp_dur = sp_info["duration_ms"] / 1000.0
                if abs(sp_dur - file_duration) / file_duration > 0.30:
                    logger.warning(
                        "Duration mismatch: file=%.0fs spotify=%.0fs — may be wrong track",
                        file_duration, sp_dur,
                    )

            return result

    # ── Step 3: Direct URL guess (no Spotify) ─────────────────────
    artist_slug = _slugify(artist_clean)
    title_slug = _slugify(title_clean)

    if artist_slug and title_slug:
        result = _songbpm_direct(artist_slug, title_slug)
        if result and result.get("bpm"):
            result["matched_name"] = f"{artist_clean} - {title_clean}"
            return result

    # ── Step 4: Deezer API fallback (blocked in China) ────────────
    result = _deezer_lookup(title_clean, artist_clean, file_duration)
    if result:
        return result

    logger.info("Online BPM lookup: no results for '%s - %s'", artist, title)
    return None


def normalize_bpm(bpm: float, alt_bpm: float | None = None) -> float:
    """Normalize BPM to DJ-friendly range (70-160).

    Songbpm.com returns Spotify's raw BPM which can be double-time
    (e.g. 181 for a 91 BPM hip-hop track). This normalizes to the
    range most DJs use for mixing.
    """
    DJ_LOW, DJ_HIGH = 70.0, 160.0

    # If primary BPM is already in DJ range, use it
    if DJ_LOW <= bpm <= DJ_HIGH:
        return bpm

    # If alt_bpm is in DJ range, prefer it
    if alt_bpm and DJ_LOW <= alt_bpm <= DJ_HIGH:
        return alt_bpm

    # Try halving or doubling
    if bpm > DJ_HIGH and DJ_LOW <= bpm / 2 <= DJ_HIGH:
        return bpm / 2
    if bpm < DJ_LOW and DJ_LOW <= bpm * 2 <= DJ_HIGH:
        return bpm * 2

    # Can't normalize — return as-is
    return bpm
