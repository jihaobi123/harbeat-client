"""Verified original-rate excerpts. Never use atempo for the native reference."""
import argparse,copy,hashlib,json,pathlib,subprocess
from functools import lru_cache
import numpy as np
import soundfile as sf
SR=44100

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
@lru_cache(maxsize=2)
def decoded_native(paths):
    cmd=['ffmpeg','-v','error','-nostdin','-threads','1']
    for p in paths:cmd+=['-i',str(p)]
    filters=';'.join('[%d:a]aresample=44100,aformat=sample_fmts=flt:channel_layouts=stereo[x%d]'%(i,i) for i in range(len(paths)))
    filters+=';'+''.join('[x%d]'%i for i in range(len(paths)))+'amerge=inputs=%d[out]'%len(paths)
    cmd+=['-filter_complex',filters,'-map','[out]','-f','f32le','-acodec','pcm_f32le','pipe:1']
    pcm=np.frombuffer(subprocess.check_output(cmd),dtype='<f4').reshape(-1,2*len(paths))
    if not np.isfinite(pcm).all():raise ValueError('nonfinite native source')
    return pcm

def native_layers(paths,start,duration,rate):
    if rate!=1 or not np.isfinite([start,duration]).all() or start<0 or duration<=0:raise ValueError('native source clock required')
    # Decode/resample once from source origin. Independent seeks restart the
    # resampler and can move the sampling phase, breaking fixed source cues.
    full=decoded_native(tuple(paths));first=round(start*SR);n=round(duration*SR);pcm=full[first:first+n]
    if len(pcm)!=n:raise ValueError('incomplete native source')
    return pcm.copy()

def render(root,nas,reports):
    selection=json.loads((root/'selection.json').read_text());bound=copy.deepcopy(selection);sources={};verified={};out=root/'audio';out.mkdir(exist_ok=True)
    for t in selection['tracks']:
        v=t['provenance'];report=reports/(t['reportId']+'.json');manifest=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(manifest.read_text());success=json.loads((manifest.parent/'_SUCCESS.json').read_text())
        assets=[m['assets']['master'],m['assets']['stems']['vocals']]
        if sha(report)!=v['reportSha256'] or sha(manifest)!=success['manifest_sha256'] or m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId'] or assets[0]['sha256']!=v['masterSha256'] or assets[1]['sha256']!=v['vocalSha256']:raise ValueError('source binding changed')
        paths=[]
        for a in assets:
            p=(nas/a['storage_key']).resolve()
            if nas.resolve() not in p.parents or a['channels']!=2 or sha(p)!=a['sha256']:raise ValueError('source format/hash mismatch')
            paths.append(p)
        sources[t['id']]=paths;verified[t['id']]=dict(v,manifestSha256=sha(manifest));print('verified direct native',t['title'],flush=True)
    cases=[]
    for c in bound['cases']:
        p=c['plan'];c['sourceVerification']={side:verified[p[key]] for side,key in [('a','from'),('b','to')]};assets={};arrays={}
        for part,tid,start,duration in [('a',p['from'],p['start']-c['pre'],c['pre']+p['duration']),('bEntry',p['to'],p['window']['start'],p['duration']),('bBody',p['to'],p['window']['end'],c['post'])]:
            pcm=native_layers(sources[tid],start,duration,1);arrays[part]=pcm
            for i,name in enumerate(['Master','Vocal']):
                path=out/(c['id']+'-'+part+name+'.wav');sf.write(path,pcm[:,i*2:i*2+2],SR,subtype='FLOAT');assets[part+name]=dict(url='/native-audio/'+path.name,sha256=sha(path),bytes=path.stat().st_size,duration=len(pcm)/SR,frames=len(pcm),sampleRate=SR,channels=2,peak=float(np.max(np.abs(pcm[:,i*2:i*2+2]))))
        continuous=native_layers(sources[p['to']],p['window']['start'],p['duration']+c['post'],1);joined=np.concatenate([arrays['bEntry'],arrays['bBody']]);delta=float(np.max(np.abs(joined-continuous)))
        if delta>1e-6:raise ValueError('B entry/body not source-continuous: '+str(delta))
        cases.append(dict(c,assets=assets,nativeContinuityAudit=dict(directNativeNoAtempo=True,absoluteSourceClock=True,adjacentCombinedSourceMaxError=delta,joinedPcmSha256=hashlib.sha256(joined.tobytes()).hexdigest(),continuousSourcePcmSha256=hashlib.sha256(continuous.tobytes()).hexdigest(),rendererSha256=sha(pathlib.Path(__file__)))))
        print('native contiguous',c['id'],delta,flush=True)
    (root/'selection-bound.json').write_text(json.dumps(bound,ensure_ascii=False,indent=2)+'\n')
    (out/'half-double-native.json').write_text(json.dumps(dict(schema='harbeat.half-double-native.v1',selectionSha256=sha(root/'selection-bound.json'),cases=cases),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('root',type=pathlib.Path);a.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));a.add_argument('--reports',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports'));v=a.parse_args();render(v.root,v.nas,v.reports)
