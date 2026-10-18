"""Render natural master/drum clips for a single independent rhythm timeline."""
import argparse,hashlib,json,pathlib
import numpy as np
try:
    from scripts.render_melody_yield import stretch_pair
    from scripts.render_melody_overlap import checked_source,sha,write_asset,SR
except ModuleNotFoundError:
    from render_melody_yield import stretch_pair
    from render_melody_overlap import checked_source,sha,write_asset,SR


def validate_case(c):
    p=c['plan'];values=[c['pre'],c['post'],c['bridgeStart'],p['start'],p['end'],p['duration'],p['rate'],p['window']['start'],p['window']['end']]
    if not all(np.isfinite(values)) or c['pre']<0 or c['post']<=0 or not 0<c['bridgeStart']<p['duration'] or p['rate']<=0 or p['start']<c['pre'] or abs(p['end']-p['start']-p['duration'])>.002 or abs((p['window']['end']-p['window']['start'])/p['rate']-p['duration'])>.002:
        raise ValueError('invalid frozen source range or drum bridge boundary')


def describe_drums(x,bridge_start):
    def rms(y):return float(np.sqrt(np.mean(y.astype('float64')**2))) if len(y) else None
    frame=round(bridge_start*SR);early=rms(x[:frame]);late=rms(x[frame:]);return dict(rms=rms(x),beforeBridgeRms=early,bridgeRms=late,bridgeToEarlierRatio=late/early if early else None,basis='Natural decoded drum stem RMS only; not perceived mixed loudness, groove quality or validated suitability')


def render(selection,nas,reports,output):
    raw=selection.read_bytes();d=json.loads(raw);output.mkdir(parents=True,exist_ok=True);sources={};evidence={}
    for t in d['tracks']:
        v=t['provenance'];m=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';doc=json.loads(m.read_text());success=json.loads((m.parent/'_SUCCESS.json').read_text());assets=doc['assets'];report=reports/(t['reportId']+'.json')
        if not report.exists() or sha(report)!=v['reportSha256']:raise ValueError('frozen report changed or unavailable')
        if doc['track_id']!=t['id'] or doc['analysis_run_id']!=v['runId'] or sha(m)!=t['manifestSha256'] or sha(m)!=success['manifest_sha256'] or assets['master']['sha256']!=v['masterSha256'] or assets['stems']['vocals']['sha256']!=v['vocalSha256'] or assets['stems']['drums']['sha256']!=t['drumSha256']:raise ValueError('source binding mismatch')
        entries=[assets['master'],assets['stems']['drums']]
        if any(a['channels']!=2 or a['sample_rate_hz']!=SR for a in entries):raise ValueError('unsupported source format')
        sources[t['id']]=[checked_source(nas,a) for a in entries]
        evidence[t['id']]=dict(v,reportId=report.stem,manifestSha256=sha(m),drumSha256=entries[1]['sha256'],drumStorageKey=entries[1]['storage_key'])
        print('verified',t['title'],flush=True)
    cases=[];skipped=[]
    for c in d['cases']:
        validate_case(c);p=c['plan'];assets={};features={}
        for part,tid,start,duration,rate in [('a',p['from'],p['start']-c['pre'],c['pre']+p['duration'],1),('bEntry',p['to'],p['window']['start'],p['duration'],p['rate']),('bBody',p['to'],p['window']['end'],c['post'],1)]:
            pcm=stretch_pair(sources[tid],start,duration,rate)
            features[part]=describe_drums(pcm[round(c['pre']*SR):,2:] if part=='a' else pcm[:,2:],c['bridgeStart'])
            for j,name in enumerate(['Master','Drums']):
                asset=write_asset(output/(c['id']+'-'+part+name+'.flac'),pcm[:,2*j:2*j+2]);asset['url']='/rhythm-bridge-audio/'+pathlib.Path(asset['url']).name;assets[part+name]=asset
        if min(features['a']['rms'],features['bEntry']['rms'])<.005:
            skipped.append(dict(id=c['id'],reason='drums too quiet for this trial; frozen cue retained',features=features));continue
        cases.append(dict(c,assets=assets,features=features,sourceVerification={side:evidence[p[key]] for side,key in [('a','from'),('b','to')]}))
        print('rendered',c['aTitle'],c['bTitle'],flush=True)
    pack=dict(schema='harbeat.rhythm-bridge-pack.v1',selectionSha256=hashlib.sha256(raw).hexdigest(),cases=cases,skipped=skipped,sourcePackSha256=d['sourcePackSha256'],rendering='Master and actual natural drums jointly stretched as four channels; reference=master; treatment changes only complementary drum correction.',limitation='Whole drums may contain separation bleed. No repeated audio or per-arm normalization. Original master non-drum fades, cues, rate, vocal checks and EQ unchanged. Shared four-channel WSOLA can differ from prior other-stem or single-master rendering; both current arms share assets. No universal eligibility rule.')
    (output/'rhythm-bridge-data.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');print('complete',len(cases),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['selection','nas','reports','output']:p.add_argument('--'+k,type=pathlib.Path,required=True)
    a=p.parse_args();render(a.selection,a.nas,a.reports,a.output)
