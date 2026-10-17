"""Prepare synchronized master/bass source clips; never mix two songs offline."""
import argparse,hashlib,json,pathlib,subprocess
import numpy as np
from render_melody_overlap import sha,checked_source,write_asset,SR

def validate_formats(assets):
 if len(assets)!=2 or any(x['channels']!=2 for x in assets) or assets[0]['sample_rate_hz'] not in (44100,48000) or assets[1]['sample_rate_hz']!=44100:raise ValueError('unsupported source format')

def stretch_pair(paths,start,duration,rate):
 if not all(np.isfinite([start,duration,rate])) or start<0 or duration<=0 or rate<=0:raise ValueError('invalid source range')
 cmd=['ffmpeg','-v','error','-nostdin','-threads','1']
 for p in paths:cmd+=['-ss',str(start),'-t',str((duration+1)*rate),'-i',str(p)]
 filters='[0:a]aresample=44100,aformat=sample_fmts=flt:channel_layouts=stereo[m];[1:a]aresample=44100,aformat=sample_fmts=flt:channel_layouts=stereo[b];[m][b]amerge=inputs=2,atempo=%s[out]'%rate
 cmd+=['-filter_complex',filters,'-map','[out]','-f','f32le','-acodec','pcm_f32le','pipe:1']
 pcm=np.frombuffer(subprocess.check_output(cmd),dtype='<f4').reshape(-1,4);frames=round(duration*SR)
 if len(pcm)<frames or not np.isfinite(pcm).all():raise ValueError('incomplete/nonfinite source audio')
 return pcm[:frames].copy()

def write_bass_asset(path,pcm):
 a=write_asset(path,pcm);a['url']='/coverage-audio/'+pathlib.Path(a['url']).name;return a

def render(selection,nas,out):
 raw=selection.read_bytes();data=json.loads(raw);out.mkdir(parents=True,exist_ok=True);sources={};evidence={}
 for t in data['tracks']:
  v=t['provenance'];p=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';d=json.loads(p.read_text());a=d['assets'];assets=[a['master'],a['stems']['bass']]
  if d['track_id']!=t['id'] or d['analysis_run_id']!=v['runId'] or assets[0]['sha256']!=v['masterSha256'] or assets[1]['sha256']!=t['bassSha256']:raise ValueError('source binding mismatch')
  validate_formats(assets)
  sources[t['id']]=[checked_source(nas,x) for x in assets];evidence[t['id']]={'runId':v['runId'],'manifestSha256':sha(p),'masterSha256':assets[0]['sha256'],'bassSha256':assets[1]['sha256']}
  print('verified',t['title'],flush=True)
 cases=[]
 for c in data['cases']:
  p=c['plan'];assets={};levels={}
  for part,tid,start,duration,rate in [('a',p['from'],p['start']-c['pre'],c['pre']+p['duration'],1),('bEntry',p['to'],p['window']['start'],p['duration'],p['rate']),('bBody',p['to'],p['window']['end'],c['post'],1)]:
   pcm=stretch_pair(sources[tid],start,duration,rate)
   for i,name in enumerate(['Master','Bass']):assets[part+name]=write_bass_asset(out/(c['id']+'-'+part+'-'+name.lower()+'.flac'),pcm[:,2*i:2*i+2])
   bass=pcm[round(c['pre']*SR):,2:] if part=='a' else pcm[:,2:];levels[part]={'bassRms':float(np.sqrt(np.mean(bass.astype(np.float64)**2)))}
  if min(levels['a']['bassRms'],levels['bEntry']['bassRms'])<.005:raise ValueError('bass layer too quiet for a meaningful audition: '+c['id']+' '+json.dumps(levels))
  print('rendered',c['id'],levels,flush=True)
  cases.append({**c,'assets':assets,'levels':levels,'sourceVerification':{'a':evidence[p['from']],'b':evidence[p['to']]}})
 result={'schema':'harbeat.bass-generalization-pack.v1','selectionSha256':hashlib.sha256(raw).hexdigest(),'harmonicRelease':data['harmonicRelease'],'cases':cases,'audit':data.get('audit'),'rendering':'shared four-channel master/bass WSOLA at frozen rate; original native B body at frozen takeover','limitation':'All three current arms share identical new source clips. Four-channel WSOLA texture may differ from previous six-channel preview. Bass separation retains bleed; limiter responses may differ.'}
 (out/'bass-generalization-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('rendered',len(cases),'case; bytes',sum(a['bytes'] for c in cases for a in c['assets'].values()),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selection',type=pathlib.Path,required=True);p.add_argument('--nas',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();render(a.selection,a.nas,a.output)
