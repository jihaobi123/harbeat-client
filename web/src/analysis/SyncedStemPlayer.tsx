import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Report, timeLabel } from './data'
import { audioNames } from './dimensions'
import { LoadProgress, StemTrack, StemTransport } from './StemTransport'

export type StemPlayerHandle={seek:(time:number)=>void;select:(name:string)=>void}
const coreNames=['master','vocals','drums','bass','other']
export default forwardRef<StemPlayerHandle,{report:Report;localAudio:string;onTime:(time:number)=>void;onSelection:(name:string)=>void}>(function SyncedStemPlayer({report,localAudio,onTime,onSelection},ref){
  const native=useRef<HTMLAudioElement>(null),engine=useRef<StemTransport|null>(null)
  const alive=useRef(true),request=useRef(0),pendingSeek=useRef(0)
  const loads=useRef(0)
  const callbacks=useRef({onTime,onSelection});callbacks.current={onTime,onSelection}
  const [synced,setSynced]=useState(false),syncedRef=useRef(false)
  const [playing,setPlaying]=useState(false),[position,setPosition]=useState(0)
  const [ready,setReady]=useState<string[]>([]),[loading,setLoading]=useState(false)
  const [progress,setProgress]=useState<LoadProgress|null>(null),[error,setError]=useState('')
  const [selection,setSelection]=useState('master')
  const assets=report.audio.assets||{}
  const masterUrl=localAudio||(assets.master?.id?`/api/analysis-lab/media/${assets.master.id}`:report.audio.sha256?`/api/analysis-lab/audio/${report.audio.sha256}`:'')
  const tracks:StemTrack[]=localAudio?[]:[...new Set([...coreNames,...Object.keys(assets).filter(k=>k.startsWith('drum_'))])].flatMap(name=>{
    const a=assets[name],url=name==='master'?masterUrl:a?.id?`/api/analysis-lab/media/${a.id}`:''
    return url?[{name,url,duration:a?.duration||report.audio.duration||report.summary.duration,channels:a?.channels||2}]:[]
  })
  const core=tracks.filter(t=>coreNames.includes(t.name)),extra=tracks.filter(t=>!coreNames.includes(t.name))
  const hasStems=core.some(t=>t.name!=='master'),completeCore=['vocals','drums','bass','other'].every(k=>tracks.some(t=>t.name===k))
  const duration=engine.current?.duration||report.audio.duration||report.summary.duration||0
  function publish(time:number){setPosition(time);callbacks.current.onTime(time)}
  function getEngine(){
    if(!engine.current){engine.current=new StemTransport(new AudioContext());void engine.current.activate().catch(()=>{})}
    return engine.current
  }
  const updateProgress=(value:LoadProgress)=>{if(alive.current){setProgress(value);if(value.phase==='ready')setReady(engine.current?.readyNames||[])}}
  async function choose(name:string,prepareExtras=false){
    const seq=++request.current;setError('')
    let loadingThis=false
    try{
      const e=getEngine()
      const wanted=prepareExtras?extra:syncedRef.current?tracks.filter(t=>name==='mix'?coreNames.includes(t.name):t.name===name):[...core,...tracks.filter(t=>t.name===name&&!coreNames.includes(t.name))]
      if(wanted.some(t=>!e.readyNames.includes(t.name))){loadingThis=true;++loads.current;setLoading(true);await e.prepare(wanted,updateProgress)}
      if(!alive.current||seq!==request.current)return
      if(prepareExtras)return
      e.select(name)
      if(!syncedRef.current){
        const wasPlaying=native.current?!native.current.paused:false
        const time=native.current?.currentTime||pendingSeek.current
        native.current?.pause();await e.seek(time)
        syncedRef.current=true;setSynced(true)
        if(wasPlaying)await e.play()
      }
      if(!alive.current)return
      setSelection(name);callbacks.current.onSelection(name);setPlaying(e.playing);publish(e.position)
    }catch(err){if(alive.current&&(seq===request.current||loadingThis))setError((err as Error).message)}
    finally{if(loadingThis)--loads.current;if(alive.current){setLoading(loads.current>0);if(!loads.current)setProgress(null);setReady(engine.current?.readyNames||[])}}
  }
  function seek(time:number){
    pendingSeek.current=time
    if(syncedRef.current)void engine.current?.seek(time).catch(err=>setError(err.message))
    else if(native.current&&native.current.readyState>0)native.current.currentTime=Math.min(time,native.current.duration||time)
    publish(time)
  }
  useImperativeHandle(ref,()=>({seek,select:name=>{if(localAudio){setError('正在试听本地原曲，请先返回报告原曲再选择分轨');return}void choose(name)}}))
  useEffect(()=>{
    alive.current=true
    const timer=setInterval(()=>{
      const e=engine.current;if(!syncedRef.current||!e)return
      if(e.playing&&e.position>=e.duration)e.pause()
      setPlaying(e.playing);publish(e.position)
    },100)
    return ()=>{alive.current=false;++request.current;clearInterval(timer);engine.current?.dispose();engine.current=null}
  },[])
  async function toggle(){
    const e=engine.current;if(!e)return
    try{if(e.playing)e.pause();else await e.play();if(alive.current)setPlaying(e.playing)}catch(err){if(alive.current)setError((err as Error).message)}
  }
  return <div className="lab-sync-player">
    <div className="lab-sync-title"><b>{synced?(selection==='mix'?'四轨合听':`${audioNames[selection]||selection} · 独听`):'原曲试听'}</b><span>{timeLabel(position)} / {timeLabel(duration)}</span></div>
    {!synced&&(masterUrl?<audio ref={native} controls preload="metadata" src={masterUrl} onLoadedMetadata={e=>{if(pendingSeek.current)e.currentTarget.currentTime=Math.min(pendingSeek.current,e.currentTarget.duration)}} onTimeUpdate={e=>publish(e.currentTarget.currentTime)} onError={()=>setError('原曲读取失败，请重试或选择本地原曲')}/>:<p>此报告未关联原曲文件。</p>)}
    {synced&&<div className="lab-sync-controls"><button className="primary" aria-label={playing?'暂停同步播放':'开始同步播放'} onClick={toggle}>{playing?'暂停':'播放'}</button><input aria-label="同步播放位置" type="range" min="0" max={duration} step="0.01" value={position} onChange={e=>seek(Number(e.target.value))}/></div>}
    {hasStems&&<><div className="lab-sync-actions"><button disabled={loading} onClick={()=>choose(tracks.some(t=>t.name==='master')?'master':completeCore?'mix':core[0].name)}>{synced?'同步音轨已准备':'准备同步分轨'}</button>{extra.length>0&&<button disabled={loading||extra.every(t=>ready.includes(t.name))} onClick={()=>choose(selection,true)}>提前准备细分鼓组</button>}<span>已准备 {ready.length} / {tracks.length} 轨</span></div>
      <p className="lab-muted">首次准备需要传输音频。已就绪音轨共用播放进度，切换只改变音量；细分鼓组可提前准备。</p>
      {synced&&<div className="lab-sync-tracks">{[...tracks.map(t=>t.name),...(completeCore?['mix']:[])].map(name=><button key={name} aria-pressed={selection===name} className={selection===name?'selected':''} onClick={()=>choose(name)}>{name==='mix'?'四轨合听':audioNames[name]||name}<small>{name==='mix'||ready.includes(name)?'已就绪':'待准备'}</small></button>)}</div>}
    </>}
    {loading&&<div className="lab-notice" role="status">{progress?`${audioNames[progress.name]||progress.name} · ${progress.phase==='decoding'?'正在解码':progress.phase==='ready'?'已就绪':`正在传输 ${(progress.bytes/1048576).toFixed(1)} MB${progress.total?` / ${(progress.total/1048576).toFixed(1)} MB`:''}`}`:'正在准备音轨…'}<p>当前试听会继续。已准备的音轨可直接切换。</p></div>}
    {error&&<div className="lab-alert" role="alert">{error}。已就绪音轨和原始文件仍保留，可重试。</div>}
  </div>
})
