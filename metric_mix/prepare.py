"""Trusted cue validation and NAS-only preparation. Run fixed program with JSON stdin."""
import hashlib,json,math,pathlib,re,subprocess,sys,tempfile
import numpy as np
import soundfile as sf
from .policy import choose_method,POLICY
from .features import describe,render_stats
from .render import mix_candidates
SR=44100

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def bound(t):
 p=t.get('provenance') or {};a=t.get('alignment') or {};s=a.get('source') or {};v=t.get('preprocessing') or {};vad=v.get('vocalActivity') or {};vs=vad.get('source') or {}
 if any(not re.fullmatch('[a-f0-9]{64}',str(p.get(k,''))) or s.get(k)!=p.get(k) for k in ['masterSha256','reportSha256','vocalSha256']) or s.get('reportId')!=t.get('reportId') or v.get('reportId')!=t.get('reportId') or v.get('masterSha256')!=p.get('masterSha256') or v.get('reportSha256')!=p.get('reportSha256') or not v.get('bindingChecks') or not all(x is True for x in v['bindingChecks'].values()):raise ValueError('来源或报告绑定不一致')
 if vad.get('status')!='ready' or vad.get('unit')!='ms' or vad.get('time_origin')!='master_audio_start' or any(vs.get(k)!=x for k,x in [('track_id',t['id']),('analysis_run_id',p.get('runId')),('vocal_sha256',p.get('vocalSha256'))]):raise ValueError('人声依据缺失或来源不一致')
 intervals=vad.get('intervals',[])
 if [[x['start_ms']/1000,x['end_ms']/1000] for x in intervals]!=t.get('vocals'):raise ValueError('人声区间与报告不一致')

def local_bars(t,start,end,count):
 rows=t['alignment']['bars'];index=next((i for i,r in enumerate(rows) if abs(r['start']-start)<=.065),None)
 if index is None:raise ValueError('缺少起始实测小节')
 bars=rows[index:index+count]
 if len(bars)!=count or abs(bars[-1]['end']-end)>.065:raise ValueError('缺少完整小节')
 for i,r in enumerate(bars):
  values=[r['start'],r['end'],*r['beats']]
  if not r['valid'] or len(r['beats'])!=4 or not all(math.isfinite(x) for x in values) or abs(r['beats'][0]-r['start'])>.001 or any(y<=x for x,y in zip(r['beats'],r['beats'][1:])) or r['beats'][-1]>=r['end'] or i and abs(bars[i-1]['end']-r['start'])>.001:raise ValueError('小节证据无效')
 return bars

def power(t,start,end):
 sums=np.zeros(3);cursor=start
 for f in t['alignment']['bandFrames']:
  s,e=max(start,f['start']),min(end,f['end'])
  if e<=s:continue
  if abs(s-cursor)>.005:raise ValueError('频段证据不连续')
  values=[f[k] for k in ['low','mid','high']]
  if any(v is not None and not math.isfinite(v) for v in values):raise ValueError('频段证据无效')
  sums+=np.array([0 if v is None else 10**(v/10) for v in values])*(e-s);cursor=e
 if cursor<end-.005:raise ValueError('频段证据不完整')
 return sums/(end-start)

def fraction(intervals,s,e,pad=0):
 spans=sorted((max(s,a-pad),min(e,b+pad)) for a,b in intervals if a-pad<e and b+pad>s);last=s;total=0
 for a,b in spans:total+=max(0,b-max(a,last));last=max(last,b)
 return total/(e-s)

