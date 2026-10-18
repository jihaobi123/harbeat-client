"""Jointly render frozen master/other excerpts; never add another technique."""
import argparse,hashlib,json,pathlib,subprocess
import numpy as np
try:
    from scripts.render_melody_overlap import checked_source,sha,write_asset,SR
except ModuleNotFoundError:
    from render_melody_overlap import checked_source,sha,write_asset,SR


def stretch_pair(paths,start,duration,rate):
    if len(paths)!=2 or not all(np.isfinite([start,duration,rate])) or start<0 or duration<=0 or rate<=0:
        raise ValueError('invalid source range')
    cmd=['ffmpeg','-v','error','-nostdin','-threads','1']
    for p in paths:cmd+=['-ss',str(start),'-t',str((duration+1)*rate),'-i',str(p)]
    filters=';'.join('[%d:a]aresample=%d,aformat=sample_fmts=flt:channel_layouts=stereo[x%d]'%(i,SR,i) for i in range(2))
    filters+=';[x0][x1]amerge=inputs=2,atempo=%s[out]'%rate
    cmd+=['-filter_complex',filters,'-map','[out]','-f','f32le','-acodec','pcm_f32le','pipe:1']
    x=np.frombuffer(subprocess.check_output(cmd),dtype='<f4').reshape(-1,4);frames=round(duration*SR)
    if len(x)<frames or not np.isfinite(x).all():raise ValueError('incomplete or nonfinite source')
    return x[:frames].copy()


def describe_other(x):
    mono=x.astype('float64').mean(axis=1);rms=float(np.sqrt(np.mean(x.astype('float64')**2)))
    frame=4096;hop=2048;profile=np.zeros(12);freq=np.fft.rfftfreq(frame,1/SR);mask=(freq>=80)&(freq<=5000)
    bins=np.rint(69+12*np.log2(freq[mask]/440)).astype(int)%12
    for start in range(0,len(mono)-frame+1,hop):
        energy=np.abs(np.fft.rfft(mono[start:start+frame]*np.hanning(frame)))**2
        profile+=np.bincount(bins,weights=energy[mask],minlength=12)
    total=profile.sum();profile=profile/total if total else profile
    return dict(otherRms=rms,pitchClassPower=profile.tolist(),concentration=float(profile.max()),basis='Uncalibrated FFT pitch-class power on local other excerpt; not harmonic-conflict or stem-bleed detection')


def render(selection,nas,reports,output):
    raw=selection.read_bytes();d=json.loads(raw);output.mkdir(parents=True,exist_ok=True);sources={};evidence={}
    for t in d['tracks']:
        v=t['provenance'];m=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';doc=json.loads(m.read_text());success=json.loads((m.parent/'_SUCCESS.json').read_text());assets=doc['assets']
        report=reports/(t['reportId']+'.json')
        if not report.exists() or sha(report)!=v['reportSha256']:raise ValueError('frozen report changed or unavailable')
        if doc['track_id']!=t['id'] or doc['analysis_run_id']!=v['runId'] or sha(m)!=success['manifest_sha256'] or assets['master']['sha256']!=v['masterSha256'] or assets['stems']['vocals']['sha256']!=v['vocalSha256']:raise ValueError('source binding mismatch')
        entries=[assets['master'],assets['stems']['other']]
        if any(a['channels']!=2 or a['sample_rate_hz']!=SR for a in entries):raise ValueError('unsupported source format')
        sources[t['id']]=[checked_source(nas,a) for a in entries]
        evidence[t['id']]=dict(v,reportId=report.stem,manifestSha256=sha(m),otherSha256=entries[1]['sha256'],otherStorageKey=entries[1]['storage_key'])
        print('verified',t['title'],flush=True)
    cases=[];skipped=[]
    for c in d['cases']:
        p=c['plan'];assets={};features={}
        for part,tid,start,duration,rate in [('a',p['from'],p['start']-c['pre'],c['pre']+p['duration'],1),('bEntry',p['to'],p['window']['start'],p['duration'],p['rate']),('bBody',p['to'],p['window']['end'],c['post'],1)]:
            pcm=stretch_pair(sources[tid],start,duration,rate)
            features[part]=describe_other(pcm[round(c['pre']*SR):,2:] if part=='a' else pcm[:,2:])
            for j,name in enumerate(['Master','Other']):
                asset=write_asset(output/(c['id']+'-'+part+name+'.flac'),pcm[:,2*j:2*j+2]);asset['url']='/melody-yield-audio/'+pathlib.Path(asset['url']).name;assets[part+name]=asset
        if min(features['a']['otherRms'],features['bEntry']['otherRms'])<.005:
            skipped.append(dict(id=c['id'],reason='other too quiet for this trial',features=features));continue
        a=np.array(features['a']['pitchClassPower']);b=np.array(features['bEntry']['pitchClassPower']);den=np.linalg.norm(a)*np.linalg.norm(b)
        features['pitchClassCosine']=float(a@b/den) if den else None
        cases.append(dict(c,assets=assets,features=features,sourceVerification={side:evidence[p[key]] for side,key in [('a','from'),('b','to')]}))
        print('rendered',c['aTitle'],c['bTitle'],flush=True)
    pack=dict(schema='harbeat.melody-yield-pack.v1',selectionSha256=hashlib.sha256(raw).hexdigest(),cases=cases,skipped=skipped,sourcePackSha256=d['sourcePackSha256'],rendering='Master and actual other jointly stretched as four channels; reference=master, treatment changes only outgoing other correction.',limitation='Other includes multiple instruments and possible separation bleed; features are not validated melody-conflict labels. No per-arm normalization; no vocal handover, bass swap, loop or echo.')
    (output/'melody-yield-data.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');print('complete',len(cases),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['selection','nas','reports','output']:p.add_argument('--'+k,type=pathlib.Path,required=True)
    a=p.parse_args();render(a.selection,a.nas,a.reports,a.output)
