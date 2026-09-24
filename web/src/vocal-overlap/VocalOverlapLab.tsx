import {useEffect,useMemo,useRef,useState} from 'react'
import type {Plan,Track} from '../realtime/planner'
import {LiveTransport} from '../realtime/transport'
import {AudioBufferPool} from '../realtime/cache'
import DecisionHistory from '../realtime/DecisionHistory'
import {loadJson} from '../phrase/load'
import {planV31,V31_RELEASE} from '../v31-release/release'
import {planVocalOverlap,OVERLAP_POLICY_VERSION,type OverlapPlan} from './planner'
import {alignedVocalOverlap,type OverlapMeasure} from './score'
import {completedComparison,readFeedback,writeFeedback,type Arm,type AuditionRequest,type Feedback} from './feedback'
import logo from '../analysis/assets/harbeat-logo.png'
import '../v31/v31.css'
import './vocal-overlap.css'

type Case={id:string;a:string;b:string;position:number;group:string}
type Pack={tracks:Track[];cases:Case[];coverage?:Record<string,unknown>}
const base=new URL('.',location.href)
const armNames:Record<Arm,string>={baseline:'正式 V3.1 评分',variant:'人声重叠评分'}
const groupNames:Record<string,string>={original20:'原有曲目与位置',new_music:'新增音乐 · 固定测试',changed_examples:'选点变化示例',unchanged_examples:'选点不变示例'}
const plannerFor=(arm:Arm)=>arm==='baseline'?planV31:planVocalOverlap
const sec=(n:number)=>`${n.toFixed(2)}s`
const pct=(n:number)=>`${(n*100).toFixed(1)}%`
function download(value:unknown,name:string){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function measure(plan:Plan|null,tracks:Track[]):OverlapMeasure|null{
 if(!plan)return null
 const evidence=(plan as OverlapPlan).vocalOverlap
 if(evidence)return evidence
 const a=tracks.find(t=>t.id===plan.from),b=tracks.find(t=>t.id===plan.to)
 if(!a||!b)return null
 try{return alignedVocalOverlap(a.vocals,b.vocals,{aStart:plan.start,bStart:plan.window.start,bEnd:plan.window.end,duration:plan.duration,rate:plan.rate})}catch{return null}
}
function VocalTimeline({plan,evidence,playTime}:{plan:Plan;evidence:OverlapMeasure;playTime?:number}){
 const left=110,width=590,x=(t:number)=>left+Math.max(0,Math.min(plan.duration,t))/plan.duration*width
 const rows=[{title:'A 人声',spans:evidence.aIntervals,y:42,kind:'vocal'},{title:'B 人声',spans:evidence.bIntervals,y:84,kind:'vocal'},{title:'同时活动',spans:evidence.collisions,y:126,kind:'collision'}]
 const weight=Array.from({length:41},(_,i)=>{const t=i/40;return `${i?'L':'M'}${x(t*plan.duration)},${210-45*4*t*(1-t)}`}).join(' ')
 return <div className="timeline-scroll overlap-timeline"><svg viewBox="0 0 740 260" role="img" aria-label={`按实际播放时间对齐的人声活动；两曲同时活动 ${evidence.simultaneousSec.toFixed(2)} 秒，加权重叠 ${pct(evidence.weightedOverlap)}`}>
  <title>从 B 开始混入到 A 完全退出；包含原有 0.3 秒源时间扩展</title>
  {Array.from({length:5},(_,i)=>i/4*plan.duration).map(t=><g key={t}><line x1={x(t)} x2={x(t)} y1="24" y2="218" className="grid-line"/><text x={x(t)} y="244" textAnchor="middle">{sec(t)}</text></g>)}
  {rows.map(row=><g key={row.title}><text x="6" y={row.y+15}>{row.title}</text><rect x={left} y={row.y} width={width} height="20" className="mix-zone"/>{row.spans.map(([s,e],i)=><rect key={i} x={x(s)} y={row.y} width={Math.max(.5,x(e)-x(s))} height="20" className={row.kind}><title>{row.title}：混入后 {sec(s)} 至 {sec(e)}</title></rect>)}</g>)}
  <text x="6" y="185">评分权重</text><path d={weight} className="overlap-weight"/><text x="110" y="20">B 开始混入</text><text x="700" y="20" textAnchor="end">A 退出 / B 接管</text>
  {playTime!==undefined&&playTime>=0&&playTime<=plan.duration&&<line x1={x(playTime)} x2={x(playTime)} y1="24" y2="218" className="playhead"/>}
 </svg><p className="quiet">横轴为播放秒数。B 按 {plan.rate.toFixed(3)}× 映射；曲线是渐变音量乘积的归一化权重。人声活动和权重只是冲突估计，不代表歌词识别或实际人声响度。</p></div>
}
function CueTable({original,variant,tracks}:{original:Plan|null;variant:Plan|null;tracks:Track[]}){
 const plans=[original,variant],measures=plans.map(p=>measure(p,tracks))
 return <div className="table-scroll"><table><caption>同一 A、B 与请求位置；先固定正式版选中的 B 素材</caption><thead><tr><th>对照项目</th><th>正式 V3.1 评分</th><th>人声重叠评分</th></tr></thead><tbody>
  <tr><th>A 混入 → 退出</th>{plans.map((p,i)=><td key={i}>{p?`${sec(p.start)} → ${sec(p.end)}`:'无计划'}</td>)}</tr>
  <tr><th>完整渐进交接</th>{plans.map((p,i)=><td key={i}>{p?sec(p.duration):'—'}</td>)}</tr>
  <tr><th>B 原曲进入片段</th>{plans.map((p,i)=><td key={i}>{p?`${sec(p.window.start)} → ${sec(p.window.end)} · ${p.rate.toFixed(3)}×`:'—'}</td>)}</tr>
  <tr><th>旧人声项：各自占比相乘</th>{plans.map((p,i)=><td key={i}>{p?pct(p.aVocal*p.bVocal):'—'}</td>)}</tr>
  <tr><th>新算法估计的加权重叠</th>{measures.map((m,i)=><td key={i}>{m?pct(m.weightedOverlap):'证据不可用'}</td>)}</tr>
  <tr><th>两曲人声同时活动</th>{measures.map((m,i)=><td key={i}>{m?sec(m.simultaneousSec):'—'}</td>)}</tr>
  <tr><th>本版规则总分</th>{plans.map((p,i)=><td key={i}>{p?p.score.toFixed(4):'—'}</td>)}</tr>
 </tbody></table></div>
}
export default function VocalOverlapLab(){
 const [pack,setPack]=useState<Pack|null>(null),[aId,setA]=useState(''),[bId,setB]=useState(''),[position,setPosition]=useState(30),[caseId,setCaseId]=useState(''),[arm,setArm]=useState<Arm>('baseline'),[tab,setTab]=useState<'compare'|'live'>('compare')
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[warm,setWarm]=useState(''),[,refresh]=useState(0),[expected,setExpected]=useState<AuditionRequest|null>(null)
 const [feedback,setFeedback]=useState<Feedback>(()=>{try{return readFeedback(localStorage)}catch{return {}}})
 const player=useRef<LiveTransport|null>(null),playerArm=useRef<Arm|null>(null),init=useRef<Promise<void>|null>(null),pool=useRef(new AudioBufferPool()),revision=useRef(0),runSequence=useRef(0),timer=useRef<ReturnType<typeof setTimeout>|null>(null)
 const dirtyFeedback=useRef<Feedback>({})
 useEffect(()=>{
  let alive=true
  Promise.all(['catalog.json','cases.json'].map(f=>loadJson(f,base))).then(([catalog,samples])=>{
   if(!alive)return
   if(!Array.isArray(catalog.tracks)||catalog.tracks.length<2||!Array.isArray(samples.cases)||!samples.cases.length)throw Error('曲库或固定测试样本不完整')
   const first=samples.cases[0] as Case
   setPack({tracks:catalog.tracks,cases:samples.cases,coverage:samples.coverage});setA(first.a);setB(first.b);setPosition(first.position);setCaseId(first.id)
  }).catch(e=>{if(alive)setError((e as Error).message)})
  return()=>{alive=false;revision.current++;if(timer.current)clearTimeout(timer.current);player.current?.dispose();player.current=null;playerArm.current=null;init.current=null}
 },[])
 const searches=useMemo(()=>{
  const a=pack?.tracks.find(t=>t.id===aId)
  if(!pack||!a)return null
  const args=[a,pack.tracks,position,{kind:'next' as const,targetId:bId},new Set<string>(),18,false] as const
  return {baseline:planV31(...args),variant:planVocalOverlap(...args)}
 },[pack,aId,bId,position])
 const caseKey=`${caseId||'custom'}|${aId}|${bId}|${position}`
 const heard=completedComparison(player.current?.logs||[],expected,caseKey,arm)
 if(!pack||!searches)return <main className="v31 vocal-overlap"><h1>HarBeat · 人声重叠评分试听</h1><p role={error?'alert':'status'}>{error||'正在读取曲库与固定测试位置…'}</p><a href="/analysis-lab-static/v31-live-20260924/index.html">打开正式 V3.1 ↗</a></main>
 const {tracks}=pack,a=tracks.find(t=>t.id===aId)!,p=player.current,locked=busy||!!p?.busy
 const latestRequest=p?.logs.filter(l=>l.kind==='request_received').at(-1)
 const execution=p?.logs.filter(l=>l.kind==='plan_scheduled'&&l.requestId===latestRequest?.requestId).at(-1)
 const hasLiveRequest=tab==='live'&&latestRequest?.origin==='vocal_overlap_live'
 const actual=hasLiveRequest?(execution?.plan as Plan|undefined):undefined
 const activeSearch=hasLiveRequest&&p?.lastSearch?p.lastSearch:searches[arm]
 const q=hasLiveRequest?actual||null:searches[arm].best,evidence=measure(q,tracks)
 const overlap=q?(q as OverlapPlan).vocalOverlap:undefined
 const ratingId=`${caseKey}|${arm}`,selectedFeedback=feedback[ratingId]
 const playTime=p?.pending&&q?.id===p.pending.plan.id?p.ctx.currentTime-p.pending.start:undefined
 function stop(){revision.current++;if(timer.current){clearTimeout(timer.current);timer.current=null}setExpected(null);setBusy(false);setWarm('');player.current?.stop()}
 function reset(){stop();const old=player.current;player.current=null;playerArm.current=null;init.current=null;old?.dispose()}
 function chooseCase(c:Case){reset();setA(c.a);setB(c.b);setPosition(c.position);setCaseId(c.id)}
 function checkCurrent(token:number,t:LiveTransport){if(token!==revision.current||player.current!==t)throw new DOMException('试听操作已取消','AbortError')}
 async function ensure(token:number){
  if(player.current&&playerArm.current===arm){const t=player.current;await init.current;checkCurrent(token,t);return t}
  player.current?.dispose()
  const t=new LiveTransport(tracks,()=>refresh(n=>n+1),base,{planner:plannerFor(arm),audioPool:pool.current,autoNext:false,prewarm:false,policyVersion:arm==='baseline'?V31_RELEASE.policyVersion:OVERLAP_POLICY_VERSION,noPlanMessage:'18 秒预算内没有可执行计划，当前音乐继续播放。可查看本次排除依据。'})
  player.current=t;playerArm.current=arm;init.current=t.initialize()
  try{await init.current;checkCurrent(token,t)}catch(e){if(player.current===t){player.current=null;playerArm.current=null;init.current=null;t.dispose()}throw e}
  t.log('source_catalog',{experimentId:OVERLAP_POLICY_VERSION,arm,baselineTag:'audio-v3.1.0',baselineCommit:'2ba6c8f',trackCount:tracks.length,changes:{vocalScore:arm==='variant'?'aligned gain-weighted overlap':'V3 marginal product',gain:'original full-overlap linear',dynamicEqRule:'unchanged; source coefficients may differ',autoNext:false,prewarm:false}})
  return t
 }
 async function run(action:(token:number)=>Promise<void>){
  const token=++revision.current;if(timer.current){clearTimeout(timer.current);timer.current=null}setExpected(null);setError('');setBusy(true)
  try{await action(token)}catch(e){if(token===revision.current&&(e as Error).name!=='AbortError')setError((e as Error).message)}finally{if(token===revision.current)setBusy(false)}
 }
 async function audition(token:number){
  const plan=searches![arm].best;if(!plan)return
  const t=await ensure(token),comparisonId=`${caseKey}|${arm}|${t.sessionId}|${++runSequence.current}`
  t.log('comparison_analysis',{comparisonId,caseKey,caseId:caseId||null,arm,sourcePosition:position,baseline:searches!.baseline,variant:searches!.variant,fixedMaterial:true})
  const playing=t.playComparison(plan,position,{experimentId:OVERLAP_POLICY_VERSION,comparisonId,caseKey,caseId:caseId||null,arm,midDb:-5,skipWaiting:true,horizonSec:18})
  const request=t.logs.filter(l=>l.kind==='request_received'&&l.experiment?.comparisonId===comparisonId).at(-1)
  if(request)setExpected({sessionId:t.sessionId,requestId:request.requestId,comparisonId,caseKey,arm,a:plan.from,b:plan.to,position,planId:plan.id})
  await playing;checkCurrent(token,t)
 }
 async function inspect(token:number,trackId:string,time:number){
  const t=await ensure(token);t.log('source_inspection',{trackId,sourceStart:time,durationSec:8,notMix:true});await t.start(trackId,time);checkCurrent(token,t)
  timer.current=setTimeout(()=>{if(token===revision.current&&player.current===t)t.stop()},8000)
 }
 async function prepare(token:number){
  const t=await ensure(token),from=t.current||a,pos=t.current?t.position:position
  const result=plannerFor(arm)(from,tracks,pos,{kind:'next',targetId:bId},t.cache.ready,18,false)
  if(!result.best){t.log('manual_preload_rejected',{from:from.id,to:bId,sourcePosition:pos,exclusions:result.exclusions});throw Error('当前没有可准备的计划，固定测试结果仍保留。')}
  const b=tracks.find(t=>t.id===result.best!.to)!,assets=[from.native,b.native,result.best.asset]
  setWarm('正在准备原曲和进入片段…');t.cache.protected=new Set(assets.map(asset=>asset.url))
  await Promise.all(assets.map(asset=>t.cache.load(asset)));checkCurrent(token,t)
  t.log('manual_preload',{arm,from:from.id,to:b.id,sourcePosition:pos,planId:result.best.id,doesNotSchedule:true});setWarm('素材已准备。请求接歌时仍会按当时位置重新选点。')
 }
 function rate(value:string,notes=String(selectedFeedback?.notes||'')){
  if(!heard||tab!=='compare')return
  const row={...heard,value,notes,updatedAt:new Date().toISOString(),version:OVERLAP_POLICY_VERSION,baselineTag:'audio-v3.1.0'}
  dirtyFeedback.current[ratingId]=row;setFeedback(current=>({...current,[ratingId]:row}))
  try{const saved=writeFeedback(localStorage,dirtyFeedback.current);dirtyFeedback.current={};setFeedback(saved)}catch{setError('本轮反馈暂存在页面中，请导出保存；浏览器中已有记录仍保留。')}
 }
 return <main className="v31 vocal-overlap"><header><img src={logo} alt="HarBeat"/><div><div className="eyebrow">V3.1 · VOCAL OVERLAP EXPERIMENT</div><h1>人声同时唱，才计入重叠。</h1><p>只调整选点中的人声评分，试听它是否让衔接更顺。</p></div><a className="old-version official-link" href="/analysis-lab-static/v31-live-20260924/index.html">打开正式 V3.1 ↗</a></header>
  <aside className="scope">正式基线为 audio-v3.1.0（2ba6c8f）。两版固定 B 曲、进入片段、变速和完整交接时长，只重新比较 A 的可用时机。渐变与动态 EQ 规则保持一致；选点改变后，动态 EQ 会使用新位置的音频证据。</aside>
  <nav aria-label="试听方式"><button aria-pressed={tab==='compare'} onClick={()=>{reset();setTab('compare')}}>① 同曲对照</button><button aria-pressed={tab==='live'} onClick={()=>{reset();setTab('live')}}>② 实时接歌</button><a href="/analysis-lab?tab=mix-debug">历史日志 ↗</a></nav>
  <section><div className="section-head"><h2>{tab==='compare'?'选同一组音乐，分别听两版':'播放 A，再按当前位置请求接歌'}</h2><span>{tracks.length} 首 · {pack.cases.length} 个试听样本</span></div>
   <label>预设样本（包含无可执行计划的情况）<select aria-label="预设样本" value={caseId} disabled={locked} onChange={e=>{const c=pack.cases.find(c=>c.id===e.target.value);if(c)chooseCase(c)}}><option value="" disabled>自选曲对与位置</option>{Array.from(new Set(pack.cases.map(c=>c.group))).map(group=><optgroup key={group} label={groupNames[group]||group}>{pack.cases.filter(c=>c.group===group).map(c=><option key={c.id} value={c.id}>{tracks.find(t=>t.id===c.a)?.title} → {tracks.find(t=>t.id===c.b)?.title} · {sec(c.position)}</option>)}</optgroup>)}</select></label>
   <div className="fields"><label>A 当前曲<select aria-label="A 当前曲" value={aId} disabled={locked} onChange={e=>{reset();setCaseId('');setA(e.target.value);if(e.target.value===bId)setB(tracks.find(t=>t.id!==e.target.value)!.id);setPosition(Math.min(position,tracks.find(t=>t.id===e.target.value)!.duration-1))}}>{tracks.map(t=><option key={t.id} value={t.id}>{t.title} · {t.bpm} BPM</option>)}</select></label><label>B 下一首<select aria-label="B 下一首" value={bId} disabled={locked} onChange={e=>{reset();setCaseId('');setB(e.target.value)}}>{tracks.filter(t=>t.id!==aId).map(t=><option key={t.id} value={t.id}>{t.title} · {t.bpm} BPM</option>)}</select></label><label>A 请求位置（原曲秒）<input aria-label="A 请求位置" type="number" min="0" max={Math.max(0,a.duration-1)} step=".1" value={position} disabled={locked} onChange={e=>{reset();setCaseId('');setPosition(Math.max(0,Math.min(a.duration-1,Number(e.target.value)||0)))}}/></label></div>
   <div className="overlap-arms">{(['baseline','variant'] as const).map(m=><button key={m} aria-pressed={arm===m} disabled={locked} onClick={()=>{if(arm!==m){reset();setArm(m)}}}><strong>{armNames[m]}</strong><span>{searches[m].best?`A ${sec(searches[m].best!.start)} → ${sec(searches[m].best!.end)} · 重叠 ${sec(searches[m].best!.duration)}`:'此请求位置没有可执行计划'}</span></button>)}</div>
   {tab==='compare'?<div className="actions"><button className="primary" disabled={locked||!searches[arm].best} onClick={()=>run(audition)}>试听{arm==='baseline'?'正式 V3.1':'人声重叠版'}</button><span className="quiet">播放混入前 4 秒至接管后 8 秒；两版保留相同的原请求位置。</span></div>:<><div className="actions"><button disabled={locked} onClick={()=>run(async token=>{const t=await ensure(token);await t.start(aId,position);checkCurrent(token,t)})}>播放 A</button><button disabled={locked||!!p?.pending} onClick={()=>run(prepare)}>准备下一首素材</button><button className="primary" disabled={locked||!p?.active||p.paused||!!p?.pending||p.current?.id===bId} onClick={()=>run(async token=>{const t=await ensure(token);await t.request({kind:'next',targetId:bId},18,{origin:'vocal_overlap_live'});checkCurrent(token,t)})}>现在请求接歌</button><button disabled={locked||!p?.active} onClick={()=>run(async token=>{const t=await ensure(token);await t.togglePause();checkCurrent(token,t)})}>{p?.paused?'继续':'暂停'}</button><button disabled={locked||!p?.pending} onClick={()=>{setExpected(null);p?.cancel()}}>取消待执行接歌</button></div><p className="quiet" role="status">{warm||'可以先准备素材。页面不自动预加载或自动接歌，下载期间 A 会继续播放。'}</p></>}
   <div className="player-bar"><span role="status">{p?.status||'等待试听'}{p?.current?` · ${p.current.title} ${sec(p.position)}`:''}</span><button onClick={stop}>停止</button><button disabled={!p} onClick={()=>download(p!.export(),'HarBeat-vocal-overlap-session.json')}>导出本次日志</button></div>
   {error&&<p role="alert" className="error">{error}</p>}<p className="quiet">两版共用已解码音频缓存。切换样本或版本会停止当前声音；新的试听从对应请求开始。</p>
  </section>
  {tab==='compare'&&<section><h2>两版究竟改了哪里</h2><CueTable original={searches.baseline.best} variant={searches.variant.best} tracks={tracks}/><p className="quiet">总分使用各自的人声项，不能把总分增加当作音质提升。“新算法估计的加权重叠”把两版选点放在同一算法下计算，最终仍以试听为准。</p>{searches.variant.best&&<p>A 整段交接相对正式评分移动 {sec((searches.variant.best as OverlapPlan).vocalOverlap.shiftSec)}；B 的原曲片段、素材和交接时长固定。</p>}</section>}
  <section><h2>{tab==='live'&&actual?'本次实际计划':'当前试听计划'} · {armNames[arm]}</h2>{q?<>
   <div className="story-metrics"><div><strong>{sec(q.duration)}</strong><span>A 渐弱、B 渐强的完整时长</span></div><div><strong>{evidence?pct(evidence.weightedOverlap):'不可用'}</strong><span>新算法估计的加权重叠</span></div><div><strong>{evidence?sec(evidence.simultaneousSec):'不可用'}</strong><span>模型人声同时活动</span></div></div>
   {evidence?<VocalTimeline plan={q} evidence={evidence} playTime={playTime}/>:<p className="error">人声时间映射证据不可用，保留原有播放计划与日志。</p>}
   <div className="source-cues"><div><b>A · {tracks.find(t=>t.id===q.from)?.title}</b><p>原曲 {sec(q.start)} 开始退让，{sec(q.end)} 退出。</p><button disabled={locked} onClick={()=>run(token=>inspect(token,q.from,Math.max(0,q.end-4)))}>听 A 退出点前后原声</button></div><div><b>B · {tracks.find(t=>t.id===q.to)?.title}</b><p>原曲 {sec(q.window.start)} → {sec(q.window.end)}，进入段 {q.rate.toFixed(3)}×；接管后恢复原速。</p><button disabled={locked} onClick={()=>run(token=>inspect(token,q.to,Math.max(0,q.window.start-2)))}>听 B 进入段原声</button></div></div>
   {overlap&&<p className="quiet">原有 {overlap.originalCandidateCount} 个候选中，{overlap.timingCandidateCount} 个时机使用相同 B 素材。仅将人声扣分从 −0.3 × 各自占比乘积，替换为 −0.3 × 加权重叠。</p>}
   <details><summary>源区间、原始行号、固定素材与动态 EQ 控制点</summary><pre>{JSON.stringify({planId:q.id,source:{aStart:q.start,aEnd:q.end,bStart:q.window.start,bEnd:q.window.end,rate:q.rate},vocalOverlap:overlap||{diagnosticOnly:true,...evidence},eq:q.v30Eq},null,2)}</pre></details>
  </>:<div className="empty"><h3>这个请求位置没有可执行计划</h3><p>样本保留在本次测试中。实时请求时会继续播放当前曲。</p><ul>{[...new Set<string>(activeSearch.exclusions.filter((e:{code:string})=>!['target_mismatch','current_track'].includes(e.code)).map((e:{reason:string})=>e.reason))].slice(0,8).map(reason=><li key={reason}>{reason}</li>)}</ul></div>}
   <details><summary>全部候选与排除原因</summary><pre>{JSON.stringify(activeSearch,null,2)}</pre></details>
  </section>
  <section><h2>计划与实际执行</h2>{execution?<div className="table-scroll"><table><thead><tr><th>动作</th><th>计划音频时钟</th><th>音频线程观察</th><th>偏差</th></tr></thead><tbody>{execution.events.map((event:any)=>{const observation=p!.logs.find(l=>l.kind==='audio_observation'&&l.requestId===execution.requestId&&l.planId===event.planId&&l.name===event.name);return <tr key={event.name}><td>{event.name}</td><td>{(event.frame/p!.ctx.sampleRate).toFixed(3)}s</td><td>{observation?`${observation.observedContextSec.toFixed(3)}s`:'未观察到'}</td><td>{observation?`${observation.observationDeltaMs.toFixed(2)}ms`:'—'}</td></tr>})}</tbody></table></div>:<p className="quiet">开始混音后，这里显示混入、EQ 恢复与正文接管的实际观察值。</p>}<p className="quiet">这是浏览器音频线程的观察，不是扬声器或蓝牙延迟测量。</p></section>
  <section><h2>保留本轮试听偏好</h2><p>{tab==='live'?'实时接歌可导出执行日志；固定对照反馈请在“同曲对照”里听完对应版本后填写。':heard?`${armNames[arm]}已完整播完，可以记录这次感受。`:'在“同曲对照”里听到交接后 8 秒自动结束，才开放当前样本、当前版本的反馈。'}</p>
   <div className="actions">{['衔接自然','人声仍有冲突','A 截句明显','节奏有跳变','难以判断'].map(value=><button key={value} disabled={!heard||tab!=='compare'} aria-pressed={selectedFeedback?.value===value} onClick={()=>rate(value)}>{value}</button>)}</div>
   <label>试听备注<textarea disabled={!heard||tab!=='compare'} value={String(selectedFeedback?.notes||'')} placeholder="例如：中间两句没有叠在一起，但 A 的尾音还是断得早。" onChange={e=>rate(String(selectedFeedback?.value||'仅备注'),e.target.value)}/></label>
   <button onClick={()=>download({version:OVERLAP_POLICY_VERSION,feedback},'HarBeat-vocal-overlap-feedback.json')}>导出本轮反馈（{Object.keys(feedback).length} 条）</button><p className="quiet">本轮反馈独立保存在此浏览器。正式版与历史实验里的偏好继续留在原页面；顶部可随时打开正式 V3.1。</p>
  </section>
  <section><details><summary>音乐与样本覆盖</summary><p>固定测试按原有曲目、新增音乐分别保留；“选点变化示例”用于看清发生了什么，不代表固定测试的成功率。</p><ul>{Array.from(new Set(pack.cases.map(c=>c.group))).map(group=><li key={group}>{groupNames[group]||group}：{pack.cases.filter(c=>c.group===group).length} 个</li>)}</ul><div className="table-scroll"><table><thead><tr><th>曲目</th><th>BPM</th><th>模型风格</th><th>进入窗口</th></tr></thead><tbody>{tracks.map(t=><tr key={t.id}><td>{t.title}</td><td>{t.bpm}</td><td>{t.style}</td><td>{t.windows.length}</td></tr>)}</tbody></table></div>{pack.coverage&&<pre>{JSON.stringify(pack.coverage,null,2)}</pre>}<a href="corpus-audit.json" target="_blank" rel="noreferrer">查看选曲与排除记录 ↗</a></details></section>
  {p&&<section><details><summary>本次全部触发记录</summary><DecisionHistory logs={p.logs} tracks={tracks} eventCount={p.logs.length}/></details></section>}
  <footer>HarBeat · 人声重叠评分实验 · 正式回退基线 audio-v3.1.0 / 2ba6c8f。评分只估计人声冲突，听感结果由本轮试听记录。</footer>
 </main>
}
