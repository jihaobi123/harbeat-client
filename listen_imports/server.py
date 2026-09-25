"""Loopback API. Nginx authenticates ALL routes with the existing owner account."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
from pathlib import Path
import shutil
import threading
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import sources
from .store import Jobs

STYLES = ['EDM', 'KPOP', 'afro', 'amapiano', 'baile funk', 'boombap', 'breakbeat',
          'dancehall', 'disco', 'funk', 'grime', 'house', 'jazz hiphop', 'jersey club', 'trap']


class Playlist(BaseModel):
    url: str = Field(min_length=1, max_length=4000)


class Search(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default='', max_length=300)


class Download(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=16)
    style: str = Field(default='', max_length=80)


def create_app(root=None, run_worker=True, minimum_free=5*1024**3):
    root = Path(root or os.environ.get('LISTEN_IMPORT_ROOT', '/srv/harbeat-listen/imports'))
    jobs = Jobs(root)
    uploads = root / 'uploads'
    uploads.mkdir(exist_ok=True)
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            from .worker import work_loop
            jobs.recover()
            thread = threading.Thread(target=work_loop, args=(jobs, stop), daemon=True)
            thread.start()
        yield
        stop.set()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs
    external_slots = asyncio.Semaphore(2)

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        allowed = os.environ.get('LISTEN_PUBLIC_ORIGIN', 'https://8.136.120.255')
        if origin and origin != allowed:
            return JSONResponse({'detail': '请从 HarBeat 播放器打开曲库管理。'}, status_code=403)
        if request.method != 'GET' and request.headers.get('x-harbeat-import') != '1':
            return JSONResponse({'detail': '缺少导入请求标记。'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    def capacity():
        if shutil.disk_usage(root).free < minimum_free:
            raise HTTPException(507, '服务器音乐存储空间不足，请扩容后再导入。现有音乐仍可播放。')

    def checked_style(style):
        if style and style not in STYLES:
            raise ValueError('请从现有风格中选择，或留空自动分析。')
        return style

    @app.get('/api/listen-import/jobs')
    def listing():
        return {'jobs': jobs.list_public(), 'styles': STYLES, 'queue_limit': jobs.limit}

    @app.post('/api/listen-import/playlist')
    async def playlist(body: Playlist):
        try:
            async with external_slots:
                return await sources.parse_playlist(body.url)
        except ValueError:
            raise
        except Exception:
            raise HTTPException(502, '音乐平台暂时没有返回歌单，请稍后重试或上传本地音乐。')

    @app.post('/api/listen-import/search')
    async def search(body: Search):
        async with external_slots:
            rows = await sources.search(body.title.strip(), body.artist.strip())
        return {'candidates': [jobs.candidate(row) for row in rows]}

    @app.post('/api/listen-import/download')
    def download(body: Download):
        capacity()
        style = checked_style(body.style)
        candidates = [sources.validate_candidate(jobs.resolve_candidate(i)) for i in dict.fromkeys(body.candidate_ids)]
        submitted = jobs.submit_many([(f"provider:{c['source']}:{c['id']}",
                                       {'kind': 'download', 'candidate': c, 'title': c['title'],
                                        'artist': c.get('artist') or '', 'style': style}) for c in candidates])
        return {'jobs': [jobs.public(row['id']) for row in submitted]}

    @app.post('/api/listen-import/upload')
    async def upload(audio: UploadFile = File(...), style: str = Form(''), title: str = Form('')):
        capacity()
        style = checked_style(style)
        filename = Path((audio.filename or '').replace('\\', '/')).name
        suffix = Path(filename).suffix.lower()
        if suffix not in sources.SUFFIXES:
            raise ValueError('支持 MP3、WAV、FLAC、M4A、AAC、OGG、Opus 和 AIFF 音频。')
        temp = uploads / (uuid.uuid4().hex + suffix)
        try:
            size = 0
            with temp.open('wb') as target:
                while chunk := await audio.read(1024*1024):
                    size += len(chunk)
                    if size > sources.MAX_BYTES:
                        raise HTTPException(413, '每个音乐文件最大 100 MB。')
                    capacity()
                    target.write(chunk)
            await asyncio.to_thread(sources.validate_audio, temp)
            sha = await asyncio.to_thread(sources.sha256, temp)
            # The random path is retained only if this exact job owns it.
            row = jobs.submit('sha:'+sha, {'kind': 'upload', 'path': str(temp), 'sha256': sha,
                                          'title': (title.strip() or Path(filename).stem)[:300], 'artist': '', 'style': style})
            if json.loads(row['payload']).get('path') == str(temp):
                temp = None
            return jobs.public(row['id'])
        finally:
            await audio.close()
            if temp is not None:
                temp.unlink(missing_ok=True)

    @app.post('/api/listen-import/jobs/{identifier}/retry')
    def retry(identifier: str):
        capacity()
        return jobs.retry(identifier)

    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=8771, access_log=False)
