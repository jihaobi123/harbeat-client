import {useEffect,useRef,useState} from 'react'
import {LiveTransport} from '../realtime/transport'
import {AudioBufferPool} from '../realtime/cache'
import type {Plan,Track} from '../realtime/planner'
import type {KeySource} from './ranking'
import './harmonic-key.css'

type Arm='baseline'|'variant'
type Case={id:string;source:string;baseline:Plan;variant:Plan;exploratory:boolean;ranking:{id:string;score:number;bonus:number;rankScore:number}[]}
type Pack={schema:string;tracks:Track[];keys:Record<string,KeySource>;cases:Case[];createdAt:string;release:string}
type Feedback={caseId:string;preference:string;notes:string;at:string}
const storageKey='harbeat.harmonic-audition.v1.feedback'
const names={baseline:'原方案',variant:'调性偏好'}
const seconds=(n:number)=>n.toFixed(1)+' 秒'
function initialFeedback():Record<string,Feedback>{try{return JSON.parse(localStorage.getItem(storageKey)||'{}')}catch{return {}}}

export default function HarmonicKeyLab(){
 const [pack,setPack]=useState<Pack|null>(null),[caseIndex,setCaseIndex]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[arm,setArm]=useState<Arm|null>(null),[,refresh]=useState(0)
 const [feedback,setFeedback]=useState(initialFeedback),[heard,setHeard]=useState<Record<string,boolean>>({}),[notes,setNotes]=useState(''),[canUndo,setCanUndo]=useState(false)
 const previousFeedback=useRef<Record<string,Feedback>|null>(null),alive=useRef(true)
 const player=useRef<LiveTransport|null>(null),pool=useRef(new AudioBufferPool()),revision=useRef(0),sessionLogs=useRef<Record<string,unknown[]>>({})
 useEffect(()=>{let live=true;alive.current=true;fetch('./harmonic-key-data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('试听资料读取失败');return r.json()}).then(p=>{if(p.schema!=='harbeat.harmonic-audition.v1'||p.cases?.length!==3)throw Error('试听资料不完整');if(live){setPack(p);setNotes(feedback[p.cases[0].id]?.notes||'')}}).catch(e=>{if(live)setError(e.message)});return()=>{live=false;alive.current=false;revision.current++;player.current?.dispose();player.current=null}},[])
 function stop(){revision.current++;const old=player.current;player.current=null;if(old){sessionLogs.current[old.sessionId]=old.logs;old.dispose()}setBusy(false);setArm(null);refresh(n=>n+1)}
 function choose(index:number){stop();setError('');setCaseIndex(index);const c=pack!.cases[index];setNotes(feedback[c.id]?.notes||'')}
 async function play(which:Arm){
  if(!pack)return
  stop();const token=++revision.current,c=pack.cases[caseIndex];let completed=false;setError('');setBusy(true);setArm(which)
  const t=new LiveTransport(pack.tracks,()=>{
   if(!alive.current||player.current!==t)return
   if(!completed&&t.logs.some(l=>l.kind==='comparison_finished')){completed=true;setHeard(old=>({...old,[c.id+':'+which]:true}));setArm(null)}
   refresh(n=>n+1)
  },new URL('.',location.href),{audioPool:pool.current,autoNext:false,prewarm:false,policyVersion:'harmonic-audition-v1'})
  player.current=t
  try{
   await t.initialize();if(token!==revision.current||player.current!==t)return
   const plan=c[which];t.log('harmonic_audition',{caseId:c.id,arm:which,provisionalLabels:c.exploratory,frozenPlanId:plan.id,ranking:c.ranking,changes:'destination ranking only; fixed per-destination plan and EQ'})
   await t.playComparison(plan,0,{experimentId:'harmonic-audition-v1',comparisonId:c.id+':'+which+':'+Date.now(),caseKey:c.id,arm:which,midDb:-5,skipWaiting:true})
  }catch(e){if(token===revision.current){setError((e as Error).message);sessionLogs.current[t.sessionId]=t.logs;player.current=null;t.dispose();setArm(null)}}finally{if(token===revision.current)setBusy(false)}
 }
 function save(preference:string){
  const c=pack!.cases[caseIndex],row={caseId:c.id,preference,notes,at:new Date().toISOString()},next={...feedback,[c.id]:row}
  previousFeedback.current=feedback;setCanUndo(true);setFeedback(next);try{localStorage.setItem(storageKey,JSON.stringify(next))}catch{setError('本机存储暂不可用，请导出反馈保存。')}
 }
 function undoFeedback(){const old=previousFeedback.current;if(!old)return;setFeedback(old);setNotes(old[pack!.cases[caseIndex].id]?.notes||'');setCanUndo(false);try{localStorage.setItem(storageKey,JSON.stringify(old))}catch{setError('本机存储暂不可用，请导出反馈保存。')}}
 function exportFeedback(){
  const sessions={...sessionLogs.current};if(player.current)sessions[player.current.sessionId]=player.current.logs
  const value={schema:'harbeat.harmonic-audition-feedback.v1',feedback,heard,caseIds:pack?.cases.map(c=>c.id),logs:Object.values(sessions).flat()}
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='HarBeat-调性试听反馈.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 }
 if(!pack)return <main className="harmonic"><h1>调性偏好试听</h1><p role={error?'alert':'status'}>{error||'正在读取三组试听资料…'}</p></main>
 const c=pack.cases[caseIndex],source=pack.tracks.find(t=>t.id===c.source)!,track=(id:string)=>pack.tracks.find(t=>t.id===id)!,p=player.current
 const bothHeard=heard[c.id+':baseline']&&heard[c.id+':variant'],same=c.baseline.id===c.variant.id
 return <main className="harmonic">
  <header><a className="brand" href="https://8.136.120.255/listen/" target="_blank" rel="noreferrer">HarBeat<span>LISTENING ROOM / 01</span></a><p className="edition">第一轮 · 调性偏好</p></header>
  <section className="intro"><p className="eyebrow">一次只比较一个变化</p><h1>下一首，调性合适<br/>会更顺吗？</h1><p>同一首当前音乐、同一批候选。每个候选的接点、交接时长与 EQ 已固定，只比较加入调性偏好后选到了哪首歌。</p><p className="notice">本轮使用待复核的调性候选标签，只供试听探索。线上默认效果保持原样。</p></section>
  <nav aria-label="试听样例">{pack.cases.map((item,i)=><button key={item.id} aria-pressed={caseIndex===i} onClick={()=>choose(i)}>0{i+1}<span>{pack.tracks.find(t=>t.id===item.source)!.title}</span></button>)}</nav>
  <section className="audition"><div className="case-top"><span>当前音乐</span><h2>{source.title}</h2><p>{source.bpm.toFixed(1)} BPM · 调性候选 {pack.keys[source.id].key?.camelot}</p></div>
   <div className="arms">{(['baseline','variant'] as const).map(which=>{const plan=c[which],b=track(plan.to);return <article key={which} className={arm===which?'active':''}><p className="eyebrow">{names[which]}</p><h3>{b.title}</h3><p>{b.bpm.toFixed(1)} BPM · 调性候选 {pack.keys[b.id].key?.camelot}</p><button className="play" disabled={busy} onClick={()=>play(which)}>{arm===which?'重新试听':'试听'}{names[which]}</button><p className="heard">{heard[c.id+':'+which]?'✓ 已完整听完':'接点前 4 秒 → 接管后 8 秒'}</p></article>})}</div>
   <div className="play-status"><p role="status">{busy?'正在准备已校验的音频…':p?.status||'选择一版开始试听'}{p?.current?' · '+p.current.title+' '+seconds(p.position):''}</p><button onClick={stop}>停止</button></div>
   {error&&<p className="error" role="alert">{error}</p>}
   <p className="case-note">{same?'这组两版保留同一个选择，可用来检查加入偏好后是否确实保持原结果。':'这组两版选择了不同的下一首，比较的是选歌结果；每个曲对的声音处理都按原计划回放。'}</p>
  </section>
  <section className="feedback"><h2>你听起来觉得怎样？</h2><p>两版完整播放后可以记录偏好。反馈只保存在这台设备。</p><div className="votes">{['原方案更顺','调性偏好更顺','差不多','两版都不理想'].map(value=><button key={value} disabled={!bothHeard} aria-pressed={feedback[c.id]?.preference===value} onClick={()=>save(value)}>{value}</button>)}</div><label>听感备注<textarea value={notes} placeholder="例如：旋律更协调，但切换后的能量下降了" onChange={e=>setNotes(e.target.value)} onBlur={()=>{if(feedback[c.id])save(feedback[c.id].preference)}}/></label><button className="export" onClick={exportFeedback}>导出本轮反馈与播放记录</button>{canUndo&&<button onClick={undoFeedback}>撤销本次记录</button>}</section>
  <details><summary>查看两版固定计划与排序依据</summary><p>调性分数上限为 0.08，不代表音质提升。整曲标签也不能保证接点处的和声兼容。</p><pre>{JSON.stringify({caseId:c.id,keys:pack.keys,frozenPlans:{baseline:c.baseline,variant:c.variant},ranking:c.ranking},null,2)}</pre></details>
  <footer>HARBEAT / HARMONIC AUDITION · 三组试听，不改线上默认方案</footer>
 </main>
}
