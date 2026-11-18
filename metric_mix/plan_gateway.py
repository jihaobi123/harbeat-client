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
from analysis_platform.execution_cohort import execution_index
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
    timeline=job.get('stemTimelineVersion') in ('stem-timeline-v1','stem-timeline-v2')
    version='jetson-decision-v3' if job.get('stemTimelineVersion')=='stem-timeline-v2' else 'jetson-decision-v2' if timeline else 'jetson-decision-v1'
    if (not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'drumPrelude','stemArrangement'}
        or value.get('schema')!='harbeat.jetson-mix-plan.v1' or value.get('id')!=job['jobId'] or value.get('status')!='ready'
        or value.get('producer')!='jetson' or value.get('analysisVersion')!=version
        or ('stemArrangement' in value)!=timeline
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
    if timeline:validate_arrangement(value['stemArrangement'],expected['duration'],value['requiredStems'],calibrated=version=='jetson-decision-v3')
    public_tree(value)
    if len(json.dumps(value,separators=(',',':'),allow_nan=False).encode())>MAX_STATE_BYTES:raise ValueError('planner result too large')
    return value


def validate_arrangement(value,duration,required,calibrated=False):
    def numeric(n):return type(n) in (int,float) and math.isfinite(n)
    def fail():raise ValueError('planner stem timeline invalid')
    roles={'drums','bass','other','vocals'}
    if (not isinstance(value,dict) or value.get('schema')!='harbeat.stem-arrangement.v1'
        or value.get('method')!='stem-handover' or type(value.get('eligible')) is not bool
        or type(value.get('recommended')) is not bool or not isinstance(value.get('reason'),str)
        or not isinstance(value.get('requiredStems'),list)):fail()
    if not value['eligible']:
        if value['recommended'] or value.get('score') is not None or value.get('timeline') is not None or value.get('evidence') is not None or value['requiredStems']:fail()
        return
    if (not numeric(value.get('score')) or not 65<=value['score']<=100 or len(value['requiredStems'])!=4
        or set(value['requiredStems'])!=roles or not roles<=set(required)):fail()
    t=value.get('timeline',{})
    if not isinstance(t,dict) or t.get('schema')!='harbeat.stem-timeline.v1' or t.get('clock')!='transition-start' or t.get('duration')!=duration:fail()
    for side in ('a','b'):
        if not isinstance(t.get(side),dict) or set(t[side])!=roles:fail()
        for curve in t[side].values():
            if not isinstance(curve,list) or not 2<=len(curve)<=32:fail()
            previous=None
            for point in curve:
                if not isinstance(point,list) or len(point)!=2 or not all(numeric(x) for x in point) or not 0<=point[0]<=duration or not 0<=point[1]<=1:fail()
                if previous and (point[0]<=previous[0] or abs(point[1]-previous[1])/(point[0]-previous[0])>20.000001):fail()
                previous=point
            if curve[0]!=[0,int(side=='a')] or curve[-1]!=[duration,int(side=='b')]:fail()
    def at(curve,time):
        for a,b in zip(curve,curve[1:]):
            if a[0]<=time<=b[0]:return a[1]+(b[1]-a[1])*(time-a[0])/(b[0]-a[0])
        return curve[-1][1]
    for role in roles:
        for time in {point[0] for side in ('a','b') for point in t[side][role]}:
            if at(t['a'][role],time)+at(t['b'][role],time)>1.000001:fail()
    e=value.get('evidence',{})
    if not isinstance(e,dict):fail()
    for field in ('baseline','processed'):
        if not isinstance(e.get(field),dict) or any(not numeric(e[field].get(r)) or not 0<=e[field][r]<=1 for r in roles):fail()
    h=e.get('headroom',{})
    if (e['processed']['vocals']>.01 or not numeric(e.get('improvement')) or not .08<=e['improvement']<=4
        or not isinstance(h,dict) or any(not numeric(h.get(k)) for k in ('peak','baselinePeak','riseDb'))
        or not 0<=h['peak']<=.95 or h['baselinePeak']<0 or h['riseDb']>3 or h.get('eqApplied') is not True or h.get('outputScale')!=.76):fail()
    reconstruction=e.get('reconstruction')
    if not isinstance(reconstruction,dict):fail()
    for side in ('a','b'):
        r=reconstruction.get(side)
        if not isinstance(r,dict):fail()
        for x in (r,r.get('boundary')):
            if (not isinstance(x,dict) or not numeric(x.get('errorRatio')) or not 0<=x['errorRatio']<=.25
                or not numeric(x.get('levelDeltaDb')) or abs(x['levelDeltaDb'])>1.5):fail()

    if calibrated:
        gains=value.get('sourceGains',{});q=e.get('sourceCalibration',{})
        if (not isinstance(gains,dict) or set(gains)!={'a','b'} or not isinstance(q,dict) or q.get('mode')!='common-linear-gain-v1'
            or not isinstance(q.get('gains'),dict) or not isinstance(q.get('rawReconstruction'),dict)):fail()
        for side in ('a','b'):
            raw=q.get('rawReconstruction',{}).get(side,{})
            if (not numeric(gains[side]) or not .5<=gains[side]<=2 or q.get('gains',{}).get(side)!=gains[side]
                or not isinstance(raw,dict) or not numeric(raw.get('errorRatio')) or not numeric(raw.get('levelDeltaDb'))):fail()
    elif 'sourceGains' in value or 'sourceCalibration' in e:fail()
    c=e.get('compatibility',{})
    if (not isinstance(c,dict) or c.get('pass') is not True or not numeric(c.get('pitchedRisk'))
        or not 0<=c['pitchedRisk']<=1 or c.get('maximumPitchedRisk')!=.35
        or not numeric(c.get('drumOverlapSeconds')) or not 0<=c['drumOverlapSeconds']<=duration+.001
        or not numeric(c.get('drumOverlapLimit')) or not 0<c['drumOverlapLimit']<=2
        or c.get('drumEvidence') not in ('observed','limited','not-overlapping')):fail()
    if (any(not numeric(c.get(k)) or not 0<=c[k]<=duration+.001 for k in ('pitchedOverlapSeconds','incompatiblePitchedSeconds'))
        or c['incompatiblePitchedSeconds']>c['pitchedOverlapSeconds']+.001
        or c['incompatiblePitchedSeconds']>c['drumOverlapLimit']):fail()
    if c['drumEvidence']=='observed':
        if (not numeric(c.get('drumDensityRatio')) or c['drumDensityRatio']<1
            or not numeric(c.get('drumOnsetAgreement')) or not 0<=c['drumOnsetAgreement']<=1):fail()
    elif c.get('drumDensityRatio') is not None or c.get('drumOnsetAgreement') is not None:fail()
    if c['drumOverlapSeconds']>c['drumOverlapLimit'] and (c['drumEvidence']!='observed' or c['drumDensityRatio']>2.5 or c['drumOnsetAgreement']<.5):fail()


