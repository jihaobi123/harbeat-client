import React,{useEffect,useRef,useState} from 'react'
import {createRoot} from 'react-dom/client'
import {BridgePlayer} from './transport'
import type {BridgeCase,Mode,PlayerState} from './types'
import './style.css'
const labels={reference:'原接法',bridge:'保留人声铺伴奏'}
const fmt=(n:number)=>`${Math.floor(n/60)}:${Math.floor(n%60).toString().padStart(2,'0')}`
function App(){
 const [cases,setCases]=useState<BridgeCase[]>([]),[selected,setSelected]=useState(0),[error,setError]=useState(''),[vote,setVote]=useState(''),[volume,setVolume]=useState(.7)
 const [state,setState]=useState<PlayerState>({status:'idle',message:'选择一组歌曲，比较两种接法',position:0,mode:'bridge',caseId:''})
 const player=useRef<BridgePlayer>();const c=cases[selected]
 useEffect(()=>{const controller=new AbortController();fetch('./cases.json',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('试听列表加载失败');return r.json()}).then(d=>setCases(d.cases)).catch(e=>{if(!controller.signal.aborted)setError(e.message)});player.current=new BridgePlayer(new URL('./',location.href),setState);return()=>{controller.abort();player.current?.dispose()}},[])
 useEffect(()=>{try{setVote(localStorage.getItem('harbeat-bridge-v1-'+c?.id)||'')}catch{setVote('')}},[c?.id])
 const choose=(i:number)=>{player.current?.stop();setSelected(i)}
 const play=(mode:Mode)=>{if(c)void player.current?.play(c,mode)}
 const position=state.caseId===c?.id?state.position:0
 const stage=!c?'':position<c.pre?'上一首正在播放':position<c.pre+c.duration*.4?'下一首伴奏铺入':position<c.pre+c.duration?'上一首人声收尾':'下一首接管'
 const busy=['playing','paused','loading'].includes(state.status)
 const saveVote=(v:string)=>{setVote(v);try{localStorage.setItem('harbeat-bridge-v1-'+c.id,v)}catch{}}
 return <main>
  <header><a className="brand" href="/listen/">HARBEAT <span>听歌</span></a><span className="badge">接歌试听 · 01</span></header>
  <section className="intro"><p className="eyebrow">让人声唱完，让伴奏先到</p><h1>给下一首，<br/>一个自然的开场。</h1><p>前一首还在唱，后一首的伴奏已经铺进来。<br className="wide"/>等这一句唱完，再把舞台交给下一首。</p></section>
  {error&&<p role="alert" className="error">{error}</p>}
  {c?<>
   <section className="player" aria-label="接歌试听播放器">
    <div className="player-top"><label htmlFor="case">试听组合</label><span>{selected+1} / {cases.length}</span></div>
    <select id="case" value={selected} onChange={e=>choose(Number(e.target.value))}>{cases.map((x,i)=><option key={x.id} value={i}>{i+1}. {x.aTitle} → {x.bTitle}</option>)}</select>
    <div className="tracks"><div><span>上一首 · 保留人声</span><h2>{c.aTitle}</h2></div><span className="arrow" aria-hidden="true">↗</span><div><span>下一首 · {c.label}</span><h2>{c.bTitle}</h2></div></div>
    <div className="tags"><span>{c.style}</span><span>交接 {c.duration.toFixed(1)} 秒</span><span>同一接点对照</span></div>
    <div className="compare"><button className={state.mode==='reference'&&busy?'active':''} onClick={()=>play('reference')}><small>A · 整首渐进交接</small>{labels.reference}<span>从头试听 ↗</span></button><button className={'primary '+(state.mode==='bridge'&&busy?'active':'')} onClick={()=>play('bridge')}><small>B · 人声与伴奏分开交接</small>{labels.bridge}<span>从头试听 ↗</span></button></div>
    <div className="now"><span>{busy||state.status==='complete'?labels[state.mode]+' · '+stage:'准备好后，点上方按钮开始'}</span><time>{fmt(position)} / {fmt(c.pre+c.duration+c.post)}</time></div>
    <progress max={c.pre+c.duration+c.post} value={position} aria-label="试听进度"/>
    <div className="controls"><button disabled={!['playing','paused'].includes(state.status)} onClick={()=>void(state.status==='paused'?player.current?.resume():player.current?.pause())}>{state.status==='paused'?'继续':'暂停'}</button><button disabled={!busy} onClick={()=>player.current?.stop()}>停止</button><label>音量 <input type="range" min="0" max="1" step=".01" value={volume} onChange={e=>{const v=Number(e.target.value);setVolume(v);player.current?.setVolume(v)}}/></label></div>
    <p className={'status '+(state.status==='error'?'error':'')} role="status">{state.message}</p>
   </section>
   <section className="feedback"><div><h3>这一组，你更喜欢哪种？</h3><p>先分别听完，再留个记号。选择只保存在这台设备。</p></div><div className="votes">{['原接法','新接法','差别不大','都不自然'].map(v=><button aria-pressed={vote===v} className={vote===v?'chosen':''} key={v} onClick={()=>saveVote(v)}>{v}</button>)}</div></section>
   <details><summary>这次试听改了什么</summary><p>新接法先交接伴奏，保留上一首的人声，等检测到的人声结束后再淡出。下一首从前奏、间奏或其他无人声片段进入，随后恢复完整歌曲。</p><p>两种接法使用相同歌曲、接点和速度。原接法沿用整首渐变和动态均衡；新接法试验分轨音量交接。试听结束前，下一首保持匹配后的速度（本组 {c.rate.toFixed(3)} 倍），这次不比较恢复原速的方式。</p><p>这里只准备短分轨素材，由浏览器实时混音。每组约 {Math.round(Object.values(c.assets).reduce((n,a)=>n+a.bytes,0)/1048576)} MB，第一次播放需要加载。分轨可能有串音，段落与人声检测也可能有偏差；当前未用调性筛选，这些都需要实际试听判断。</p><p>这是独立的六组试听，不会替换正式听歌页，也不代表全曲库都适合这种接法。</p></details>
  </>:!error&&<p role="status">正在加载试听组合…</p>}
  <footer><span>HARBEAT · Vocal bridge 01</span><a href="/listen/">返回实时听歌 ↗</a></footer>
 </main>
}
createRoot(document.getElementById('root')!).render(<App/> )
