"""Durable cloud queue -> detached Jetson job -> incremental cloud publication."""
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from . import sources

HOST = os.environ.get('LISTEN_JETSON_HOST', 'mark@100.87.142.21')
REMOTE = '/home/mark/harbeat-listen-imports'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', HOST]


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=kwargs.pop('timeout', 120), **kwargs)


def remote(args):
    return command(SSH+[shlex.join(args)])


def remote_finished(state, has_result):
    if has_result:
        return True
    if state not in ('active','activating','reloading'):
        raise ValueError('Jetson 分析任务已中断，请重试；已完成的结果会复用。')
    return False


def process(jobs, job):
    from .publish import publish, existing_track
    payload = job['payload']
    folder = jobs.root/'work'/job['id']
    folder.mkdir(parents=True, exist_ok=True)
    def update(status, message):
        jobs.update(job['id'], status=status, message=message)
    update('transferring', '正在核对音乐文件')
    if payload['kind'] == 'download':
        source = jobs.root/'uploads'/(job['id']+'.mp3')
        if not source.exists():
            update('downloading', '正在下载所选音源')
            asyncio.run(sources.download(payload['candidate'], source))
    else:
        source = Path(payload['path'])
    sha = sources.sha256(source)
    if payload.get('sha256') and sha != payload['sha256']:
        raise ValueError('上传文件核验失败，请重新上传。')
    existing = existing_track(sha)
    if existing:
        jobs.update(job['id'], status='ready' if existing['mixStatus']=='ready' else 'ready_playback', track_id=existing['id'], message='这首音乐已经在实时曲库中，已复用现有分析。')
        source.unlink(missing_ok=True)
        return
    payload = {**payload, 'sha256': sha}
    (folder/'input.json').write_text(json.dumps(payload, ensure_ascii=False))
    target = REMOTE+'/jobs/'+job['id']
    update('transferring', '正在把音乐发送到 Jetson')
    remote(['mkdir', '-p', target])
    command(['rsync', '-a', '--protect-args', '-e', 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes',
             str(source), HOST+':'+target+'/audio'], timeout=600)
    command(['rsync', '-a', '--protect-args', '-e', 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes',
             str(folder/'input.json'), HOST+':'+target+'/input.json'])
    # Systemd owns the work, so closing the page or restarting the cloud service
    # does not interrupt GPU processing. Restarted workers reconnect to this unit.
    unit = 'harbeat-listen-import-'+job['id']
    state = remote(['systemctl', '--user', 'show', unit, '--property=ActiveState', '--value']).stdout.strip()
    result_exists = subprocess.run(SSH+[shlex.join(['test', '-s', target+'/result.json'])], capture_output=True, timeout=30).returncode == 0
    if state not in ('active', 'activating') and not result_exists:
        remote(['rm', '-f', target+'/status.json'])
        subprocess.run(SSH+[shlex.join(['systemctl', '--user', 'reset-failed', unit])], capture_output=True, timeout=30)
        remote(['systemd-run', '--user', '--collect', '--unit='+unit,
                '--property=EnvironmentFile=/home/mark/.config/harbeat-analysis.env',
                '--property=WorkingDirectory='+REMOTE+'/code', '--property=CPUQuota=200%',
                '--property=MemoryMax=20G', '--property=RuntimeMaxSec=32400',
                '/home/mark/harbeat-analysis-venv/bin/python', '-m', 'listen_imports.jetson', target])
    update('analyzing', 'Jetson 正在处理，关闭页面后任务仍会继续')
    deadline = time.monotonic()+33000
    while not result_exists:
        if time.monotonic() > deadline:
            raise ValueError('Jetson 处理超时，请在任务列表中重试。')
        r = subprocess.run(SSH+[shlex.join(['cat', target+'/status.json'])], capture_output=True, text=True, timeout=40)
        if r.returncode == 0:
            status = json.loads(r.stdout)
            if status['stage'] == 'prepared':
                break
            if status['stage'] == 'failed':
                raise ValueError(status['message'])
            update('analyzing', status['message'])
        state = remote(['systemctl','--user','show',unit,'--property=ActiveState','--value']).stdout.strip()
        # A killed process cannot update its own status.json. Check the owner
        # unit too, rather than monopolizing the single queue until timeout.
        if state not in ('active','activating','reloading'):
            exists = subprocess.run(SSH+[shlex.join(['test','-s',target+'/result.json'])],capture_output=True,timeout=30).returncode == 0
            if remote_finished(state, exists):
                break
        time.sleep(8)
    command(['rsync', '-a', '--protect-args', '--exclude=audio', '--exclude=normalized.flac', '--exclude=*.log',
             '-e', 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes', HOST+':'+target+'/', str(folder)+'/'], timeout=600)
    result = json.loads((folder/'result.json').read_text())
    if result['item']['input_sha256'] != sha:
        raise ValueError('Jetson 返回的歌曲与上传文件不一致。')
    update('publishing', '分析完成，正在准备与现有曲库的衔接素材')
    track = publish(result, folder/'prepared', lambda message: update('publishing', message))
    jobs.update(job['id'], status='ready' if track['mixStatus']=='ready' else 'ready_playback', track_id=track['id'],
                message='已加入实时曲库，可以选择播放。' if track['mixStatus']=='ready' else '已加入曲库，可单独播放；当前分析未通过混音质量检查。')
    source.unlink(missing_ok=True)
    (folder/'audio').unlink(missing_ok=True)


def work_loop(jobs, stop):
    # An extra process must never render or activate a competing library release.
    import fcntl
    with (jobs.root/'worker.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logging.error('listen import worker already running')
            return
        while not stop.is_set():
            job = jobs.claim()
            if not job:
                stop.wait(2)
                continue
            try:
                process(jobs, job)
            except Exception as exc:
                logging.exception('import failed job=%s', job['id'])
                message = str(exc) if isinstance(exc, ValueError) else '处理暂未完成，请重试；详细原因已记录在服务器日志。'
                jobs.update(job['id'], status='failed', message=message[:350])
