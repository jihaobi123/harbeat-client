"""Render synchronized source excerpts only; gain comparison happens in browser."""
import argparse,hashlib,json,pathlib,subprocess
import numpy as np
SR=44100

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def checked_source(root,asset):
 root=root.resolve();p=(root/asset['storage_key']).resolve()
 if root not in p.parents:raise ValueError('source outside NAS root')
 if sha(p)!=asset['sha256']:raise ValueError('source hash mismatch: '+str(p))
 return p

def stretch_layers(paths,start,duration,rate):
 if not all(np.isfinite([start,duration,rate])) or start<0 or duration<=0 or rate<=0:raise ValueError('invalid source range')
 cmd=['ffmpeg','-v','error','-nostdin','-threads','1']
 for p in paths:cmd+=['-ss',str(start),'-t',str((duration+1)*rate),'-i',str(p)]
 filters=';'.join('[%d:a]aresample=%d,aformat=sample_fmts=flt:channel_layouts=stereo[x%d]'%(i,SR,i) for i in range(3))
 filters+=';[x0][x1][x2]amerge=inputs=3,atempo=%s[out]'%rate
 cmd+=['-filter_complex',filters,'-map','[out]','-f','f32le','-acodec','pcm_f32le','pipe:1']
 data=np.frombuffer(subprocess.check_output(cmd),dtype='<f4').reshape(-1,6)
 frames=round(duration*SR)
 if len(data)<frames or not np.isfinite(data).all():raise ValueError('incomplete/nonfinite source audio')
 return data[:frames].copy()

def write_asset(path,data):
 if data.ndim!=2 or data.shape[1]!=2 or not len(data) or not np.isfinite(data).all():raise ValueError('invalid PCM')
 peak=float(np.max(np.abs(data)))
 if peak>=1:path=path.with_suffix('.wav')
 codec=['-c:a','pcm_f32le'] if peak>=1 else ['-c:a','flac','-sample_fmt','s32']
 subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-f','f32le','-ar',str(SR),'-ac','2','-i','pipe:0']+codec+[str(path)],input=data.astype('<f4').tobytes(),check=True)
 return {'url':'/melody-audio/'+path.name,'sha256':sha(path),'bytes':path.stat().st_size,'duration':len(data)/SR,'frames':len(data),'sampleRate':SR,'channels':2,'peak':peak}

def render(selection,nas,output):
 selection_bytes=selection.read_bytes();data=json.loads(selection_bytes);output.mkdir(parents=True,exist_ok=True)
 sources={};evidence={}
 for t in data['tracks']:
  v=t['provenance'];p=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';d=json.loads(p.read_text());a=d['assets']
  if d['track_id']!=t['id'] or d['analysis_run_id']!=v['runId'] or a['master']['sha256']!=v['masterSha256'] or a['stems']['vocals']['sha256']!=v['vocalSha256']:raise ValueError('source binding mismatch '+t['id'])
  assets=[a['master'],a['stems']['vocals'],a['stems']['drums']]
  if any(x['channels']!=2 or x['sample_rate_hz']!=SR for x in assets):raise ValueError('unsupported source format')
  sources[t['id']]=[checked_source(nas,x) for x in assets]
  evidence[t['id']]={'manifestSha256':sha(p),'runId':v['runId'],'masterSha256':assets[0]['sha256'],'vocalSha256':assets[1]['sha256'],'drumSha256':assets[2]['sha256']}
  print('verified',t['title'],flush=True)
 cases=[];skipped=list(data['skipped'])
 for c in data['cases']:
  p=c['plan'];assets={};levels={}
  for part,tid,start,duration,rate in [('a',p['from'],p['start']-c['pre'],c['pre']+p['duration'],1),('bEntry',p['to'],p['window']['start'],p['duration'],p['rate']),('bBody',p['to'],p['window']['end'],c['post'],1)]:
   pcm=stretch_layers(sources[tid],start,duration,rate)
   residual=pcm[:,:2]-pcm[:,2:4]-pcm[:,4:6]
   if part=='a':residual=residual[round(c['pre']*SR):]
   levels[part]={'melodyRms':float(np.sqrt(np.mean(residual.astype(np.float64)**2))),'basis':'master - vocals - drums; includes bass and separation residual'}
   for j,name in enumerate(['Master','Vocal','Drum']):assets[part+name]=write_asset(output/(c['id']+'-'+part+'-'+name.lower()+'.flac'),pcm[:,j*2:j*2+2])
  if min(levels['a']['melodyRms'],levels['bEntry']['melodyRms'])<.005:
   skipped.append({'id':c['id'],'reason':'residual melody/bass layer too quiet for this comparison','levels':levels});continue
  cases.append({**c,'assets':assets,'levels':levels,'sourceVerification':{'a':evidence[p['from']],'b':evidence[p['to']]}})
  print('rendered',c['id'],levels,flush=True)
 result={'schema':'harbeat.melody-overlap-pack.v1','selectionSha256':hashlib.sha256(selection_bytes).hexdigest(),'harmonicRelease':data['harmonicRelease'],'cases':cases,'skipped':skipped,'rendering':'shared six-channel WSOLA at original frozen rate; original native speed after takeover; short excerpts, no offline mix','limitation':'new multichannel reference render may differ from earlier single-master WSOLA texture; both current arms share identical assets'}
 (output/'melody-overlap-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('finished cases',len(cases),'bytes',sum(f.stat().st_size for f in output.glob('*.flac')),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selection',type=pathlib.Path,required=True);p.add_argument('--nas',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args();render(args.selection,args.nas,args.output)
