"""Reuse the repository's providers, with bounded downloads and explicit source IDs."""
import asyncio
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import httpx

from app.modules.fangpi.playlist_parser import parse_playlist_url
from app.modules.fangpi.service import smart_search_fangpi, search_fangpi, _fangpi_get_audio_url, _kuwo_get_audio_url

MAX_BYTES = 100 * 1024 * 1024
SUFFIXES = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.aif', '.aiff'}


def playlist_url(text):
    match = re.search(r'https?://[^\s<>"\u201c\u201d\u3000\uFF08\uFF09]+', text)
    if not match:
        raise ValueError('请粘贴网易云或 QQ 音乐的歌单分享链接。')
    url = match[0].rstrip(').,，。')
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443) or not (
        host == 'music.163.com' or host.endswith('.music.163.com') or host == 'y.qq.com' or host.endswith('.y.qq.com')
    ):
        raise ValueError('仅支持网易云和 QQ 音乐歌单链接。')
    return url


async def parse_playlist(text):
    url = playlist_url(text)
    # Resolve QQ short links ourselves: every redirect must stay on the platform.
    if 'qq.com' in (urlparse(url).hostname or ''):
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            for _ in range(5):
                if re.search(r'/playlist/\d+|[?&](?:id|disstid)=\d+', url):
                    break
                response = await client.get(url)
                if response.is_redirect:
                    url = playlist_url(urljoin(url, response.headers['location']))
                else:
                    break
        # Never send an unresolved short URL into the legacy unrestricted resolver.
        match = re.search(r'/playlist/(\d+)|[?&](?:id|disstid)=(\d+)', url)
        if not match:
            raise ValueError('这个 QQ 分享链接没有返回歌单编号，请复制完整歌单链接。')
        url = 'https://y.qq.com/n/ryqq/playlist/' + next(x for x in match.groups() if x)
    result = await parse_playlist_url(url)
    result['tracks'] = result.get('tracks', [])[:500]
    return result


def validate_candidate(row):
    if row.get('source') not in ('fangpi', 'kuwo') or not re.fullmatch(r'\d{1,24}', str(row.get('id', ''))):
        raise ValueError('无效的音源编号。')
    if not isinstance(row.get('title'), str) or not 0 < len(row['title']) <= 300:
        raise ValueError('歌曲名称不完整。')
    return {k: row.get(k) for k in ('id', 'source', 'title', 'artist', 'duration')}


def match_candidates(rows, title, artist):
    def norm(text):
        return ''.join(c for c in unicodedata.normalize('NFKC', text or '').casefold() if c.isalnum())
    def similarity(a,b):
        a,b=norm(a),norm(b)
        if not a or not b:
            return 0
        if min(len(a),len(b))>=3 and (a in b or b in a):
            return .95 if a!=b else 1
        return SequenceMatcher(None,a,b).ratio()
    result = []
    for row in rows:
        try:
            candidate = validate_candidate(row)
            title_score = similarity(candidate['title'], title)
            artist_score = similarity(candidate.get('artist'), artist) if artist else 1
            if title_score < .72 or artist_score < .45 or (candidate.get('duration') and not 20 <= candidate['duration'] <= 1200):
                continue
            result.append((title_score+artist_score*.25,candidate))
        except ValueError:
            continue
    return [row for _,row in sorted(result,key=lambda x:-x[0])][:8]


async def search(title, artist):
    rows = await smart_search_fangpi(title, artist)
    result = match_candidates(rows, title, artist)
    if not result and artist:
        result = match_candidates(await search_fangpi(title), title, artist)
    return result


def validate_audio(path, expected_duration=None):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
                                 '-of', 'json', str(path)], capture_output=True, text=True, timeout=30, check=True)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        if not 20 <= duration <= 1200 or not any(s['codec_type'] == 'audio' for s in data['streams']):
            raise ValueError()
        if expected_duration and abs(duration-expected_duration) > max(12, expected_duration*.08):
            raise ValueError('音源时长与匹配歌曲不一致，可能是试听片段，请换一个音源。')
        return duration
    except (subprocess.SubprocessError, OSError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc):
            raise
        raise ValueError('请上传可解码的音乐文件，时长需在 20 秒至 20 分钟之间。') from exc


async def public_audio_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError('音源返回了无效地址。')
    # Only the established provider CDNs, including their redirects, may be fetched.
    host = parsed.hostname or ''
    if not any(host == domain or host.endswith('.'+domain) for domain in ('kuwo.cn', 'kwcdn.kuwo.cn', 'fangpi.net')):
        raise ValueError('音源地址不属于已支持的平台，请尝试其他音源或本地上传。')
    answers = await asyncio.to_thread(socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
        raise ValueError('音源网络地址不可用。')


async def download(candidate, target):
    candidate = validate_candidate(candidate)
    resolver = _fangpi_get_audio_url if candidate['source'] == 'fangpi' else _kuwo_get_audio_url
    url = await resolver(candidate['id'])  # Never reinterpret a provider ID as another provider's ID.
    target = Path(target)
    temp = target.with_suffix('.part')
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            for _ in range(6):
                await public_audio_url(url)
                async with client.stream('GET', url, headers={'User-Agent': 'okhttp/3.10.0'}) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers['location'])
                        continue
                    response.raise_for_status()
                    size = 0
                    with temp.open('wb') as output:
                        async for chunk in response.aiter_bytes(1024*1024):
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError('音源超过 100 MB，请使用较小的文件。')
                            output.write(chunk)
                    if size < 200_000:
                        raise ValueError('音源没有返回完整音乐，请换一个音源或本地上传。')
                    validate_audio(temp, candidate.get('duration'))
                    temp.replace(target)
                    return target
        raise ValueError('音源重定向次数过多。')
    finally:
        temp.unlink(missing_ok=True)


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()
