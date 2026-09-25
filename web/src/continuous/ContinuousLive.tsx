import {useEffect,useMemo,useRef,useState} from 'react'
import {loadJson} from '../phrase/load'
import {LiveTransport} from '../realtime/transport'
import {planVocalOverlap} from '../vocal-overlap/planner'
import {filterLibrary,readLibraryIndex,suggestNext,TrackLibrary,refreshLibraryTracks,type LibraryEntry,type LibraryIndex} from './catalog'
import {NextSelection,type SelectionState} from './selection'
import {automaticAction} from './automatic'
import {initializeFromGesture} from './activation'
import {styleChoices,pickStyle} from './styles'
import MusicImport from './MusicImport'
import './continuous.css'
import './import.css'

const base=new URL('.',location.href)
const clock=(input:number|null)=>{const value=input??0;return `${Math.floor(Math.max(0,value)/60)}:${String(Math.floor(Math.max(0,value)%60)).padStart(2,'0')}`}
const idle:SelectionState={id:null,status:'idle',error:''}
export default function ContinuousLive(){
 const [index,setIndex]=useState<LibraryIndex|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[starting,setStarting]=useState(false)
 const [collection,setCollection]=useState(''),[label,setLabel]=useState(''),[query,setQuery]=useState(''),[limit,setLimit]=useState(40)
 const [selection,setSelection]=useState<SelectionState>(idle),[volume,setVolume]=useState(.85),[automatic,setAutomatic]=useState(true),[seekDraft,setSeekDraft]=useState<number|null>(null)
 const [importOpen,setImportOpen]=useState(false),[chooseMode,setChooseMode]=useState<'song'|'style'>('song'),[styleDraft,setStyleDraft]=useState(''),[intentStyle,setIntentStyle]=useState('')
 const styleIntent=useRef(''),startingId=useRef<string|null>(null);styleIntent.current=intentStyle
 const [,refresh]=useState(0),transport=useRef<LiveTransport|null>(null),initializing=useRef<Promise<LiveTransport>|null>(null),library=useRef<TrackLibrary|null>(null),next=useRef<NextSelection|null>(null)
 const alive=useRef(true),startRevision=useRef(0),recent=useRef<string[]>([]),lastCurrent=useRef<string|null>(null),autoAt=useRef(0),autoExcluded=useRef(new Set<string>()),autoWorking=useRef(false),selectionRevision=useRef(0),filters=useRef({collection,label,query}),volumeRef=useRef(volume)
 filters.current={collection,label,query};volumeRef.current=volume
 useEffect(()=>{autoAt.current=0;autoExcluded.current.clear()},[collection,label])
 useEffect(()=>{
  alive.current=true;let valid=true
  loadJson('library.json',base).then(readLibraryIndex).then(value=>{if(!valid)return;library.current=new TrackLibrary(value.tracks,base);setIndex(value)}).catch(e=>{if(valid)setError((e as Error).message)})
  return()=>{valid=false;alive.current=false;startRevision.current++;next.current?.clear();next.current=null;transport.current?.dispose();transport.current=null;initializing.current=null}
 },[])
 const t=transport.current,current=t?.current||null,position=t?.position||0
 const entries=index?.tracks||[],visible=useMemo(()=>filterLibrary(entries,{collection,label,query}),[index,collection,label,query])
 const collections=useMemo(()=>[...new Set(entries.map(e=>e.collection))],[index]),labels=useMemo(()=>[...new Set(entries.filter(e=>!collection||e.collection===collection).flatMap(e=>e.styleLabels))].sort(),[index,collection])
 const selected=entries.find(e=>e.id===selection.id),pending=entries.find(e=>e.id===t?.pending?.plan.to)
 const styles=useMemo(()=>styleChoices(entries),[index])
 async function refreshLibrary(){
  const response=await fetch(new URL('library.json',base),{cache:'no-store'})
  if(!response.ok)throw Error('新曲库暂时没有读取成功，请稍后重试。')
  const value=readLibraryIndex(await response.json()),lib=new TrackLibrary(value.tracks,base)
  const pins=()=>{
   const player=transport.current
   if(player?.busy&&!player.current)throw Error('播放位置正在加载，曲库会稍后自动更新。')
   return [startingId.current,player?.current?.id,player?.pending?.plan.to,next.current?.state.id].filter(Boolean) as string[]
  }
  await refreshLibraryTracks(lib,pins)
  if(!alive.current)return
  library.current=lib;setIndex(value);install()
 }
 function install(){
  const lib=library.current,player=transport.current;if(!lib||!player)return
  lib.trim(new Set([player.current?.id,player.pending?.plan.to,next.current?.state.id].filter(Boolean) as string[]))
  player.tracks=lib.values()
 }
 async function ensure(){
  if(transport.current)return transport.current
  if(initializing.current)return initializing.current
  const player=new LiveTransport([],()=>{if(alive.current)refresh(x=>x+1)},base,{planner:planVocalOverlap,autoNext:false,prewarm:false,policyVersion:'vocal-overlap-v1',noPlanMessage:'这个时间附近没有合适的交接点，当前歌曲会继续播放。可以稍后重试或选另一首。'})
  const task=initializeFromGesture(player).then(()=>{
   if(!alive.current){player.dispose();throw Error('页面已关闭')}
   transport.current=player;player.setVolume(volumeRef.current)
   next.current=new NextSelection(id=>library.current!.load(id),{install:()=>install(),prepare:id=>player.prepareNext(id)},state=>{if(alive.current)setSelection({...state})})
   return player
  }).catch(e=>{player.dispose();throw e}).finally(()=>{if(initializing.current===task)initializing.current=null})
  initializing.current=task;return task
 }
 async function startSong(entry:LibraryEntry){
  const revision=++startRevision.current;startingId.current=entry.id;setStarting(true);setNotice('');setError('');next.current?.clear();transport.current?.cancelPreparation()
  try{const player=await ensure();await library.current!.load(entry.id);if(revision!==startRevision.current||!alive.current)return;install();await player.start(entry.id)}catch(e){if(revision===startRevision.current&&alive.current)setError((e as Error).message)}finally{if(revision===startRevision.current&&alive.current){startingId.current=null;setStarting(false)}}
 }
 function choose(id:string,automaticChoice=false,keepStyle=false){
  setNotice('');const player=transport.current;if(!player)return
  // A seek replaces the active source asynchronously. Cancelling here would
  // abort that seek and leave no song for prepareNext to attach to.
  if(!player.current){if(player.busy)setNotice('正在加载播放位置，请稍候再选下一首。');return}
  if(!automaticChoice&&!keepStyle){setIntentStyle('');styleIntent.current='';setChooseMode('song')}
  selectionRevision.current++
  if(!automaticChoice){autoExcluded.current.clear();autoAt.current=player.position+Math.min(12,Math.max(0,(player.current?.duration||0)-player.position-22))}
  if((player.pending||player.busy)&&!player.gate.locked)player.cancel()
  player.cancelPreparation();void next.current?.select(id,{defer:!!player.pending&&player.gate.locked})
 }
 function suggest(id:string){
  const entry=entries.find(e=>e.id===id);if(!entry)return
  const candidates=styleIntent.current?entries.filter(e=>e.styleLabels.includes(styleIntent.current)):filterLibrary(entries,{collection:filters.current.collection,label:filters.current.label})
  const pick=suggestNext(candidates,entry,recent.current.slice(-8))
  if(pick)choose(pick.id,false,true);else next.current?.clear()
 }
 function chooseStyle(){
  const player=transport.current,key=styleDraft||styles[0]?.key
  const from=entries.find(e=>e.id===(player?.gate.locked?player?.pending?.plan.to:player?.current?.id))
  if(!from||!key)return
  const pick=pickStyle(entries,from,key,recent.current.slice(-8))
  if(!pick){setNotice(`“${key}”暂时没有节奏能衔接的歌曲。当前音乐会继续播放，可以换一个风格。`);return}
  styleIntent.current=key;setIntentStyle(key);choose(pick.id,false,true)
 }
 useEffect(()=>{
  const id=current?.id||null
  if(!id&&transport.current?.busy)return
  if(id===lastCurrent.current)return
  lastCurrent.current=id;autoAt.current=0;autoExcluded.current.clear()
  if(id){recent.current.push(id);setNotice('');if(!next.current?.state.id||next.current.state.id===id)suggest(id);else choose(next.current.state.id,false,true);install()}
  else {next.current?.clear();transport.current?.cancelPreparation()}
 },[current?.id])
 useEffect(()=>{
  if(!automatic||!t||!current||autoWorking.current)return
  const action=automaticAction({position,duration:current.duration,playing:t.playing,busy:t.busy,pending:!!t.pending,status:selection.status,hasSelection:!!selection.id},autoAt.current)
  if(!action)return
  autoAt.current=position+(action==='prepare'?12:3)
  if(action==='prepare'&&selection.id){choose(selection.id,true);return}
  const alternative=()=>{
   if(selection.id)autoExcluded.current.add(selection.id)
   const entry=entries.find(e=>e.id===current.id)
   if(!entry)return
   const candidates=(styleIntent.current?entries.filter(e=>e.styleLabels.includes(styleIntent.current)):filterLibrary(entries,{collection:filters.current.collection,label:filters.current.label})).filter(e=>!autoExcluded.current.has(e.id))
   const pick=suggestNext(candidates,entry,recent.current.slice(-8))
   if(pick){choose(pick.id,true);setNotice('已选歌曲暂时没有可用交接点，正在自动准备另一首。')}
   else{autoAt.current=current.duration;setNotice('这次曲尾没有找到可接的歌曲。你可以手动选择下一首，或扩大曲库筛选范围。')}
  }
  if(action==='alternative'){alternative();return}
  autoWorking.current=true;const sourceId=current.id,revision=selectionRevision.current
  void mix('continuous_end_auto').then(()=>{if(alive.current&&revision===selectionRevision.current&&transport.current?.current?.id===sourceId&&!transport.current.pending)alternative()}).finally(()=>{autoWorking.current=false})
 },[automatic,current?.id,position,selection.status,selection.id])
 async function mix(origin='continuous_user'){
  const player=transport.current,id=next.current?.state.id;if(!player||!id)return
  setNotice('');setError('')
  try{await player.request({kind:'next',targetId:id},18,{origin});if(!player.pending&&alive.current)setNotice(player.status)}catch(e){if(alive.current)setError((e as Error).message)}
 }
 function stop(){startRevision.current++;startingId.current=null;setStarting(false);next.current?.clear();transport.current?.stop();lastCurrent.current=null;setSeekDraft(null);setNotice('')}
 async function seek(){
  if(seekDraft===null||!transport.current)return
  const offset=seekDraft,id=next.current?.state.id;setSeekDraft(null);setNotice('');autoAt.current=0;autoExcluded.current.clear()
  try{await transport.current.seek(offset);if(id)choose(id,false,true)}catch(e){setError((e as Error).message)}
 }
 function exportSession(){const player=transport.current;if(!player)return;const url=URL.createObjectURL(new Blob([JSON.stringify(player.export(),null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`harbeat-continuous-${Date.now()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 const readyCount=entries.filter(e=>e.playStatus==='ready').length
 return <main className="continuous-page">
  <header className="masthead"><a className="brand" href="./index.html" aria-label="HarBeat 首页">HarBeat<span>●</span></a><span className="edition">LIVE / 连续播放</span><span className="library-count">{index?`${entries.length} 首 · ${collections.length} 组曲库`:'正在载入曲库'}</span></header>
  <section className="intro"><p className="eyebrow">让音乐接着走</p><h1>边听，边选下一首。</h1><p>选一首歌，或换一种风格。HarBeat 会在合适的位置渐进交接。</p></section>
  {(error||notice)&&<div className={error?'message error':'message'} role={error?'alert':'status'}>{error||notice}<button onClick={()=>{setError('');setNotice('')}} aria-label="关闭提示">×</button></div>}
  <section className="player-grid" aria-label="实时播放器">
   <div className="now card"><div className="card-top"><span className="eyebrow">正在播放</span><span className={`live-dot ${t?.playing?'is-playing':''}`}>{t?.paused?'已暂停':t?.playing?'LIVE':'READY'}</span></div>
    <div className="disc" aria-hidden="true"><div>H<span>•</span>B</div></div>
    <h2>{current?.title||'从曲库开始'}</h2><p className="song-meta">{current?`${entries.find(e=>e.id===current.id)?.collection||''} · ${current.bpm.toFixed(1).replace('.0','')} BPM`:'三组音乐，一段接着一段'}</p>
    <div className="progress"><input aria-label="播放进度" type="range" min={0} max={current?.duration||1} step={.1} value={seekDraft??position} disabled={!current||!!t?.busy} onChange={e=>setSeekDraft(Number(e.target.value))} onPointerUp={()=>void seek()} onKeyUp={e=>{if(['ArrowLeft','ArrowRight','Home','End','PageUp','PageDown'].includes(e.key))void seek()}} onBlur={()=>void seek()}/><div><span>{clock(seekDraft??position)}</span><span>{clock(current?.duration||0)}</span></div></div>
    <div className="play-actions"><button className="primary" disabled={!current} onClick={()=>{setError('');void t?.togglePause().catch(e=>setError(e.message))}}>{t?.paused?'▶ 继续播放':'Ⅱ 暂停'}</button><button disabled={!current&&!starting&&!t?.busy} onClick={stop}>停止</button><label className="volume">音量<input aria-label="音量" type="range" min={0} max={1} step={.01} value={volume} onChange={e=>{const v=Number(e.target.value);setVolume(v);t?.setVolume(v)}}/></label></div>
    <p className="transport-status" role="status">{starting?(t?.status||'正在读取歌曲资料…'):t?.status||'点选任意歌曲，开始播放完整原曲。'}</p>
   </div>
   <div className="next card"><div className="card-top"><span className="eyebrow">接下来</span><label className="auto-toggle"><input type="checkbox" checked={automatic} onChange={e=>setAutomatic(e.target.checked)}/>自动续播</label></div>
    <div className="next-mode" role="group" aria-label="下一首选择方式"><button aria-pressed={chooseMode==='song'} onClick={()=>setChooseMode('song')}>选下一首</button><button aria-pressed={chooseMode==='style'} onClick={()=>setChooseMode('style')}>选下个风格</button></div>
    {chooseMode==='style'&&<div className="style-picker"><label>下一首风格<select aria-label="下一首风格" value={styleDraft||styles[0]?.key||''} onChange={e=>setStyleDraft(e.target.value)}>{styles.map(s=><option key={s.key} value={s.key}>{s.key} · {s.count} 首</option>)}</select></label><button disabled={!current||!styles.length||!!t?.busy&&!t?.pending} onClick={chooseStyle}>按此风格选歌</button></div>}
    {intentStyle&&<p className="style-intent">后续优先播放 {intentStyle}<button onClick={()=>{setIntentStyle('');styleIntent.current=''}}>取消偏好</button></p>}
    {pending&&<div className="handoff" role="status"><span>{t!.ctx.currentTime<t!.pending!.start?'已安排交接':'正在渐进交接'}</span><strong>{pending.title}</strong><small>{Math.max(0,t!.pending!.end-t!.ctx.currentTime).toFixed(1)} 秒后完成</small></div>}
    <div className="next-choice"><span className="next-number" aria-hidden="true">↗</span><h2>{selected?.title||'下一首，由你来选'}</h2><p className="song-meta">{selected?`${selected.collection} · ${selected.bpm?.toFixed(1).replace('.0','')||'—'} BPM`:'播放中选歌，当前音乐会继续。'}</p></div>
    <p className={`prep-status ${selection.status==='failed'?'failed':''}`} role="status">{selection.status==='loading'?(t?.paused?'正在后台准备，播放保持暂停。':'正在后台准备，当前音乐继续…'):selection.status==='queued'?'当前交接完成后，会准备这首歌。':selection.status==='ready'?'素材已准备，点击后选择可用交接点。':selection.status==='failed'?selection.error:'开始播放后，会为你准备一首可接的歌曲。'}</p>
    <div className="next-actions"><button className="primary" disabled={!current||!t?.playing||selection.status!=='ready'||selection.id===current.id||!!t.pending} onClick={()=>void mix()}>现在接歌 <span>↗</span></button>{selection.status==='failed'&&<button onClick={()=>selection.id&&choose(selection.id)}>重新准备</button>}{(t?.pending||t?.busy)&&current&&<button disabled={!!t.gate.locked} onClick={()=>{t.cancel();setNotice('')}}>{t.gate.locked?'交接中':'取消交接'}</button>}</div>
    <p className="next-hint">{chooseMode==='style'?'选好风格后会自动准备下一首；也可在曲库点选具体歌曲。':'在曲库点选下一首，当前音乐会继续。'} 开启自动续播后，临近曲尾会尝试衔接；也可点“现在接歌”提前交接。</p>
   </div>
  </section>
  <section className="library" aria-labelledby="library-title"><div className="section-heading"><div><p className="eyebrow">YOUR COLLECTION</p><h2 id="library-title">所有音乐 <span>{entries.length}</span></h2></div><div className="library-tools"><button className="add-music" onClick={()=>setImportOpen(true)}>＋ 添加音乐</button><label className="search"><span aria-hidden="true">⌕</span><input type="search" aria-label="搜索歌曲或风格" placeholder="搜索歌曲或风格" value={query} onChange={e=>{setQuery(e.target.value);setLimit(40)}}/></label></div></div>
   <div className="filters"><div className="collection-tabs" role="group" aria-label="曲库分组"><button className={!collection?'selected':''} onClick={()=>{setCollection('');setLabel('');setLimit(40)}}>全部 <span>{entries.length}</span></button>{collections.map(c=><button key={c} className={collection===c?'selected':''} onClick={()=>{setCollection(c);setLabel('');setLimit(40)}}>{c} <span>{entries.filter(e=>e.collection===c).length}</span></button>)}</div><select aria-label="筛选风格" value={label} onChange={e=>{setLabel(e.target.value);setLimit(40)}}><option value="">全部风格</option>{labels.map(l=><option key={l} value={l}>{l}</option>)}</select></div>
   {!index&&!error&&<p className="empty">正在载入歌曲清单…</p>}
   {index&&visible.length===0&&<p className="empty">没有找到符合条件的歌曲，试试其他名称或分组。</p>}
   <div className="song-list">{visible.slice(0,limit).map((entry,i)=>{const isCurrent=current?.id===entry.id,isNext=selection.id===entry.id,unavailable=entry.playStatus!=='ready'||!!current&&entry.mixStatus!=='ready';return <article className={`song-row ${isCurrent?'current':''} ${isNext?'queued':''}`} key={entry.id}><span className="song-number">{isCurrent?'♫':String(i+1).padStart(2,'0')}</span><div className="song-name"><h3>{entry.title}</h3><p>{entry.collection}{entry.styleLabels.length?' / '+entry.styleLabels.join(' · '):''}{unavailable?' · '+(entry.reason||'暂未准备好'):''}</p></div><span className="tempo">{entry.bpm!==null&&Number.isFinite(entry.bpm)?entry.bpm.toFixed(0):'—'}<small>BPM</small></span><span className="duration">{entry.duration===null?'—':clock(entry.duration)}</span><button aria-label={`${!current?'播放':isCurrent?'正在播放':isNext?'已选':'接下来播'} ${entry.title}`} disabled={unavailable||isCurrent||starting||!!t?.busy&&!current} className={isNext?'selected':''} onClick={()=>current?choose(entry.id):void startSong(entry)}>{isCurrent?'播放中':isNext?'已选 ✓':current?'接下来播':'播放 ↗'}</button></article>})}</div>
   {visible.length>limit&&<button className="more" onClick={()=>setLimit(n=>n+40)}>再显示 {Math.min(40,visible.length-limit)} 首</button>}
   {index&&<p className="library-note">{readyCount} 首可播放 · 分组与风格沿用原有曲库标签。选歌不打断当前播放。</p>}
  </section>
  <footer><span className="brand small">HarBeat<span>●</span></span><p>让每一次交接，都留在节奏里。</p><details><summary>本次播放记录</summary><p>记录仅保存在当前浏览器，可导出交接与播放数据。</p><button disabled={!t} onClick={exportSession}>导出记录</button><p>{t?.persistenceStatus||'播放后开始记录'}</p></details></footer>
  <MusicImport open={importOpen} onClose={()=>setImportOpen(false)} onPublished={refreshLibrary}/>
 </main>
}
