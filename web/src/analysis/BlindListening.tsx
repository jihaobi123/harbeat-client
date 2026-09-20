import { useEffect, useRef, useState } from 'react'
import { download } from './data'

export default function BlindListening() {
  const files = useRef<File[]>([])
  const [order, setOrder] = useState<number[]>([])
  const [urls, setUrls] = useState<string[]>([])
  const [revealed, setRevealed] = useState(false)
  const [votes, setVotes] = useState<any[]>([])
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  useEffect(() => () => urls.forEach(URL.revokeObjectURL), [urls])
  useEffect(() => { try {setVotes(JSON.parse(localStorage.getItem('harbeat_lab_votes') || '[]'))} catch {} }, [])
  function choose(list: FileList | null) {
    if (!list || list.length !== 2) return
    files.current = Array.from(list)
    const bit = crypto.getRandomValues(new Uint8Array(1))[0] % 2
    const next = bit ? [1,0] : [0,1]
    setOrder(next); setUrls(next.map(i => URL.createObjectURL(files.current[i]))); setRevealed(false)
  }
  async function vote(preference: string) {
    if(recording || revealed)return
    setRecording(true);setError('')
    try {
    const hashes = await Promise.all(files.current.map(async f => {
      const buffer = await crypto.subtle.digest('SHA-256', await f.arrayBuffer())
      return Array.from(new Uint8Array(buffer)).map(v=>v.toString(16).padStart(2,'0')).join('')
    }))
    const record = { timestamp: new Date().toISOString(), preference, note,
      blind: !revealed, mapping: order.map(i=>({file:files.current[i].name,sha256:hashes[i]})),
      protocol: 'local randomized pair; supplied excerpts; no automatic loudness matching' }
    const next = [...votes, record]; setVotes(next); localStorage.setItem('harbeat_lab_votes', JSON.stringify(next)); setRevealed(true)
    } catch(e){setError((e as Error).message)} finally{setRecording(false)}
  }
  return <div className="lab-panel"><h2>转场盲听对照</h2><p className="lab-muted">选择同一转场的两个版本。先准备相同长度、响度匹配的片段；页面随机隐藏文件名。投票保存在本机浏览器。</p>
    <label className="lab-button">选择两个音频<input type="file" accept="audio/*" multiple onChange={e=>choose(e.target.files)}/></label>
    <div className="lab-ab">{urls.map((url,i)=><div key={url}><h3>版本 {i?'B':'A'}</h3><audio controls src={url}/>{revealed && <small>{files.current[order[i]].name}</small>}</div>)}</div>
    {urls.length===2 && <><textarea placeholder="记录错拍、人声冲突、响度跳变或整体偏好" value={note} onChange={e=>setNote(e.target.value)}/><div className="lab-actions">{['A','B','无明显差别'].map(v=><button key={v} disabled={revealed||recording} onClick={()=>vote(v)}>{v === '无明显差别' ? v : `偏好 ${v}`}</button>)}</div></>}
    {error&&<p role="alert">{error}</p>}
    <p>{votes.length} 条试听记录 · <button onClick={()=>download('listening-votes.json',JSON.stringify(votes,null,2))}>导出记录</button></p>
  </div>
}
