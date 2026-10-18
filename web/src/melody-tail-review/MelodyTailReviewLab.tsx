import {useEffect,useRef,useState} from 'react'
import {MelodyYieldPlayer,type MelodyYieldCase,type State} from './transport'
import {archiveRound,canVote,createRound,letters,markHeard,markPlayed,recordChoice,restoreStore,revealCase,setPractice,storageKey,updateFeedback,withPlayerLogs,type Choice,type Letter,type Round,type RoundStore,type Symptom} from './rounds'
import {RoundPersistence,indexedDBBackend} from '../bass-generalization/storage'
import './style.css'

type Pack={schema:string;selectionSha256:string;harmonicRelease?:string;rendering:unknown;limitation:unknown;cases:MelodyYieldCase[];audit?:{candidates:{aTitle:string;bTitle:string;accepted:boolean;reason:string}[];[key:string]:unknown}}
const choices:{value:Choice;label:string}[]=[{value:'A',label:'A 更顺'},{value:'B',label:'B 更顺'},{value:'tie',label:'差不多'},{value:'none',label:'都不理想'}]
const symptoms:{value:Symptom;label:string}[]=[{value:'space-clearer',label:'旋律叠加更清楚'},{value:'melody-cut',label:'末尾接管突兀'},{value:'thin',label:'声音变空'},{value:'stem-bleed',label:'误伤人声、鼓或贝斯'},{value:'clicks',label:'有接缝或咔嗒声'},{value:'louder',label:'声音更响'},{value:'quieter',label:'声音更轻'}]
const names={natural:'原方案',relay:'提前收掉 A 的旋律／其他乐器'}
const idle:State={status:'idle',message:'',position:0,caseId:'',mode:'natural'}
const timestamp=()=>new Date().toISOString()
const fresh=(pack:Pack,orderPhase:0|1=0)=>({...createRound(pack.cases.map(c=>c.id),pack.selectionSha256,false,Math.random,undefined,undefined,orderPhase),assetFingerprint:JSON.stringify(pack.cases.map(c=>({id:c.id,assets:Object.entries(c.assets).sort(([a],[b])=>a.localeCompare(b))}))),sourceSnapshot:pack})

