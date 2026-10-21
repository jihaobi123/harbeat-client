"""Bounded public render requests over the already-public listening library."""
import concurrent.futures,hashlib,json,os,pathlib,re,shutil,subprocess,threading,time
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse
from .policy import POLICY
from .prepare import validated_plan,sha,worker_version
ROOT=pathlib.Path(os.environ.get('METRIC_MIX_ROOT','/srv/harbeat-listen/metric-mix'))
SITE=pathlib.Path(os.environ.get('LISTEN_SITE_ROOT','/srv/harbeat-listen'))
ORIGIN=os.environ.get('LISTEN_PUBLIC_ORIGIN','https://8.136.120.255')
REMOTE='mark@100.87.142.21';REMOTE_CODE='/home/mark/harbeat-metric-mix';REMOTE_PY='/home/mark/harbeat-analysis-venv/bin/python'
CODE_VERSION=worker_version()
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None);executor=concurrent.futures.ThreadPoolExecutor(max_workers=1);slots=threading.BoundedSemaphore(3);lock=threading.Lock();active=set();last_post={}

def identifier(x):
 if not isinstance(x,str) or not re.fullmatch('[A-Za-z0-9_-]{1,160}',x):raise ValueError('歌曲标识无效')
 return x

def trusted_request(data,site=SITE):
 if not isinstance(data,dict) or set(data)-{'from','to','windowId','start'}:raise ValueError('请求只能包含曲目、窗口和接点')
 a_id,b_id=identifier(data.get('from')),identifier(data.get('to'))
 if a_id==b_id:raise ValueError('请选择不同的下一首')
 release=(site/'current').resolve();index=json.loads((release/'library.json').read_text());rows={x['id']:x for x in index['tracks']};ready={x['id'] for x in index['tracks'] if x['playStatus']=='ready' and x['mixStatus']=='ready'}
 if index.get('schema')!='harbeat.continuous-library.v1' or len(rows)!=len(index['tracks']):raise ValueError('曲库索引无效')
 if a_id not in ready or b_id not in ready:raise ValueError('歌曲尚未准备好混音')
 tracks=[]
 for tid in [a_id,b_id]:
  detail=rows[tid].get('detailUrl','')
  if not isinstance(detail,str) or not re.fullmatch(r'(?:catalog/[A-Za-z0-9_-]{1,160}/)?details/'+re.escape(tid)+r'\.json',detail):raise ValueError('曲库资料路径无效')
  file=(release/detail).resolve()
  if release not in file.parents:raise ValueError('曲库路径无效')
  t=json.loads(file.read_text())['track']
  if t['id']!=tid:raise ValueError('曲库身份不一致')
  tracks.append(t)
 p=validated_plan(*tracks,data.get('windowId'),data.get('start'))
 # Bound transport size while retaining full source-bound vocal and grid evidence.
 a,b=tracks;a['windows']=[];b['windows']=[{**w,'variants':{a_id:w['variants'][a_id]}} for w in b['windows'] if w['id']==p['windowId']]
 job={'a':a,'b':b,'windowId':p['windowId'],'start':p['start'],'codeVersion':CODE_VERSION};job_id=hashlib.sha256(json.dumps(job,sort_keys=True,separators=(',',':')).encode()).hexdigest();job['jobId']=job_id;return job

def atomic(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.part');temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')));os.replace(temp,path)

def state_path(j):return ROOT/'state'/(j+'.json')
def cleanup_cache():
 cache=ROOT/'media';cache.mkdir(parents=True,exist_ok=True)
 folders=sorted((p for p in cache.iterdir() if p.is_dir() and re.fullmatch('[a-f0-9]{64}',p.name)),key=lambda p:p.stat().st_mtime)
 sizes={p:sum(f.stat().st_size for f in p.iterdir() if f.is_file()) for p in folders};total=sum(sizes.values())
 for p in folders:
  if total<=768*1024**2:break
  if p.name in active or total<=1024**3 and time.time()-p.stat().st_mtime<3600:continue
  # Only disposable outputs produced by this service, never library/NAS sources.
  shutil.rmtree(p);state_path(p.name).unlink(missing_ok=True);total-=sizes[p]
 if total>1024**3 or shutil.disk_usage(ROOT).free<4*1024**3:raise ValueError('缓存空间不足，请稍后重试')

