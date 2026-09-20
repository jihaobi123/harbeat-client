"""Resumable missing-only library backfill through the existing serialized API queue."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from datetime import datetime,timezone
import httpx
from .store import Store
from .coverage import latest_reports, missing_modules, counts

# First fill inexpensive existing measurements across the whole library. Existing
# model extensions then run before newly added harmony/dynamics and emotion summary.
PHASES=[('接歌预处理',['dj_signals']),
        ('已有基础特征',['core_features']),
        ('已有补充特征',['roughness','repeat','instruments','genre']),
        ('和弦与动态',['chords','measurements']),
        ('情绪曲线与摘要',['emotion','emotion_summary'])]


def now():return datetime.now(timezone.utc).isoformat()


def run(root,url,phases=None):
    store=Store(Path(root));state_path=store.root/'backfill-status.json'
    with (store.root/'backfill.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=json.loads(state_path.read_text()) if state_path.is_file() else {}
        resume=old.get('status') in ('running','interrupted')
        reports=latest_reports(store)
        baseline={str(r['audio'].get('catalog_track_id') or r['id']):r['source_hashes'] for r in reports}
        state=old if resume else {'started_at':now(),'attempts':[],'errors':[],'source_hashes_before':baseline}
        baseline=state['source_hashes_before']
        state.update(status='running',total=len(reports),coverage=counts(reports),execution='Jetson serialized analysis queue')
        headers={'x-analysis-relay-token':os.getenv('ANALYSIS_RELAY_TOKEN','')}
        with httpx.Client(base_url=url,headers=headers,trust_env=False,timeout=60) as client:
            def save():state['updated_at']=now();store.write(state_path,state)
            def wait_job(job_id):
                while True:
                    try:
                        response=client.get('/jobs/'+job_id);response.raise_for_status();job=response.json()
                        state.update(current_job=job_id,current_module=job.get('module'),module_started_at=job.get('module_started_at'))
                        save()
                        if job['status'] not in ('queued','running'):return job
                    except (httpx.TransportError,httpx.HTTPStatusError) as exc:
                        state['connection_note']=type(exc).__name__;save()
                    time.sleep(5)
            def finish(job,key):
                state.setdefault('attempts',[]).append(key)
                if job.get('status')!='completed':state['errors'].append({'key':key,'job_id':job['id'],'reason':job.get('reason',job['status'])})
                else:
                    for module,item in job.get('module_results',{}).items():
                        if item.get('status')!='ready':state['errors'].append({'key':key,'job_id':job['id'],'module':module,'reason':item.get('reason',item.get('status'))})
                        if module=='core_features':
                            for name,sub in (item.get('data') or {}).items():
                                if isinstance(sub,dict) and sub.get('status')=='failed':state['errors'].append({'key':key,'job_id':job['id'],'module':'core_features.'+name,'reason':sub.get('reason')})
                state.pop('current_job',None);state.pop('pending_key',None);state.pop('connection_note',None);save()
            try:
                save()
                if state.get('current_job') and state.get('pending_key'):
                    finish(wait_job(state['current_job']),state['pending_key'])
                for phase,modules in phases or PHASES:
                    state.update(phase=phase,phase_modules=modules,processed=0)
                    # Short singles first; long recordings remain eligible and use the existing timeout.
                    tracks=sorted(latest_reports(store),key=lambda r:r['summary'].get('duration') or 0)
                    for index,original in enumerate(tracks):
                        track_id=original['audio'].get('catalog_track_id')
                        current=next((r for r in store.reports() if track_id and r.get('audio',{}).get('catalog_track_id')==track_id),{'id':original['id']})
                        r=store.get_report(current['id'])
                        state.update(current_title=r['title'],current_track_id=track_id,processed=index)
                        for module in missing_modules(r,modules):
                            # Summary is automatically recomputed with emotion; resolve newest result below.
                            key=':'.join([phase,str(track_id or r['id']),str(r['audio'].get('sha256') or ''),module])
                            if key in state['attempts']:continue
                            if module=='emotion_summary':
                                current=next((v for v in store.reports() if track_id and v.get('audio',{}).get('catalog_track_id')==track_id),{'id':r['id']})
                                r=store.get_report(current['id'])
                                if not missing_modules(r,[module]):continue
                            # Let user work queued ahead of this batch finish first.
                            while True:
                                tasks=client.get('/jobs');tasks.raise_for_status()
                                if not any(j['status'] in ('queued','running') for j in tasks.json()):break
                                save();time.sleep(5)
                            response=client.post(f'/reports/{r["id"]}/modules/{module}',json={})
                            if response.status_code==429:time.sleep(5);response=client.post(f'/reports/{r["id"]}/modules/{module}',json={})
                            if response.status_code!=200:
                                state['attempts'].append(key);state['errors'].append({'key':key,'reason':response.text[:300]});save();continue
                            job=response.json();state.update(current_job=job['id'],pending_key=key);save()
                            result=wait_job(job['id']);finish(result,key)
                            if result.get('report_id'):r=store.get_report(result['report_id'])
                        state['processed']=index+1
                        if (index+1)%5==0:state['coverage']=counts(latest_reports(store))
                        save()
                    state['coverage']=counts(latest_reports(store));save()
                after=latest_reports(store)
                changed=[r['audio'].get('catalog_track_id') for r in after if baseline.get(str(r['audio'].get('catalog_track_id') or r['id']),r['source_hashes'])!=r['source_hashes']]
                state.update(status='completed_with_errors' if state['errors'] else 'completed',finished_at=now(),coverage=counts(after),source_hash_changes=changed,current_title=None,current_module=None)
                save()
            except BaseException:
                state.update(status='interrupted');save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default=os.getenv('ANALYSIS_LAB_DIR','data/analysis-platform'));parser.add_argument('--url',default='http://127.0.0.1:8765/api/analysis-lab');parser.add_argument('--phase',type=int,choices=range(1,len(PHASES)+1))
    args=parser.parse_args();run(args.root,args.url,[PHASES[args.phase-1]] if args.phase else None)
