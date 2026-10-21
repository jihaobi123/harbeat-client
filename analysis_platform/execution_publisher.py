"""Cloud CPU-only catalog bridge; source changes and set requests are incremental.

Run as its own systemd service. It never starts or recovers the GPU/import worker.
"""
import argparse
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time

LOG=logging.getLogger(__name__)
HASH=re.compile(r'[a-f0-9]{64}')
ID=re.compile(r'[A-Za-z0-9_-]{1,160}')
PILOT=['track-d2d58531421de0eb9690','track-831997216a86a4914ef9','track-642bd1ac0da727a3b53b',
       'track-0a1c8c54ff45b04f1568','track-6bcba4d577699a35104c','track-90b739cb337d10030cc5']


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.part')
    temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False));os.replace(temp,path)


def compact_catalog(source,destination):
    source=source.resolve();index=json.loads((source/'library.json').read_text());bindings={}
    for row in index['tracks']:
        if not ID.fullmatch(row['id']):raise ValueError('invalid track ID')
        detail=(source/row['detailUrl']).resolve()
        if source not in detail.parents:raise ValueError('unsafe detail URL')
        track=json.loads(detail.read_text())['track']
        if track['id']!=row['id']:raise ValueError('detail identity mismatch')
        slim={k:track[k] for k in ['id','duration','provenance','reportId','bpm','sections'] if k in track}
        slim['alignment']={'bars':(track.get('alignment') or {}).get('bars',[])}
        row['detailUrl']='details/'+row['id']+'.json';atomic(destination/row['detailUrl'],{'track':slim})
        bindings[row['id']]=slim.get('provenance') or {}
    atomic(destination/'library.json',index)
    return bindings


