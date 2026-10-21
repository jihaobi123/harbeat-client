"""A separately bounded JSON strategy queue; legacy WAV jobs stay unchanged."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import threading
import time
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse
from analysis_platform.jetson_plan import plan_runner_version,profile_proof
from .prepare import validated_plan,worker_version

HASH=re.compile(r'^[a-f0-9]{64}$')
MAX_STATE_BYTES=1024*1024


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.part')
    temp.write_text(json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False))
    os.replace(temp,path)


def public_tree(value,depth=0):
    if depth>32:raise ValueError('planner result nesting exceeds budget')
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('path','files','pcm','stderr','stdout','command','privatePath'):raise ValueError('private planning field in result')
            public_tree(item,depth+1)
    elif isinstance(value,list):
        if len(value)>20000:raise ValueError('planner result array exceeds budget')
        for item in value:public_tree(item,depth+1)
    elif isinstance(value,str):
        if len(value)>4096 or any(prefix in value for prefix in ('/mnt/','/home/','/tmp/','/private/','file://','\\Users\\')):raise ValueError('private path in planning result')
    elif isinstance(value,(int,float)):
        if not math.isfinite(value):raise ValueError('nonfinite planning result')
    elif value is not None:raise ValueError('invalid planning result value')


def validate_result(value,job):
    required={'schema','id','status','producer','analysisVersion','algorithmSha256','plan','sourceProof',
              'controls','metrics','decision','eq','restore','requiredStems','analysisSha256'}
    if (not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'drumPrelude'}
        or value.get('schema')!='harbeat.jetson-mix-plan.v1' or value.get('id')!=job['jobId'] or value.get('status')!='ready'
        or value.get('producer')!='jetson' or value.get('analysisVersion')!='jetson-decision-v1'
        or value.get('algorithmSha256')!=job['plannerSha256'] or not HASH.fullmatch(str(value.get('analysisSha256','')))):
        raise ValueError('planner result version mismatch')
    expected=validated_plan(job['a'],job['b'],job['windowId'],job['start'])
    plan=value.get('plan',{})
    if not isinstance(plan,dict) or any(plan.get(k)!=expected[k] for k in ('from','to','windowId')):raise ValueError('planner result cue mismatch')
    for key in ('start','end','duration','rate','bStart','bEnd'):
        number=plan.get(key)
        if type(number) not in (int,float) or not math.isfinite(number) or abs(number-expected[key])>.00001:raise ValueError('planner result geometry mismatch')
    if not isinstance(value.get('sourceProof'),dict):raise ValueError('planner source proof missing')
    if value['sourceProof']!=job.get('executionBindings'):raise ValueError('planner execution profile changed')
    for side in ('a','b'):
        track=job[side];proof=value['sourceProof'].get(side,{})
        if not isinstance(proof,dict) or not isinstance(proof.get('stemSha256'),dict):raise ValueError('planner source proof invalid')
        provenance=track['provenance']
        if (proof.get('trackId')!=track['id'] or proof.get('runId')!=provenance['runId']
            or any(proof.get(key)!=provenance[key] for key in ('masterSha256','reportSha256','vocalSha256'))
            or any(not HASH.fullmatch(str(proof.get(key,''))) for key in ('manifestSha256','profileSha256'))
            or any(not HASH.fullmatch(str(proof.get('stemSha256',{}).get(stem,''))) for stem in ('drums','bass','other','vocals'))
            or proof['stemSha256']['vocals']!=provenance['vocalSha256']):raise ValueError('planner result source mismatch')
    controls=value.get('controls',{})
    if not isinstance(controls,dict) or controls.get('duration')!=expected['duration']:raise ValueError('planner controls missing')
    if (not isinstance(value.get('decision'),dict) or not isinstance(value['decision'].get('methods'),dict)
        or not isinstance(value['decision']['methods'].get('original'),dict) or not isinstance(value.get('metrics'),dict)
        or not isinstance(value.get('eq'),dict) or not isinstance(value.get('requiredStems'),list)
        or any(stem not in ('master','bass','other','drums','vocals') for stem in value['requiredStems'])
        or value['decision'].get('methods',{}).get('original',{}).get('eligible') is not True):raise ValueError('planner strategy missing approved fallback')
    if type(value['restore']) not in (int,float) or not expected['start']<=value['restore']<=expected['end']:raise ValueError('planner restore out of bounds')
    public_tree(value)
    if len(json.dumps(value,separators=(',',':'),allow_nan=False).encode())>MAX_STATE_BYTES:raise ValueError('planner result too large')
    return value


class PlanService:
    def __init__(self,root,origin,trusted_request,*,planner_sha256=None,executor=None):
        self.root=pathlib.Path(root);self.origin=origin;self.trusted_request=trusted_request
        self.planner_sha256=planner_sha256 if planner_sha256 is not None else os.environ.get('HARBEAT_PLAN_ENGINE_SHA256','')
        self.executor=executor or concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.slots=threading.BoundedSemaphore(3);self.lock=threading.Lock();self.active=set()

    def path(self,identity):return self.root/'state'/(identity+'.json')
    def job_path(self,identity):return self.root/'private'/(identity+'.job.json')

    def execution_bindings(self,tracks):
        # Bind the job identity to the currently published execution profiles,
        # even when the master/report did not change during republication.
        root=pathlib.Path(os.environ.get('HARBEAT_PLAN_CLOUD_EXECUTION_ROOT','/srv/harbeat-listen/execution-current'))
        index=root/'index.json'
        if not index.is_file() or index.stat().st_size>8*1024*1024:raise ValueError('execution index unavailable')
        value=json.loads(index.read_bytes())
        rows=value.get('tracks',[]) if isinstance(value,dict) else []
        if (not isinstance(value,dict) or value.get('schema')!='harbeat.execution-library.v1'
            or not isinstance(rows,list) or len(rows)>5000 or any(not isinstance(row,dict) for row in rows)):
            raise ValueError('execution index invalid')
        bindings={}
        for side,track in tracks.items():
            entries=[row for row in rows if row.get('trackId')==track['id']]
            if len(entries)!=1:raise ValueError('execution profile unavailable')
            entry=entries[0];provenance=track['provenance'];stems=entry.get('stemSha256',{})
            if (entry.get('runId')!=provenance['runId'] or entry.get('sourceSha256')!=provenance['masterSha256']
                or entry.get('reportSha256')!=provenance['reportSha256'] or not isinstance(stems,dict)
                or stems.get('vocals')!=provenance['vocalSha256']
                or not HASH.fullmatch(str(entry.get('manifestSha256','')))
                or any(not HASH.fullmatch(str(stems.get(stem,''))) for stem in ('drums','bass','other','vocals'))):
                raise ValueError('execution source mismatch')
            proof={'runId':entry['runId'],'reportSha256':entry['reportSha256'],'manifestSha256':entry['manifestSha256'],
                'assets':{'master':{'sha256':entry['sourceSha256']},
                    **{stem:{'sha256':stems[stem]} for stem in ('drums','bass','other','vocals')}}}
            bindings[side]=profile_proof(track,proof,root)
        return bindings

    def job(self,data):
        base=self.trusted_request(data);base.pop('jobId',None)
        base.update(runnerVersion=plan_runner_version(),plannerSha256=self.planner_sha256,
                    executionBindings=self.execution_bindings({side:base[side] for side in ('a','b')}))
        raw=json.dumps(base,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if len(raw)>32*1024*1024:raise ValueError('trusted source metadata exceeds budget')
        base['jobId']=hashlib.sha256(raw).hexdigest()
        return base

    def remote(self,job):
        remote=os.environ.get('HARBEAT_PLAN_REMOTE','mark@100.87.142.21')
        code=os.environ.get('HARBEAT_PLAN_REMOTE_CODE','/home/mark/harbeat-metric-mix')
        python=os.environ.get('HARBEAT_PLAN_REMOTE_PY','/home/mark/harbeat-analysis-venv/bin/python')
        if (not re.fullmatch(r'[A-Za-z0-9_.@:-]+',remote) or remote.startswith('-')
            or any(not re.fullmatch(r'/[A-Za-z0-9_./-]+',path) for path in (code,python))):raise ValueError('invalid fixed remote configuration')
        command=f'cd {code} && {python} -m analysis_platform.jetson_plan'
        result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',remote,command],
                              input=json.dumps(job,separators=(',',':'),allow_nan=False).encode(),
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=300)
        if len(result.stdout)>MAX_STATE_BYTES:raise ValueError('remote planning result too large')
        return json.loads(result.stdout)

    def cleanup(self,reserve=0):
        folder=self.root/'state';folder.mkdir(parents=True,exist_ok=True)
        paths=sorted((p for p in folder.glob('*.json') if HASH.fullmatch(p.stem)),key=lambda p:p.stat().st_mtime)
        removable=[p for p in paths if p.stem not in self.active]
        def usage():
            return sum(file.stat().st_size for path in paths for file in (path,self.job_path(path.stem),self.root/'private'/(path.stem+'.txt')) if file.is_file())
        while (len(paths)>512 or usage()+reserve>128*1024*1024) and removable:
            victim=removable.pop(0);victim.unlink(missing_ok=True);paths.remove(victim)
            (self.root/'private'/(victim.stem+'.txt')).unlink(missing_ok=True)
            self.job_path(victim.stem).unlink(missing_ok=True)
        if usage()+reserve>128*1024*1024:raise ValueError('planning cache budget exceeded')

    def run(self,job):
        identity=job['jobId']
        try:
            atomic(self.path(identity),{'id':identity,'status':'running','message':'正在核验声部并计算设备执行方案','createdAt':time.time()})
            value=validate_result(self.remote(job),job)
            current=self.job({'from':job['a']['id'],'to':job['b']['id'],'windowId':job['windowId'],'start':job['start']})
            if current['jobId']!=identity:raise ValueError('source revision changed during planning')
            atomic(self.path(identity),value)
        except Exception as error:
            private=self.root/'private';private.mkdir(parents=True,exist_ok=True)
            path=private/(identity+'.txt')
            path.write_text((type(error).__name__+': '+str(error)+'\n'+getattr(error,'stderr',b'').decode(errors='replace'))[-12000:]);os.chmod(path,0o600)
            atomic(self.path(identity),{'id':identity,'status':'failed','message':'本次策略计算未完成；当前音乐继续播放，可稍后重试。','createdAt':time.time()})
        finally:
            with self.lock:self.active.discard(identity)
            self.slots.release()


def install_plan_routes(app,service):
    app.state.plan_service=service

    @app.post('/plans')
    async def create_plan(request:Request):
        if request.headers.get('origin')!=service.origin:raise HTTPException(403,'请从混音页面发起请求')
        raw=b''
        async for chunk in request.stream():
            if len(raw)+len(chunk)>8192:raise HTTPException(413,'请求过大')
            raw+=chunk
        if not HASH.fullmatch(service.planner_sha256):raise HTTPException(503,'策略执行器尚未配置')
        try:job=service.job(json.loads(raw))
        except (ValueError,TypeError,KeyError,OSError):raise HTTPException(422,'曲目、接点或分析依据不符合当前规则')
        identity=job['jobId'];path=service.path(identity)
        with service.lock:
            if identity in service.active:return {'id':identity,'status':'running'}
            if path.is_file() and path.stat().st_size<=MAX_STATE_BYTES:
                try:
                    old=json.loads(path.read_text())
                    if old.get('status')=='ready':
                        validate_result(old,job)
                        return old
                except (ValueError,TypeError,KeyError,OSError):pass
            if not service.slots.acquire(False):raise HTTPException(429,'策略计算队列繁忙，请稍后重试')
            service.active.add(identity)
            try:
                service.cleanup(len(json.dumps(job,separators=(',',':')).encode())+MAX_STATE_BYTES)
                atomic(service.job_path(identity),job);os.chmod(service.job_path(identity),0o600)
                atomic(path,{'id':identity,'status':'queued','message':'已加入策略计算队列','createdAt':time.time()})
                service.executor.submit(service.run,job)
            except Exception:
                service.active.discard(identity);service.slots.release()
                raise HTTPException(503,'策略计算暂不可用')
        return JSONResponse({'id':identity,'status':'queued'},status_code=202)

    @app.get('/plans/{identity}')
    def get_plan(identity:str):
        if not HASH.fullmatch(identity):raise HTTPException(404,'未找到策略记录')
        path=service.path(identity)
        if not path.is_file() or path.stat().st_size>MAX_STATE_BYTES:raise HTTPException(404,'策略记录已过期，请重新准备')
        try:
            # Check pending state and ownership together. A restarted process has
            # no owner for the old queue entry; terminate it so polling consumers
            # can retry instead of waiting forever. The lock also prevents a
            # finishing live task from being mistaken for an orphan.
            with service.lock:
                value=json.loads(path.read_text())
                public_tree(value)
                if value.get('status') in ('queued','running'):
                    if set(value)!={'id','status','message','createdAt'} or value.get('id')!=identity:raise ValueError('invalid planning state')
                    if identity not in service.active:
                        value={'id':identity,'status':'failed','message':'策略计算已中断，请重新准备。','createdAt':time.time()}
                        atomic(path,value)
            if value.get('status')=='ready':
                private=service.job_path(identity)
                if not private.is_file() or private.stat().st_size>32*1024*1024:raise ValueError('missing planning provenance')
                job=json.loads(private.read_text())
                if job.get('plannerSha256')!=service.planner_sha256:raise ValueError('expired planning engine')
                validate_result(value,job)
                current=service.job({'from':job['a']['id'],'to':job['b']['id'],'windowId':job['windowId'],'start':job['start']})
                if current['jobId']!=identity:raise ValueError('source changed after planning')
            elif (set(value)!={'id','status','message','createdAt'} or value.get('id')!=identity
                  or value.get('status') not in ('queued','running','failed')):raise ValueError('invalid planning state')
        except (ValueError,TypeError,KeyError,OSError):raise HTTPException(404,'策略记录已过期，请重新准备')
        return value
