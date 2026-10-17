import {useEffect,useRef,useState} from 'react'
import {CoveragePlayer,type CoverageCase,type State} from './transport'
import {archiveRound,canVote,createRound,letters,markHeard,recordChoice,restoreStore,revealCase,setPractice,storageKey,updateFeedback,withPlayerLogs,type Choice,type Letter,type Round,type RoundStore,type Symptom} from './rounds'
import {RoundPersistence,indexedDBBackend} from './storage'
import './style.css'

type Pack={schema:string;selectionSha256:string;harmonicRelease:string;rendering:unknown;limitation:unknown;cases:CoverageCase[];audit?:unknown}
const choices:{value:Choice;label:string}[]=[{value:'A',label:'A 更顺'},{value:'B',label:'B 更顺'},{value:'C',label:'C 更顺'},{value:'tie',label:'差不多'},{value:'none',label:'都不理想'}]
const symptoms:{value:Symptom;label:string}[]=[{value:'bass-clearer',label:'贝斯更清楚'},{value:'kick-weaker',label:'底鼓变弱'},{value:'low-end-empty',label:'低频变空'},{value:'abrupt',label:'交接突兀'},{value:'voice-muddy',label:'人声变糊'},{value:'louder',label:'声音更响'},{value:'quieter',label:'声音更轻'}]
const names={reference:'原渐变',stem:'独立贝斯交接',eq:'低频 EQ 交接'}
const idle:State={status:'idle',message:'',position:0,caseId:'',mode:'reference'}
const timestamp=()=>new Date().toISOString()
const fresh=(pack:Pack)=>({...createRound(pack.cases.map(c=>c.id),pack.selectionSha256),sourceSnapshot:pack})