def eq_controls(a,b,p):
 d=p['duration'];av=fraction(a['vocals'],p['start'],p['end'],.3);bv=fraction(b['vocals'],p['bStart'],p['bEnd'],.3);duck=av*d>=.5 and av>=.05 and bv*(p['bEnd']-p['bStart'])>=.5 and bv>=.05;template={'a':[-9,0,-1.4],'b':[-7,-5 if duck else 0,1.2]};out={'a':[],'b':[]};n=max(1,math.ceil(d/.25))
 def activity(t,s,e):return sum(max(0,min(e,x['tailEnd'])-max(s,x['start'])) for x in t['alignment'].get('phrases',[]))/(e-s)
 for i in range(n+1):
  t=d*i/n;x=t/d;center=min(d-.001,max(.001,t));l=max(0,center-.25);r=min(d,center+.25);pa=power(a,p['start']+l,p['start']+r);pb=power(b,p['bStart']+l*p['rate'],min(p['bEnd'],p['bStart']+r*p['rate']));targets={k:np.array(v,dtype=float) for k,v in template.items()};weight=4*x*(1-x)
  for j in [0,2]:
   aa=pa[j]*10**(template['a'][j]/10);bb=pb[j]*10**(template['b'][j]/10);ratio=10*np.log10((aa+1e-12)/(bb+1e-12))
   if aa+bb>1e-10:targets['a'][j]-=weight*np.clip((ratio-3)*.35,0,3);targets['b'][j]-=weight*np.clip((-ratio-3)*.35,0,3)
  va=np.clip(activity(a,p['start']+l,p['start']+r),0,1);vb=np.clip(activity(b,p['bStart']+l*p['rate'],p['bStart']+r*p['rate']),0,1);targets['b'][1]+=weight*(2-4*va*vb if duck else -2*va*vb)
  for side in ['a','b']:
   prev=out[side][-1] if out[side] else None;values=[prev[k]+float(np.clip(targets[side][j]-prev[k],-3*(t-prev['t']),3*(t-prev['t']))) if prev else template[side][j] for j,k in enumerate(['low','mid','high'])];out[side].append(dict(t=t,**dict(zip(['low','mid','high'],values))))
 return out

def validated_plan(a,b,window_id,start):
 bound(a);bound(b)
 if not isinstance(start,(int,float)) or isinstance(start,bool) or not math.isfinite(start):raise ValueError('接点无效')
 w=next((x for x in b['windows'] if x['id']==window_id),None)
 if not w or a['id'] not in w['variants']:raise ValueError('进入窗口不存在或无匹配速度')
 v=w['variants'][a['id']];d=v['duration'];rate=v['rate'];end=start+d
 if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in [start,end,d,rate,w['start'],w['end'],a['duration'],b['duration']]) or not 1<=d<=32 or not .95<=rate<=1.05 or start<0 or end>=a['duration']-.1 or w['start']<0 or b['duration']-w['end']<12 or abs((w['end']-w['start'])/rate-d)>.002 or w['bars'] not in [2,4,8]:raise ValueError('速度、时长或素材范围超出当前规则')
 aa=local_bars(a,start,end,w['bars']);bb=local_bars(b,w['start'],w['end'],w['bars']);fa=[x for bar in aa for x in bar['beats']]+[aa[-1]['end']];fb=[x for bar in bb for x in bar['beats']]+[bb[-1]['end']];err=max(abs(x-(start+(y-w['start'])/rate)) for x,y in zip(fa,fb))
 if err>.065:raise ValueError('局部拍点偏差超过65ms')
 last,prev=aa[-1],aa[-2];p={'from':a['id'],'to':b['id'],'windowId':window_id,'start':start,'end':end,'duration':d,'rate':rate,'bStart':w['start'],'bEnd':w['end'],'lastBarStart':last['start']-start,'bassTiming':{'duckStart':prev['start']-start,'swapStart':prev['beats'][3]-start,'swapEnd':last['start']-start},'restore':d-min(d,120/a['bpm']),'beatErrorMs':err*1000,'vocalExit':None,'vocalBenefit':0}
 p['eq']=eq_controls(a,b,p);return p

