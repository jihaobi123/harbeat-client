"""Run on Jetson. Reuse installed GPU runtimes and the serialized extension queue."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from analysis_platform.catalog import import_manifest
from analysis_platform.media import MediaRegistry
from analysis_platform.report import build_report, canonical
from analysis_platform.store import Store
from scripts.build_continuous_library import atomic_json, file_sha, prepare_track


def normalize_source(source, folder):
    import soundfile as sf
    try:
        info = sf.info(source)
        if info.samplerate in (44100, 48000) and info.channels == 2:
            return source
    except Exception:
        pass
    normalized, checkpoint = folder/'normalized.flac', folder/'normalization.json'
    input_sha = file_sha(source)
    if normalized.exists() and checkpoint.exists():
        meta = json.loads(checkpoint.read_text())
        if meta.get('input_sha256') == input_sha and meta.get('output_sha256') == file_sha(normalized):
            return normalized
    temporary = folder/'normalized.part.flac'
    try:
        result = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(source)],
                                capture_output=True,text=True,check=True,timeout=30)
        duration = float(json.loads(result.stdout)['format']['duration'])
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-ar','44100','-ac','2',
                        '-c:a','flac',str(temporary)],check=True,timeout=600)
        info = sf.info(temporary)
        if info.samplerate != 44100 or info.channels != 2 or abs(info.duration-duration) > .5:
            raise ValueError('normalized audio duration or format differs')
        output_sha = file_sha(temporary)
        temporary.replace(normalized)
        atomic_json(checkpoint, {'input_sha256':input_sha,'output_sha256':output_sha})
        return normalized
    finally:
        temporary.unlink(missing_ok=True)


def process(folder):
    folder = Path(folder).resolve()
    payload = json.loads((folder/'input.json').read_text())
    source = folder / 'audio'
    sha = file_sha(source)
    if sha != payload['sha256']:
        raise ValueError('transferred audio checksum differs')
    track_id = 'track-'+sha[:20]
    # Normalize unsupported formats before analysis, preserving one time origin.
    source = normalize_source(source, folder)
    analysis_sha = file_sha(source)
    nas = Path('/mnt/nas/harbeat/preprocess')
    pointer_file = nas/'published/tracks'/track_id/'latest.json'
    def progress(stage, message):
        atomic_json(folder/'status.json', {'stage': stage, 'message': message, 'updated': time.time()})
    with (folder.parent/'analysis.lock').open('a+') as lock:
        progress('analyzing', '等待 Jetson 分析资源')
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (folder/'result.json').exists():
            return
        reusable = False
        if pointer_file.exists():
            pointer = json.loads(pointer_file.read_text())
            manifest = json.loads((nas/pointer['manifest_storage_key']).read_text())
            reusable = manifest['source'].get('input_sha256') == analysis_sha
        if not reusable:
            progress('analyzing', 'Jetson 正在分析节拍、段落并分离人声')
            args = ['/usr/local/bin/harbeat-same-style-preprocess', str(source), '--track-id', track_id,
                    '--title', payload['title'], '--root', str(nas), '--disable-adtof']
            if payload.get('artist'):
                args += ['--artist', payload['artist']]
            if payload.get('style'):
                args += ['--style-label', payload['style']]
            with (folder/'preprocess.log').open('a') as log:
                subprocess.run(args, stdout=log, stderr=log, check=True, timeout=21600)
        pointer = json.loads(pointer_file.read_text())
        path = nas/pointer['manifest_storage_key']
        manifest = json.loads(path.read_text())
        progress('analyzing', '正在核验或补齐人声时间轴')
        # Core publication and VAD publication are independent checkpoints. A
        # committed core run does not prove VAD succeeded. Retry the idempotent
        # VAD stage even when the expensive core analysis was reused.
        release = os.environ.get('LISTEN_PREPROCESS_RELEASE','/opt/harbeat/same-style-preprocess-current')
        env = {**os.environ, 'PYTHONPATH':release+'/vendor:/opt/harbeat/runtime/preprocess-packages:'+release}
        with (folder/'vocal-activity.log').open('a') as log:
            subprocess.run([os.environ.get('LISTEN_CORE_PYTHON','/opt/harbeat/current/venv/bin/python'), '-c',
                            'import sys; from pathlib import Path; from app.modules.library.vocal_activity import publish_vocal_activity; publish_vocal_activity(Path(sys.argv[1]),sys.argv[2])',
                            str(nas),pointer['manifest_storage_key']],env=env,stdout=log,stderr=log,check=True,timeout=1800,
                           cwd=release)
        store = Store(Path(os.environ.get('ANALYSIS_LAB_DIR', '/mnt/nas/harbeat/data/analysis-platform')))
        registry = MediaRegistry(store, [Path('/mnt/nas/harbeat')])
        progress('analyzing', '正在核验已有分析和人声文件')
        # The generic catalog importer scans every historical report. For one
        # new upload only matching, source-bound history is relevant.
        history = {}
        source_hashes = {manifest['source']['input_sha256'], manifest['assets']['master']['sha256']}
        for row in store.reports():
            old_sha = row.get('audio', {}).get('sha256')
            if old_sha in source_hashes and len(history.get(old_sha, [])) < 8:
                history.setdefault(old_sha, []).append(store.get_report(row['id']))
        report = import_manifest(path, nas, store, registry, pointer.get('manifest_sha256'), extension_history=history)
        master = report['audio']['assets']['master']
        audio = {**report['audio'], 'sha256': registry.verify(master['id']), 'hash_verification': 'verified'}
        report = build_report(report['documents'], report['extensions'], audio)
        store.save_report(report)
        import httpx
        headers = {'x-analysis-relay-token': os.environ.get('ANALYSIS_RELAY_TOKEN', '')}
        with httpx.Client(base_url='http://127.0.0.1:8765/api/analysis-lab', headers=headers, timeout=60, trust_env=False) as client:
            for module, label in [('dj_signals', '核验人声时间和接歌特征'), ('genre', '识别音乐风格')]:
                if report.get('extensions', {}).get(module, {}).get('status') == 'ready':
                    continue
                progress('analyzing', 'Jetson 正在'+label)
                checkpoint = folder/(module+'-job.json')
                if checkpoint.exists():
                    job = client.get('/jobs/'+json.loads(checkpoint.read_text())['id']).json()
                else:
                    job = None
                deadline = time.monotonic()+7200
                if not job or job.get('status') not in ('queued', 'running', 'completed'):
                    while True:
                        r = client.post(f'/reports/{report["id"]}/modules/{module}')
                        if r.status_code != 429:
                            r.raise_for_status()
                            job = r.json()
                            atomic_json(checkpoint, {'id': job['id']})
                            break
                        if time.monotonic() > deadline:
                            raise TimeoutError('Jetson analysis queue timeout')
                        time.sleep(10)
                while job.get('status') in ('queued', 'running'):
                    if time.monotonic() > deadline:
                        raise TimeoutError('Jetson feature analysis timeout')
                    time.sleep(5)
                    r = client.get('/jobs/'+job['id']); r.raise_for_status(); job = r.json()
                if job.get('status') != 'completed':
                    raise RuntimeError('Jetson extension failed: '+module)
                report = store.get_report(job['report_id'])
                if report.get('extensions', {}).get(module, {}).get('status') != 'ready':
                    raise RuntimeError('Jetson feature unavailable: '+module)
        item = dict(track_id=track_id, title=payload['title'], artist=payload.get('artist', ''), input_sha256=sha,
                    source_collection='我的导入', style_labels=[payload['style']] if payload.get('style') else [],
                    analysis_run_id=manifest['analysis_run_id'], manifest_storage_key=pointer['manifest_storage_key'],
                    status=manifest['status'])
        # Human labels are preserved; model genre remains a separate field.
        out = folder/'prepared'
        (out/'scratch').mkdir(parents=True, exist_ok=True)
        track, master_path = prepare_track(item, manifest, canonical(report), report, nas, out, '/listen/')
        atomic_json(folder/'result.json', {'item': item, 'job': {'track': track, 'source': str(master_path)}})
        progress('prepared', 'Jetson 分析完成，等待云端准备衔接素材')


if __name__ == '__main__':
    folder = Path(sys.argv[1])
    try:
        process(folder)
    except Exception as exc:
        atomic_json(folder/'status.json', {'stage': 'failed', 'message': 'Jetson 分析未完成，可重试；详情已保存在服务器日志。', 'updated': time.time()})
        raise