def ready_track(track,entry,bindings,objects,profiles,*,verify_objects=True):
    def finite(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
    tid=entry['trackId'];source=bindings.get(tid,{})
    if track.get('schema')!='harbeat.execution-track.v1' or track.get('trackId')!=tid:raise ValueError('track schema mismatch')
    for key,field in [('sourceSha256','masterSha256'),('reportSha256','reportSha256'),('runId','runId')]:
        if track.get(key)!=source.get(field) or entry.get(key)!=source.get(field):raise ValueError('track binding mismatch')
    if not HASH.fullmatch(str(track.get('manifestSha256',''))) or track.get('manifestSha256')!=entry.get('manifestSha256'):raise ValueError('manifest fingerprint mismatch')
    descriptor=entry.get('profile') or {}
    if track.get('profile')!=descriptor or not HASH.fullmatch(str(descriptor.get('sha256',''))):raise ValueError('profile descriptor mismatch')
    if isinstance(descriptor.get('bytes'),bool) or not isinstance(descriptor.get('bytes'),int) or not 1<=descriptor['bytes']<=32*1024**2:raise ValueError('invalid profile size')
    checksum=descriptor['sha256'];profile_file=profiles/(checksum+'.json')
    if descriptor.get('url')!='/listen/execution/profiles/'+checksum+'.json' or not profile_file.is_file() or profile_file.stat().st_size!=descriptor.get('bytes') or sha(profile_file)!=checksum:raise ValueError('profile bytes mismatch')
    profile=json.loads(profile_file.read_text())
    if profile.get('schema')!='harbeat.execution-profile.v1' or any(profile.get(k)!=track.get(k) for k in ['trackId','sourceSha256','reportSha256','manifestSha256','runId']):raise ValueError('profile content binding mismatch')
    sr=track.get('sampleRate');frames=track.get('frames');duration=track.get('duration')
    if isinstance(sr,bool) or not isinstance(sr,int) or not 8000<=sr<=96000 or track.get('channels')!=2:raise ValueError('unsupported sample format')
    if isinstance(frames,bool) or not isinstance(frames,int) or not 0<frames<=sr*1800 or not isinstance(duration,(float,int)) or not math.isfinite(duration) or abs(duration-frames/sr)>1/sr:raise ValueError('invalid source duration')
    master_grid=track.get('masterSampleGrid')
    if master_grid is not None:
        ms,mf=master_grid.get('sampleRate'),master_grid.get('frames')
        if isinstance(ms,bool) or isinstance(mf,bool) or not isinstance(ms,int) or not isinstance(mf,int) or not 8000<=ms<=192000 or mf*sr!=frames*ms:raise ValueError('invalid rational master sample mapping')
    total=0
    grid=None
    for name in ['drums','bass','other','vocals']:
        stem=(track.get('stems') or {}).get(name,{})
        if not HASH.fullmatch(str(stem.get('sourceSha256',''))):raise ValueError('missing stem source fingerprint')
        if stem['sourceSha256']!=(entry.get('stemSha256') or {}).get(name) or stem['sourceSha256']!=((profile.get('stems') or {}).get(name) or {}).get('sourceSha256'):raise ValueError('stem/profile fingerprint mismatch')
        if name=='vocals' and stem['sourceSha256']!=source.get('vocalSha256'):raise ValueError('vocal fingerprint mismatch')
        cursor=0;sample_cursor=0;current_grid=[]
        if not 1<=len(stem.get('segments',[]))<=512:raise ValueError('invalid segment count')
        for segment in stem.get('segments',[]):
            asset=segment['asset'];checksum=asset['sha256']
            if not HASH.fullmatch(checksum) or asset['url']!='/listen/execution-media/'+checksum+'.flac':raise ValueError('unsafe object URL')
            if not finite(segment.get('start')) or not finite(segment.get('end')) or abs(segment['start']-cursor)>1/track['sampleRate'] or segment['end']<=cursor:raise ValueError('noncontiguous source timeline')
            first,last=segment.get('startFrame'),segment.get('endFrame')
            if isinstance(first,bool) or isinstance(last,bool) or not isinstance(first,int) or not isinstance(last,int) or first!=sample_cursor or not first<last<=frames:raise ValueError('invalid segment sample bounds')
            count=last-first
            if abs(segment['start']-first/sr)>1/sr or abs(segment['end']-last/sr)>1/sr or count>32*sr:raise ValueError('invalid segment source mapping')
            if asset.get('sampleRate')!=sr or asset.get('channels')!=2 or asset.get('frames')!=count or not finite(asset.get('duration')) or abs(asset['duration']-count/sr)>1/sr:raise ValueError('asset sample grid mismatch')
            if isinstance(asset.get('bytes'),bool) or not isinstance(asset.get('bytes'),int) or not 1<=asset['bytes']<=64*1024**2:raise ValueError('invalid asset size')
            cursor=segment['end'];path=objects/(checksum+'.flac')
            sample_cursor=last;current_grid.append((first,last))
            if verify_objects and (not path.is_file() or path.stat().st_size!=asset['bytes'] or sha(path)!=checksum):raise ValueError('missing or corrupt execution object')
            total+=asset['bytes']
        if abs(cursor-track['duration'])>1/track['sampleRate']:raise ValueError('incomplete stem coverage')
        if sample_cursor!=frames or grid is not None and current_grid!=grid:raise ValueError('stems use different sample grids')
        grid=current_grid
    return total


class Publisher:
    def __init__(self,args):
        self.args=args;self.root=args.root;self.root.mkdir(parents=True,exist_ok=True,mode=0o755)
        self.root.chmod(0o755)
    def remote(self,argv,timeout=3600,input=None):
        return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',self.args.remote,shlex.join(argv)],check=True,capture_output=True,timeout=timeout,input=input)
    def copy(self,source,target,*,remote=False,files=None):
        command=['rsync','-azc','--max-size=67108864','--protect-args','-e','ssh -o BatchMode=yes -o ConnectTimeout=15']
        if files:command+=['--files-from',str(files)]
        subprocess.run(command+[source,str(target)],check=True,capture_output=True,timeout=1200)
    def cycle(self):
        import fcntl
        with (self.root/'.publisher.lock').open('a') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            self._cycle()
    def read_index(self):
        code="import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); print(p.read_text() if p.is_file() else '{\"tracks\":[]}')"
        return json.loads(self.remote([self.args.remote_python,'-c',code,self.args.remote_output+'/index.json']).stdout)
    def kick_profiles(self,base):
        # A catalog fill is a separate CPU job. Selected sets never wait for it
        # to finish; the exporter's per-track lock yields between songs.
        code='''import json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); args=json.loads(sys.argv[2]); existing=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  cmd=(p/'cmdline').read_bytes().split(b'\\0'); cwd=os.readlink(p/'cwd')
  if cwd==str(root) and b'analysis_platform.device_export' in cmd and b'--profiles-only' in cmd:existing.append(int(p.name))
 except (OSError,PermissionError):pass
if not existing:
 log=(root/'profiles-background.log').open('ab')
 process=subprocess.Popen(args,cwd=root,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 existing=[process.pid]
print(json.dumps({'cpuProfileJobs':existing}))
'''
        self.remote([self.args.remote_python,'-c',code,self.args.remote_code,json.dumps(base+['--profiles-only'])],timeout=30)
    def _cycle(self):
        catalog=self.root/'catalog';bindings=compact_catalog(self.args.library,catalog)
        if not self.args.existing_only:self.copy(str(catalog)+'/',self.args.remote+':'+self.args.remote_code+'/catalog/')
        base=['env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','nice','-n','10',self.args.remote_python,
              '-m','analysis_platform.device_export','--library',self.args.remote_code+'/catalog','--output',self.args.remote_output,'--incremental']
        public=self.root/'public';public.mkdir(exist_ok=True)
        (public/'profiles').mkdir(exist_ok=True)
        remote_index=self.read_index()
        if remote_index.get('tracks'):self.copy(self.args.remote+':'+self.args.remote_output+'/profiles/',public/'profiles/')
        LOG.info('Source profiles synchronized: %d indexed tracks',len(remote_index.get('tracks',[])))
        requested=set(PILOT)
        explicit=[]
        request_file=self.root/'requests.json'
        if request_file.exists():
            request=json.loads(request_file.read_text())
            explicit=list(dict.fromkeys(x for x in request.get('trackIds',[]) if isinstance(x,str) and ID.fullmatch(x)))
            requested.update(explicit)
        statuses={};entries={x['trackId']:x for x in remote_index.get('tracks',[])}
        for tid in explicit+[x for x in PILOT if x not in explicit]:
            if tid not in bindings:
                statuses[tid]={'status':'pending','reason':'source-bound preprocessing not ready'};continue
            try:
                args=base+['--track-id',tid]
                previous=entries.get(tid,{})
                current=all(previous.get(k)==bindings[tid].get(v) for k,v in [('runId','runId'),('sourceSha256','masterSha256'),('reportSha256','reportSha256')])
                if not previous.get('assetsReady') or not current:
                    if self.args.existing_only:
                        statuses[tid]={'status':'pending','reason':'source stems are still preparing'};continue
                    self.remote(['sh','-c','cd '+shlex.quote(self.args.remote_code)+' && '+shlex.join(args)])
                    update=self.read_index()
                    entry=next((v for v in update.get('tracks',[]) if v['trackId']==tid),None)
                    if entry is None or not entry.get('assetsReady'):
                        statuses[tid]={'status':'pending','reason':'source-bound preprocessing not ready'};continue
                    entries[tid]=entry
                    profile_id=entry['profile']['sha256']
                    if not HASH.fullmatch(profile_id):raise ValueError('unsafe profile hash')
                    self.copy(self.args.remote+':'+self.args.remote_output+'/profiles/'+profile_id+'.json',public/'profiles/')
                raw=self.remote(['cat',self.args.remote_output+'/tracks/'+tid+'.json']).stdout;track=json.loads(raw)
                objects=public/'objects';objects.mkdir(exist_ok=True)
                entry=entries[tid]
                ready_track(track,entry,bindings,objects,public/'profiles',verify_objects=False)
                assets={s['asset']['sha256']:s['asset'] for stem in track['stems'].values() for s in stem['segments']}
                if any(not HASH.fullmatch(k) for k in assets):raise ValueError('unsafe object hash')
                missing=[k for k,v in assets.items() if not (objects/(k+'.flac')).is_file() or sha(objects/(k+'.flac'))!=k]
                needed=sum(assets[k]['bytes'] for k in missing);used=sum(p.stat().st_size for p in objects.glob('*.flac'))
                # Validate actual source sizes before transfer/budget accounting.
                check="import json,pathlib,sys; base=pathlib.Path(sys.argv[1]); rows=json.load(sys.stdin); assert all((base/(k+'.flac')).stat().st_size==v for k,v in rows.items()), 'remote object size mismatch'"
                self.remote([self.args.remote_python,'-c',check,self.args.remote_output+'/objects'],input=json.dumps({k:assets[k]['bytes'] for k in missing}).encode(),timeout=90)
                if used+needed>self.args.maximum_bytes or shutil.disk_usage(self.root).free-needed<3*1024**3:
                    statuses[tid]={'status':'pending','reason':'execution cache capacity; no existing audio removed'};continue
                listing=self.root/'objects-to-copy.txt';listing.write_text(''.join(k+'.flac\n' for k in missing))
                if missing:self.copy(self.args.remote+':'+self.args.remote_output+'/objects/',str(objects)+'/',files=listing)
                ready_track(track,entry,bindings,objects,public/'profiles')
                atomic(public/'tracks'/(tid+'.json'),track)
                entry.update(assetsReady=True,trackUrl='/listen/execution/tracks/'+tid+'.json')
                statuses[tid]={'status':'ready'}
                LOG.info('Execution assets ready: %s (%d encoded bytes)',tid,sum(asset['bytes'] for asset in assets.values()))
            except Exception:
                LOG.exception('Execution preparation failed for %s',tid)
                statuses[tid]={'status':'pending','reason':'source verification or transfer incomplete'}
                (public/'tracks'/(tid+'.json')).unlink(missing_ok=True)
        if not self.args.existing_only:self.kick_profiles(base)
        published=[]
        for manifest in (public/'tracks').glob('*.json'):
            if manifest.stem not in entries or manifest.stem not in bindings:manifest.unlink(missing_ok=True)
        for tid,entry in entries.items():
            if tid not in bindings:continue
            profile_id=(entry.get('profile') or {}).get('sha256','')
            if not HASH.fullmatch(profile_id) or not (public/'profiles'/(profile_id+'.json')).is_file() or sha(public/'profiles'/(profile_id+'.json'))!=profile_id:continue
            # NAS readiness is not cloud readiness. A complete local manifest and
            # current binding are required before advertising downloadable stems.
            ready=False;manifest=public/'tracks'/(tid+'.json')
            if manifest.exists():
                try:ready_track(json.loads(manifest.read_text()),entry,bindings,public/'objects',public/'profiles');ready=True
                except Exception:manifest.unlink(missing_ok=True)
            entry.update(assetsReady=ready,trackUrl='/listen/execution/tracks/'+tid+'.json' if ready else None)
            published.append(entry)
        atomic(public/'index.json',{'schema':'harbeat.execution-library.v1','generatedAt':int(time.time()),'tracks':published,
                                  'excluded':[{'trackId':x['trackId'],'reason':'source binding or audio evidence unavailable'} for x in remote_index.get('excluded',[])]})
        atomic(self.root/'status.json',{'updatedAt':int(time.time()),'tracks':statuses,'profileCount':len(published)})
        LOG.info('Publication complete: %d profiles, %d selected tracks ready',len(published),sum(v['status']=='ready' for v in statuses.values()))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=Path('/srv/harbeat-listen/current'))
    parser.add_argument('--root',type=Path,default=Path('/srv/harbeat-listen/execution-state'))
    parser.add_argument('--remote',default='mark@100.87.142.21')
    parser.add_argument('--remote-code',default='/home/mark/harbeat-device-execution')
    parser.add_argument('--remote-output',default='/mnt/nas/harbeat/preprocess/device-execution-v1')
    parser.add_argument('--remote-python',default='/home/mark/harbeat-analysis-venv/bin/python')
    parser.add_argument('--maximum-bytes',type=int,default=2*1024**3)
    parser.add_argument('--interval',type=int,default=180)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--existing-only',action='store_true',help='Publish already prepared NAS sidecars/assets without waiting for CPU export')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO);publisher=Publisher(args)
    while True:
        try:publisher.cycle()
        except Exception:LOG.exception('Execution catalog cycle incomplete; existing playback continues')
        if args.once:break
        time.sleep(max(30,args.interval))


if __name__=='__main__':main()
