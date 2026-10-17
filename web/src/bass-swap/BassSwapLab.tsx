import {useEffect,useRef,useState} from 'react'
import {BassPlayer,type BassCase,type State} from './transport'
import type {Mode} from './policy'
import './style.css'
type Pack={schema:string;selectionSha256:string;harmonicRelease:string;rendering:string;limitation:string;cases:BassCase[]}
type Feedback={preference:string;notes:string;at:string}
const key='harbeat.bass-swap.v1.feedback',names={reference:'原渐变方案',swap:'独立贝斯交接'}
const initial=()=>{try{return JSON.parse(localStorage.getItem(key)||'{}') as Record<string,Feedback>}catch{return {}}}
export default function BassSwapLab(){
 const [pack,setPack]=useState<Pack|null>(null),[error,setError]=useState(''),[state,setState]=useState<State>({status:'idle',message:'选择一版开始试听',position:0,caseId:'',mode:'reference'})
 const [feedback,setFeedback]=useState(initial),[heard,setHeard]=useState<Record<string,boolean>>({}),[notes,setNotes]=useState(''),[canUndo,setCanUndo]=useState(false)
 const player=useRef<BassPlayer|null>(null),previous=useRef<Record<string,Feedback>|null>(null)
 useEffect(()=>{let live=true;const p=new BassPlayer(new URL('.',location.href),s=>{if(!live)return;setState(s);if(s.status==='complete')setHeard(old=>({...old,[s.mode]:true}))});player.current=p
  fetch('./bass-swap-data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('试听资料读取失败');return r.json()}).then(data=>{if(data.schema!=='harbeat.bass-swap-pack.v1'||data.cases?.length!==1)throw Error('固定试听资料不完整');if(live){setPack(data);setNotes(feedback[data.cases[0].id]?.notes||'')}}).catch(e=>{if(live)setError(e.message)})
  return()=>{live=false;player.current=null;p.dispose()}
 },[])
 function store(next:Record<string,Feedback>){setFeedback(next);try{localStorage.setItem(key,JSON.stringify(next))}catch{setError('本机存储暂不可用，请导出保存。')}}
 function vote(preference:string){const c=pack!.cases[0];previous.current=feedback;setCanUndo(true);store({...feedback,[c.id]:{preference,notes,at:new Date().toISOString()}})}
 function undo(){if(previous.current){store(previous.current);setNotes(previous.current[pack!.cases[0].id]?.notes||'');setCanUndo(false)}}
 function exportRound(){const value={schema:'harbeat.bass-swap-feedback.v1',selectionSha256:pack?.selectionSha256,harmonicRelease:pack?.harmonicRelease,rendering:pack?.rendering,limitation:pack?.limitation,feedback,heard,draft:{caseId:pack?.cases[0].id,notes},logs:player.current?.logs};const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='HarBeat-独立贝斯交接试听.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 if(!pack)return <main className="harmonic"><h1>独立贝斯交接</h1><p role={error?'alert':'status'}>{error||'正在读取固定试听资料…'}</p></main>
 const c=pack.cases[0],busy=state.status==='loading',both=heard.reference&&heard.swap,t=state.position-c.pre
 const phase=state.mode==='reference'?'原渐变播放中':t<c.timing.duckStart?'保留 A 贝斯':t<c.timing.swapStart?'正在轻收 A 贝斯':t<c.timing.swapEnd?'A → B 贝斯交接中':'由 B 贝斯承接'
 return <main className="harmonic">
  <header><a className="brand" href="http://127.0.0.1:5188/melody-overlap.html">HarBeat<span>LISTENING ROOM / 03</span></a><p className="edition">第三轮 · 独立贝斯交接</p></header>
  <section className="intro"><p className="eyebrow">这次只换贝斯</p><h1>先轻收 A 贝斯，<br/>让 B 的低音接上。</h1><p>沿用第二组固定曲对、原速度和进出点。A 的贝斯先逐渐减弱，最后一拍让 B 的贝斯进入，其他乐器继续原来的渐变。</p><p className="notice">鼓、人声、其他旋律和 EQ 使用相同控制曲线。分离贝斯可能含串音，低频变化也可能改变整体限幅响应。本页两版共享同步准备的片段，变速纹理可能与上轮略有差异；线上默认保持原样。</p></section>
  <section className="audition"><div className="case-top"><span>固定曲对 · 原第二组</span><h2>{c.aTitle}<small>→ {c.bTitle}</small></h2><p>{c.bpm[0].toFixed(1)} → {c.bpm[1].toFixed(1)} BPM · 原接点 {c.plan.start.toFixed(2)}—{c.plan.end.toFixed(2)} 秒</p></div>
   <div className="arms">{(['reference','swap'] as Mode[]).map(mode=><article key={mode} className={state.status==='playing'&&state.mode===mode?'active':''}><p className="eyebrow">{names[mode]}</p><h3>{mode==='reference'?'所有声部一起渐变':'B 贝斯先接上'}</h3><p>{mode==='reference'?'贝斯沿用原渐变曲线':'单独交接贝斯，其余声部照旧'}</p><button className="play" disabled={busy} onClick={()=>void player.current?.play(c,mode)}>试听{names[mode]}</button><p className="heard">{heard[mode]?'✓ 已完整听完':'接点前 4 秒 → 正文接管后 8 秒'}</p></article>)}</div>
   <div className="play-status"><p role="status">{state.status==='playing'?phase+' · '+state.position.toFixed(1)+' 秒':state.message}</p><button onClick={()=>player.current?.stop()}>停止</button></div>
   {(error||state.status==='error')&&<p className="error" role="alert">{error||state.message}</p>}
   <ol className="bass-phases"><li>轻收 A 贝斯<span>试听约 {(c.pre+c.timing.duckStart).toFixed(1)} 秒起</span></li><li>一拍交接<span>约 {(c.timing.swapEnd-c.timing.swapStart).toFixed(2)} 秒</span></li><li>B 贝斯承接<span>比正文接管早约 {(c.plan.duration-c.timing.swapEnd).toFixed(1)} 秒</span></li></ol>
  </section>
  <section className="feedback"><h2>这次贝斯交接有帮助吗？</h2><p>两版完整播放后可以记录偏好。留意低频是否更清楚、换贝斯时是否变空，以及节奏是否自然。</p><div className="votes">{['原方案更顺','贝斯交接更顺','差不多','两版都不理想'].map(v=><button key={v} disabled={!both} aria-pressed={feedback[c.id]?.preference===v} onClick={()=>vote(v)}>{v}</button>)}</div><label>听感备注<textarea value={notes} onChange={e=>setNotes(e.target.value)} onBlur={()=>{if(feedback[c.id])store({...feedback,[c.id]:{...feedback[c.id],notes}})}} placeholder="例如：低音更干净，但换入时有些突兀"/></label><button onClick={exportRound}>导出反馈与完整播放记录</button>{canUndo&&<button onClick={undo}>撤销本次记录</button>}</section>
  <details><summary>查看固定计划与贝斯依据</summary><p>参考版贝斯与其他声部使用同一增益，重构原混音。实验版只补偿独立贝斯的增益差；来源和同步通过核验，分离质量仍需听感判断。</p><pre>{JSON.stringify({plan:c.plan,planSha256:c.planSha256,timing:c.timing,sourceVerification:c.sourceVerification,levels:c.levels},null,2)}</pre></details>
  <footer>HARBEAT / BASS SWAP · 一组固定接点试听 · 反馈仅保存在本机</footer>
 </main>
}