export default function MelodyTailReviewLab(){
 const [pack,setPack]=useState<Pack|null>(null),[store,setStore]=useState<RoundStore|null>(null),[index,setIndex]=useState(0),[error,setError]=useState(''),[storageWarning,setStorageWarning]=useState('')
 const [state,setState]=useState<State>(idle)
 const [persistence]=useState(()=>new RoundPersistence(indexedDBBackend('harbeat.melody-tail-review.v1'),()=>localStorage.getItem(storageKey)))
 const [saving,setSaving]=useState(false)
 const soloAudio=useRef<HTMLAudioElement|null>(null)
 const player=useRef<MelodyYieldPlayer|null>(null),latest=useRef<RoundStore|null>(null),saveRevision=useRef(0)
 latest.current=store
 function snapshot(value:RoundStore,p=player.current){return p?withPlayerLogs(value,p.recordId,p.logs):value}
 function save(value:RoundStore){
  const revision=++saveRevision.current
  setSaving(true)
  void persistence.save(JSON.stringify(value)).then(()=>{if(revision===saveRevision.current){setSaving(false);setStorageWarning('')}}).catch(()=>{if(revision===saveRevision.current){setSaving(false);setStorageWarning('本机保存失败，请导出记录，避免关闭页面后丢失。')}})
 }
 useEffect(()=>{if(store)save(store)},[store])
 useEffect(()=>{
  let live=true
  const p=new MelodyYieldPlayer(new URL('.',location.href),s=>{
   if(!live)return
   setState(s)
   if(s.status==='playing'){
    const played={status:s.status,roundId:s.roundId,caseId:s.caseId,letter:s.letter}
    setStore(old=>{
     if(!old)return old
     const current=markPlayed(old.current,played)
     return current===old.current?old:{...old,current}
    })
   }else if(s.status==='complete'){
    // Capture the emitting event before the queued updater runs or the UI changes round.
    const completion={status:s.status,roundId:s.roundId,caseId:s.caseId,letter:s.letter}
    setStore(old=>old?snapshot({...old,current:markHeard(old.current,completion)},p):old)
   }else if(s.status==='error'||s.status==='idle'){
    queueMicrotask(()=>{if(live)setStore(old=>old?snapshot(old,p):old)})
   }
  })
  player.current=p
  fetch('./melody-tail-review-data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('试听资料读取失败');return r.json()}).then(async(data:Pack)=>{
   if(data.schema!=='harbeat.melody-tail-review-pack.v1'||![1,2,3].includes(data.cases?.length)||!data.selectionSha256)throw Error('固定试听资料不完整，需要一到三组已核验样例。')
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
 function choose(i:number){soloAudio.current?.pause();player.current?.stop();setIndex(i);setState(idle)}
 function play(letter:Letter){
  if(!store||!pack)return
  soloAudio.current?.pause()
  const c=pack.cases[index],roundId=store.current.id,mode=store.current.cases[c.id].mapping[letter]
  changeRound(r=>r.id===roundId?{...r,startedAt:r.startedAt??timestamp()}:r)
  void player.current?.play(c,mode,{roundId,letter})
 }
 function newRound(){
  if(!pack)return
  soloAudio.current?.pause()
  player.current?.stop()
  setStore(old=>old?archiveRound(snapshot(old),fresh(pack,old.current.orderPhase===0?1:0)):old)
  setIndex(0);setState(idle)
 }
 function download(value:unknown,filename:string){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
 function exportRound(){
  if(!store)return
  const complete=snapshot(store)
  setStore(complete)
  download({...complete,schema:'harbeat.melody-tail-review-feedback.v1',exportedAt:timestamp(),pack,listenerRoundIds:[...complete.history,complete.current].filter(r=>!r.practice).map(r=>r.id),interpretation:'练习轮不计听众偏好；允许提前选择，每次保留当时完整听过的版本。推荐顺序与实际播放分开记录，不能假设遵守推荐。小样本用于验证特定片段的人声与伴奏交接，不能推广到所有歌曲。'},'HarBeat-旋律让位末尾补听-全部记录.json')
 }
 async function exportRaw(){download({...(await persistence.recover()),inMemory:latest.current? snapshot(latest.current):null,error,exportedAt:timestamp()},'HarBeat-旋律让位末尾补听-原始本机记录.json')}
 if(!pack||!store)return <main id="top" className="harmonic coverage vocal-bed"><h1>旋律让位末尾补听</h1><p role={error?'alert':'status'}>{error||'正在读取固定试听资料…'}</p>{error&&<button onClick={exportRaw}>导出原始本机记录</button>}</main>
 const round=store.current,c=pack.cases[index],feedback=round.cases[c.id]
 const votedCases=Object.values(round.cases).filter(item=>!!item.firstBlindChoice).length
 const revealed=!!feedback.revealedAt&&(round.practice||votedCases===pack.cases.length),current=state.caseId===c.id&&state.roundId===round.id
 const status=current?({idle:'已停止',loading:'正在准备音频…',playing:'正在播放',complete:'已完整播放',error:'播放失败，请重试'}[state.status]):'选择一个版本开始试听'
 const heardCount=letters.filter(l=>!!feedback.heard[l]).length
 return <main id="top" className="harmonic coverage vocal-bed">
  <header><a className="brand" href="#top">HarBeat<span>LISTENING ROOM / MELODY</span></a><p className="edition">Attention · 最后接管补听</p></header>
  <section className="intro"><p className="eyebrow">同一片段 · 末尾补听</p><h1>最后接管，<br/>哪一版更顺。</h1><p>只补听 Attention → HIPHOP，每版约 7 秒：接管前 4 秒到接管后 3 秒。两版仍是原方案与旋律让位，选点、速度、人声、鼓、贝斯和 EQ 都沿用原计划。先生成完整原计划再截取这段，未加入新的混音手法。</p><p className="notice">你之前三组的选择保留不变。这里单独记录末尾补听，不与第一次偏好合并。可随时选择；判断最后接管时，请至少听过中间的接管位置。</p></section>
  <section className="round-bar" aria-label="本轮记录"><div><strong>{round.practice?'练习轮':'正式试听轮'}</strong><span>已记录 {votedCases} / {pack.cases.length} 组 · {saving?'正在保存…':storageWarning?'保存受限':'已保存在本机'}</span></div><label><input type="checkbox" checked={round.practice} disabled={!!round.startedAt||votedCases>0} onChange={e=>changeRound(r=>setPractice(r,e.target.checked))}/>练习轮（熟悉操作，不计入听众偏好）</label><p>开始播放或作出选择后，本轮用途固定。新一轮保留旧记录，重新分配 A/B，并翻转建议先听的版本。练习轮可逐组揭晓；正式轮需完成所有组初选。</p><div className="round-actions"><button onClick={exportRound}>导出本轮、历史与完整播放记录</button><button onClick={newRound}>保存本轮并开始新一轮</button></div></section>
  {storageWarning&&<p className="error" role="alert">{storageWarning} <button onClick={exportRaw}>导出原始本机记录</button></p>}
  <nav aria-label="试听样例">{pack.cases.map((item,i)=><button key={item.id} aria-pressed={index===i} onClick={()=>choose(i)}>{String(i+1).padStart(2,'0')}<span>{item.aTitle}</span>{round.cases[item.id].firstBlindChoice?'已记录':'待试听'}</button>)}</nav>
  <section className="audition"><div className="case-top"><span>{`固定曲对 ${String(index+1).padStart(2,'0')} / ${String(pack.cases.length).padStart(2,'0')}`}</span><h2>{c.aTitle}<small>→ {c.bTitle}</small></h2><p>{c.bpm[0].toFixed(1)} → {c.bpm[1].toFixed(1)} BPM · 两版使用同一原计划和接点</p></div>
   <p className="order-hint">本组建议先听 {feedback.recommendedOrder[0]}，再听 {feedback.recommendedOrder[1]}。可以自由重听，也可以随时选择。</p><div className="arms">{feedback.recommendedOrder.map(letter=><article key={letter} className={current&&state.status==='playing'&&state.letter===letter?'active':''}><p className="eyebrow">版本 {letter}</p><h3>{revealed?names[feedback.mapping[letter]]:`版本 ${letter}`}</h3><p>{revealed?'处理说明见下方揭晓记录':'可以随时选择偏好，记录会自动保存。'}</p><button className="play" onClick={()=>play(letter)}>试听 {letter}</button><p className="heard">{feedback.heard[letter]?'✓ 已完整听完':'尚未完整听完'}</p></article>)}</div>
   <div className="play-status"><p role="status">{current&&state.letter?`版本 ${state.letter} · `:''}{status}{current&&state.status==='playing'?` · ${state.position.toFixed(1)} 秒`:''}</p><button onClick={()=>{soloAudio.current?.pause();player.current?.stop()}}>停止</button></div>
   {state.status==='error'&&current&&<p className="error" role="alert">音频未能完整播放。请重试；本次不会计为听完。</p>}
  </section>
  <section className="feedback"><h2>哪一版交接更顺？</h2><p>{heardCount===2?'两版已完整听完，可以记录偏好。':`已完整听完 ${heardCount} / 2 版。现在就可以选择，无需全部播完。`}每次改选都会留下记录，第一次盲听选择会一直保留。</p><div className="votes">{choices.map(({value,label})=><button key={value} disabled={!canVote(round,c.id)} aria-pressed={feedback.choice===value} onClick={()=>changeRound(r=>recordChoice(r,c.id,value))}>{label}</button>)}</div>
   {feedback.firstBlindChoice&&<p className="first-choice">初次盲听：{choices.find(item=>item.value===feedback.firstBlindChoice?.choice)?.label} · {new Date(feedback.firstBlindChoice.at).toLocaleString('zh-CN')} · 初选时完整听过：{letters.filter(l=>feedback.firstBlindChoice?.heard[l]).join('、')||'尚无完整播放'}{revealed?' · 已揭晓':''}</p>}
   <fieldset className="symptoms"><legend>听到了什么？（可多选，备注里写明版本）</legend>{symptoms.map(item=><label key={item.value}><input type="checkbox" checked={feedback.symptoms.includes(item.value)} onChange={e=>{const checked=e.target.checked;changeRound(r=>{const entry=r.cases[c.id];return updateFeedback(r,c.id,checked?[...entry.symptoms,item.value]:entry.symptoms.filter(v=>v!==item.value),entry.notes)})}}/>{item.label}</label>)}</fieldset>
   <label>听感备注<textarea value={feedback.notes} onChange={e=>{const notes=e.target.value;changeRound(r=>updateFeedback(r,c.id,r.cases[c.id].symptoms,notes))}} placeholder="例如：A 最后接管更自然；B 末尾变空或有接缝；差别不大"/></label>
   {!revealed&&<><button disabled={!feedback.firstBlindChoice||!round.practice&&votedCases!==pack.cases.length} onClick={()=>changeRound(r=>revealCase(r,c.id))}>揭晓本组处理方式</button>{!round.practice&&votedCases<pack.cases.length&&<p>正式轮需先完成所有组初次盲听选择。当前已完成 {votedCases} / {pack.cases.length} 组。</p>}</>}
  </section>
  {revealed&&<section className="reveal" aria-label="本组揭晓记录"><h2>本组处理方式</h2><p>揭晓于 {new Date(feedback.revealedAt!).toLocaleString('zh-CN')}，之后的改选会单独标记。</p><ul>{letters.map(letter=><li key={letter}>{letter} · {names[feedback.mapping[letter]]}</li>)}</ul><p>原方案按原渐变。处理版从交接开始逐步收掉 A 的“其他乐器”，在原曲 {(c.plan.start+c.yieldEnd).toFixed(2)} 秒收完；B 及两边的人声、鼓、贝斯沿用原曲线。没有新增其他混音手法。</p><p>“其他乐器”包括和声、旋律和多种乐器，也可能有分离串音。两版使用同一套素材、EQ 和输出链，没有分别调整响度。请判断是否更清楚，还是变空、突兀或误伤其他声部。</p><p>单独复核 A 的其他乐器分轨：</p><audio ref={soloAudio} controls preload="none" src={c.assets.aOther.url} onPlay={()=>player.current?.stop()}/><p>上面的单独分轨是原完整片段；补听 A/B 则截取最后接管前后 7 秒。</p><details><summary>固定计划与来源核验</summary><pre>{JSON.stringify({selectionSha256:pack.selectionSha256,planSha256:c.planSha256,plan:c.plan,yieldEnd:c.yieldEnd,firstBar:c.firstBar,sourceVerification:c.sourceVerification,features:c.features,rendering:pack.rendering,limitation:pack.limitation},null,2)}</pre></details></section>}
  <section className="history"><h2>保存在本机的历史</h2>{store.history.length?<ul>{store.history.map(r=><li key={r.id}>{new Date(r.createdAt).toLocaleString('zh-CN')} · {r.practice?'练习轮':'正式试听轮'} · {Object.values(r.cases).filter(item=>item.firstBlindChoice).length} / {Object.keys(r.cases).length} 组已记录</li>)}</ul>:<p>还没有归档的轮次。开始新一轮时，当前记录会保存在这里。</p>}<p>练习轮保留在导出文件中，并带有单独标记。这里不汇总方法胜率。</p></section>
  <footer>HARBEAT / MELODY YIELD · {pack.cases.length} 组固定曲对 · 本页为独立试听实验 · 反馈保存在当前浏览器</footer>
 </main>
}
