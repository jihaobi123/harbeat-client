import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from listen_imports.store import Jobs
from listen_imports.sources import playlist_url, validate_candidate, validate_audio, match_candidates
from listen_imports.server import create_app


def test_queue_deduplicates_survives_restart_and_reserves_capacity(tmp_path):
    jobs = Jobs(tmp_path, limit=2)
    first = jobs.submit('sha:a', {'title': 'A', 'path': '/private/a'})
    assert jobs.submit('sha:a', {'title': 'duplicate'})['id'] == first['id']
    jobs.submit('sha:b', {'title': 'B'})
    with pytest.raises(ValueError, match='队列'):
        jobs.submit('sha:c', {'title': 'C'})
    assert jobs.claim()['id'] == first['id']
    recovered = Jobs(tmp_path, limit=2)
    recovered.recover()
    assert recovered.claim()['id'] == first['id']
    recovered.update(first['id'], status='ready', track_id='track-a')
    assert 'payload' not in recovered.public(first['id'])
    assert '/private' not in json.dumps(recovered.list_public())
    assert recovered.submit('sha:a', {})['status'] == 'ready'


def test_retry_only_failed_and_no_duplicate_claim(tmp_path):
    jobs = Jobs(tmp_path)
    one = jobs.submit('one', {'title': 'A'})
    assert jobs.claim()['id'] == one['id']
    assert jobs.claim() is None
    with pytest.raises(ValueError):
        jobs.retry(one['id'])
    jobs.update(one['id'], status='failed', message='temporary network failure')
    assert jobs.retry(one['id'])['status'] == 'queued'


@pytest.mark.parametrize('value', [
    'https://music.163.com.evil.test/playlist?id=12',
    'http://127.0.0.1/?music.163.com&id=12',
    'https://music.163.com@127.0.0.1/?id=12',
    'file:///etc/passwd', 'https://y.qq.com:9000/playlist/12',
])
def test_playlist_rejects_disguised_hosts(value):
    with pytest.raises(ValueError):
        playlist_url(value)


def test_share_text_and_candidate_validation():
    assert playlist_url('分享歌单 https://music.163.com/#/playlist?id=12345 （来自网易云）').endswith('id=12345')
    assert playlist_url('https://y.qq.com/n/ryqq/playlist/123')
    assert playlist_url('https://y.music.163.com/m/playlist?id=123')
    with pytest.raises(ValueError):
        validate_candidate({'id': '../secret', 'source': 'kuwo', 'title': 'A'})
    with pytest.raises(ValueError):
        validate_candidate({'id': '12', 'source': 'arbitrary', 'title': 'A'})


def test_matching_does_not_default_to_unrelated_or_short_search_hits():
    rows = [dict(id='1', source='kuwo', title='Faded & Closer', artist='Alan Walker', duration=50),
            dict(id='2', source='kuwo', title='The Spectre', artist='Alan Walker', duration=14),
            dict(id='3', source='kuwo', title='The Spectre', artist='Alan Walker', duration=193)]
    assert [c['id'] for c in match_candidates(rows, 'The Spectre', 'Alan Walker')] == ['3']


def test_upload_requires_write_header_and_valid_audio(tmp_path):
    with TestClient(create_app(tmp_path, run_worker=False, minimum_free=0)) as client:
        r = client.post('/api/listen-import/upload', files={'audio': ('a.mp3', b'not audio')})
        assert r.status_code == 403
        r = client.post('/api/listen-import/upload', headers={'X-HarBeat-Import': '1'},
                        files={'audio': ('a.mp3', b'not audio')})
        assert r.status_code == 422
        assert not client.get('/api/listen-import/jobs').json()['jobs']
        assert not list((tmp_path / 'uploads').glob('*'))


def test_download_only_accepts_server_issued_candidates(tmp_path):
    with TestClient(create_app(tmp_path, run_worker=False, minimum_free=0)) as client:
        r = client.post('/api/listen-import/download', headers={'X-HarBeat-Import': '1'},
                        json={'candidate_ids': ['invented'], 'style': 'house'})
        assert r.status_code == 422
        assert not client.get('/api/listen-import/jobs').json()['jobs']


def test_real_audio_upload_dedup_and_oversize_cleanup(tmp_path, monkeypatch):
    import io
    import wave
    from listen_imports import sources
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 8000 * 21)
    with TestClient(create_app(tmp_path, run_worker=False, minimum_free=0)) as client:
        def upload():
            return client.post('/api/listen-import/upload', headers={'X-HarBeat-Import': '1'},
                               files={'audio':('../../my song.wav',output.getvalue(),'audio/wav')})
        first = upload()
        assert first.status_code == 200
        assert first.json()['title'] == 'my song'
        assert upload().json()['id'] == first.json()['id']
        assert len(list((tmp_path/'uploads').glob('*'))) == 1
        monkeypatch.setattr(sources,'MAX_BYTES',10)
        assert upload().status_code == 413
        assert len(list((tmp_path/'uploads').glob('*'))) == 1


def test_batch_queue_transaction_rolls_back_on_capacity(tmp_path):
    jobs=Jobs(tmp_path,limit=1)
    with pytest.raises(ValueError):
        jobs.submit_many([('a',{'title':'A'}),('b',{'title':'B'})])
    assert jobs.list_public()==[]


def test_netease_short_share_markdown_url():
    assert playlist_url('分享歌单: 舞者的HIP-HOP [https://163cn.tv/bg8QkvT3](https://163cn.tv/bg8QkvT3) (@网易云音乐)') == 'https://163cn.tv/bg8QkvT3'


def test_netease_short_redirect_is_resolved_and_restricted(monkeypatch):
    import asyncio
    import httpx
    from listen_imports import sources
    original = httpx.AsyncClient
    called = []
    destination = ['https://music.163.com/m/playlist?app_version=9.5.90&id=2835757']
    def handler(request):
        called.append(str(request.url))
        return httpx.Response(302, headers={'location': destination[0]})
    monkeypatch.setattr(sources.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    async def parse(url):
        assert url == 'https://music.163.com/playlist?id=2835757'
        return {'name': '舞者的HIP-HOP', 'tracks': []}
    monkeypatch.setattr(sources, 'parse_playlist_url', parse)
    assert asyncio.run(sources.parse_playlist('https://163cn.tv/bg8QkvT3'))['name'] == '舞者的HIP-HOP'
    for bad in ['http://127.0.0.1/playlist?id=2835757', 'https://music.163.com.evil.test/playlist?id=1', 'https://y.qq.com/n/ryqq/playlist/1']:
        destination[0] = bad
        with pytest.raises(ValueError):
            asyncio.run(sources.parse_playlist('https://163cn.tv/bg8QkvT3'))
    assert called == ['https://163cn.tv/bg8QkvT3'] * 4
