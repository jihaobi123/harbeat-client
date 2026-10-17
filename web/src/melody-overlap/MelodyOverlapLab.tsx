import {useEffect,useRef,useState} from 'react'
import {MelodyPlayer,type MelodyCase,type State} from './transport'
import type {Mode} from './policy'
import './style.css'
type Pack={schema:string;selectionSha256:string;harmonicRelease:string;rendering:string;limitation:string;cases:MelodyCase[];skipped:unknown[]}
type Feedback={preference:string;notes:string;at:string}
const storageKey='harbeat.melody-overlap.v1.feedback'
const names={reference:'原重叠方案',short:'分轨短重叠'}
const initial=()=>{try{return JSON.parse(localStorage.getItem(storageKey)||'{}') as Record<string,Feedback>}catch{return {}}}
export default function MelodyOverlapLab(){
 const [pack,setPack]=useState<Pack|null>(null),[index,setIndex]=useState(0),[error,setError]=useState('')
 const [state,setState]=useState<State>({status:'idle',message:'选择一版开始试听',position:0,caseId:'',mode:'reference'})
 const [feedback,setFeedback]=useState(initial),[heard,setHeard]=useState<Record<string,boolean>>({}),[notes,setNotes]=useState(''),[canUndo,setCanUndo]=useState(false)
 const player=useRef<MelodyPlayer|null>(null),previous=useRef<Record<string,Feedback>|null>(null)
 useEffect(()=>{
  let live=true
  const p=new MelodyPlayer(new URL('.',location.href),s=>{if(!live)return;setState(s);if(s.status==='complete')setHeard(old=>({...old,[s.caseId+':'+s.mode]:true}))});player.current=p
  fetch('./melody-overlap-data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('试听资料读取失败');return r.json()}).then(data=>{if(data.schema!=='harbeat.melody-overlap-pack.v1'||!data.cases?.length)throw Error('没有符合条件的固定样例');if(live){setPack(data);setNotes(feedback[data.cases[0].id]?.notes||'')}}).catch(e=>{if(live)setError(e.message)})
  return()=>{live=false;player.current=null;p.dispose()}
 },[])
 function choose(i:number){player.current?.stop();setIndex(i);setNotes(feedback[pack!.cases[i].id]?.notes||'');setCanUndo(false)}
 function vote(preference:string){const c=pack!.cases[index],next={...feedback,[c.id]:{preference,notes,at:new Date().toISOString()}};previous.current=feedback;setCanUndo(true);store(next)}
 function store(next:Record<string,Feedback>){setFeedback(next);try{localStorage.setItem(storageKey,JSON.stringify(next))}catch{setError('本机存储暂不可用，请导出反馈保存。')}}
 function undo(){if(previous.current){store(previous.current);setNotes(previous.current[pack!.cases[index].id]?.notes||'');setCanUndo(false)}}
 function exportRound(){const value={schema:'harbeat.melody-overlap-feedback.v1',selectionSha256:pack?.selectionSha256,harmonicRelease:pack?.harmonicRelease,rendering:pack?.rendering,limitation:pack?.limitation,feedback,heard,draft:{caseId:pack?.cases[index].id,notes},logs:player.current?.logs};const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='HarBeat-分轨短重叠试听.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 if(!pack)return <main className="harmonic"><h1>分轨短重叠试听</h1><p role={error?'alert':'status'}>{error||'正在读取固定试听资料…'}</p></main>
 const c=pack.cases[index],both=heard[c.id+':reference']&&heard[c.id+':short'],busy=state.status==='loading',current=state.caseId===c.id
 return <main className="harmonic">
  <header><a className="brand" href="http://127.0.0.1:5187/harmonic-key.html">HarBeat<span>LISTENING ROOM / 02</span></a><p className="edition">第二轮 · 分轨短重叠</p></header>
  <section className="intro"><p className="eyebrow">一次只比较一个变化</p><h1>鼓和人声照旧，<br/>旋律少叠一会。</h1><p>同一曲对、同一速度与进出点。沿用调性偏好的选歌和人声冲突检查，只比较旋律／贝斯交接集中到最后一小节，是否听起来更自然。</p><p className="notice">鼓与人声使用相同曲线；分轨可能有串音和残留。本页参考版与短重叠版共享同步片段，变速细节可能与上轮略有差异。线上默认方案保持原样。</p></section>
  <nav aria-label="试听样例">{pack.cases.map((item,i)=><button key={item.id} aria-pressed={index===i} onClick={()=>choose(i)}>0{i+1}<span>{item.aTitle}</span></button>)}</nav>
  <section className="audition"><div className="case-top"><span>固定曲对</span><h2>{c.aTitle}<small>→ {c.bTitle}</small></h2><p>{c.bpm[0].toFixed(1)} → {c.bpm[1].toFixed(1)} BPM · 原接点 {c.plan.start.toFixed(2)}—{c.plan.end.toFixed(2)} 秒</p></div>
   <div className="arms">{(['reference','short'] as Mode[]).map(mode=><article key={mode} className={current&&state.status==='playing'&&state.mode===mode?'active':''}><p className="eyebrow">{names[mode]}</p><h3>旋律重叠约 {(mode==='reference'?c.plan.duration:c.plan.duration-c.shortStart).toFixed(1)} 秒</h3><p>{mode==='reference'?'保留原来的完整渐变':'旋律／贝斯只在最后一小节交接'}</p><button className="play" disabled={busy} onClick={()=>void player.current?.play(c,mode)}>试听{names[mode]}</button><p className="heard">{heard[c.id+':'+mode]?'✓ 已完整听完':'接点前 4 秒 → 正文接管后 8 秒'}</p></article>)}</div>
   <div className="play-status"><p role="status">{current?state.message:'选择一版开始试听'}{current&&state.status==='playing'?' · '+state.position.toFixed(1)+' 秒':''}</p><button onClick={()=>player.current?.stop()}>停止</button></div>
   {(error||state.status==='error')&&<p className="error" role="alert">{error||state.message}</p>}
   <p className="case-note">鼓、人声和 EQ 保持原处理；只调整旋律／贝斯层。分轨残留仍可能造成和声碰撞，缩短重叠也可能让交接更明显，听感由你判断。</p>
  </section>
  <section className="feedback"><h2>这次交接更顺了吗？</h2><p>两版完整播放后可以记录偏好。也请留意节奏是否连续、旋律是否突然、人声是否清楚。</p><div className="votes">{['原方案更顺','短重叠更顺','差不多','两版都不理想'].map(value=><button disabled={!both} key={value} aria-pressed={feedback[c.id]?.preference===value} onClick={()=>vote(value)}>{value}</button>)}</div><label>听感备注<textarea value={notes} onChange={e=>setNotes(e.target.value)} onBlur={()=>{if(feedback[c.id])store({...feedback,[c.id]:{...feedback[c.id],notes}})}} placeholder="例如：旋律不打架了，但切换变得突然"/></label><button onClick={exportRound}>导出反馈与完整播放记录</button>{canUndo&&<button onClick={undo}>撤销本次记录</button>}</section>
  <details><summary>查看固定计划与分轨依据</summary><p>分轨增益相同时可重构原混音。旋律／贝斯层定义为原混音减去人声和鼓，包含分离残差。片段有足够能量只说明可以试听，不代表已经检测出旋律冲突。</p><pre>{JSON.stringify({planSha256:c.planSha256,plan:c.plan,shortStart:c.shortStart,sourceVerification:c.sourceVerification,levels:c.levels},null,2)}</pre></details>
  <footer>HARBEAT / MELODY OVERLAP · {pack.cases.length} 组固定接点试听 · 反馈仅保存在本机</footer>
 </main>
}