export default function BassCoverageLab(){
 const [pack,setPack]=useState<Pack|null>(null),[store,setStore]=useState<RoundStore|null>(null),[index,setIndex]=useState(0),[error,setError]=useState(''),[storageWarning,setStorageWarning]=useState('')
 const [state,setState]=useState<State>(idle)
 const [persistence]=useState(()=>new RoundPersistence(indexedDBBackend(),()=>localStorage.getItem(storageKey)))
 const [saving,setSaving]=useState(false)
 const player=useRef<CoveragePlayer|null>(null),latest=useRef<RoundStore|null>(null),sessionId=useRef(crypto.randomUUID()),saveRevision=useRef(0)
 latest.current=store
 function snapshot(value:RoundStore,p=player.current){return p?withPlayerLogs(value,sessionId.current,p.logs):value}
 function save(value:RoundStore){
  const revision=++saveRevision.current
  setSaving(true)
  void persistence.save(JSON.stringify(value)).then(()=>{if(revision===saveRevision.current){setSaving(false);setStorageWarning('')}}).catch(()=>{if(revision===saveRevision.current){setSaving(false);setStorageWarning('本机保存失败，请导出记录，避免关闭页面后丢失。')}})
 }
 useEffect(()=>{if(store)save(store)},[store])
 useEffect(()=>{
  let live=true
  const p=new CoveragePlayer(new URL('.',location.href),s=>{
   if(!live)return
   setState(s)
   if(s.status==='complete'){
    // Capture the emitting event before the queued updater runs or the UI changes round.
    const completion={status:s.status,roundId:s.roundId,caseId:s.caseId,letter:s.letter}
    setStore(old=>old?snapshot({...old,current:markHeard(old.current,completion)},p):old)
   }else if(s.status==='error'||s.status==='idle'){
    queueMicrotask(()=>{if(live)setStore(old=>old?snapshot(old,p):old)})
   }
  })
  player.current=p
  fetch('./bass-generalization-data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('试听资料读取失败');return r.json()}).then(async(data:Pack)=>{
   if(data.schema!=='harbeat.bass-generalization-pack.v1'||data.cases?.length!==6||!data.selectionSha256)throw Error('固定试听资料不完整，需要六组已核验样例。')
   const loaded=await persistence.load()
   // Legacy localStorage stays untouched; only validated records migrate to IndexedDB.
   const restored=restoreStore(loaded.raw,fresh(data))
   if(live){setPack(data);setStore(restored);if(loaded.warning)setStorageWarning('本机记录读取受限，请导出本轮和原始记录备份。')}
  }).catch(e=>{if(live)setError(e instanceof Error?e.message:'试听资料读取失败')})
  const timer=window.setInterval(()=>{if(live&&p.logs.length)setStore(old=>old?snapshot(old,p):old)},2000)
  const saveOnExit=()=>{if(latest.current)void persistence.save(JSON.stringify(snapshot(latest.current,p))).catch(()=>{if(live)setStorageWarning('本机保存失败，请导出记录备份。')})}
  const saveWhenHidden=()=>{if(document.visibilityState==='hidden')saveOnExit()}
  window.addEventListener('pagehide',saveOnExit)
  document.addEventListener('visibilitychange',saveWhenHidden)
  return()=>{saveOnExit();live=false;window.clearInterval(timer);window.removeEventListener('pagehide',saveOnExit);document.removeEventListener('visibilitychange',saveWhenHidden);p.dispose();player.current=null}
 },[])
 const changeRound=(update:(round:Round)=>Round)=>setStore(old=>old?{...old,current:update(old.current)}:old)
 function choose(i:number){player.current?.stop();setIndex(i);setState(idle)}
 function play(letter:Letter){
  if(!store||!pack)return
  const c=pack.cases[index],roundId=store.current.id,mode=store.current.cases[c.id].mapping[letter]
  changeRound(r=>r.id===roundId?{...r,startedAt:r.startedAt??timestamp()}:r)
  void player.current?.play(c,mode,{roundId,letter})
 }
 function newRound(){
  if(!pack)return
  player.current?.stop()
  setStore(old=>old?archiveRound(snapshot(old),fresh(pack)):old)
  setIndex(0);setState(idle)
 }
 function download(value:unknown,filename:string){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
 function exportRound(){
  if(!store)return
  const complete=snapshot(store)
  setStore(complete)
  download({...complete,schema:'harbeat.bass-generalization-feedback.v1',exportedAt:timestamp(),pack,listenerRoundIds:[...complete.history,complete.current].filter(r=>!r.practice).map(r=>r.id),interpretation:'练习轮只用于操作检查；旧锚点已听过。六组覆盖仅供初步观察，不代表全曲库。'},'HarBeat-贝斯交接覆盖-全部记录.json')
 }
 async function exportRaw(){download({...(await persistence.recover()),inMemory:latest.current? snapshot(latest.current):null,error,exportedAt:timestamp()},'HarBeat-贝斯交接-原始本机记录.json')}
 if(!pack||!store)return <main className="harmonic coverage"><h1>贝斯交接覆盖试听</h1><p role={error?'alert':'status'}>{error||'正在读取固定试听资料…'}</p>{error&&<button onClick={exportRaw}>导出原始本机记录</button>}</main>
 const round=store.current,c=pack.cases[index],feedback=round.cases[c.id]
 const votedCases=Object.values(round.cases).filter(item=>!!item.firstBlindChoice).length
 const revealed=!!feedback.revealedAt&&(round.practice||votedCases===6),current=state.caseId===c.id&&state.roundId===round.id
 const status=current?({idle:'已停止',loading:'正在准备音频…',playing:'正在播放',complete:'已完整播放',error:'播放失败，请重试'}[state.status]):'选择一个版本开始试听'
 const heardCount=letters.filter(l=>!!feedback.heard[l]).length
 return <main className="harmonic coverage">
  <header><a className="brand" href="http://127.0.0.1:5187/harmonic-key.html">HarBeat<span>LISTENING ROOM / 04</span></a><p className="edition">第四轮 · 六组交接覆盖</p></header>
  <section className="intro"><p className="eyebrow">固定曲对 · 三版盲听</p><h1>换几首歌，<br/>再听听交接。</h1><p>每组都是同一个接点。试听 A、B、C，听到足够判断时就可以选择，也可以随时改选。正式试听轮要先完成六组初次选择，才能揭晓处理方式。</p><p className="notice">六组只能初步观察适用范围和失败样例，无法代表全曲库或长期自动播放。旧样例已听过，会单列为锚点。三版未单独做等响校准，音量差异也请记录。</p></section>
  <section className="round-bar" aria-label="本轮记录"><div><strong>{round.practice?'练习轮':'正式试听轮'}</strong><span>已记录 {votedCases} / 6 组 · {saving?'正在保存…':storageWarning?'保存受限':'已保存在本机'}</span></div><label><input type="checkbox" checked={round.practice} disabled={!!round.startedAt} onChange={e=>changeRound(r=>setPractice(r,e.target.checked))}/>练习轮（熟悉操作，不计入听众偏好）</label><p>开始播放后，本轮用途固定。新一轮会保留旧记录，并重新分配 A/B/C。练习轮可逐组揭晓；正式轮需完成六组初次选择。</p><div className="round-actions"><button onClick={exportRound}>导出本轮、历史与完整播放记录</button><button onClick={newRound}>保存本轮并开始新一轮</button></div></section>
  {storageWarning&&<p className="error" role="alert">{storageWarning} <button onClick={exportRaw}>导出原始本机记录</button></p>}
  <nav aria-label="试听样例">{pack.cases.map((item,i)=><button key={item.id} aria-pressed={index===i} onClick={()=>choose(i)}>{String(i+1).padStart(2,'0')} · {item.anchor?'已听锚点':item.slot.label}<span>{item.aTitle}</span>{round.cases[item.id].firstBlindChoice?'已记录':'待试听'}</button>)}</nav>
  <section className="audition"><div className="case-top"><span>{c.anchor?'旧样例 · 已听过的锚点，不算独立新样本':`新样例 · ${c.slot.label}（原曲库标签）`}</span><h2>{c.aTitle}<small>→ {c.bTitle}</small></h2><p>{c.bpm[0].toFixed(1)} → {c.bpm[1].toFixed(1)} BPM · 三版使用同一原计划和接点</p></div>
   <div className="arms">{letters.map(letter=><article key={letter} className={current&&state.status==='playing'&&state.letter===letter?'active':''}><p className="eyebrow">版本 {letter}</p><h3>{revealed?names[feedback.mapping[letter]]:`先听版本 ${letter}`}</h3><p>{revealed?'处理说明见下方揭晓记录':'可以随时选择偏好，记录会自动保存。'}</p><button className="play" onClick={()=>play(letter)}>试听 {letter}</button><p className="heard">{feedback.heard[letter]?'✓ 已完整听完':'尚未完整听完'}</p></article>)}</div>
   <div className="play-status"><p role="status">{current&&state.letter?`版本 ${state.letter} · `:''}{status}{current&&state.status==='playing'?` · ${state.position.toFixed(1)} 秒`:''}</p><button onClick={()=>player.current?.stop()}>停止</button></div>
   {state.status==='error'&&current&&<p className="error" role="alert">音频未能完整播放。请重试；本次不会计为听完。</p>}
  </section>
  <section className="feedback"><h2>哪一版交接更顺？</h2><p>{heardCount===3?'三版已完整听完，可以记录偏好。':`已完整听完 ${heardCount} / 3 版。现在就可以选择，无需全部播完。`}每次改选都会留下记录，第一次盲听选择会一直保留。</p><div className="votes">{choices.map(({value,label})=><button key={value} disabled={!canVote(round,c.id)} aria-pressed={feedback.choice===value} onClick={()=>changeRound(r=>recordChoice(r,c.id,value))}>{label}</button>)}</div>
   {feedback.firstBlindChoice&&<p className="first-choice">初次盲听：{choices.find(item=>item.value===feedback.firstBlindChoice?.choice)?.label} · {new Date(feedback.firstBlindChoice.at).toLocaleString('zh-CN')}{revealed?' · 已揭晓':''}</p>}
   <fieldset className="symptoms"><legend>听到了什么？（可多选，备注里写明版本）</legend>{symptoms.map(item=><label key={item.value}><input type="checkbox" checked={feedback.symptoms.includes(item.value)} onChange={e=>{const checked=e.target.checked;changeRound(r=>{const entry=r.cases[c.id];return updateFeedback(r,c.id,checked?[...entry.symptoms,item.value]:entry.symptoms.filter(v=>v!==item.value),entry.notes)})}}/>{item.label}</label>)}</fieldset>
   <label>听感备注<textarea value={feedback.notes} onChange={e=>{const notes=e.target.value;changeRound(r=>updateFeedback(r,c.id,r.cases[c.id].symptoms,notes))}} placeholder="例如：B 的贝斯更清楚，但底鼓也轻了；C 的交接有点突然"/></label>
   {!revealed&&<><button disabled={!feedback.firstBlindChoice||!round.practice&&votedCases!==6} onClick={()=>changeRound(r=>revealCase(r,c.id))}>揭晓本组处理方式</button>{!round.practice&&votedCases<6&&<p>正式轮需先完成六组初次盲听选择。当前已完成 {votedCases} / 6 组。</p>}</>}
  </section>
  {revealed&&<section className="reveal" aria-label="本组揭晓记录"><h2>本组处理方式</h2><p>揭晓于 {new Date(feedback.revealedAt!).toLocaleString('zh-CN')}。此后的改选会标记为揭晓后选择。</p><ul>{letters.map(letter=><li key={letter}><strong>{letter} · {names[feedback.mapping[letter]]}</strong></li>)}</ul><p>原渐变沿用整曲增益和动态 EQ。独立贝斯版让 A 的贝斯轻收，在最后一拍交接，由 B 在下一小节提前承接；分离可能有串音和残留。其他声部沿用参考曲线。</p><p>低频 EQ 版在原处理上增加固定 140 Hz 低架滤波，最多额外削减 18 dB。A 从 duckStart 到 swapStart 由 0 降至 −6 dB，再到 swapEnd 降至 −18 dB；B 在 swapStart 前为 −18 dB，到 swapEnd 恢复 0 dB。它也会影响该频段的底鼓和其他声音。</p><p>三版使用相同接点、同步素材和输出链，没有按版本分别归一化。EQ 和独立贝斯并未做逐频率或等响匹配，请结合“更响／更轻”的听感判断。</p><details><summary>固定计划、处理时刻与来源核验</summary><pre>{JSON.stringify({selectionSha256:pack.selectionSha256,planSha256:c.planSha256,plan:c.plan,timing:c.timing,levels:c.levels,sourceVerification:c.sourceVerification,harmonicRelease:pack.harmonicRelease,rendering:pack.rendering,limitation:pack.limitation,audit:pack.audit},null,2)}</pre></details></section>}
  <section className="history"><h2>保存在本机的历史</h2>{store.history.length?<ul>{store.history.map(r=><li key={r.id}>{new Date(r.createdAt).toLocaleString('zh-CN')} · {r.practice?'练习轮':'正式试听轮'} · {Object.values(r.cases).filter(item=>item.firstBlindChoice).length} / 6 组已记录</li>)}</ul>:<p>还没有归档的轮次。开始新一轮时，当前记录会保存在这里。</p>}<p>练习轮保留在导出文件中，并带有单独标记。这里不汇总方法胜率。</p></section>
  <footer>HARBEAT / BASS COVERAGE · 6 组固定曲对 · 本页为独立试听实验 · 反馈保存在当前浏览器</footer>
 </main>
}