def source_assets(t,nas,reports):
 p=t['provenance'];tid=t['id'];run=p['runId']
 if not all(re.fullmatch('[A-Za-z0-9_-]{1,160}',x) for x in [tid,run]):raise ValueError('源标识无效')
 folder=nas/'published/tracks'/tid/'runs'/run;mf=folder/'manifest.json';m=json.loads(mf.read_text());success=json.loads((folder/'_SUCCESS.json').read_text());rp=reports/(t['reportId']+'.json')
 if sha(mf)!=success['manifest_sha256'] or sha(rp)!=p['reportSha256'] or m['track_id']!=tid or m['analysis_run_id']!=run or m['assets']['master']['sha256']!=p['masterSha256'] or m['assets']['stems']['vocals']['sha256']!=p['vocalSha256']:raise ValueError('NAS来源或报告指纹不一致')
 assets={'master':m['assets']['master'],**m['assets']['stems']};paths={};proof={}
 for key in ['master','bass','other','drums','vocals']:
  v=assets.get(key)
  if not v:
   if key=='master':raise ValueError('原曲缺失')
   continue
  path=(nas/v['storage_key']).resolve()
  if nas.resolve() not in path.parents or not path.is_file() or sha(path)!=v['sha256']:raise ValueError('NAS音频指纹不一致')
  info=sf.info(path)
  if info.channels!=2 or abs(info.duration-t['duration'])>.05:raise ValueError('原曲与分轨时长或声道不一致')
  paths[key]=path;proof[key]={'sha256':v['sha256'],'duration':info.duration,'sampleRate':info.samplerate,'channels':info.channels}
 return paths,{'trackId':tid,'runId':run,'manifestSha256':sha(mf),'reportSha256':p['reportSha256'],'assets':proof}

def read_segment(path,start,duration):
 n=round(duration*SR)
 if path.suffix.lower() in ['.wav','.flac']:
  with sf.SoundFile(path) as f:
   if f.samplerate==SR:f.seek(round(start*SR));x=f.read(n,dtype='float32',always_2d=True)
   else:x=None
  if x is not None:
   if len(x)!=n:raise ValueError('分轨观测范围不足')
   return x
 raw=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(start),'-i',str(path),'-t',str(duration+.02),'-ar',str(SR),'-ac','2','-f','f32le','pipe:1'],check=True,stdout=subprocess.PIPE,timeout=90).stdout;x=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
 if len(x)<n:raise ValueError('原曲观测范围不足')
 return x[:n]

def joint_stretch(sources,start,duration,rate):
 keys=list(sources);source_duration=duration*rate+(.5 if abs(rate-1)>1e-12 else 0);x=np.concatenate([read_segment(sources[k],start,source_duration) for k in keys],axis=1);n=round(duration*SR)
 if abs(rate-1)<1e-12:y=x
 else:
  cmd=['ffmpeg','-nostdin','-v','error','-f','f32le','-ar',str(SR),'-ac',str(x.shape[1]),'-i','pipe:0','-af','atempo='+str(rate),'-f','f32le','pipe:1'];raw=subprocess.run(cmd,input=x.astype('<f4').tobytes(),stdout=subprocess.PIPE,check=True,timeout=90).stdout;y=np.frombuffer(raw,dtype='<f4').reshape(-1,x.shape[1])
 if len(y)<n:raise ValueError('联合变速输出覆盖不足')
 y=y[:n]
 return {k:y[:,i*2:i*2+2] for i,k in enumerate(keys)}

