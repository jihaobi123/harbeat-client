import {useEffect,useRef,useState} from 'react'

type Job={id:string;title:string;status:string;message:string;track_id?:string;updated:number}
type Candidate={candidate_id:string;title:string;artist:string;source:string;duration:number}
type Song={title:string;artist:string;duration?:number;selected:boolean;candidates?:Candidate[];pick?:string;searched?:boolean}
const states:Record<string,string>={queued:'等待处理',downloading:'下载中',transferring:'发送到 Jetson',analyzing:'Jetson 分析中',publishing:'准备衔接素材',ready:'可播放 / 可混音',ready_playback:'可单独播放',failed:'未完成'}

export default function MusicImport({open,onClose,onPublished}:{open:boolean;onClose:()=>void;onPublished:()=>Promise<void>}){
 const dialog=useRef<HTMLDialogElement>(null),[mode,setMode]=useState<'upload'|'playlist'>('upload')
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),auth=useRef(''),[connected,setConnected]=useState(false)
 const [jobs,setJobs]=useState<Job[]>([]),[styles,setStyles]=useState<string[]>([]),[style,setStyle]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState('')
 const [url,setUrl]=useState(''),[playlistName,setPlaylistName]=useState(''),[songs,setSongs]=useState<Song[]>([]),[files,setFiles]=useState<File[]>([])
 const seen=useRef(new Set<string>()),published=useRef(onPublished);published.current=onPublished
 const polling=useRef<Promise<void>|null>(null)
 useEffect(()=>{if(open&&!dialog.current?.open)dialog.current?.showModal();else if(!open&&dialog.current?.open)dialog.current.close()},[open])
 async function api(path:string,body?:unknown){
  const form=body instanceof FormData
  const response=await fetch('/api/listen-import/'+path,{method:body===undefined?'GET':'POST',credentials:'omit',cache:'no-store',headers:{Authorization:auth.current,'X-HarBeat-Import':'1',...(!form&&body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:form?body:JSON.stringify(body)})
  if(response.status===401){setConnected(false);throw Error('管理员账号或密码不正确。')}
  if(!response.ok){const value=await response.json().catch(()=>null);throw Error(typeof value?.detail==='string'?value.detail:`服务暂时不可用（${response.status}），请稍后重试。`)}
  return response.json()
 }
 async function poll(){
  if(polling.current)return polling.current
  const task=(async()=>{
   const data=await api('jobs');setJobs(data.jobs);setStyles(data.styles)
   const ready:Job[]=data.jobs.filter((j:Job)=>['ready','ready_playback'].includes(j.status)&&!seen.current.has(j.id+':'+j.updated))
   if(ready.length){await published.current();ready.forEach(j=>seen.current.add(j.id+':'+j.updated))}
  })().finally(()=>{polling.current=null})
  polling.current=task;return task
 }
 useEffect(()=>{
  if(!connected)return
  let live=true,timer:ReturnType<typeof setTimeout>
  const run=async()=>{try{await poll()}catch(e){if(live)setError((e as Error).message)}finally{if(live)timer=setTimeout(run,5000)}}
  void run();return()=>{live=false;clearTimeout(timer)}
 },[connected])
 async function act(label:string,run:()=>Promise<void>){setBusy(label);setError('');try{await run()}catch(e){setError((e as Error).message)}finally{setBusy('')}}
 async function login(){
  const bytes=new TextEncoder().encode(username+':'+password);auth.current='Basic '+btoa(Array.from(bytes,c=>String.fromCharCode(c)).join(''))
  await poll();setConnected(true);setPassword('')
 }
 async function parse(){const data=await api('playlist',{url});setPlaylistName(data.name);setSongs(data.tracks.map((s:Song,i:number)=>({...s,selected:i<16})))}
 async function match(){
  const selected=songs.map((s,i)=>({s,i})).filter(({s})=>s.selected)
  if(selected.length>16)throw Error('每批最多导入 16 首，请减少勾选数量。')
  for(let n=0;n<selected.length;n++){
   const {s,i}=selected[n];setBusy(`正在匹配 ${n+1}/${selected.length}：${s.title}`)
   const data=await api('search',{title:s.title,artist:s.artist})
   setSongs(old=>old.map((row,at)=>at===i?{...row,candidates:data.candidates,pick:data.candidates[0]?.candidate_id||'',searched:true}:row))
  }
 }
 async function submit(){const ids=songs.filter(s=>s.selected&&s.pick).map(s=>s.pick);if(!ids.length)throw Error('请先匹配音源，并选择需要导入的音乐。');await api('download',{candidate_ids:ids,style});await poll();setSongs(old=>old.map(s=>({...s,selected:false})))}
 async function upload(){
  if(files.length>16)throw Error('每批最多上传 16 首。')
  for(let i=0;i<files.length;i++){
   const file=files[i];if(file.size>100*1024*1024)throw Error(file.name+' 超过 100 MB。')
   setBusy(`正在上传 ${i+1}/${files.length}：${file.name}`)
   const body=new FormData();body.append('audio',file);body.append('style',style);await api('upload',body);await poll()
  }
  setFiles([])
 }
 return <dialog className="import-dialog" ref={dialog} onCancel={e=>{e.preventDefault();onClose()}} onClose={onClose} aria-labelledby="import-title">
  <div className="import-heading"><div><p className="eyebrow">YOUR MUSIC</p><h2 id="import-title">添加音乐</h2></div><button onClick={onClose} aria-label="关闭添加音乐">×</button></div>
  <p className="import-lead">上传文件，或从歌单挑选音乐。Jetson 会分析人声、节拍和段落，准备好后自动加入曲库。</p>
  {error&&<p className="message error" role="alert">{error}</p>}
  {!connected?<form className="import-login" onSubmit={e=>{e.preventDefault();void act('正在连接…',login)}}>
   <p>使用现有曲库管理员账号添加音乐。听歌无需登录。</p>
   <label>管理员账号<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label>
   <label>密码<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
   <button className="primary" disabled={!!busy}>进入曲库管理</button>
  </form>:<>
   <div className="import-tabs" role="group" aria-label="添加方式"><button aria-pressed={mode==='upload'} onClick={()=>setMode('upload')}>上传音乐</button><button aria-pressed={mode==='playlist'} onClick={()=>setMode('playlist')}>歌单链接</button></div>
   <label className="import-style">加入风格<select value={style} onChange={e=>setStyle(e.target.value)}><option value="">暂不指定</option>{styles.map(s=><option key={s}>{s}</option>)}</select></label>
   {mode==='upload'?<div className="upload-area"><label>选择音乐文件<input aria-label="选择音乐文件" type="file" multiple accept=".mp3,.wav,.flac,.m4a,.aac,.ogg,.opus,.aif,.aiff" disabled={!!busy} onChange={e=>setFiles(Array.from(e.target.files||[]))}/></label><p>每首最多 100 MB，20 秒至 20 分钟；每批最多 16 首。</p>{files.length>0&&<p>{files.length} 首已选择：{files.map(f=>f.name).join('、')}</p>}<button className="primary" disabled={!!busy||!files.length} onClick={()=>void act('正在上传…',upload)}>上传并分析</button></div>:
   <div className="playlist-import"><form onSubmit={e=>{e.preventDefault();void act('正在读取歌单…',parse)}}><label>网易云 / QQ 音乐歌单<textarea aria-label="歌单链接" placeholder="粘贴歌单分享链接或分享文字" value={url} onChange={e=>setUrl(e.target.value)} required maxLength={4000}/></label><button disabled={!!busy||!url.trim()}>读取歌单</button></form>
    {songs.length>0&&<><div className="playlist-summary"><strong>{playlistName} · {songs.length} 首</strong><button disabled={!!busy} onClick={()=>setSongs(old=>old.map(s=>({...s,selected:false})))}>清空勾选</button></div><p className="import-help">每批勾选最多 16 首。匹配后可核对歌名、歌手和音源，再开始下载。</p><div className="import-song-list">{songs.map((song,i)=><div className="import-song" key={i}><label><input type="checkbox" checked={song.selected} disabled={!!busy} onChange={e=>setSongs(old=>old.map((s,n)=>n===i?{...s,selected:e.target.checked}:s))}/><span>{song.title}<small>{song.artist}</small></span></label>{song.candidates?.length?<select aria-label={`${song.title} 的音源`} value={song.pick} disabled={!!busy} onChange={e=>setSongs(old=>old.map((s,n)=>n===i?{...s,pick:e.target.value}:s))}>{song.candidates.map(c=><option key={c.candidate_id} value={c.candidate_id}>{c.title} · {c.artist} · {c.source==='fangpi'?'放屁音乐':'酷我'}{c.duration?` · ${Math.round(c.duration)} 秒`:''}</option>)}</select>:song.searched?<small>暂未找到音源，可用本地文件上传。</small>:null}</div>)}</div><div className="import-actions"><button disabled={!!busy||!songs.some(s=>s.selected)} onClick={()=>void act('正在匹配音源…',match)}>匹配所选音源</button><button className="primary" disabled={!!busy||!songs.some(s=>s.selected&&s.pick)} onClick={()=>void act('正在加入队列…',submit)}>确认下载并分析</button></div></>}
   </div>}
   <section className="import-jobs" aria-label="导入进度"><h3>导入进度</h3><p className="import-help">关闭窗口后任务仍会继续。完成后，音乐会出现在“我的导入”中；重复文件会复用已有音乐。</p>{jobs.length===0?<p className="import-help">还没有导入任务。</p>:jobs.map(job=><article key={job.id}><div><strong>{job.title}</strong><span className={job.status==='failed'?'failed':''}>{states[job.status]||job.status}</span></div><p>{job.message||'已加入处理队列'}</p>{job.status==='failed'&&<button disabled={!!busy} onClick={()=>void act('正在重试…',async()=>{await api('jobs/'+job.id+'/retry',{});await poll()})}>重试</button>}</article>)}</section>
  </>}
  {busy&&<p className="import-busy" role="status" aria-live="polite">{busy}</p>}
 </dialog>
}
