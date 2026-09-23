import DecisionTracePanel from '../realtime/DecisionTracePanel'
import {useEffect,useState} from 'react'
import type {Report} from './data'
import {download} from './data'
import type {Track} from '../realtime/planner'
import EvidencePanel from '../realtime/EvidencePanel'
import {Curve,Segments} from './Charts'
import {listSessions,readSession,saveSession,validateSession,type SessionSnapshot,type SessionIndex} from '../realtime/sessionStore'
import './mix-trace.css'
const LIVE='/analysis-lab-static/v3-live-20260922/'
const sourceLink=(id:string,tab='evidence')=>`/analysis-lab?report=${encodeURIComponent(id)}&tab=${tab}`
const fmt=(x:unknown)=>typeof x==='number'&&Number.isFinite(x)?x.toFixed(3):'未知'
export function associateTrack(tracks:Track[],report:Report){
 const sha=report.audio?.sha256||report.documents?.core?.assets?.master?.sha256
 if(!sha)return null
 const t=tracks.find(t=>t.provenance?.masterSha256===sha&&t.reportId===report.id)||tracks.find(t=>t.provenance?.masterSha256===sha)
 return t?{track:t,binding:t.reportId===report.id?'exact_report':'same_audio_other_version'}:null
}
export function executionRows(logs:any[],sampleRate?:number){return logs.filter(x=>x.kind==='plan_scheduled').flatMap(s=>(Array.isArray(s.events)?s.events:[]).map((e:any)=>{
 const a=logs.find(x=>x.kind==='audio_observation'&&x.requestId===s.requestId&&x.planId===s.planId&&x.name===e.name)
 const actual=Number.isFinite(a?.observedContextSec)?a.observedContextSec:null,planned=Number.isFinite(e.time)?e.time:Number.isFinite(e.frame)&&Number.isFinite(sampleRate)&&sampleRate!>0?e.frame/sampleRate!:null
 return {requestId:s.requestId,planId:s.planId,name:e.name,planned,actual,deltaMs:actual!==null&&planned!==null?(actual-planned)*1000:null}
}))}
function SourceLinks({track}:{track:any}){return <div className="lab-actions">{track.reportId?<><a className="lab-button" href={sourceLink(track.reportId)} target="_blank" rel="noreferrer">原始分析报告 ↗</a><a className="lab-button" href={sourceLink(track.reportId,'stems')} target="_blank" rel="noreferrer">原曲与分轨来源 ↗</a><a className="lab-button" href={`/api/analysis-lab/reports/${encodeURIComponent(track.reportId)}`} target="_blank" rel="noreferrer">分析 JSON ↗</a></>:<span>旧日志未记录报告 ID；不可按歌曲名猜测来源。</span>}</div>}
export function MaterialEvidence({track}:{track:Track}){
 const [cursor,setCursor]=useState(0),p=track.mixProfile
 return <article className="mix-material"><h3>{track.title}</h3><p>分析报告 {track.reportId||'未记录'} · {track.bpm||'—'} BPM · 当前试听素材 {fmt(track.duration||track.native?.duration)} 秒</p><SourceLinks track={track}/>
 <div className="mix-hashes"><p>原曲 SHA256 <code>{String(track.provenance?.masterSha256||p?.source.masterSha256||'未记录')}</code></p><p>实际播放素材 SHA256 <code>{track.native?.sha256||'未记录'}</code></p><p>原目录分析文件 <code>{String(track.provenance?.reportSha256||'未记录')}</code></p><p>本次补充读取的分析文件 <code>{String(p?.source.reportFileSha256||'未记录')}</code></p></div>
 <p className="lab-muted">原曲与试听素材的哈希可能不同：试听素材经过格式转换或截取。比较分析版本时以原曲身份和报告记录为准。</p>
 {p&&<><Segments title="原始段落候选 · 点击定位证据" segments={track.sections} duration={track.duration} onSeek={setCursor}/><Curve title="绝对功率曲线 · dBFS（展示分辨率0.5秒，规划使用原50ms帧）" points={p.energyCurve.filter(x=>x.dbfs!==null).map(x=>({time:x.start,value:x.dbfs!}))} duration={track.duration} cursor={cursor} onSeek={setCursor}/><p>当前证据位置：{fmt(cursor)} 秒</p></>}
 <EvidencePanel track={track}/><button onClick={()=>download(`mix-material-${track.id}.json`,JSON.stringify(track,null,2))}>导出素材与全部选点依据</button>
 <details><summary>模型版本、原始局部风格分数与来源</summary><pre>{JSON.stringify(p?.source||track.provenance,null,2)}</pre>{typeof p?.source.genreSidecarUrl==='string'&&/^evidence\/[a-zA-Z0-9_.-]+\.json$/.test(p.source.genreSidecarUrl)&&<a className="lab-button" href={LIVE+p.source.genreSidecarUrl} target="_blank" rel="noreferrer">查看局部模型原始400类分数 ↗</a>}</details>
 </article>
}
export function SessionEvidence({session}:{session:SessionSnapshot}){
 const logs=session.logs,tracks=session.catalog,rows=executionRows(logs,session.sampleRate),title=(id:string)=>tracks.find(t=>t.id===id)?.title||id||'未知'
 return <div className="mix-session"><h3>会话 {session.sessionId}</h3><p>保存时间：{session.savedAt||'导入日志未记录'} · {logs.length} 个事件</p><button onClick={()=>download(`${session.sessionId}.json`,JSON.stringify(session,null,2))}>导出本次完整日志</button>
 <h4>本会话实际记录的素材来源</h4>{tracks.map(t=><details key={t.id}><summary>{t.title} · 报告 {t.reportId||'未记录'}</summary><SourceLinks track={t}/><pre>{JSON.stringify({native:t.native,provenance:t.provenance,profileSource:t.mixProfile?.source},null,2)}</pre></details>)}
 <h4>计划与实际执行</h4><p>均为 AudioContext 时间。未观察到不等于已执行；可能尚未开始、被取消或记录缺失。音频线程观察不等于扬声器／蓝牙出声。</p>
 <div className="lab-table-wrap"><table><thead><tr><th>请求／事件</th><th>计划时间（秒）</th><th>音频线程观察（秒）</th><th>偏差（ms）</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td>{r.requestId}<br/>{r.name}</td><td>{fmt(r.planned)}</td><td>{r.actual===null?'未观察到':fmt(r.actual)}</td><td>{r.deltaMs===null?'—':fmt(r.deltaMs)}</td></tr>)}</tbody></table></div>
 <h4>逐次请求与判断依据</h4>{logs.filter(x=>x.kind==='request_received').map((r,i)=>{
 const events=logs.filter(x=>x.requestId===r.requestId),s=events.find(x=>x.kind==='plan_scheduled'),o=events.find(x=>x.kind==='request_outcome'),d=s?.plan?.decision
 return <details key={i}><summary>{r.wallTime||''} · {r.intent?.style||'不限风格'} · {r.intent?.energy||r.intent?.kind||'未知请求'} · {o?.outcome||'未记录最终结果'}</summary>
 <p>{title(r.sourceTrackId)} 原曲 {fmt(r.sourcePosition)} 秒触发；预算 {fmt(r.budgetSec)} 秒。{o?.reason||'还没有最终结果。'}</p>
 {s&&<><p><b>{title(s.plan?.from)} → {title(s.plan?.to)}</b> · {s.selection?.reason||'旧日志没有记录排名原因'}</p><ul>{d?.pointReasons?.map((x:string,j:number)=><li key={j}>{x}</li>)}</ul><p>{d?.strategy?.selectionReason}</p><p>{d?.strategy?.midDuck?.reason}</p><DecisionTracePanel trace={s.trace}/><details><summary>选点、人声、能量、风格、变速和 EQ 完整证据</summary><pre>{JSON.stringify(d||s.plan,null,2)}</pre></details></>}
 {events.filter(x=>x.kind==='decision_search').map((search,j)=><details key={j}><summary>{search.phase} · {search.result?.candidateCount||0} 个合格候选</summary><ul>{search.result?.exclusions?.map((x:any,k:number)=><li key={k}>{x.track} / {x.windowId||'整曲'}：{x.reason}（{x.code}，{x.count}次）</li>)}</ul><pre>{JSON.stringify(search.result,null,2)}</pre></details>)}
 <details><summary>请求事件链与失败位置</summary><pre>{JSON.stringify(events,null,2)}</pre></details></details>
 })}</div>
}
export default function MixTracePanel({report,materialOnly=false}:{report?:Report|null;materialOnly?:boolean}){
 const [catalog,setCatalog]=useState<{tracks:Track[]}|null>(null),[error,setError]=useState(''),[sessionError,setSessionError]=useState(''),[chosen,setChosen]=useState(''),[sessions,setSessions]=useState<SessionIndex[]>([]),[session,setSession]=useState<SessionSnapshot|null>(null),[sessionId,setSessionId]=useState(''),[running,setRunning]=useState(false)
 useEffect(()=>{let alive=true;fetch(LIVE+'catalog.json').then(async r=>{if(!r.ok)throw new Error('混音素材目录读取失败');return r.json()}).then(x=>{if(alive){setCatalog(x);setChosen(x.tracks[0]?.id||'')}}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}},[])
 useEffect(()=>{if(materialOnly)return;let alive=true;const reload=()=>listSessions().then(x=>{if(alive){setSessions(x);setSessionError('');if(sessionId)void readSession(sessionId).then(v=>{if(alive)setSession(v)}).catch(e=>setSessionError(e.message))}}).catch(e=>{if(alive)setSessionError(e.message)})
 const message=(e:MessageEvent)=>{if(e.origin===window.location.origin&&e.data?.kind==='harbeat-session-saved')void reload()};void reload();window.addEventListener('message',message);window.addEventListener('harbeat-session-saved',reload);const timer=setInterval(reload,5000);return()=>{alive=false;clearInterval(timer);window.removeEventListener('message',message);window.removeEventListener('harbeat-session-saved',reload)}},[sessionId,materialOnly])
 async function importing(file?:File){if(!file)return;try{if(file.size>50*1024*1024)throw new Error('会话日志最大50MB');const s=validateSession(JSON.parse(await file.text()));await saveSession(s);setSessionId(s.sessionId);setSession(s);setSessionError('')}catch(e){setSessionError((e as Error).message)}}
 const association=report&&catalog?associateTrack(catalog.tracks,report):null,track=materialOnly?association?.track:catalog?.tracks.find(t=>t.id===chosen)
 return <section className="lab-panel mix-trace"><h2>{materialOnly?'本曲混音素材与来源':'混音调试 · 素材 → 决策 → 执行'}</h2><p>原始分析、局部模型候选与实际播放记录分开显示，所有判断都能追溯到报告版本和时间窗口。</p>
 {error&&<p role="alert">{error}</p>}
 {!catalog&&!error&&<p>正在读取混音素材与窗口档案…</p>}
 {catalog&&<p className="lab-notice">当前精确窗口档案覆盖 {catalog.tracks.length} 首 V3 演示曲，不代表 NAS 全库已经补算。</p>}
 {materialOnly&&catalog&&!track&&<p>本曲尚未纳入这批局部窗口档案；已有分析仍在原来的各个标签页中，不能把其他歌曲的数据移用到这里。</p>}
 {materialOnly&&association?.binding==='same_audio_other_version'&&<p className="lab-notice">当前报告与混音使用的报告版本不同，但原曲 SHA256 相同。下方显示的是混音实际使用的版本，请通过“原始分析报告”核对。</p>}
 {!materialOnly&&catalog&&<label>查看混音素材 <select aria-label="查看混音素材" value={chosen} onChange={e=>setChosen(e.target.value)}>{catalog.tracks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>}
 {track&&<MaterialEvidence key={track.id} track={track}/>}
 {!materialOnly&&<><h2>实时混音与过程记录</h2><p>开始后，播放器的计划、执行观察与失败请求会自动保存在本浏览器。跨设备／同事共享请导出后导入；本次没有开放匿名服务器写入。</p><button onClick={()=>setRunning(!running)}>{running?'关闭播放器（将停止播放）':'在本页打开实时混音播放器'}</button> <a className="lab-button" href={LIVE+'index.html'} target="_blank" rel="noreferrer">独立播放页 ↗</a>
 {running&&<iframe title="V3 实时混音与执行日志" src={LIVE+'index.html'} allow="autoplay" className="mix-player-frame"/>}
 <p><a className="lab-button" href="/analysis-lab-static/v31-candidate-20260923/index.html" target="_blank" rel="noreferrer">V3.1 候选 · 20 首可视化对照与实时试听 ↗</a></p><p><a className="lab-button" href="/analysis-lab-static/v3-decision-evidence-20260923/index.html" target="_blank" rel="noreferrer">保护版 · 查看逐行决策证据 ↗</a> <a className="lab-button" href="/analysis-lab-static/v3-decision-evidence-20260923/index.html?mode=v3" target="_blank" rel="noreferrer">V3 下一首 · 查看逐行决策证据 ↗</a></p><h3>已保存的混音会话</h3><p>同源同浏览器下，独立播放页与这里共享记录。以前只存在内存中且没有导出的会话无法补回；浏览器清理站点数据后本地记录也会删除。</p>
 <label className="lab-button">导入同事／历史会话 JSON<input type="file" accept=".json" onChange={e=>{void importing(e.target.files?.[0]);e.target.value=''}}/></label>
 {sessionError&&<p role="alert">会话存储：{sessionError}。可在播放页手动导出完整日志。</p>}
 <select aria-label="选择混音会话" value={sessionId} onChange={e=>{setSessionId(e.target.value);setSession(null)}}><option value="">选择已保存的会话…</option>{sessions.map(s=><option key={s.sessionId} value={s.sessionId}>{s.savedAt} · {s.requests}次请求 · {s.events}个事件</option>)}</select>
 {!sessions.length&&<p>尚无已保存会话。可以在本页播放后触发接歌，或导入之前导出的完整日志。</p>}{session&&<SessionEvidence session={session}/>}</>}
 </section>
}
