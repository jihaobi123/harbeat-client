"""Bind native clips and create only the mapped Bentry, preserving frozen cues."""
import argparse,copy,json,pathlib,hashlib,shutil
import numpy as np
import soundfile as sf
from scripts.half_double_audio import validate_map,warp_shared

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path,pcm):
    sf.write(path,pcm,44100,subtype='FLOAT');return dict(url='/half-double-audio/'+path.name,sha256=sha(path),bytes=path.stat().st_size,duration=len(pcm)/44100,frames=len(pcm),sampleRate=44100,channels=2,peak=float(np.max(np.abs(pcm))))
def package(root,web):
    selection=json.loads((root/'selection.json').read_text());render=json.loads((root/'source-audio/half-double-native.json').read_text());bound=json.loads((root/'selection-bound.json').read_text());tracks=json.loads((root/'tracks.json').read_text());output=web/'half-double-audio';output.mkdir(exist_ok=True);cases=[];audit=[]
    if render['selectionSha256']!=sha(root/'selection-bound.json'):raise ValueError('native renderer selection binding changed')
    keys=['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']
    for frozen,c,bt in zip(selection['cases'],render['cases'],bound['cases']):
        if frozen['plan']!=c['plan'] or frozen['metric']!=c['metric'] or frozen['planSha256']!=c['planSha256'] or c['id']!=frozen['id']:raise ValueError('frozen plan changed during source rendering')
        c=copy.deepcopy(c);p=c['plan'];assets={};decoded={}
        if c.get('nativeContinuityAudit',{}).get('directNativeNoAtempo') is not True or c['nativeContinuityAudit'].get('absoluteSourceClock') is not True or c['nativeContinuityAudit']['rendererSha256']!=sha(pathlib.Path(__file__).with_name('render_half_double_sources.py')) or c['nativeContinuityAudit']['adjacentCombinedSourceMaxError']>1e-6:raise ValueError('native source continuity evidence missing')
        for side,key in [('a','from'),('b','to')]:
            t=next(t for t in tracks if t['id']==p[key]);v=c['sourceVerification'][side];expected=t['provenance'];binding=t['preprocessing']['vocalActivity']['source']
            if any(v[k]!=expected[k] for k in ['runId','reportSha256','masterSha256','vocalSha256']) or v['manifestSha256']!=binding['manifest_sha256'] or v['manifestSha256']!=bt['sourceVerification'][side]['manifestSha256']:raise ValueError('render/source/activity binding mismatch')
        for key in keys:
            a=c['assets'][key];src=root/'source-audio'/pathlib.Path(a['url']).name
            if not src.is_file() or sha(src)!=a['sha256'] or src.stat().st_size!=a['bytes']:raise ValueError('native clip hash changed')
            pcm,sr=sf.read(src,dtype='float32',always_2d=True);duration=c['pre']+p['duration'] if key.startswith('a') else p['duration'] if key.startswith('bEntry') else c['post']
            if sr!=44100 or pcm.shape!=(round(duration*sr),2) or not np.isfinite(pcm).all():raise ValueError('native clip clock/format changed')
            target=output/(c['id']+'-'+key+src.suffix);shutil.copy2(src,target);assets[key]=dict(a,url='/half-double-audio/'+target.name);decoded[key]=pcm
        x,y=validate_map(c['metric']['input'],c['metric']['output'],p['duration']);native=np.concatenate([decoded['bEntryMaster'],decoded['bEntryVocal']],axis=1);mapped=warp_shared(native,44100,x,y)
        if np.array_equal(mapped,native):raise ValueError('identity comparison would not test alignment')
        for i,name in enumerate(['Master','Vocal']):assets['bAligned'+name]=write(output/(c['id']+'-bAligned'+name+'.wav'),mapped[:,i*2:i*2+2])
        row=dict(id=c['id'],nativeFrames=len(native),mappedFrames=len(mapped),inputBeatSeconds=x.tolist(),outputBeatSeconds=y.tolist(),localRates=(np.diff(x)/np.diff(y)).tolist(),nominalMaximumGridCorrection=float(max(abs(x-y))),wsolaSearchRadiusSeconds=.0125,phaseGridEvidence='nominal input/output map, not independently observed musical attacks',waveformRelativeDifference=float(np.sqrt(np.mean((mapped-native).astype(float)**2))/(np.sqrt(np.mean(native.astype(float)**2))+1e-12)),nativeRms=float(np.sqrt(np.mean(native.astype(float)**2))),mappedRms=float(np.sqrt(np.mean(mapped.astype(float)**2))),first8SamplesExact=np.array_equal(mapped[:8],native[:8]),last8SamplesExact=np.array_equal(mapped[-8:],native[-8:]),boundarySamples='same source frames at both ends; common10ms boundary ramps',gainPolicy='same original linear curves, same EQ, same output, no per-arm normalization',originalAssets={k:a['sha256'] for k,a in assets.items() if k in keys})
        c['assets']=assets;c['metric']['renderAudit']=row;cases.append(c);audit.append(row)
    if len(cases)!=3 or len(render['cases'])!=3:raise ValueError('incomplete frozen cases')
    identity=dict(selectionSha256=sha(root/'selection.json'),boundSelectionSha256=sha(root/'selection-bound.json'),nativePackSha256=sha(root/'source-audio/half-double-native.json'),rendererSha256=sha(pathlib.Path(__file__).with_name('half_double_audio.py')),packagerSha256=sha(pathlib.Path(__file__)),selectionAlgorithmSha256=sha(root/'exploration-algorithm.py'),cases=[dict(id=c['id'],assets=c['assets'],plan=c['plan'],metric=c['metric']) for c in cases])
    pack=dict(schema='harbeat.half-double-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),cases=cases,audit=dict(selection=selection['audit'],audio=audit),rendering='Original native six source clips; optional endpoint-preserving joint master/vocal Bentry WSOLA against observed2:1/1:2grid. Same original gain/EQ/source schedule in both arms.',limitation='Both original songs already have near2:1or1:2metrical relation; trial tests local phase correction, not BPM labels, global speed conversion or new semantic phrase alignment. Only3pairs/5tracks, first2shareA, existing grids/proxies provisional. No combined effects or production change.')
    raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'half-double-data.json').write_text(raw);(root/'preparation-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n');(root/'audio-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print([(c['aTitle'],c['bTitle'],c['metric']['renderAudit']['waveformRelativeDifference']) for c in cases])
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('root',type=pathlib.Path);a.add_argument('web',type=pathlib.Path);v=a.parse_args();package(v.root,v.web)
