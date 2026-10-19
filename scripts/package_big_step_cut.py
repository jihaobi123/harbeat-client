"""Bind six unchanged native sources to the frozen section-cut experiment."""
import argparse,copy,json,pathlib,hashlib,shutil
import numpy as np
import soundfile as sf

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_frozen(frozen,rendered):
    if frozen!={k:v for k,v in rendered.items() if k not in ['assets','sourceVerification','nativeContinuityAudit']}|({'sourceVerification':{}} if 'sourceVerification' in frozen else {}):
        raise ValueError('frozen case changed during rendering')

def package(root,web):
    selection=json.loads((root/'selection.json').read_text());render=json.loads((root/'source-audio/half-double-native.json').read_text());bound=json.loads((root/'selection-bound.json').read_text());tracks=json.loads((root/'tracks.json').read_text());output=web/'big-step-cut-audio';output.mkdir(exist_ok=True);cases=[]
    if render['selectionSha256']!=sha(root/'selection-bound.json') or [len(x['cases']) for x in [selection,render,bound]]!=[3,3,3]:raise ValueError('incomplete or unbound sources')
    if len({c['id'] for c in selection['cases']})!=3 or len({c['plan'][side] for c in selection['cases'] for side in ['from','to']})!=6:raise ValueError('experiment requires3distinct pairs and6unique tracks')
    keys=['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal']
    for frozen,c,bt in zip(selection['cases'],render['cases'],bound['cases']):
        verify_frozen(frozen,c);verify_frozen(frozen,bt);c=copy.deepcopy(c);p=c['plan'];assets={}
        audit=c.get('nativeContinuityAudit',{})
        if audit.get('directNativeNoAtempo') is not True or audit.get('absoluteSourceClock') is not True or audit['rendererSha256']!=sha(pathlib.Path(__file__).with_name('render_half_double_sources.py')) or audit['adjacentCombinedSourceMaxError']>1e-6 or audit['joinedPcmSha256']!=audit['continuousSourcePcmSha256']:raise ValueError('native source continuity evidence missing')
        for side,key in [('a','from'),('b','to')]:
            t=next(t for t in tracks if t['id']==p[key]);v=c['sourceVerification'][side];expected=t['provenance'];binding=t['preprocessing']['vocalActivity']['source']
            if any(v[k]!=expected[k] for k in ['runId','reportSha256','masterSha256','vocalSha256']) or v['manifestSha256']!=binding['manifest_sha256'] or v!=bt['sourceVerification'][side]:raise ValueError('render/source/activity binding mismatch')
        if set(c['assets'])!=set(keys):raise ValueError('unexpected source/effect asset')
        for key in keys:
            a=c['assets'][key];src=root/'source-audio'/pathlib.Path(a['url']).name
            if not src.is_file() or sha(src)!=a['sha256'] or src.stat().st_size!=a['bytes']:raise ValueError('native clip hash changed')
            pcm,sr=sf.read(src,dtype='float32',always_2d=True);duration=c['pre']+p['duration'] if key.startswith('a') else p['duration'] if key.startswith('bEntry') else c['post']
            start=p['start']-c['pre'] if key.startswith('a') else p['window']['start'] if key.startswith('bEntry') else p['window']['end']
            expected=round((start+duration)*44100)-round(start*44100)
            if sr!=44100 or pcm.shape!=(expected,2) or not np.isfinite(pcm).all():raise ValueError('native clip clock/format changed')
            target=output/(c['id']+'-'+key+src.suffix);shutil.copy2(src,target);assets[key]=dict(a,url='/big-step-cut-audio/'+target.name)
        c['assets']=assets;cases.append(c)
    identity=dict(selectionSha256=sha(root/'selection.json'),boundSelectionSha256=sha(root/'selection-bound.json'),nativePackSha256=sha(root/'source-audio/half-double-native.json'),rendererSha256=sha(pathlib.Path(__file__).with_name('render_half_double_sources.py')),packagerSha256=sha(pathlib.Path(__file__)),selectorSha256=sha(pathlib.Path(__file__).with_name('prepare_big_step_cut.ts')),explorationSha256=sha(pathlib.Path(__file__).with_name('explore_big_step_cut.py')),cases=cases)
    pack=dict(schema='harbeat.big-step-cut-pack.v1',selectionSha256=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),cases=cases,audit=dict(selection=selection['audit']),rendering='Identical six original-speed source clips. Reference begins original fade at fixed section candidate; treatment exchanges accompaniment at that point with5ms edge. Original vocal gain/EQ/source scheduling unchanged.',limitation='3distinct pairs/6tracks; model section/downbeat and VAD/RMS proxies remain provisional. This tests accompaniment cut, not instantaneous full-mix vocal cut, extra effects or general genre rules.')
    raw=json.dumps(pack,ensure_ascii=False,indent=2)+'\n';(root/'pack.json').write_text(raw);(web/'big-step-cut-data.json').write_text(raw);(root/'preparation-identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n');print('bound',len(cases),'cases /',sum(len(c['assets']) for c in cases),'unchanged native clips')
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('root',type=pathlib.Path);a.add_argument('web',type=pathlib.Path);v=a.parse_args();package(v.root,v.web)