class PlanService:
    def __init__(self,root,origin,trusted_request,*,planner_sha256=None,executor=None,cohort=None):
        self.root=pathlib.Path(root);self.origin=origin;self.trusted_request=trusted_request
        self.planner_sha256=planner_sha256 if planner_sha256 is not None else os.environ.get('HARBEAT_PLAN_ENGINE_SHA256','')
        self.executor=executor or concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.slots=threading.BoundedSemaphore(3);self.lock=threading.Lock();self.active=set()
        self.cohort=cohort

    def path(self,identity):return self.root/'state'/(identity+'.json')
    def job_path(self,identity):return self.root/'private'/(identity+'.job.json')

    def execution_bindings(self,tracks):
        # Bind the job identity to the currently published execution profiles,
        # even when the master/report did not change during republication.
        root=pathlib.Path(os.environ.get('HARBEAT_PLAN_CLOUD_EXECUTION_ROOT','/srv/harbeat-listen/execution-current'))
        rows=execution_index(root)['tracks']
        cohort=self.cohort() if self.cohort is not None else None
        supplemental=execution_index(cohort.execution)['tracks'] if cohort and any(
            track['id'] in cohort.tracks for track in tracks.values()) else []
        bindings={}
        for side,track in tracks.items():
            entries=[row for row in rows if row.get('trackId')==track['id']]
            source_root=root
            if cohort and track['id'] in cohort.tracks and not any(row.get('assetsReady') for row in entries):
                entries=[row for row in supplemental if row.get('trackId')==track['id'] and row.get('assetsReady') is True]
                source_root=cohort.execution
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
            bindings[side]=profile_proof(track,proof,source_root)
        return bindings

    def job(self,data):
        if not isinstance(data,dict):raise ValueError('invalid planning request')
        request=dict(data);timeline=request.pop('stemTimelineVersion',None)
        if 'stemTimelineVersion' in data and timeline not in ('stem-timeline-v1','stem-timeline-v2'):raise ValueError('unsupported stem timeline version')
        base=self.trusted_request(request);base.pop('jobId',None)
        if timeline is not None:base['stemTimelineVersion']=timeline
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
            current=self.job({'from':job['a']['id'],'to':job['b']['id'],'windowId':job['windowId'],'start':job['start'],**({'stemTimelineVersion':job['stemTimelineVersion']} if 'stemTimelineVersion' in job else {})})
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
                current=service.job({'from':job['a']['id'],'to':job['b']['id'],'windowId':job['windowId'],'start':job['start'],**({'stemTimelineVersion':job['stemTimelineVersion']} if 'stemTimelineVersion' in job else {})})
                if current['jobId']!=identity:raise ValueError('source changed after planning')
            elif (set(value)!={'id','status','message','createdAt'} or value.get('id')!=identity
                  or value.get('status') not in ('queued','running','failed')):raise ValueError('invalid planning state')
        except (ValueError,TypeError,KeyError,OSError):raise HTTPException(404,'策略记录已过期，请重新准备')
        return value
