#!/usr/bin/env python3
"""Render on ECS local disk; fetch only the current sources, then release copies."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.build_continuous_library import Renderer,atomic_json,build_track,file_sha,library_index
from analysis_platform.media import MediaRegistry
from analysis_platform.store import Store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--jobs',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    data=json.loads(args.jobs.read_text())
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'scratch').mkdir(exist_ok=True)
    registry=MediaRegistry(Store(args.store),[args.out.parent])
    renderer=Renderer(args.out,registry,batch=24)
    all_tracks=[job['track'] for job in data['jobs']]
    completed={};timings=[];failures={};started=time.monotonic()
    version=file_sha(Path(__file__).parent/'build_continuous_library.py')

    def run(job):
        original=job['track'];track=copy.deepcopy(original)
        identity=hashlib.sha256((version+json.dumps(original,sort_keys=True)).encode()).hexdigest()
        detail=args.out/'details'/(track['id']+'.json')
        if detail.is_file():
            cached=json.loads(detail.read_text())
            if cached.get('cloudPreparationId')==identity:
                return cached['track'],dict(id=track['id'],reusedComplete=True,seconds=0)
        if shutil.disk_usage(args.out).free<5*1024**3:
            raise ValueError('cloud disk reserve reached; expand storage before continuing')
        source=Path(job['source'])
        if not source.is_relative_to('/mnt/nas/harbeat/preprocess') or '..' in source.parts:
            raise ValueError('source outside the published music root')
        with tempfile.TemporaryDirectory(dir=args.out/'scratch',prefix='source-') as temp:
            local=Path(temp)/source.name
            subprocess.run(['rsync','-a','--protect-args','-e',
                            'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes',
                            'mark@100.87.142.21:'+str(source),str(local)],check=True,timeout=600)
            if file_sha(local)!=track['provenance']['masterSha256']:
                raise ValueError('downloaded master checksum mismatch')
            track,timing=build_track(track,local,all_tracks,renderer,args.out)
        atomic_json(detail,dict(track=track,cloudPreparationId=identity),compressed=True)
        return track,timing

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures={executor.submit(run,job):job for job in data['jobs']}
        for future in as_completed(futures):
            job=futures[future]
            try:
                track,timing=future.result();completed[track['id']]=track;timings.append(timing)
                print('BUILT',json.dumps({**timing,'title':track['title'],'completed':len(completed),'mixStatus':track['mixStatus']},ensure_ascii=False),flush=True)
            except Exception as error:
                failures[job['track']['id']]=str(error)
                print('FAILED',job['track']['id'],str(error),flush=True)
            atomic_json(args.out/'progress.json',dict(completed=len(completed),total=len(data['jobs']),
                failures=failures,built=renderer.built,seconds=time.monotonic()-started))
    index=library_index(data['items'],completed,failures,'/listen/details/',prepared={t['id']:t for t in all_tracks})
    audit={**data['audit'],'coverage':index['coverage'],'mixReady':index['coverage']['mixReady'],
           'failures':failures,'timings':timings,'cloudLocal':True,'renderSeconds':time.monotonic()-started}
    atomic_json(args.out/'library-index.json',index,compressed=True)
    atomic_json(args.out/'corpus-audit.json',audit)
    print('DONE',json.dumps(index['coverage'],ensure_ascii=False),flush=True)
    if failures:raise SystemExit(2)


if __name__=='__main__':main()
