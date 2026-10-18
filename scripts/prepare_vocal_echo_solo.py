"""Finite vocal-only echo over unchanged original dry fades; no handover treatment."""
import argparse,copy,hashlib,json,pathlib,shutil
import numpy as np
import soundfile as sf
from scripts.report_vocal_endpoints import verified_analysis
from scripts.prepare_vocal_endpoint_pack import validate_handover_sources
from analysis_platform.stem_effects import plan_vocal_echo,render_vocal_echo

SEND_POLICY='original-a-fade-before-delay-v1'
DRY_POLICY='original-natural-v1'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def original_send_gain(time,pre,duration):
    if not np.isfinite([pre,duration]).all() or pre<0 or duration<=0 or not np.isfinite(time).all():raise ValueError('invalid original fade clock')
    return np.clip((pre+duration-np.asarray(time))/duration,0,1)

def render_original_send(audio,sr,pre,duration,fx):
    x=np.asarray(audio)
    if sr<=0 or x.ndim!=2 or x.shape[1]!=2 or len(x)!=round((pre+duration)*sr):raise ValueError('vocal send differs from fixed source timeline')
    return render_vocal_echo(x*original_send_gain(np.arange(len(x))/sr,pre,duration)[:,None],sr,fx)

def prepare(parent,web,out):
    out.mkdir(parents=True,exist_ok=True);frozen=json.loads((out/'frozen-input.json').read_text());source=parent/'pack.json'
    if sha(source)!=frozen['sourcePackSha256']:raise ValueError('frozen source pack changed')
    reports=[]
    for binding in frozen['analysisSources']:
        root=pathlib.Path(binding['path'])
        if sha(root/'analysis.json')!=binding['sha256']:raise ValueError('frozen endpoint analysis changed')
        reports.append(verified_analysis(root))
    pack=json.loads(source.read_text());audio=web/'vocal-echo-solo-audio';audio.mkdir(exist_ok=True);cases=[];audit=[]
    dry_keys=['aMaster','aBass','aVocal','bEntryMaster','bEntryBass','bEntryVocal','bBodyMaster','bBodyBass','bBodyVocal']
    for index,old in enumerate(pack['cases']):
        c=copy.deepcopy(old);p=c['plan'];a,b=c['evidence']['analysis'],c['evidence']['control'];row=dict(id=c['id'],aTitle=c['aTitle'],bTitle=c['bTitle'],planSha256=c['planSha256'],accepted=False)
        if not any(a in r['contexts'] and b in r['contexts'] for r in reports):raise ValueError('embedded observations differ from freshly verified source evidence')
        if c['baselineBass']!='reference' or sorted(c['assets'])!=sorted(dry_keys):raise ValueError('only original reference dry sources permitted')
        expected={k:round(a['selected'][k]-p['start'],9) for k in ['tailEnd','nextOnset','fadeStart','fadeEnd']}
        if c['endpoint']!=expected:raise ValueError('frozen endpoint changed')
        validate_handover_sources(c,a,b)
        try:fx=plan_vocal_echo(c,a,b)
        except ValueError as e:
            row['reason']=str(e);audit.append(row);continue
        source_pcm=None;assets={};caseid='vocal-echo-solo-'+str(index+1).zfill(2)
        for key in dry_keys:
            asset=c['assets'][key];src=(web/asset['url'].lstrip('/')).resolve()
            if web.resolve() not in src.parents or not src.is_file() or sha(src)!=asset['sha256'] or src.stat().st_size!=asset['bytes']:raise ValueError('dry source hash mismatch '+key)
            pcm,sr=sf.read(src,dtype='float32',always_2d=True);duration=c['pre']+p['duration'] if key.startswith('a') else p['duration'] if key.startswith('bEntry') else c['post']
            if sr!=44100 or pcm.shape!=(round(duration*sr),2) or not np.isfinite(pcm).all():raise ValueError('dry source clock/format mismatch '+key)
            if key=='aVocal':source_pcm=pcm
            target=audio/(caseid+'-'+key+src.suffix);shutil.copy2(src,target);assets[key]=dict(asset,url='/vocal-echo-solo-audio/'+target.name)
        wet=render_original_send(source_pcm,44100,c['pre'],p['duration'],fx);peak=float(np.max(abs(wet)))
        if not .00001<peak<=.7:raise ValueError('wet silent or above declared isolated peak bound')
        target=audio/(caseid+'-aEcho.wav');sf.write(target,wet,44100,subtype='FLOAT');assets['aEcho']=dict(url='/vocal-echo-solo-audio/'+target.name,sha256=sha(target),bytes=target.stat().st_size,duration=len(wet)/44100,frames=len(wet),sampleRate=44100,channels=2,peak=peak)
        active=np.flatnonzero(np.max(abs(wet),axis=1)>1e-9)
        fxEvidence=dict(inputVocalSha256=assets['aVocal']['sha256'],wetSha256=assets['aEcho']['sha256'],dryPolicy=DRY_POLICY,sendGainPolicy=SEND_POLICY,isolatedWetPeak=peak,isolatedWetRms=float(np.sqrt(np.mean(wet.astype('float64')**2))),decodedSupport=[int(active[0])/44100,(int(active[-1])+1)/44100],window=fx,outgoingGapBoundaryType='observed-next-onset' if a['selected'].get('nextOnsetObserved') else 'observation-horizon-censored',outgoingCoverage=a['coverage'],analysisSources=frozen['analysisSources'],normalization='none; unchanged common dry/EQ/output chain',status='provisional-activity-window; no human lyric-end certification')
        c.update(id=caseid,sourceCaseId=old['id'],assets=assets,fx=fx,fxEvidence=fxEvidence);cases.append(c);row.update(accepted=True,reason='same original dry plan; finite vocal echo support checks passed',fx=fx);audit.append(row)
        print('prepared',c['aTitle'],c['bTitle'],'wet peak',peak,'support',fxEvidence['decodedSupport'],flush=True)
    if not cases:raise ValueError('No original fixed cues pass standalone echo support; do not move cues')
    identity=dict(frozenInput=frozen,preparerSha256=sha(pathlib.Path(__file__)),effectImplementationSha256=sha(pathlib.Path(__file__).parents[1]/'analysis_platform/stem_effects.py'),cases=[dict(id=c['id'],planSha256=c['planSha256'],assets=c['assets'],fx=c['fx'],fxEvidence=c['fxEvidence']) for c in cases])
    result=dict(schema='harbeat.vocal-echo-solo-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),sourcePackSha256=sha(source),cases=cases,audit=audit,rendering='Exact original nine dry clips and natural dry curves; only finite wet-only vocal layer toggles0/1. Original gain weighting before delay; original A EQ at wet output time.',limitation='Three frozen pairs, provisional source-bound activity endpoints. No protected vocal handover, dry vocal extension, independent bass/drum/melody treatment or per-arm normalization. No global rule or production activation.')
    raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n';(web/'vocal-echo-solo-data.json').write_text(raw);(out/'pack.json').write_text(raw);(out/'preparation-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('parent',type=pathlib.Path);parser.add_argument('web',type=pathlib.Path);parser.add_argument('output',type=pathlib.Path);a=parser.parse_args();prepare(a.parent,a.web,a.output)
