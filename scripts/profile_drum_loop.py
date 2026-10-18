"""Measure frozen outgoing drum windows; no listening or cue search."""
import argparse,json,pathlib,subprocess,numpy as np
from render_melody_overlap import checked_source,sha,SR
from drum_loop_audio import rms,cv,classify_profile,choose_source_bar

def profile(data,nas):
 tracks={t['id']:t for t in data['tracks']};cache={};rows=[]
 for c in data['cases']:
  p=c['plan'];t=tracks[p['from']];v=t['provenance'];mp=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(mp.read_text());assets=m['assets'];a=assets['stems']['drums']
  if assets['master']['sha256']!=v['masterSha256'] or m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId']:raise ValueError('source binding mismatch')
  if a['channels']!=2 or a['sample_rate_hz']!=SR:raise ValueError('drum format unsupported')
  if t['id'] not in cache:cache[t['id']]=checked_source(nas,a)
  start=p['start']-c['pre'];duration=c['pre']+p['duration'];raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-ss',str(start),'-t',str(duration),'-i',str(cache[t['id']]),'-f','f32le','-ar',str(SR),'-ac','2','pipe:1']);pcm=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
  sample=lambda s,e:pcm[max(0,round((s-start)*SR)):min(len(pcm),round((e-start)*SR))]
  result={'caseId':c['id'],'aTitle':c['aTitle'],'sourceVerification':{'runId':v['runId'],'masterSha256':v['masterSha256'],'manifestSha256':sha(mp),'drumSha256':a['sha256']},'eligible':False}
  bars=t['bars'];last=next((i for i,b in enumerate(bars) if abs(b['end']-p['end'])<=.065),None)
  if last is None or last<1:rows.append({**result,'reason':'no final measured bars'});continue
  previous,final=bars[last-1],bars[last]
  if not all(b['valid'] and len(b['beats'])==4 for b in [previous,final]) or previous['start']<p['start'] or abs(previous['end']-final['start'])>.001:rows.append({**result,'reason':'target bars unavailable'});continue
  targets=[{**previous},{**final,'end':p['end']}];apply_start=previous['start'];earlier=[b for b in bars if b['valid'] and len(b['beats'])==4 and b['start']>=start and b['end']<=apply_start+.000001]
  if not earlier:rows.append({**result,'reason':'no earlier source bar'});continue
  measure=lambda b:{'rms':rms(sample(b['start'],b['end'])),'beatRms':[rms(sample(s,e)) for s,e in zip(b['beats'],b['beats'][1:]+[b['end']])]}
  ev=[measure(b) for b in earlier];early=ev[-2:];target=[measure(b) for b in targets];early_beats=[x for e in early for x in e['beatRms']];target_beats=[x for e in target for x in e['beatRms']];threshold=max(.005,.25*float(np.median(early_beats)))
  early_rms=float(np.sqrt(np.mean([e['rms']**2 for e in early])));target_rms=float(np.sqrt(np.mean([e['rms']**2 for e in target])));early_active=float(np.mean(np.array(early_beats)>=threshold));target_active=float(np.mean(np.array(target_beats)>=threshold));category=classify_profile(early_rms,target_rms,early_active,target_active,cv(target_beats))
  source=choose_source_bar(earlier,ev,apply_start,threshold);metrics={'earlyRms':early_rms,'targetRms':target_rms,'ratio':target_rms/max(early_rms,1e-12),'earlyActive':early_active,'targetActive':target_active,'targetBeatCv':cv(target_beats),'activeThreshold':threshold,'earlierBars':earlier,'earlierEvidence':ev,'targetBarsMeasured':[previous,final],'targetEvidence':target,'measuredFinalEnd':final['end'],'frozenFinalEnd':p['end'],'basis':'source drum RMS/activity acoustic proxy, not validated groove quality'}
  if not source or not category:rows.append({**result,'category':category,'metrics':metrics,'reason':'no stable earlier loop' if not source else 'neither thinning nor stable proxy'});continue
  b=earlier[source['index']];errors=[max(abs((beat-b['start'])/(b['end']-b['start'])*(tbar['end']-tbar['start'])+tbar['start']-tbeat) for beat,tbeat in zip(b['beats'],tbar['beats'])) for tbar in targets]
  metrics['loopBeatMappingErrorSec']=errors
  if max(errors)>.035:rows.append({**result,'category':category,'metrics':metrics,'reason':'loop beat mapping over35ms'});continue
  loop={'sourceStart':b['start'],'sourceEnd':b['end'],'applyStart':apply_start-p['start'],'applyEnd':p['duration'],'targetBars':[{'start':b['start']-p['start'],'end':b['end']-p['start']} for b in targets],'category':category,'metrics':metrics}
  rows.append({**result,'eligible':True,'category':category,'loop':loop,'metrics':metrics});print('profiled',c['aTitle'],category,metrics['ratio'],flush=True)
 return rows
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--input',type=pathlib.Path,required=True);a.add_argument('--nas',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);x=a.parse_args();x.output.write_text(json.dumps(profile(json.loads(x.input.read_text()),x.nas),ensure_ascii=False,indent=2)+'\n')
