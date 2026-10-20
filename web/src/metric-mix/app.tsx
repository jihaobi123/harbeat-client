import {useEffect,useRef,useState} from 'react'
import {createRoot} from 'react-dom/client'
import {TrackLibrary,readLibraryIndex,type LibraryEntry} from '../continuous/catalog'
import {loadJson} from '../phrase/load'
import {planContinuous} from '../continuous/beatAlignment'
import {initializeFromGesture} from '../continuous/activation'
import {MetricTransport} from './transport'
import type {Track,Plan} from '../realtime/planner'
import type {Prepared,Method} from './types'
import {canArm} from './plan'
import {mixNearby,nearbyPlan} from './nearby'
import {LOCAL_ORIGINAL,localOriginal,preloadOriginal} from './local-original'
import './style.css'
const base=new URL('/listen/',location.href),api='/listen/smart-api/'
const clock=(n:number)=>`${Math.floor(Math.max(0,n)/60)}:${String(Math.floor(Math.max(0,n)%60)).padStart(2,'0')}`
const pct=(v:number|null|undefined)=>v==null?'未知':v.toFixed(2)
function App(){
 const [entries,setEntries]=useState<LibraryEntry[]>([]),[from,setFrom]=useState(''),[to,setTo]=useState(''),[query,setQuery]=useState(''),[error,setError]=useState(''),[message,setMessage]=useState(''),[working,setWorking]=useState(false),[result,setResult]=useState<Prepared|null>(null),[method,setMethod]=useState<Method>('original'),[volume,setVolume]=useState(.85),[seek,setSeek]=useState<number|null>(null)
 const [,refresh]=useState(0),lib=useRef<TrackLibrary|null>(null),player=useRef<MetricTransport|null>(null),alive=useRef(true),request=useRef<AbortController|null>(null),sequence=useRef(0),pair=useRef<{a:Track;b:Track}|null>(null)
 const p=player.current,current=p?.current,position=p?.position??0,locked=!!p?.transition
 useEffect(()=>{alive.current=true;loadJson('library.json',base).then(readLibraryIndex).then(index=>{if(!alive.current)return;lib.current=new TrackLibrary(index.tracks,base);setEntries(index.tracks);setFrom(index.tracks.find(e=>e.playStatus==='ready')?.id??'')}).catch(e=>setError(e.message));return()=>{alive.current=false;sequence.current++;request.current?.abort();player.current?.dispose()}},[])
 useEffect(()=>{
  if(!p||!current||!to||to===current.id)return
  const controller=new AbortController();let running=false
  const warm=async()=>{
   if(running||!p.playing||p.transition||p.current?.id!==current.id)return
   running=true
   try{const b=await lib.current!.load(to);controller.signal.throwIfAborted();const plan=nearbyPlan(current,b,p.position);if(plan)await preloadOriginal(p,current,b,plan,controller.signal)}catch(e){if((e as Error).name!=='AbortError')p.logs.push({kind:'nearby_preload_failed',at:new Date().toISOString(),reason:(e as Error).message})}finally{running=false}
  }
  void warm();const timer=setInterval(()=>void warm(),2000)
  return()=>{clearInterval(timer);controller.abort()}
 },[current?.id,to,p])
 function invalidate(){sequence.current++;request.current?.abort();setWorking(false);setResult(null);pair.current=null;setMessage('');setError('')}
 async function ensure(){if(!player.current){player.current=new MetricTransport(base,()=>{if(alive.current)refresh(x=>x+1)});player.current.setVolume(volume)}const p=player.current;await initializeFromGesture(p);return p}
 async function start(){invalidate();const token=sequence.current;setWorking(true);try{const p=await ensure();const track=await lib.current!.load(from);if(!alive.current||token!==sequence.current)return;await p.start(track);lib.current!.trim(new Set([track.id,to]));setMessage('当前歌曲继续播放。选择下一首后点击“最近接点切歌”。')}catch(e){if(alive.current&&token===sequence.current)setError((e as Error).message)}finally{if(alive.current&&token===sequence.current)setWorking(false)}}
 async function cloud(a:Track,b:Track,plan:Plan,signal:AbortSignal){
  const response=await fetch(api+'jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:a.id,to:b.id,windowId:plan.window.id,start:plan.start}),signal});const job=await response.json();if(!response.ok)throw Error(typeof job.detail==='string'?job.detail:'云端暂时无法准备')
  for(let i=0;i<180;i++){
   signal.throwIfAborted()
   const r=await fetch(api+'jobs/'+job.id,{cache:'no-store',signal});const data=await r.json();if(!r.ok)throw Error(data.detail??'记录读取失败')
   signal.throwIfAborted()
   if(data.status==='failed')throw Error(data.message)
   if(data.status==='ready'){
    const prepared=data as Prepared
    if(prepared.plan.from!==a.id||prepared.plan.to!==b.id||Math.abs(prepared.plan.start-plan.start)>.002||prepared.plan.windowId!==plan.window.id)throw Error('云端结果与本次选点不一致')
    return prepared
   }
   await new Promise<void>((resolve,reject)=>{const timer=window.setTimeout(done,2000);function abort(){clearTimeout(timer);signal.removeEventListener('abort',abort);reject(new DOMException('已取消','AbortError'))}function done(){signal.removeEventListener('abort',abort);resolve()}signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort()})
  }
  throw Error('云端准备超时，请稍后重试')
 }
 async function prepare(soon=false){
  const p=player.current;if(!p?.current||!to||p.transition)return
  const ready=result?{result,method}:undefined
  invalidate();const token=sequence.current,controller=request.current=new AbortController();setWorking(true);setMessage('正在读取下一首的分析资料…')
  try{
   const a=p.current,b=await lib.current!.load(to);lib.current!.trim(new Set([a.id,b.id]));if(token!==sequence.current||!alive.current)return
   if(soon){
    const outcome=await mixNearby({player:p,a,b,signal:controller.signal,ready,prepare:(plan,signal)=>localOriginal(p,a,b,plan,signal),onStatus:message=>{if(alive.current&&token===sequence.current)setMessage(message)}})
    if(!alive.current||token!==sequence.current)return
    pair.current={a,b};setResult(outcome.result);setMethod(outcome.method);setMessage('已安排附近合适接点，将自动混入；当前歌曲继续播放。');return
   }
   const plan=planContinuous(a,[b],p.position+25,{kind:'next',targetId:b.id},new Set(),60,false).best
   if(!plan)throw Error('接下来这一段没有通过拍点、人声和速度检查的接点。可以换歌，或稍后重试。')
   if(Math.abs(plan.rate-1)>.05)throw Error('这组需要超过5%的变速，当前自动规则暂缓使用。请换一首速度更接近的歌。')
   setMessage('已找到接点，云端正在计算分轨指标…')
   const prepared=await cloud(a,b,plan,controller.signal)
   if(!alive.current||token!==sequence.current)return
   pair.current={a,b};setResult(prepared);setMethod(prepared.decision.recommended);setMessage('已准备好。可按原播放位置接歌，也可从接点前4秒试听。')
  }catch(e){if(alive.current&&token===sequence.current&&(e as Error).name!=='AbortError')setError((e as Error).message)}finally{if(alive.current&&token===sequence.current)setWorking(false)}
 }
 async function apply(audition=false){if(!result||!pair.current)return;const token=++sequence.current;setError('');setWorking(true);try{const p=await ensure();if(token!==sequence.current||!pair.current)return;if(audition)await p.audition(result,method,pair.current.a,pair.current.b);else await p.arm(result,method,pair.current.b)}catch(e){if(alive.current&&token===sequence.current)setError((e as Error).message)}finally{if(alive.current&&token===sequence.current)setWorking(false)}}
 function stop(){invalidate();player.current?.stop();setSeek(null)}
 async function jump(){if(seek===null)return;invalidate();try{await p?.seek(seek);setSeek(null)}catch(e){setError((e as Error).message)}}
 function exportRecord(){const value={...p?.export(),selectedResult:result,selectedMethod:method,exportedAt:new Date().toISOString()},url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='HarBeat-指标混音记录.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 const options=entries.filter(e=>e.playStatus==='ready'&&(!query||e.title.toLocaleLowerCase().includes(query.toLocaleLowerCase())))
 return <main><header><a href="/listen/">HarBeat / 返回连续播放</a><span>SMART MIX · 指标规则第一版</span></header><section className="intro"><p>听清交接，再决定怎么混</p><h1>让合适的处理，<br/>出现在合适的位置。</h1><p>选点和人声冲突检查沿用现有规则。云端分析这段音乐，推荐少量处理；手机负责播放，你也可以切换通过检查的方案。</p></section>
 <section className="player"><p className="eyebrow">正在播放</p><h2>{current?.title??'从曲库开始'}</h2><p role="status">{p?.status??'选择当前歌曲，再点击播放'}</p><label className="sr">播放进度<input type="range" aria-label="播放进度" disabled={!current||locked||working} min="0" max={current?.duration??1} step=".1" value={seek??position} onChange={e=>setSeek(+e.target.value)} onPointerUp={()=>void jump()} onKeyUp={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key))void jump()}}/></label><div className="time"><span>{clock(seek??position)}</span><span>{clock(current?.duration??0)}</span></div><div className="buttons"><button disabled={!current} onClick={()=>{if(p?.playing){request.current?.abort();p.pause()}else void p?.resume().catch(e=>setError(e.message))}}>{p?.playing?'暂停':'继续播放'}</button><button disabled={!current&&!working&&!p?.busy} onClick={stop}>停止</button><label>音量<input aria-label="音量" type="range" min="0" max="1" step=".01" value={volume} onChange={e=>{setVolume(+e.target.value);p?.setVolume(+e.target.value)}}/></label></div>{locked&&<p className="notice">{p!.ctx.currentTime<p!.transition!.at?'已安排交接，等待原接点。':'正在交接。'}暂停会暂停整个时间轴；停止可取消。</p>}</section>
 <section className="choose"><h2>选择这次的两首音乐</h2><label>搜索歌名<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="筛选下面的歌曲"/></label><div className="pair"><label>当前歌曲<select aria-label="当前歌曲" value={from} disabled={working||locked} onChange={e=>{invalidate();setFrom(e.target.value)}}><option value="">请选择</option>{entries.filter(e=>options.some(o=>o.id===e.id)||e.id===from).map(e=><option key={e.id} value={e.id}>{e.title} · {e.bpm?.toFixed(1)} BPM</option>)}</select></label><button className="primary" disabled={!from||working||locked} onClick={()=>void start()}>播放当前歌</button><label>下一首<select aria-label="下一首" value={to} disabled={working||locked} onChange={e=>{invalidate();setTo(e.target.value)}}><option value="">请选择</option>{entries.filter(e=>e.mixStatus==='ready'&&e.id!==(current?.id??from)&&(options.some(o=>o.id===e.id)||e.id===to)).map(e=><option key={e.id} value={e.id}>{e.title} · {e.bpm?.toFixed(1)} BPM</option>)}</select></label><button className="primary" disabled={!current||!to||working||locked||!p?.playing||to===current.id} onClick={()=>void prepare(true)}>最近接点切歌</button><button disabled={!current||!to||working||locked||to===current.id} onClick={()=>void prepare()}>{working?'正在准备…':'按指标准备交接'}</button></div><p>播放中会预载附近素材。点击切歌采用最近合格接点：分轨方案已就绪就使用，否则按原渐混接歌。曲库共 {entries.length} 首。当前版本优先选择变速不超过5%的曲对，未通过条件时当前歌曲继续播放。</p></section>
 {working&&current&&!locked&&<button onClick={()=>{invalidate();setMessage('已取消这次准备，当前歌曲继续播放。')}}>取消本次准备</button>}{message&&<p className="notice" role="status">{message}</p>}{error&&<p className="error" role="alert">{error}</p>}
 {result&&<section className="decision"><p className="eyebrow">本次推荐</p><h2>{result.decision.methods[result.decision.recommended].name}</h2><p>{result.decision.explanation}</p><p>接点：A {clock(result.plan.start)} → {clock(result.plan.end)}；B 从 {clock(result.plan.bStart)} 进入，{clock(result.plan.bEnd)} 接管。</p><div className="metric-grid"><div><span>局部拍点最大偏差</span><strong>{result.plan.beatErrorMs.toFixed(1)} ms</strong></div><div><span>速度调整</span><strong>{((result.plan.rate-1)*100).toFixed(1)}%</strong></div><div><span>贝斯同时可闻指标</span><strong>{pct(result.metrics.bassOverlap)}</strong></div><div><span>旋律声部同时可闻指标</span><strong>{pct(result.metrics.otherOverlap)}</strong></div></div><p className="muted">重叠指标为0–1的分析代理，不代表冲突概率。规则分只用于本次排序，不代表成功率。</p><label>采用的混音方案<select aria-label="采用的混音方案" value={method} disabled={locked||p?.busy} onChange={e=>setMethod(e.target.value as Method)}>{Object.entries(result.decision.methods).filter(([k,v])=>v.eligible&&result.assets[k as Method]).map(([k,v])=><option key={k} value={k}>{v.name} · 规则分 {v.score?.toFixed(1)}</option>)}</select></label><div className="buttons"><button className="primary" disabled={working||locked||p?.busy||(!canArm(result.plan,current?.id??null,position)&&!p?.playing)} onClick={()=>void (canArm(result.plan,current?.id??null,position)?apply():prepare(true))}>{canArm(result.plan,current?.id??null,position)?'按当前播放位置接歌':'重新找点并混入'}</button><button disabled={locked||p?.busy} onClick={()=>void apply(true)}>试听交接（前4秒开始）</button></div>{!locked&&!canArm(result.plan,current?.id??null,position)&&<p>原接点已过或当前歌曲已变化。播放中点击“重新找点并混入”，会从当前位置重新准备并自动接入。</p>}
 <details><summary>为什么选择它，其他方案为什么没选</summary><ul className="method-list">{Object.entries(result.decision.methods).map(([k,v])=><li key={k}><strong>{v.name} {v.eligible?`· ${v.score?.toFixed(1)} 分`:'· 未采用'}</strong><p>{v.reason}</p>{v.eligible&&<small>处理代价 −{v.processingCost}，音量连续性扣分 −{v.levelPenalty.toFixed(1)}</small>}</li>)}</ul><p>人声退出检查：{result.policyVersion===LOCAL_ORIGINAL?'沿用原选点的人声检查；本次未生成独立人声退出方案':result.metrics.vocalSafe?'声学尾部和空隙检查通过，仍不保证歌词语义完整':'本段没有通过当前保守的人声退出条件'}</p><p>规则版本 {result.policyVersion}。{result.decision.limitations.join('；')}。</p></details><button onClick={exportRecord}>导出本次判断与播放记录</button></section>}
 <section className="rules"><h2>当前规则怎么判断</h2><p><a href="./standards.html">查看完整判断标准、门槛与公式</a></p><ol><li>先检查来源、拍点、速度和可用素材，不合格方案不进入排序。</li><li>看实际重叠段的贝斯、旋律和人声指标，再扣除额外处理及音量突变代价。</li><li>新增单项至少比原版高4分；组合还要超过较好单项6分。分差不足优先少处理。</li></ol><p>这些门槛是第一版工程设置，尚未经过大样本听感校准。鼓桥、循环、回声、留白、大跨度和第三首叠加本版暂不自动采用。现有主播放器保持可用。</p></section><footer>HarBeat · 云端准备 / 手机播放 · 规则可追溯</footer></main>
}
createRoot(document.getElementById('root')!).render(<App/> )
