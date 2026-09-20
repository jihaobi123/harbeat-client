"""Loopback-only analysis workbench, without production DB/model imports."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import json
import os
import secrets
import socket
import shutil
from datetime import datetime, timezone
from pathlib import Path
import threading
from urllib.parse import urlparse
import uuid
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .report import build_report, canonical, validate_report
from .runner import run_modules, MODULES
from .store import Store
from .evaluation import compare_annotations
from .media import MediaRegistry
from .styles import evidence, review, save_review, ReviewConflict, audit, bind_review_identity
from .stems import measure_stems, cache_path

MAX_BYTES = 1024 * 1024 * 1024


def create_app(root=None, run_workers=True):
    store = Store(Path(root or os.getenv('ANALYSIS_LAB_DIR', 'data/analysis-platform')))
    media_roots = [p for p in os.getenv('ANALYSIS_MEDIA_ROOTS', '').split(os.pathsep) if p]
    registry = MediaRegistry(store, media_roots)
    relay_token = os.getenv('ANALYSIS_RELAY_TOKEN', '')
    public_origin = os.getenv('ANALYSIS_PUBLIC_ORIGIN', '').rstrip('/')
    if public_origin and (urlparse(public_origin).scheme != 'https' or len(relay_token) < 32):
        raise ValueError('public relay requires HTTPS origin and a token of at least 32 characters')
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='analysis-lab')
    slots = threading.BoundedSemaphore(8)

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title='HarBeat Analysis Lab', lifespan=lifespan)
    from .dj_routes import install
    install(app,store)

    @app.middleware('http')
    async def local_only(request, call_next):
        host = request.url.hostname
        origin = request.headers.get('origin')
        allowed_hosts = {'localhost', '127.0.0.1', '::1', 'testserver', urlparse(public_origin).hostname}
        if host not in allowed_hosts:
            return JSONResponse({'detail': 'local access only'}, status_code=403)
        if relay_token and not secrets.compare_digest(request.headers.get('x-analysis-relay-token', ''), relay_token):
            return JSONResponse({'detail': 'relay authentication required'}, status_code=401)
        origin_allowed = origin == public_origin if public_origin else (urlparse(origin or '').hostname in ('localhost', '127.0.0.1', '::1') and urlparse(origin or '').scheme in ('http', 'https'))
        if origin and not origin_allowed:
            return JSONResponse({'detail': 'origin rejected'}, status_code=403)
        try:
            if int(request.headers.get('content-length', 0)) > MAX_BYTES + 1024*1024:
                return JSONResponse({'detail': 'upload exceeds 1 GB'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': 'invalid content length'}, status_code=400)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'artifact not found'}, status_code=404)

    @app.get('/api/analysis-lab/reports')
    def reports():
        return store.reports()

    @app.get('/api/analysis-lab/status')
    def status():
        return {'execution_host': socket.gethostname(), 'modules': list(MODULES),
                'storage_available_bytes': shutil.disk_usage(store.root).free,
                'server_time': datetime.now(timezone.utc).isoformat()}

    coverage_cache={}
    coverage_lock=threading.Lock()

    @app.get('/api/analysis-lab/coverage')
    def coverage_status():
        path = store.root/'backfill-status.json'
        if not path.is_file():return {'status':'not_started'}
        data=json.loads(path.read_text())
        index=store.root/'report-index.json'
        stamp=index.stat().st_mtime_ns if index.is_file() else 0
        with coverage_lock:
            if coverage_cache.get('stamp')!=stamp:
                from .coverage import latest_reports, counts
                coverage_cache.update(stamp=stamp,coverage=counts(latest_reports(store)))
            data['coverage']=coverage_cache['coverage']
        return {**{k:v for k,v in data.items() if k not in ('attempts','source_hashes_before','errors')},'error_count':len(data.get('errors',[])),'errors':data.get('errors',[])[-100:]}

    @app.get('/api/analysis-lab/reports/{identifier}')
    def report(identifier: str):
        return store.get_report(identifier)

    @app.get('/api/analysis-lab/reports/{identifier}/styles')
    def style_evidence(identifier: str):
        r=store.get_report(identifier)
        return {**evidence(r), 'review':review(store,r)}

    @app.post('/api/analysis-lab/reports/{identifier}/style-review')
    async def style_review(identifier: str, request: Request):
        try:
            return save_review(store,store.get_report(identifier),await request.json())
        except ReviewConflict as exc:
            raise HTTPException(409,str(exc))

    @app.get('/api/analysis-lab/styles/audit')
    def style_audit():
        return audit(store)

    @app.get('/api/analysis-lab/media/{identifier}')
    def existing_media(identifier: str):
        return FileResponse(registry.resolve(identifier))

    @app.get('/api/analysis-lab/catalog')
    def catalog_status():
        path=store.root/'catalog-status.json'
        result=json.loads(path.read_text()) if path.is_file() else {'status':'not_configured'}
        progress=store.root/'catalog-measurement.json'
        if progress.is_file():result['measurement']=json.loads(progress.read_text())
        return result

    @app.post('/api/analysis-lab/reports/{identifier}/stems')
    def analyze_stems(identifier: str):
        report=store.get_report(identifier)
        assets=report['audio'].get('assets',{})
        if not any(assets.get(n,{}).get('id') for n in ('vocals','drums','bass','other')):
            raise ValueError('该报告没有关联真实分轨文件，请选择正式曲库或 NAS 预处理报告')
        if not slots.acquire(blocking=False):raise HTTPException(429,'analysis queue full')
        job={'id':uuid.uuid4().hex,'status':'queued','source_report_id':identifier,
             'created_at':datetime.now(timezone.utc).isoformat(),'modules':['stem_activity'],'kind':'stem_activity'}
        store.save_job(job)
        def execute_stems():
            started=time.monotonic()
            try:
                job.update(status='running',started_at=datetime.now(timezone.utc).isoformat(),module='stem_activity',module_results={})
                store.save_job(job)
                def progress(name):
                    job.update(detail='读取真实音轨：'+name,module_started_at=datetime.now(timezone.utc).isoformat());store.save_job(job)
                path=cache_path(store,assets)
                data=json.loads(path.read_text()) if path.is_file() else measure_stems(assets,registry,on_progress=progress)
                store.write(path,data)
                result=build_report({**report['documents'],'separated_stem_activity':data},report['extensions'],report['audio'])
                store.save_report(result)
                job.update(status='completed',report_id=result['id'],module=None,
                    module_results={'stem_activity':{'status':'ready','elapsed_ms':round((time.monotonic()-started)*1000)}})
            except Exception as exc:
                job.update(status='failed',reason=f'{type(exc).__name__}: {exc}')
            finally:
                job['finished_at']=datetime.now(timezone.utc).isoformat();store.save_job(job);slots.release()
        if run_workers:executor.submit(execute_stems)
        else:slots.release()
        return job

    @app.post('/api/analysis-lab/import')
    async def import_report(request: Request):
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError('expected report object')
        report = validate_report(data) if data.get('schema') == 'harbeat.analysis_report' else build_report(data.get('documents', {}), data.get('extensions'), data.get('audio'))
        store.save_report(report)
        return report

    @app.post('/api/analysis-lab/reports/{identifier}/evaluate')
    async def evaluate(identifier: str, request: Request):
        report=store.get_report(identifier)
        if report['audio'].get('hash_verification')=='source_declared':
            master=report['audio'].get('assets',{}).get('master',{})
            if not master.get('id') or registry.verify(master['id'])!=report['audio'].get('sha256'):
                raise ValueError('当前仅有来源声明的音频指纹；请上传对应原始音频核验后再进行标注评估')
        return compare_annotations(report, await request.json())

    def execute(job, report, audio_path, config):
        try:
            job.update(status='running', started_at=datetime.now(timezone.utc).isoformat(), module_results={}, detail='核验原曲指纹')
            store.save_job(job)
            master=job['audio'].get('assets',{}).get('master',{})
            from .embedding_cache import audio_sha256
            actual=registry.verify(master['id']) if master.get('id') else audio_sha256(audio_path)
            if job['audio'].get('sha256') and job['audio']['sha256'] != actual:
                raise ValueError('实际音频指纹与原报告不一致，不能绑定新分析结果')
            job['audio']={**job['audio'],'sha256':actual,'hash_verification':'verified'}
            bind_review_identity(store,report,job['audio'])
            job['detail']=None
            store.save_job(job)
            def progress(module):
                job['module'] = module
                job['module_started_at'] = datetime.now(timezone.utc).isoformat()
                store.save_job(job)
            def checkpoint(name, result):
                job['module_results'][name] = result
                store.save_job(job)
                print(json.dumps({'job_id': job['id'], 'module': name, 'status': result['status'], 'elapsed_ms': result['elapsed_ms']}, ensure_ascii=False), flush=True)
            from .extension_history import merge_latest
            report={**report,'extensions':merge_latest(store,report,{},job['audio'])}
            base={**report['timeline'], 'summary':report['summary'], 'extensions':report['extensions'], 'audio_sha256':actual}
            if 'dj_signals' in (job.get('modules') or MODULES):
                # Only server-registered media paths enter the worker request; callers
                # cannot supply arbitrary filesystem paths through this API.
                vocal=job['audio'].get('assets',{}).get('vocals',{})
                base['stem_assets']={'vocals':vocal}
                if vocal.get('id'):
                    try:
                        base['stem_assets']['vocals']={**vocal,'verified_sha256':registry.verify(vocal['id'])}
                        base['stem_paths']={'vocals':str(registry.resolve(vocal['id']))}
                    except (ValueError,FileNotFoundError,OSError) as exc:
                        base['stem_unavailable_reason']=str(exc)
            extensions = run_modules(audio_path, base, config, progress=progress, on_result=checkpoint, modules=job.get('modules'))
            result = build_report(report['documents'], merge_latest(store,report,extensions,job['audio']), job['audio'])
            store.save_report(result)
            job.update(status='completed', report_id=result['id'], module=None)
        except Exception as exc:
            job.update(status='failed', reason=f'{type(exc).__name__}: {exc}')
        finally:
            job['finished_at'] = datetime.now(timezone.utc).isoformat()
            store.save_job(job)
            slots.release()

    @app.post('/api/analysis-lab/jobs')
    async def create_job(report_id: str = Form(...), audio: UploadFile = File(...)):
        try:
            report = store.get_report(report_id)
        except (ValueError, FileNotFoundError):
            raise ValueError('请先导入已有分析结果')
        if not slots.acquire(blocking=False):
            raise HTTPException(429, 'analysis queue full')
        identifier = uuid.uuid4().hex
        temp = store.path('audio', identifier, '.upload')
        try:
            size, sha = 0, hashlib.sha256()
            with temp.open('wb') as out:
                while chunk := await audio.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, 'audio exceeds 1 GB')
                    sha.update(chunk)
                    out.write(chunk)
            import soundfile as sf
            try:
                info = sf.info(temp)
            except Exception:
                raise ValueError('音频无法解码，请使用 WAV、FLAC、OGG 或受支持的 MP3')
            if not .5 <= info.duration <= 7200:
                raise ValueError('audio duration must be between 0.5 seconds and 2 hours')
            audio_hash = sha.hexdigest()
            original = report.get('audio', {}).get('sha256')
            if original and original != audio_hash:
                raise ValueError('audio SHA256 differs from the source report')
            declared = report['summary'].get('duration') or 0
            if declared and abs(declared-info.duration) > 2:
                raise ValueError('音频时长与分析记录不一致，不能绑定到同一时间轴')
            target = store.path('audio', audio_hash, '.audio')
            if target.exists():
                temp.unlink()
            else:
                temp.replace(target)
            job = {'id': identifier, 'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'queued', 'source_report_id': report_id, 'modules':list(MODULES),
                   'audio': {**report.get('audio', {}), 'sha256': audio_hash, 'duration': info.duration, 'name': Path(audio.filename or 'audio').name,
                             'hash_verification':'verified',
                             'binding': 'hash_verified' if original else 'user_associated_duration_checked'}}
            store.save_job(job)
            config = {'models_dir': str(Path(os.getenv('ANALYSIS_MODELS_DIR', 'data/analysis-platform-models')).resolve()),
                      'model_python': os.getenv('ANALYSIS_MODEL_PYTHON'), 'chord_python': os.getenv('ANALYSIS_CHORD_PYTHON'), 'timeout_sec': int(os.getenv('ANALYSIS_MODULE_TIMEOUT', '300')),
                      'repeat_threshold': .5, 'instrument_threshold': .35, 'embedding_cache_dir':str(store.root/'embedding-cache')}
            if run_workers:
                executor.submit(execute, job, report, target, config)
            else:
                slots.release()
            return job
        except Exception:
            slots.release()
            temp.unlink(missing_ok=True)
            raise

    @app.post('/api/analysis-lab/reports/{identifier}/rerun')
    def rerun(identifier: str):
        return submit_modules(identifier,list(MODULES))

    @app.post('/api/analysis-lab/reports/{identifier}/modules/{module}')
    def run_module(identifier: str, module: str):
        if module not in MODULES: raise ValueError('unknown analysis module')
        return submit_modules(identifier,[module,'emotion_summary'] if module=='emotion' else [module])

    def submit_modules(identifier, modules):
        report = store.get_report(identifier)
        sha = report.get('audio', {}).get('sha256')
        master = report.get('audio',{}).get('assets',{}).get('master',{})
        if not sha and not master.get('id'):
            raise ValueError('报告未绑定音频，请先选择原曲')
        path = registry.resolve(master['id']) if master.get('id') else store.path('audio', sha, '.audio')
        if not path.is_file():
            raise ValueError('服务端尚未保存该音频，请先选择原曲')
        if not slots.acquire(blocking=False):
            raise HTTPException(429, 'analysis queue full')
        job = {'id': uuid.uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat(),
               'status': 'queued', 'source_report_id': identifier, 'audio': report['audio'], 'modules':modules}
        try:
            store.save_job(job)
            config = {'models_dir': str(Path(os.getenv('ANALYSIS_MODELS_DIR', 'data/analysis-platform-models')).resolve()),
                      'model_python': os.getenv('ANALYSIS_MODEL_PYTHON'), 'chord_python': os.getenv('ANALYSIS_CHORD_PYTHON'), 'timeout_sec': int(os.getenv('ANALYSIS_MODULE_TIMEOUT', '300')),
                      'repeat_threshold': .5, 'instrument_threshold': .35, 'embedding_cache_dir':str(store.root/'embedding-cache')}
            if run_workers:
                executor.submit(execute, job, report, path, config)
            else:
                slots.release()
            return job
        except Exception:
            slots.release()
            raise

    @app.get('/api/analysis-lab/jobs')
    def jobs():
        return store.jobs()

    @app.get('/api/analysis-lab/jobs/{identifier}')
    def get_job(identifier: str):
        return store.get_job(identifier)

    @app.get('/api/analysis-lab/audio/{identifier}')
    def audio(identifier: str):
        path = store.path('audio', identifier, '.audio')
        if not path.is_file():
            raise HTTPException(404, 'audio not found')
        return FileResponse(path)

    dist = Path(__file__).resolve().parent.parent / 'web' / 'dist'
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='lab-assets')
        app.mount('/analysis-lab-static', StaticFiles(directory=dist), name='lab-static')

    @app.get('/')
    def root_redirect():
        return RedirectResponse('/analysis-lab')

    @app.get('/analysis-lab')
    def index():
        if not (dist / 'index.html').is_file():
            raise HTTPException(503, 'Build web frontend first: npm run build')
        return FileResponse(dist / 'index.html')

    return app


if __name__ == '__main__':
    import uvicorn
    bind = os.getenv('ANALYSIS_LAB_BIND', '127.0.0.1')
    if bind not in ('127.0.0.1', '::1', 'localhost') and len(os.getenv('ANALYSIS_RELAY_TOKEN', '')) < 32:
        raise SystemExit('Non-loopback binding requires ANALYSIS_RELAY_TOKEN')
    uvicorn.run(create_app(), host=bind, port=int(os.getenv('ANALYSIS_LAB_PORT', '8765')))
