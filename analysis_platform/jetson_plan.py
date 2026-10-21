"""Verify NAS inputs and return a JSON-only device strategy from a fixed CLI.

No final mix WAV is rendered or copied. Raw source-window PCM is temporary,
private to this invocation, and removed after the JSON planner exits.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

import numpy as np
from metric_mix.prepare import validated_plan,source_assets,read_segment,sha,worker_version,local_bars

SCHEMA='harbeat.jetson-plan-input.v1'
STEMS=('master','bass','other','drums','vocals')
SR=44100
DEFAULT_NODE='/usr/local/bin/node'
MAX_RESULT_BYTES=1024*1024
HASH=re.compile(r'^[a-f0-9]{64}$')


def plan_runner_version():
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


def invoke_cli(command,payload):
    try:
        return subprocess.run(command,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
    except subprocess.CalledProcessError as error:
        # SSH captures the runner traceback into cloud-private diagnostics. A
        # CalledProcessError alone omits the Node cause from that traceback.
        raw=error.stderr or b''
        if isinstance(raw,str):raw=raw.encode(errors='replace')
        limit=8192;marker=b'\n[stderr truncated]\n'
        if len(raw)>limit:raw=raw[:2048]+marker+raw[-(limit-2048-len(marker)):]
        raise RuntimeError('Node planner exited '+str(error.returncode)+'; stderr:\n'+raw.decode(errors='replace')) from None


def write_pcm(path,source,start,duration):
    values=read_segment(source,start,duration)
    if values.shape!=(round(duration*SR),2) or not np.isfinite(values).all():
        raise ValueError('source PCM coverage or samples invalid')
    path.write_bytes(values.astype('<f4').tobytes())
    os.chmod(path,0o600)
    return {'path':str(path),'frames':len(values),'start':start,'duration':len(values)/SR}


def profile_proof(track,proof,execution_root):
    index=execution_root/'index.json'
    if not index.is_file() or index.stat().st_size>8*1024*1024:raise ValueError('execution profile index unavailable')
    value=json.loads(index.read_bytes())
    rows=value.get('tracks',[])
    if value.get('schema')!='harbeat.execution-library.v1' or not isinstance(rows,list) or len(rows)>5000:raise ValueError('execution profile index invalid')
    entries=[row for row in rows if row.get('trackId')==track['id']]
    if len(entries)!=1:raise ValueError('execution profile unavailable')
    entry=entries[0];identity={'trackId':track['id'],'runId':proof['runId'],'sourceSha256':proof['assets']['master']['sha256'],
                              'reportSha256':proof['reportSha256'],'manifestSha256':proof['manifestSha256']}
    if any(entry.get(key)!=item for key,item in identity.items()):raise ValueError('execution profile index source mismatch')
    checksum=entry.get('profile',{}).get('sha256','')
    if not HASH.fullmatch(str(checksum)):raise ValueError('execution profile fingerprint invalid')
    path=execution_root/'profiles'/(checksum+'.json')
    if not path.is_file() or path.stat().st_size>16*1024*1024 or sha(path)!=checksum:raise ValueError('execution profile fingerprint mismatch')
    profile=json.loads(path.read_bytes())
    if profile.get('schema')!='harbeat.execution-profile.v1' or any(profile.get(key)!=item for key,item in identity.items()):raise ValueError('execution profile source mismatch')
    stem_hashes={stem:asset['sha256'] for stem,asset in proof['assets'].items() if stem!='master'}
    if any(profile.get('stems',{}).get(stem,{}).get('sourceSha256')!=stem_sha for stem,stem_sha in stem_hashes.items()):raise ValueError('execution profile stem mismatch')
    return {'trackId':track['id'],'runId':proof['runId'],'masterSha256':proof['assets']['master']['sha256'],
            'reportSha256':proof['reportSha256'],'vocalSha256':proof['assets']['vocals']['sha256'],
            'manifestSha256':proof['manifestSha256'],'profileSha256':checksum,'stemSha256':stem_hashes}


def pcm_window(folder,label,sources,start,duration):
    files={}
    for stem in STEMS:
        if stem in sources:
            path=folder/(label+'-'+stem+'.f32le')
            write_pcm(path,sources[stem],start,duration);files[stem]=str(path)
    return {'start':start,'duration':duration,'files':files}


def cli_input(job,a,b,plan,source_a,source_b,proof_a,proof_b,folder,*,include_body=False):
    padding=.35 if abs(plan['rate']-1)>1e-10 else 0.
    data={'schema':SCHEMA,'jobId':job['jobId'],'plannerSha256':job['plannerSha256'],'sampleRate':SR,'channels':2,
          'a':a,'b':b,'request':{'windowId':job['windowId'],'start':job['start']},'plan':plan,
          'sourceProof':{'a':proof_a,'b':proof_b},
          'pcm':{'a':pcm_window(folder,'a',source_a,plan['start'],plan['duration']),
                 'b':pcm_window(folder,'b',source_b,plan['bStart'],(plan['duration']+.008)*plan['rate']+padding)}}
    if include_body:
        body_path=folder/'b-body.f32le'
        write_pcm(body_path,source_b['master'],plan['bEnd'],8.)
        data['pcm']['body']={'start':plan['bEnd'],'duration':8.,'files':{'master':str(body_path)}}
    else:
        # Experimental drum prefixes are prepared only for this audition round.
        return data
    rows=a['alignment']['bars'];index=next((i for i,row in enumerate(rows) if abs(row['start']-plan['start'])<=.065),None)
    if index is not None and index>=3:
        before=rows[index-3:index]
        lead=rows[index]['start']-before[0]['start'];b_start=plan['bStart']-lead*plan['rate']
        try:local_bars(a,plan['start']-lead,plan['start'],3)
        except ValueError:return data
        if b_start>=0 and all(abs(x['end']-y['start'])<=.001 for x,y in zip(before,before[1:])):
            data['prelude']={'leadSeconds':lead,'fadeInSeconds':before[0]['end']-before[0]['start'],
                             'holdSeconds':lead-(before[0]['end']-before[0]['start']),
                             'pcm':{'a':pcm_window(folder,'prelude-a',source_a,plan['start']-lead,lead+plan['duration']),
                                    'b':pcm_window(folder,'prelude-b',source_b,b_start,(lead+plan['duration']+.008)*plan['rate']+padding)}}
    return data


def prepare_plan(job,*,nas=pathlib.Path('/mnt/nas/harbeat/preprocess'),
                 reports=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'),
                 cli=None,node=None,execution_root=None,audition_output=None,audition_single_method=None):
    if audition_single_method is not None and (audition_output is None or audition_single_method not in ('bass','filter','yield','vocal')):
        raise ValueError('single-method override is restricted to an internal audition')
    if not isinstance(job,dict) or set(job)-{'a','b','windowId','start','codeVersion','runnerVersion','plannerSha256','jobId','executionBindings'}:
        raise ValueError('invalid fixed planning request')
    if job.get('codeVersion')!=worker_version() or job.get('runnerVersion')!=plan_runner_version():
        raise ValueError('planner worker version mismatch')
    if not HASH.fullmatch(str(job.get('plannerSha256',''))) or not HASH.fullmatch(str(job.get('jobId',''))):raise ValueError('planner engine or job version missing')
    a,b=job['a'],job['b']
    for track in (a,b):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',str(track.get('reportId',''))):raise ValueError('invalid report identifier')
    plan=validated_plan(a,b,job['windowId'],job['start'])
    cli=pathlib.Path(cli or os.environ.get('HARBEAT_PLAN_CLI','/home/mark/harbeat-device-execution/jetson-plan.cjs'))
    if not cli.is_file() or cli.stat().st_size>8*1024*1024 or sha(cli)!=job['plannerSha256']:
        raise ValueError('planner engine version mismatch')
    source_a,proof_a=source_assets(a,pathlib.Path(nas),pathlib.Path(reports))
    source_b,proof_b=source_assets(b,pathlib.Path(nas),pathlib.Path(reports))
    execution_root=pathlib.Path(execution_root or os.environ.get('HARBEAT_PLAN_EXECUTION_ROOT','/mnt/nas/harbeat/preprocess/device-execution-v1'))
    proof_a=profile_proof(a,proof_a,execution_root);proof_b=profile_proof(b,proof_b,execution_root)
    if job.get('executionBindings')!={'a':proof_a,'b':proof_b}:
        # Only an explicitly internal legacy audition can omit cloud bindings.
        # Production must match the profiles that keyed the cloud request.
        if audition_output is None or 'executionBindings' in job:
            raise ValueError('execution binding changed before planning')
    with tempfile.TemporaryDirectory(prefix='harbeat-json-plan-') as temp:
        data=cli_input(job,a,b,plan,source_a,source_b,proof_a,proof_b,pathlib.Path(temp),include_body=audition_output is not None)
        if audition_single_method is not None:data['auditionSingleMethod']=audition_single_method
        command=[node or os.environ.get('HARBEAT_PLAN_NODE',DEFAULT_NODE),str(cli)]
        if audition_output is not None:command+=['--audition-output',str(audition_output)]
        result=invoke_cli(command,json.dumps(data,separators=(',',':'),allow_nan=False).encode())
        if len(result.stdout)>MAX_RESULT_BYTES:raise ValueError('planner output too large')
        value=json.loads(result.stdout)
        if not isinstance(value,dict):raise ValueError('planner result is not an object')
        if value.get('schema')!='harbeat.jetson-mix-plan.v1' or value.get('id')!=job['jobId'] or value.get('algorithmSha256')!=job['plannerSha256'] or value.get('sourceProof')!={'a':proof_a,'b':proof_b}:raise ValueError('planner output identity mismatch')
        return value


def main():
    raw=sys.stdin.buffer.read(32*1024*1024+1)
    if len(raw)>32*1024*1024:raise ValueError('planning request too large')
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--audition-output',type=pathlib.Path)
    parser.add_argument('--audition-single-method',choices=('bass','filter','yield','vocal'));args=parser.parse_args()
    value=prepare_plan(json.loads(raw),audition_output=args.audition_output,audition_single_method=args.audition_single_method)
    encoded=json.dumps(value,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if len(encoded.encode())>MAX_RESULT_BYTES:raise ValueError('planning result too large')
    print(encoded)


if __name__=='__main__':main()
