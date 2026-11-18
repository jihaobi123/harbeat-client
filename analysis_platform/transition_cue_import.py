"""Add transition evidence during a Jetson library import."""

import json
import re

from .transition_cues import read_cues, write_cues


def netease_lyrics(payload, track):
    candidate = payload.get('candidate') or {}
    identifier = str(candidate.get('id', ''))
    duration = candidate.get('duration')
    if (payload.get('kind') != 'download' or candidate.get('source') != 'netease'
            or not re.fullmatch(r'[0-9]{1,24}', identifier)
            or not isinstance(duration, (float, int)) or abs(duration-track['duration']) > 2
            or not re.fullmatch(r'[a-f0-9]{64}', str(payload.get('sha256', '')))
            or track['id'] != 'track-'+payload['sha256'][:20]):
        return None
    import httpx

    try:
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            with client.stream('GET', 'https://music.163.com/api/song/lyric',
                               params={'id': identifier, 'lv': 1, 'tv': -1},
                               headers={'User-Agent': 'HarBeat/0.1', 'Referer': 'https://music.163.com/'}) as response:
                response.raise_for_status()
                raw = bytearray()
                for part in response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > 512 * 1024:
                        return None
        value = json.loads(raw)
        lrc = (value.get('lrc') or {}).get('lyric')
        if value.get('code') == 200 and isinstance(lrc, str) and lrc.strip():
            return {'masterSha256': track['provenance']['masterSha256'], 'lrc': lrc}
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    return None


def prepare_import_cues(folder, track, payload):
    """Use the already validated download ID. Local uploads use acoustic evidence."""
    cached = read_cues(folder, track)
    if cached is not None:
        return cached
    return write_cues(folder, track, netease_lyrics(payload, track))