def vocal_exit(a,b,stems,p):
 # Require both report activity and fine isolated-vocal energy to be quiet afterwards.
 if 'vocals' not in stems['a'] or 'vocals' not in stems['b']:return
 d=p['duration'];step=.05;rows=[];v=stems['a']['vocals'];rms=[]
 for i in range(0,len(v),round(step*SR)):rms.append(float(np.sqrt(np.mean(v[i:i+round(step*SR)].astype(float)**2))))
 gate=max(np.percentile(rms,95)*.008,10**(-70/20));activity=[(p['start']+i*step,p['start']+(i+1)*step) for i,value in enumerate(rms) if value>=gate]+[tuple(x) for x in a['vocals'] if x[0]<p['end'] and x[1]>p['start']]
 if not activity:return
 tail=max(min(p['end'],e) for s,e in activity);relative=tail-p['start'];safe=tail+.08
 beat=next((beat for bar in a['alignment']['bars'] for beat in bar['beats'] if beat>=safe and beat+.2+.25<=p['end']),None)
 if beat is None or relative<d*.2 or p['end']-tail<.25:return
 fade_end=beat-p['start']+.2;b_safe=p['bStart']+(fade_end+.08)*p['rate']
 if any(s<b_safe and e>p['bStart']-.08 for s,e in b['vocals']):return
 # Measured B vocal RMS also protects soft, unlabelled material in the held region.
 bv=stems['b']['vocals'];before=bv[:round((fade_end+.08)*SR)]
 if len(before) and np.sqrt(np.mean(before.astype(float)**2))>10**(-45/20):return
 p['vocalExit']={'tailEnd':relative,'fadeStart':beat-p['start'],'fadeEnd':fade_end,'quietAfter':p['end']-tail,'basis':'VAD union fine isolated-vocal RMS;acoustic candidate,not semantic lyric endpoint'};p['vocalBenefit']=min(1,relative/d)

def worker_version(root=None):
 h=hashlib.sha256()
 for p in sorted((pathlib.Path(root) if root is not None else pathlib.Path(__file__).parent).glob('*.py')):
  if not p.name.startswith('.'):h.update(p.name.encode()+b'\0'+p.read_bytes()+b'\0')
 return h.hexdigest()

def prepare(job,out,nas=pathlib.Path('/mnt/nas/harbeat/preprocess'),reports=pathlib.Path('/mnt/nas/harbeat/data/analysis-platform/reports')):
 if job.get('codeVersion') and job['codeVersion']!=worker_version():raise ValueError('执行器代码版本不一致')
 a,b=job['a'],job['b'];p=validated_plan(a,b,job['windowId'],job['start']);sa,pa=source_assets(a,nas,reports);sb,pb=source_assets(b,nas,reports);stems={'a':joint_stretch(sa,p['start'],p['duration'],1),'b':joint_stretch(sb,p['bStart'],p['duration'],p['rate'])};p['body']=read_segment(sb['master'],p['bEnd'],.008);vocal_exit(a,b,stems,p);metrics=describe(stems,p,SR);outputs=mix_candidates(stems,p,SR);stats={k:render_stats(v[:round(p['duration']*SR)],SR) for k,v in outputs.items()};decision=choose_method(metrics,stats);out.mkdir(parents=True,exist_ok=True);assets={}
 for k,v in outputs.items():
  target=out/(k+'.wav');sf.write(target,v,SR,subtype='FLOAT');assets[k]={'sha256':sha(target),'bytes':target.stat().st_size,'duration':len(v)/SR,'sampleRate':SR,'channels':2}
 p.pop('body');result={'schema':'harbeat.metric-mix-result.v1','policyVersion':POLICY['version'],'workerCodeVersion':worker_version(),'plan':p,'metrics':metrics,'stats':stats,'decision':decision,'assets':assets,'sourceProof':{'a':pa,'b':pb},'rendering':'All master and stems jointly aligned. Same existing dynamic-EQ gain points;64-sample coefficient blocks. Signed corrections,common0.60gain,floatWAV,no per-method normalization;B8ms native tail for stitching. Not bit-identical to old browser filters.','limitations':decision['limitations']};(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')));return result

if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='cleanup':
  import shutil
  identity=sys.argv[2]
  if not re.fullmatch('[a-f0-9]{64}',identity):raise ValueError('invalid job')
  target=pathlib.Path('/tmp/harbeat-metric-mix')/identity
  if target.is_dir():shutil.rmtree(target)
  raise SystemExit(0)
 job=json.load(sys.stdin);identity=job.pop('jobId')
 if not re.fullmatch('[a-f0-9]{64}',identity):raise ValueError('invalid job')
 out=pathlib.Path('/tmp/harbeat-metric-mix')/identity;prepare(job,out);print(json.dumps({'jobId':identity,'complete':True}))