def run(job):
 j=job['jobId'];stage=ROOT/'staging'/j;dest=ROOT/'media'/j
 try:
  atomic(state_path(j),{'id':j,'status':'running','message':'云端正在核验来源、分析分轨并准备交接…','createdAt':time.time()});cleanup_cache();stage.mkdir(parents=True,exist_ok=True)
  command=f'cd {REMOTE_CODE} && {REMOTE_PY} -m metric_mix.prepare'
  subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',REMOTE,command],input=json.dumps(job,separators=(',',':')).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=300)
  subprocess.run(['rsync','-a','--protect-args','-e','ssh -o BatchMode=yes -o ConnectTimeout=10',f'{REMOTE}:/tmp/harbeat-metric-mix/{j}/',str(stage)+'/'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
  result=json.loads((stage/'result.json').read_text())
  if result['schema']!='harbeat.metric-mix-result.v1' or result['policyVersion']!=POLICY['version'] or result.get('workerCodeVersion')!=CODE_VERSION:raise ValueError('结果版本不一致')
  for method,a in result['assets'].items():
   if method not in ['original','bass','filter','yield','vocal','bass_filter']:raise ValueError('未知处理方法')
   p=stage/(method+'.wav')
   if p.stat().st_size!=a['bytes'] or sha(p)!=a['sha256'] or not 1<=a['duration']<=33:raise ValueError('交接文件校验失败')
   a['url']=f'/listen/smart-media/{j}/{method}.wav'
  dest.parent.mkdir(parents=True,exist_ok=True)
  if dest.exists():shutil.rmtree(stage)
  else:os.replace(stage,dest)
  result.update(id=j,status='ready',createdAt=time.time(),codeVersion=CODE_VERSION);atomic(state_path(j),result)
  try:subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',REMOTE,command+' cleanup '+j],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
  except subprocess.SubprocessError:pass
 except Exception as e:
  # Diagnostic retained privately; never leak SSH/NAS paths into public response.
  private=ROOT/'private';private.mkdir(exist_ok=True);(private/(j+'.txt')).write_text(type(e).__name__+': '+str(e)+'\n'+getattr(e,'stderr',b'').decode(errors='replace')[-12000:]);atomic(state_path(j),{'id':j,'status':'failed','message':'本次云端准备未完成；当前歌曲继续播放，可以重新准备或换歌。','createdAt':time.time()})
 finally:
  if stage.exists():shutil.rmtree(stage)
  with lock:active.discard(j)
  slots.release()

@app.get('/health')
def health():return {'status':'ok','policyVersion':POLICY['version'],'codeVersion':CODE_VERSION,'queuedOrRunning':len(active)}

@app.get('/rules')
def rules():return {'policy':POLICY,'names':__import__('metric_mix.policy',fromlist=['NAMES']).NAMES}

@app.post('/jobs')
async def create(request:Request):
 if request.headers.get('origin')!=ORIGIN:raise HTTPException(403,'请从混音页面发起请求')
 raw=b''
 async for chunk in request.stream():
  if len(raw)+len(chunk)>8192:raise HTTPException(413,'请求过大')
  raw+=chunk
 try:job=trusted_request(json.loads(raw))
 except (ValueError,KeyError,TypeError,OSError):raise HTTPException(422,'曲目、接点或分析依据不符合当前规则，请重新准备或换歌。')
 j=job['jobId'];path=state_path(j)
 with lock:
  if path.exists():
   old=json.loads(path.read_text())
   if old['status']=='ready' and (ROOT/'media'/j).is_dir():return {'id':j,'status':'ready','cached':True}
  if j in active:return {'id':j,'status':'running'}
  if not slots.acquire(False):raise HTTPException(429,'云端正在准备其他交接，请稍后重试')
  active.add(j);atomic(path,{'id':j,'status':'queued','message':'已加入云端准备队列','createdAt':time.time()});executor.submit(run,job)
 return JSONResponse({'id':j,'status':'queued'},status_code=202)

@app.get('/jobs/{job_id}')
def get_job(job_id:str):
 if not re.fullmatch('[a-f0-9]{64}',job_id):raise HTTPException(404,'未找到交接记录')
 path=state_path(job_id)
 if not path.is_file():raise HTTPException(404,'交接记录已过期，请重新准备')
 return json.loads(path.read_text())

# JSON strategies have their own bounded queue and state. Existing /jobs stays
# compatible for old auditions and clients requesting rendered assets.
from .plan_gateway import PlanService,install_plan_routes
install_plan_routes(app,PlanService(ROOT/'plans',ORIGIN,lambda data:trusted_request(data)))
