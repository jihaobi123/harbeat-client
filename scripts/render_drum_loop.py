"""Render synchronized source clips and A-only drum replacement; never mix two songs offline."""
import argparse,json,pathlib,hashlib,subprocess,numpy as np
from render_melody_overlap import checked_source,sha,write_asset,stretch_layers,SR
from render_bass_coverage import stretch_pair
from drum_loop_audio import build_loop_drums,rms

def write(path,pcm):
 a=write_asset(path,pcm);a['url']='/drum-loop-audio/'+pathlib.Path(a['url']).name;return a

def decode(path):
 return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(path),'-f','f32le','-ar',str(SR),'-ac','2','pipe:1']),dtype='<f4').reshape(-1,2)

def render(selection,nas,out):
 raw=selection.read_bytes();d=json.loads(raw);out.mkdir(parents=True,exist_ok=True);a_ids={c['plan']['from'] for c in d['cases']};expected={}
 for c in d['cases']:
  for side,tid in [('a',c['plan']['from']),('b',c['plan']['to'])]:
   prev=c['sourceVerification'][side];expected.setdefault(tid,{})['bass']=prev['bassSha256']
  expected[c['plan']['from']]['drums']=c['drumProfileVerification']['drumSha256']
 sources={};evidence={}
 for t in d['tracks']:
  v=t['provenance'];mp=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';m=json.loads(mp.read_text());a=m['assets'];assets=[a['master'],a['stems']['bass']]+([a['stems']['drums']] if t['id'] in a_ids else [])
  if m['track_id']!=t['id'] or m['analysis_run_id']!=v['runId'] or a['master']['sha256']!=v['masterSha256'] or any(a['stems'][k]['sha256']!=value for k,value in expected[t['id']].items()):raise ValueError('source binding mismatch')
  if any(x['channels']!=2 for x in assets) or assets[0]['sample_rate_hz'] not in [44100,48000] or any(x['sample_rate_hz']!=SR for x in assets[1:]):raise ValueError('unsupported source format')
  sources[t['id']]=[checked_source(nas,x) for x in assets];evidence[t['id']]={'runId':v['runId'],'manifestSha256':sha(mp),'masterSha256':a['master']['sha256'],'bassSha256':a['stems']['bass']['sha256'],**({'drumSha256':a['stems']['drums']['sha256']} if t['id'] in a_ids else {})};print('verified',t['title'],flush=True)
 cases=[]
 for c in d['cases']:
  p=c['plan'];x=c['loop'];start=p['start']-c['pre'];length=c['pre']+p['duration'];pcm=stretch_layers(sources[p['from']],start,length,1);drums=pcm[:,4:6]
  frame=lambda t:round((t-start)*SR);source_range=(frame(x['sourceStart']),frame(x['sourceEnd']));targets=[(frame(p['start']+b['start']),frame(p['start']+b['end'])) for b in x['targetBars']]
  if abs(targets[-1][1]-len(pcm))>1:raise ValueError('frozen exit frame mismatch')
  targets[-1]=(targets[-1][0],len(pcm));loop=build_loop_drums(drums,source_range,targets);prefix=targets[0][0]
  if not np.array_equal(drums[:prefix],loop[:prefix]):raise ValueError('changed samples outside replacement')
  assets={}
  for key,values in [('aMaster',pcm[:,:2]),('aBass',pcm[:,2:4]),('aDrum',drums),('aLoopDrum',loop)]:assets[key]=write(out/(c['id']+'-'+key+'.flac'),values)
  natural_decoded=decode(out/pathlib.Path(assets['aDrum']['url']).name);loop_decoded=decode(out/pathlib.Path(assets['aLoopDrum']['url']).name);error=float(np.max(np.abs(natural_decoded[:prefix]-loop_decoded[:prefix]))) if prefix else 0
  if error>1e-6:raise ValueError('encoded drum corrections diverge before target')
  for part,s,duration,rate in [('bEntry',p['window']['start'],p['duration'],p['rate']),('bBody',p['window']['end'],c['post'],1)]:
   bp=stretch_pair(sources[p['to']][:2],s,duration,rate)
   for j,name in enumerate(['Master','Bass']):assets[part+name]=write(out/(c['id']+'-'+part+name+'.flac'),bp[:,2*j:2*j+2])
  cases.append({**c,'assets':assets,'sourceVerification':{'a':evidence[p['from']],'b':evidence[p['to']]},'drumRendering':{'sourceFrames':source_range,'targetFrames':targets,'entryFadeFrames':221,'internalSeamBridgeFrames':32,'sameSourceBarEachTarget':True,'outsideTargetRawPcmIdentical':True,'outsideTargetDecodedMaxError':error,'naturalTargetRms':rms(drums[prefix:]),'loopTargetRms':rms(loop[prefix:]),'method':'each copy uses same source bar with WSOLA ratio sourceFrames/targetFrames; no arm-specific normalization'}});print('rendered',c['id'],c['aTitle'],'outsideError',error,flush=True)
 pack={'schema':'harbeat.drum-loop-pack.v1','selectionSha256':hashlib.sha256(raw).hexdigest(),'cases':cases,'audit':d['audit'],'rendering':'A master/bass/drums jointly extracted on six channels; B master/bass on four channels at frozen entry rate and original native takeover','limitation':'Both arms share new source clips; texture may differ from prior previews. Drum separation can retain bleed; loop stretching, entry blend and seam smoothing can affect transients. Gain curves fixed; loudness and limiter response may differ.'};(out/'drum-loop-data.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');print('finished',len(cases),'cases',sum(a['bytes'] for c in cases for a in c['assets'].values()),'bytes',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selection',type=pathlib.Path,required=True);p.add_argument('--nas',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();render(a.selection,a.nas,a.output)
