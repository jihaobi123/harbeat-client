"""Package fixed raw-bar halfbeat accompaniment gaps with original voice rules."""
import argparse,copy,hashlib,json,pathlib,shutil
import numpy as np
import soundfile as sf
from scripts.report_vocal_endpoints import verified_analysis
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_gap_boundary(c,a,edge,beats):
    from scripts.prepare_cut_handover import validate_cut_boundary
    validate_cut_boundary(c,a,edge)
    bpm=c['bpm'][0]
    if not np.isfinite([bpm,beats]).all() or bpm<=0 or abs(beats-.5)>1e-9:raise ValueError('pause requires fixed halfbeat and finite original BPM')
    pause=beats*60/bpm;p=c['plan'];e=c['endpoint']
    if pause+edge>=p['duration'] or c['post']<=edge or e['tailEnd']>p['duration']-pause-edge-.08:raise ValueError('outgoing vocal tail leaves insufficient local accompaniment gap')
    return pause


def prepare(parent,web,out):
    frozen=json.loads((out/'frozen-input.json').read_text());source=parent/'pack.json'
    if sha(source)!=frozen['sourcePackSha256']:raise ValueError('frozen source pack changed')
    reports=[]
    for binding in frozen['analysisSources']:
        root=pathlib.Path(binding['path'])
        if sha(root/'analysis.json')!=binding['sha256']:raise ValueError('frozen endpoint analysis changed')
        reports.append(verified_analysis(root))
    original=json.loads(source.read_text());audio=web/'bed-gap-audio';audio.mkdir(exist_ok=True);cases=[];audit=[];keys=['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']
    for index,old in enumerate(original['cases']):
        c=copy.deepcopy(old);p=c['plan'];a,b=c['evidence']['analysis'],c['evidence']['control'];row=dict(id=c['id'],aTitle=c['aTitle'],bTitle=c['bTitle'],planSha256=c['planSha256'],accepted=False)
        if not any(a in r['contexts'] and b in r['contexts'] for r in reports):raise ValueError('observations differ from freshly verified inputs')
        expected={k:round(a['selected'][k]-p['start'],9) for k in ['tailEnd','nextOnset','fadeStart','fadeEnd']}
        if c['endpoint']!=expected:raise ValueError('frozen endpoint changed')
        try:
            validate_handover_sources(c,a,b);pause=validate_gap_boundary(c,a,frozen['pauseEdgeSeconds'],frozen['pauseBeats'])
        except ValueError as e:
            row['reason']=str(e);audit.append(row);continue
        caseid='bed-gap-'+str(index+1).zfill(2);assets={}
        for key in keys:
            asset=c['assets'][key];src=(web/asset['url'].lstrip('/')).resolve()
            if web.resolve() not in src.parents or not src.is_file() or sha(src)!=asset['sha256'] or src.stat().st_size!=asset['bytes']:raise ValueError('original clip hash mismatch '+key)
            pcm,sr=sf.read(src,dtype='float32',always_2d=True);duration=c['pre']+p['duration'] if key.startswith('a') else p['duration'] if key.startswith('bEntry') else c['post']
            if sr!=44100 or pcm.shape!=(round(duration*sr),2) or not np.isfinite(pcm).all():raise ValueError('original clip format/clock mismatch '+key)
            target=audio/(caseid+'-'+key+src.suffix);shutil.copy2(src,target);assets[key]=dict(asset,url='/bed-gap-audio/'+target.name)
        cue=p['decision']['cues']['aExit'];evidence=dict(rawBoundary=cue['nearestRawBar'],nearestModelSectionBoundary=cue.get('nearestSectionBoundary'),vocalTailSource=a['selected']['tailEnd'],vocalTailGapSeconds=p['duration']-c['endpoint']['tailEnd'],outgoingGapBoundaryType='observed-next-onset' if a['selected'].get('nextOnsetObserved') else 'observation-horizon-censored',outgoingCoverage=a['coverage'],incomingCoverage=b['coverage'],analysisSources=frozen['analysisSources'],voicePolicy='original-linear-fades',accompanimentPolicy='original-gradual-outside-local-final-halfbeat-gap',pauseSeconds=pause,pauseBeats=frozen['pauseBeats'],downStart=c['pre']+p['duration']-pause-frozen['pauseEdgeSeconds'],gapStart=c['pre']+p['duration']-pause,recoveryEnd=c['pre']+p['duration']+frozen['pauseEdgeSeconds'],sourceScheduling='Original A/B fade until a5ms descent into the final halfbeat accompaniment gap. Bentry keeps advancing while muted; original Bbody starts at unchanged native takeover with5ms accompaniment recovery. Original4ms entry/body edges and original vocals retained.',interpretation='Raw beat-grid bar boundary, not confirmed phrase or section ending. Provisional vocal activity evidence, not certified lyric completeness.')
        c.update(id=caseid,sourceCaseId=old['id'],assets=assets,pauseSeconds=pause,pauseBeats=frozen['pauseBeats'],pauseEdgeSeconds=frozen['pauseEdgeSeconds'],pauseEvidence=evidence);cases.append(c);row.update(accepted=True,reason='fixed raw bar and source-bound vocal coverage passed',pauseEvidence=evidence);audit.append(row)
        print('prepared',c['aTitle'],c['bTitle'],'tail gap',evidence['vocalTailGapSeconds'],'section distance',cue.get('nearestSectionBoundary',{}).get('distanceSec'),flush=True)
    if not cases:raise ValueError('No frozen cue passes; do not move cue to create a result')
    identity=dict(frozenInput=frozen,preparerSha256=sha(pathlib.Path(__file__)),boundaryValidatorSha256=sha(pathlib.Path(__file__).with_name('prepare_cut_handover.py')),cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],pauseSeconds=c['pauseSeconds'],pauseBeats=c['pauseBeats'],pauseEdgeSeconds=c['pauseEdgeSeconds'],pauseEvidence=c['pauseEvidence']) for c in cases]);pack=dict(schema='harbeat.bed-gap-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),sourcePackSha256=sha(source),cases=cases,audit=audit,rendering='Exact six original master/vocal clips. Original vocal curves in both arms via signed correction. Treatment follows original accompaniment fades except for a final halfbeat gap with5ms edges around unchanged B native takeover; voices retain original fades.',limitation='Near-tempo frozen pairs; not a verified section/phrase-ending or distant-style transition experiment. No per-arm normalization, voice handover, prior short-exchange hold curve, bass/drum FX, loop, echo, transport stop or scratch. Vocal separation bleed and activity uncertainty remain. No global activation.')
    raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(web/'bed-gap-data.json').write_text(raw);(out/'pack.json').write_text(raw);(out/'preparation-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('parent',type=pathlib.Path);p.add_argument('web',type=pathlib.Path);p.add_argument('output',type=pathlib.Path);a=p.parse_args();prepare(a.parent,a.web,a.output)
