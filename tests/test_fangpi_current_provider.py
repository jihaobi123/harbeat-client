import asyncio
import json
import httpx
import pytest
from app.modules.fangpi import service


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def fixture_client(monkeypatch, response):
    original = httpx.AsyncClient
    def client(**kwargs):
        return original(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(service.httpx, 'AsyncClient', client)


def test_search_uses_current_provider_domain(monkeypatch):
    def respond(request):
        if request.url.host != 'www.fangpiw.com':
            raise httpx.ConnectError('legacy domain unavailable', request=request)
        if request.url.path == '/api/s':
            return httpx.Response(200, json={'code': 1})
        return httpx.Response(200, text='<a href="/music/4886072" title="Ayy Macarena - Tyga">song</a>')
    fixture_client(monkeypatch, respond)
    rows = run(service._fangpi_search('Ayy Macarena'))
    assert len(rows) == 1 and rows[0]['id'] == '4886072'
    assert rows[0]['url'] == 'https://www.fangpiw.com/music/4886072'


@pytest.mark.parametrize('code', [1, 4])
def test_download_uses_page_csrf_and_download_purpose_without_bypassing_denials(monkeypatch, code):
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.host != 'www.fangpiw.com':
            raise httpx.ConnectError('legacy domain unavailable', request=request)
        if request.method == 'GET':
            return httpx.Response(200, text='<meta name="csrf-token" content="page-token">'
                + "<script>window.appData = JSON.parse('{\"play_id\":\"bound-id\"}')</script>", headers={'Set-Cookie':'provider_session=test-session; Path=/; Secure; HttpOnly'})
        if request.url.path != '/member/common-play-url':
            return httpx.Response(405, text='old route removed')
        assert request.headers['X-CSRF-TOKEN'] == 'page-token'
        assert request.headers['Cookie'] == 'provider_session=test-session'
        assert request.headers['X-Requested-With'] == 'XMLHttpRequest'
        assert request.content == b'id=bound-id&purpose=download'
        return httpx.Response(200, json={'code':code, 'msg':'需人工验证',
            'data':{'url':'https://kw-lw.kuwo.cn/a.mp3'} if code == 1 else {'reason':'verification_required'}})
    fixture_client(monkeypatch, respond)
    if code == 1:
        assert run(service._fangpi_get_audio_url('4886072')) == 'https://kw-lw.kuwo.cn/a.mp3'
    else:
        with pytest.raises(ValueError):
            run(service._fangpi_get_audio_url('4886072'))
    assert len(calls) == 2


def test_search_keeps_title_dashes_and_encodes_url_characters(monkeypatch):
    seen=[]
    def respond(request):
        if request.method == 'POST':
            return httpx.Response(200, json={'code':1})
        seen.append(request.url.raw_path)
        return httpx.Response(200, text='<a href="/music/12" title="DJ Song - F#/ Mix - DJ COKE">song</a>')
    fixture_client(monkeypatch, respond)
    rows=run(service._fangpi_search('DJ Song - F#/ Mix'))
    assert seen == [b'/s/DJ%20Song%20-%20F%23%2F%20Mix']
    assert rows[0]['title']=='DJ Song - F#/ Mix'
    assert rows[0]['artist']=='DJ COKE'
