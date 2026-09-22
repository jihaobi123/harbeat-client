import { useEffect, useMemo, useRef, useState } from 'react'
import { call, getReport, post, loadWorkspace } from './api'
import { csv, download, flatten, Report, series, sourceDocuments, timeLabel, discoverTimelines, differences } from './data'
import { Curve, Segments } from './Charts'
import BlindListening from './BlindListening'
import './analysis.css'
import './complete.css'
import logo from './assets/harbeat-logo.png'
import AllDimensions from './AllDimensions'
import MixTracePanel from './MixTracePanel'
import StylePanel from './StylePanel'
import MeasurementsPanel from './MeasurementsPanel'
import DJPanel from './DJPanel'
import StemPanel from './StemPanel'
import { audioNames } from './dimensions'
import SourceStatus from './SourceStatus'
import StructurePanel from './StructurePanel'
import SyncedStemPlayer, { StemPlayerHandle } from './SyncedStemPlayer'

const moduleNames: Record<string,string> = {dj_signals:'接歌声音特征',core_features:'已有特征补算',chords:'和弦时间轴',measurements:'动态与起音',emotion_summary:'情绪摘要',genre:'模型风格',emotion:'情绪曲线',instruments:'通用乐器',roughness:'感官粗糙度',repeat:'重复段落'}
const statuses: Record<string,string> = {ready:'已计算 · 待验证',unavailable:'运行条件未满足',failed:'计算失败'}

export function canOpenJobResult(followedId:string|null,selectedId:string|null,job:any){
  return Boolean(followedId===job.id&&selectedId===job.source_report_id&&job.status==='completed')
}

export default function AnalysisLab() {
  const [catalogSearch,setCatalogSearch] = useState('')
  const [allVersions,setAllVersions] = useState(false)
  const [audioChoice,setAudioChoice] = useState('master')
  const [coverage,setCoverage] = useState<any>(null)
  const [catalog,setCatalog] = useState<any>(null)
  const [runtime,setRuntime] = useState<any>(null)
  const [jobs,setJobs] = useState<any[]>([])
  const [history,setHistory] = useState<any[]>([])
  const [report,setReport] = useState<Report|null>(null)
  const [comparison,setComparison] = useState<Report|null>(null)
  const [error,setError] = useState('')
  const [notice,setNotice] = useState('')
  const [busy,setBusy] = useState(false)
  const [job,setJob] = useState<any>(null)
  const [tab,setTab] = useState(()=>{const t=typeof window!=='undefined'?new URLSearchParams(window.location.search).get('tab'):null;return t&&['timeline','dj','measurements','styles','dimensions','stems','evidence','compare','listen','mix-material','mix-debug'].includes(t)?t:'timeline'})
  const [search,setSearch] = useState('')
  const [cursor,setCursor] = useState(0)
  const [localAudio,setLocalAudio] = useState<string>('')
  const [audioFile,setAudioFile] = useState<File|null>(null)
  const [evaluation,setEvaluation] = useState<any>(null)
  const [extraCurve,setExtraCurve] = useState('')
  const [extraInterval,setExtraInterval] = useState('')
  const player = useRef<StemPlayerHandle>(null)
  const selectionSeq=useRef(0)
  const selectedReportId=useRef<string|null>(null)
  const followedJobId=useRef<string|null>(null)
  function trackJob(next:any,follow=true){followedJobId.current=follow?next.id:null;setJob(next)}
  const lastCatalogUpdate=useRef('')
  const lastCoverageUpdate=useRef('')
  const [loadingId,setLoadingId]=useState('')
  const rows = useMemo(()=>report ? flatten(report.documents) : [],[report])
  const discovered = useMemo(()=>discoverTimelines(report?.documents || {}),[report])
  const filtered = useMemo(()=>rows.filter(r=>(r.path+' '+r.value).toLowerCase().includes(search.toLowerCase())),[rows,search])
  const changes = useMemo(()=>comparison && report ? differences({documents:report.documents,extensions:report.extensions},{documents:comparison.documents,extensions:comparison.extensions}) : [],[report,comparison])
  const duration = report?.summary.duration || report?.audio.duration || 1
  const latestHistory=useMemo(()=>{const seen=new Set<string>();return history.filter(item=>{const key=item.audio?.catalog_track_id||item.audio?.sha256||item.id;if(seen.has(key))return false;seen.add(key);return true})},[history])
  const newer=report&&latestHistory.find(item=>item.audio?.catalog_track_id&&item.audio.catalog_track_id===report.audio.catalog_track_id&&item.id!==report.id)
  async function refresh(onItems?:(items:any[])=>void) { return loadWorkspace(items=>{setHistory(items);onItems?.(items)},setJobs) }
  async function select(id:string) {const seq=++selectionSeq.current;selectedReportId.current=id;setLoadingId(id);try{const next=await getReport(id);if(seq!==selectionSeq.current)return;selectedReportId.current=next.id;setReport(next);setComparison(null);setEvaluation(null);setLocalAudio('');setAudioFile(null);setCursor(0);setSearch('');setAudioChoice('master');setError('');setNotice('')}finally{if(seq===selectionSeq.current)setLoadingId('')}}
  useEffect(()=>{const initialSelection=selectionSeq.current;refresh(items=>{if(items.length&&selectionSeq.current===initialSelection)select(new URLSearchParams(window.location.search).get('report')||(items.find(item=>item.audio?.catalog_track_id)||items[0]).id).catch(e=>setError(e.message))}).then(async ({tasks})=>{const running=tasks.find(t=>['running','queued'].includes(t.status));if(running)trackJob(await call(`/jobs/${running.id}`),false)}).catch(e=>setError(e.message));call<any>('/status').then(setRuntime).catch(()=>{});call<any>('/catalog').then(setCatalog).catch(()=>{})},[])
  useEffect(()=>{const timer=setInterval(()=>{call<any>('/catalog').then(next=>{setCatalog(next);if(next.measurement?.updated_at&&next.measurement.updated_at!==lastCatalogUpdate.current){lastCatalogUpdate.current=next.measurement.updated_at;refresh().catch(()=>{})}}).catch(()=>{})},10000);return ()=>clearInterval(timer)},[])
  useEffect(()=>{const update=()=>call<any>('/coverage').then(next=>{setCoverage(next);if(next.updated_at&&next.updated_at!==lastCoverageUpdate.current){lastCoverageUpdate.current=next.updated_at;refresh().catch(()=>{})}}).catch(()=>{});update();const timer=setInterval(update,10000);return ()=>clearInterval(timer)},[])
  useEffect(()=>()=>{if(localAudio)URL.revokeObjectURL(localAudio)},[localAudio])
  useEffect(()=>{
    if (!job || !['queued','running'].includes(job.status)) return
    const id=setTimeout(()=>call<any>(`/jobs/${job.id}`).then(async next=>{
      setJob(next)
      if(next.status==='completed'){if(canOpenJobResult(followedJobId.current,selectedReportId.current,next)){await select(next.report_id);setNotice('分析任务已完成，原始报告仍保留在历史记录中')}await refresh()}
    }).catch(e=>{setError(`连接暂时中断，正在重试：${e.message}`);setJob({...job})}),1500)
    return ()=>clearTimeout(id)
  },[job])
  async function importing(files:FileList|null, attach=false) {
    if(!files?.length)return
    setBusy(true);setError('')
    try {
      let last: Report|null=null
      if(attach && report) {
        const documents={...report.documents}
        for(const file of Array.from(files)) {
          if(file.size>20*1024*1024)throw new Error('单个 JSON 最大 20 MB')
          if(documents[file.name])throw new Error('同名来源已存在，请重命名后添加')
          documents[file.name]=JSON.parse(await file.text())
        }
        last=await post<Report>('/import',{documents,audio:report.audio,extensions:report.extensions})
      } else {
        for(const file of Array.from(files)) {
          if(file.size>20*1024*1024)throw new Error('单个 JSON 最大 20 MB')
          const value=JSON.parse(await file.text())
          if(value.schema==='harbeat.analysis_report')last=await post<Report>('/import',value)
          else for(const source of sourceDocuments(value,file.name))last=await post<Report>('/import',{documents:source.documents,audio:{name:source.title}})
        }
      }
      if(last){selectedReportId.current=last.id;setReport(last);setComparison(null);setLocalAudio('');setAudioFile(null);setEvaluation(null)}
      await refresh();setNotice('已保存全部来源字段；可以添加 PANNs、分轨、人声等独立结果')
    } catch(e) {setError((e as Error).message)} finally {setBusy(false)}
  }
  async function run() {
    if(!report)return
    setBusy(true);setError('')
    try { if(audioFile){const body=new FormData();body.append('audio',audioFile);body.append('report_id',report.id);trackJob(await call('/jobs',{method:'POST',body}))}else{trackJob(await post(`/reports/${report.id}/rerun`,{}))} }
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  function seek(t:number){setCursor(t);player.current?.seek(t)}
  async function annotate(file:File|undefined) {
    if(!file || !report)return
    try{setEvaluation(await post(`/reports/${report.id}/evaluate`,JSON.parse(await file.text())))}catch(e){setError((e as Error).message)}
  }
  const active=job && ['queued','running'].includes(job.status)
  const emotion=report?.extensions.emotion?.data?.points || []
  const roughness=report?.extensions.roughness?.data?.points || []
  return <div className="analysis-lab">
    <aside className="lab-sidebar"><a className="lab-brand" href="/analysis-lab"><img className="lab-logo" src={logo} alt="HarBeat 标志"/><div>HarBeat<small>ANALYSIS LAB</small></div></a>
      <div className="lab-side-heading">工作空间 <span>01</span></div><button className="lab-side-current" onClick={()=>setTab('timeline')}>◉ 音乐分析工作台</button><button className="lab-side-link" onClick={()=>setTab('mix-debug')}>◈ 混音调试与素材来源</button><button className="lab-side-link" onClick={()=>setTab('listen')}>◫ 转场盲听</button>
      <div className="lab-side-heading">曲库 <span>{latestHistory.length}</span></div>
      <input className="lab-catalog-search" aria-label="搜索曲目" placeholder="搜索歌曲或曲目编号" value={catalogSearch} onChange={e=>setCatalogSearch(e.target.value)}/><label className="lab-version-toggle"><input type="checkbox" checked={allVersions} onChange={e=>setAllVersions(e.target.checked)}/> 显示全部 {history.length} 个版本</label><div className="lab-history">{(allVersions?history:latestHistory).filter(item=>(item.title+' '+(item.audio?.catalog_track_id||'')).toLowerCase().includes(catalogSearch.toLowerCase())).map(item=><button key={item.id} className={report?.id===item.id?'selected':''} onClick={()=>select(item.id).catch(e=>setError(e.message))}><b>{item.title}</b><small>{item.audio?.binding==='published_manifest_reference'?'NAS 预处理':item.audio?.binding==='library_record_reference'?'正式曲库':'历史报告'} · {item.summary?.bpm ?? '—'} BPM · {item.id.slice(0,7)}</small></button>)}{!history.length&&<p className="lab-muted">导入后，分析版本会保存在这里。</p>}</div>
      <div className="lab-side-footer">独立分析 · 完整保留<br/><span>HarBeat / Analysis workspace</span></div>
    </aside>
    <main className="lab-main"><header className="lab-top"><div className="lab-breadcrumb">工作空间 <span>/</span> 音乐分析</div><span className="lab-local"><i/>{runtime ? `执行机器：${runtime.execution_host}` : '分析工作台'}</span></header>
      <div className="lab-heading"><div><p className="lab-eyebrow">LISTEN. MEASURE. UNDERSTAND.</p><h1>音乐分析工作台</h1><p>把声音放到时间线上，查看每个判断的依据。</p></div><label className="lab-button primary">＋ 导入分析 JSON<input type="file" accept=".json" multiple disabled={busy} onChange={e=>{importing(e.target.files);e.target.value=''}}/></label></div>
      {catalog?.imported>0&&<p className="lab-source-summary">已接入 {catalog.imported} 份正式曲库与 NAS 预处理来源 · {catalog.errors?.length||0} 项接入异常 · 原始数据完整保留</p>}
      {catalog?.measurement&&<div className="lab-source-summary" role="status"><b>真实分轨曲线 · {catalog.measurement.status==='running'?'Jetson 后台计算中':'批量计算已结束'}</b><p>已处理 {catalog.measurement.processed} / {catalog.measurement.total} 首 · 已生成 {catalog.measurement.measured} 份 · 无可用分轨 {catalog.measurement.unavailable} 份 · 错误 {catalog.measurement.errors?.length||0} 项</p>{catalog.measurement.current_title&&<p>正在读取：{catalog.measurement.current_title} · {audioNames[catalog.measurement.current_stem]||'准备音轨'}</p>}<progress value={catalog.measurement.processed} max={catalog.measurement.total}/>{catalog.measurement.errors?.length>0&&<details><summary>查看计算异常</summary><pre>{JSON.stringify(catalog.measurement.errors,null,2)}</pre></details>}</div>}
      {coverage&&coverage.status!=='not_started'&&<div className="lab-source-summary" role="status"><b>曲库补算 · {({running:'正在运行',completed:'已完成',completed_with_errors:'已结束，部分结果需检查',interrupted:'已中断，可续跑'} as any)[coverage.status]||coverage.status}</b><p>{coverage.phase} · 本阶段 {coverage.processed||0} / {coverage.total||0} 首 · {coverage.current_title||''} {moduleNames[coverage.current_module]||''}</p><progress value={coverage.processed||0} max={coverage.total||1}/><details><summary>查看各模块覆盖与异常（{coverage.error_count||0}）</summary><div className="lab-table-wrap"><table><thead><tr><th>模块</th><th>已计算</th><th>未计算</th><th>失败 / 条件不足</th></tr></thead><tbody>{Object.entries(coverage.coverage?.modules||{}).map(([name,c]:[string,any])=><tr key={name}><td>{moduleNames[name]||name}</td><td>{c.ready||0}</td><td>{c.missing||0}</td><td>{(c.failed||0)+(c.unavailable||0)}</td></tr>)}</tbody></table></div><p>统计的是计算覆盖，不代表预测正确；原算法子项输入不足会单独记录。</p>{coverage.errors?.length>0&&<pre>{JSON.stringify(coverage.errors,null,2)}</pre>}</details></div>}
      {loadingId&&<div className="lab-notice" role="status">正在加载完整分析报告…</div>}
      {newer&&<div className="lab-notice">本曲已有更新的分析版本。<button onClick={()=>select(newer.id)}>查看最新结果</button></div>}
      {error&&<div className="lab-alert" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
      {notice&&<div className="lab-notice" role="status">{notice}</div>}
      {!report&&tab!=='listen'&&tab!=='mix-debug'&&<div className="lab-empty"><div className="lab-empty-mark">≋</div><h2>从一份已有分析开始</h2><p>支持 HarBeat 原始分析、NAS 清单、TrackAnalysis 和批量曲库 JSON。</p><p>所有原始字段都会保留；新增模型单独记录来源与状态。</p><label className="lab-button">选择分析文件<input type="file" accept=".json" multiple onChange={e=>importing(e.target.files)}/></label></div>}
      {report&&tab!=='mix-debug'&&<><section className="lab-track"><div className="lab-cover">≋</div><div className="lab-track-info"><span className="lab-eyebrow">ANALYSIS REPORT · {report.id.slice(0,8)}</span><h2>{report.title}</h2><p>{Object.keys(report.documents).length} 份来源 · 原始数据完整保留 · {timeLabel(duration)}</p></div><div className="lab-actions"><label className="lab-button">添加来源<input type="file" accept=".json" multiple onChange={e=>{importing(e.target.files,true);e.target.value=''}}/></label><button onClick={()=>download(`${report.title}-analysis.json`,JSON.stringify(report,null,2))}>导出报告 ↓</button></div></section>
      {report.diagnostics?.warnings.map((warning,i)=><div key={i} className="lab-alert" role="status">{warning}</div>)}
      <section className="lab-metrics">{[['速度',report.summary.bpm,'BPM'],['调性',report.summary.key,''],['Camelot',report.summary.camelot,''],['能量',report.summary.energy,'原始指标']].map(([label,value,unit])=><div key={String(label)}><small>{label}</small><strong>{value ?? '—'}</strong><span>{value==null?'未提供':unit}</span></div>)}</section>
      <section className="lab-player lab-multitrack"><SyncedStemPlayer key={`${report.id}:${localAudio}`} ref={player} report={report} localAudio={localAudio} onTime={setCursor} onSelection={setAudioChoice}/><div className="lab-actions"><label className="lab-button">选择原曲<input type="file" accept="audio/*" onChange={e=>{const f=e.target.files?.[0];if(f){setAudioFile(f);setLocalAudio(URL.createObjectURL(f));setCursor(0);setAudioChoice('master')}}}/></label>{localAudio&&<button onClick={()=>{setLocalAudio('');setAudioFile(null);setCursor(0)}}>返回报告原曲</button>}<button className="primary" disabled={(!audioFile&&!report.audio.sha256&&!report.audio.assets?.master?.id)||busy||active} onClick={run}>{active?'分析运行中…':'运行补充分析'}</button></div></section>
      {job&&<div className="lab-notice" role="status">任务：{({queued:'排队中',running:'正在计算',completed:'已完成',failed:'失败',interrupted:'已中断'} as any)[job.status]} {job.module==='stem_activity'?'真实分轨活动':moduleNames[job.module] || ''} {job.detail||''} {job.reason || ''} · 已记录 {Object.keys(job.module_results||{}).length} / {job.modules?.length||Object.keys(moduleNames).length} 个步骤{job.started_at&&` · 总耗时 ${Math.max(0,Math.floor(((job.finished_at?Date.parse(job.finished_at):Date.now())-Date.parse(job.started_at))/1000))} 秒`}{active&&job.module_started_at&&` · 当前步骤 ${Math.max(0,Math.floor((Date.now()-Date.parse(job.module_started_at))/1000))} 秒`}</div>}
      <nav className="lab-tabs">{[['timeline','时间轴'],['mix-material','混音素材与来源'],['dj','接歌准备'],['measurements','和弦与动态'],['styles','风格与人工确认'],['dimensions','全部维度'],['stems','分轨试听'],['evidence','全部特征与依据'],['compare','版本对照'],['listen','转场盲听']].map(([key,label])=><button key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      {tab==='timeline'&&<><SourceStatus report={report}/><div className="lab-module-grid">{Object.entries(moduleNames).map(([key,name])=>{const taskMatches=job&&(job.source_report_id===report.id||job.report_id===report.id);const m=(taskMatches?job.module_results?.[key]:null)||report.extensions[key];const running=taskMatches&&active&&job.module===key;return <div key={key} className="lab-module"><span>{name}</span><b className={m?.status==='ready'?'ready':''}>{running?'正在计算':m ? statuses[m.status] || m.status : '尚未运行'}</b><small>{m?.reason || (m ? `${((m.elapsed_ms||0)/1000).toFixed(1)}s · 独立补充结果` : '不影响已有分析')}</small></div>})}</div>
        <div className="lab-panel"><div className="lab-panel-title"><h2>音乐时间轴</h2><span>点击定位 · 单位：秒</span></div>
        <StructurePanel report={report} onSeek={seek}/>
        <Curve title="能量变化" points={series(report.timeline.energy,'relative_energy').length?series(report.timeline.energy,'relative_energy'):series(report.timeline.energy,'energy').length?series(report.timeline.energy,'energy'):series(report.timeline.energy,'value')} duration={duration} cursor={cursor} onSeek={seek} unit="按来源定义"/>
        <Curve title="局部速度" points={series(report.timeline.bpm,'bpm')} duration={duration} cursor={cursor} onSeek={seek} color="#279b81" unit="BPM"/>
        <div className="lab-beats"><b>拍点 {report.timeline.beats.length} · 小节首拍 {report.timeline.downbeats.length}</b><div>{report.timeline.beats.filter(t=>Math.abs(t-cursor)<4).map((t,i)=><button key={i} onClick={()=>seek(t)}>{timeLabel(t)}</button>)}</div><small>展示当前播放位置前后 4 秒的拍点，完整数据保留在报告内。</small></div>
        <Curve title="愉悦度 Valence" points={series(emotion,'valence')} duration={duration} cursor={cursor} onSeek={seek} domain={[-1,1]}/>
        <Curve title="激活度 Arousal" points={series(emotion,'arousal')} duration={duration} cursor={cursor} onSeek={seek} domain={[0,1]} color="#d88842"/>
        <Curve title="感官粗糙度" points={series(roughness,'value')} duration={duration} cursor={cursor} onSeek={seek} color="#49829f" unit="声学描述，非审美评分"/>
        <div className="lab-notice">分轨：{Object.values(report.audio.assets||{}).filter(a=>a.id).length} 个音频文件 · {report.timeline.stems.length} 个活动窗口 <button onClick={()=>setTab('stems')}>查看分轨与试听</button></div>
        <Segments title="重复段落分组（保留原始段落名称）" segments={report.extensions.repeat?.data?.segments || []} duration={duration} onSeek={seek}/>
        <Segments title="候选转场区间" segments={report.timeline.transitions.map(s=>({...s,start:s.start??s.start_ms/1000,end:s.end??s.end_ms/1000,label:s.label||s.role||'候选'})).filter(s=>Number.isFinite(s.start)&&s.end>s.start)} duration={duration} onSeek={seek}/>
        <div className="lab-tags"><b>通用乐器标签</b>{(report.extensions.instruments?.data?.labels||[]).map((v:any)=><span key={v.label}>{v.label} <small>{v.score.toFixed(2)}</small></span>)}{!report.extensions.instruments?.data&&<p>尚无可用模型输出；不会用缺失值替代已有 PANNs 结果。</p>}</div>
        <h3>探索全部来源的时间特征</h3><p className="lab-muted">自动识别已有 PANNs、人声、和弦和其他带时间的结果，各来源并列保留。</p>
        <select aria-label="选择时间曲线" value={extraCurve} onChange={e=>setExtraCurve(e.target.value)}><option value="">选择曲线（{discovered.curves.length}）</option>{discovered.curves.map(c=><option key={c.title} value={c.title}>{c.title}</option>)}</select>
        {discovered.curves.filter(c=>c.title===extraCurve).map(c=><Curve key={c.title} title={c.title} points={c.points} duration={duration} cursor={cursor} onSeek={seek}/>)}
        <select aria-label="选择区间来源" value={extraInterval} onChange={e=>setExtraInterval(e.target.value)}><option value="">选择区间（{discovered.intervals.length}）</option>{discovered.intervals.map(c=><option key={c.title} value={c.title}>{c.title}</option>)}</select>
        {discovered.intervals.filter(c=>c.title===extraInterval).map(c=><Segments key={c.title} title={c.title} segments={c.segments} duration={duration} onSeek={seek}/>)}
        </div></>}
      {tab==='mix-material'&&<MixTracePanel key={report.id} report={report} materialOnly/>}
      {tab==='dj'&&<DJPanel key={report.id} auditionMatches={!localAudio} report={report} history={latestHistory} cursor={cursor} onSeek={seek} busy={Boolean(active)||busy} onRun={async()=>{setBusy(true);try{trackJob(await post(`/reports/${report.id}/modules/dj_signals`,{}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}/>}
      {tab==='measurements'&&<MeasurementsPanel report={report} cursor={cursor} onSeek={seek} busy={Boolean(active)||busy} onRun={async module=>{setBusy(true);try{trackJob(await post(`/reports/${report.id}/modules/${module}`,{}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}/>}
      {tab==='styles'&&<StylePanel key={report.id} report={report} busy={Boolean(active)||busy} onSeek={seek} onRun={async()=>{setBusy(true);try{trackJob(await post(`/reports/${report.id}/modules/genre`,{}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}/>}
      {tab==='dimensions'&&<AllDimensions key={report.id} report={report} cursor={cursor} onSeek={seek}/>}
      {tab==='stems'&&<StemPanel report={report} cursor={cursor} onSeek={seek} selected={audioChoice} onSelect={name=>player.current?.select(name)} busy={Boolean(active)||busy} onMeasure={async()=>{setBusy(true);try{trackJob(await post(`/reports/${report.id}/stems`,{}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}/>}
      {tab==='evidence'&&<div className="lab-panel"><div className="lab-panel-title"><h2>全部特征与依据</h2><button onClick={()=>download('analysis-features.csv',csv(rows),'text/csv;charset=utf-8')}>导出完整 CSV</button></div><p className="lab-muted">{rows.length} 个原始字段 · 下表展示前 500 项，导出包含全部字段。空值表示未知，不表示零。</p><input className="lab-search" placeholder="搜索特征、来源或数值…" value={search} onChange={e=>setSearch(e.target.value)}/><div className="lab-table-wrap"><table><thead><tr><th>来源 / 字段路径</th><th>原始值</th></tr></thead><tbody>{filtered.slice(0,500).map(r=><tr key={r.path}><td>{r.path}</td><td>{r.value===null?<em>未知（null）</em>:String(r.value)}</td></tr>)}</tbody></table></div>{filtered.length>500&&<p>匹配 {filtered.length} 项，显示前 500 项；请缩小搜索或导出。</p>}
        <h3>分析任务记录</h3><p className="lab-muted">点击任务可查看或恢复进度跟踪，也可导出每一步的状态与错误。</p><div className="lab-actions">{jobs.filter(j=>j.source_report_id===report.id||j.report_id===report.id).map(j=><button key={j.id} onClick={()=>call<any>(`/jobs/${j.id}`).then(setJob).catch(e=>setError(e.message))}>{j.id.slice(0,8)} · {j.status}</button>)}</div>{job&&<details><summary>任务 {job.id.slice(0,8)} · {job.status}</summary><button onClick={()=>download('analysis-job.json',JSON.stringify(job,null,2))}>导出任务记录</button><pre>{JSON.stringify(job,null,2)}</pre></details>}
        <h3>来源指纹</h3>{Object.entries(report.source_hashes).map(([name,hash])=><p key={name} className="lab-hash">{name}<code>{hash}</code></p>)}<h3>补充模块的模型、参数与状态</h3>{Object.entries(report.extensions).map(([name,value])=><details key={name}><summary>{moduleNames[name]||name} · {statuses[value.status]||value.status}</summary><pre>{JSON.stringify(value,null,2)}</pre></details>)}</div>}
      {tab==='compare'&&<div className="lab-panel"><h2>同曲版本对照</h2><p className="lab-muted">比较字段与曲线；只有绑定到同一音频的人工标注才参与准确率评估。</p><select value={comparison?.id||''} onChange={e=>e.target.value?getReport(e.target.value).then(setComparison):setComparison(null)}><option value="">选择另一份报告</option>{history.filter(h=>h.id!==report.id).map(h=><option key={h.id} value={h.id}>{h.title} · {h.id.slice(0,8)}</option>)}</select>
        {comparison&&<><p className="lab-notice">{report.audio.sha256&&report.audio.sha256===comparison.audio.sha256?(report.audio.hash_verification==='source_declared'||comparison.audio.hash_verification==='source_declared'?'来源声明的音频指纹一致；人工标注评估时会核验实际原曲':'音频 SHA256 一致，可进行同曲对照'):'尚未确认同一音频，仅展示差异，不判断优劣'}</p><table><thead><tr><th>指标</th><th>当前版本</th><th>对照版本</th></tr></thead><tbody>{Object.keys(report.summary).map(key=><tr key={key}><td>{key}</td><td>{String((report.summary as any)[key]??'未知')}</td><td>{String((comparison.summary as any)[key]??'未知')}</td></tr>)}</tbody></table><Curve title="当前版本能量" points={series(report.timeline.energy,'energy')} duration={duration} cursor={cursor} onSeek={seek}/><Curve title="对照版本能量" points={series(comparison.timeline.energy,'energy')} duration={comparison.summary.duration} cursor={cursor} onSeek={seek} color="#d88842"/><details><summary>逐字段差异 · {changes.length} 项</summary><button onClick={()=>download('analysis-differences.json',JSON.stringify({current:report.id,comparison:comparison.id,differences:changes},null,2))}>导出全部差异</button><div className="lab-table-wrap"><table><thead><tr><th>字段</th><th>当前版本</th><th>对照版本</th><th>差异</th></tr></thead><tbody>{changes.slice(0,500).map(row=><tr key={row.path}><td>{row.path}</td><td>{row.current===undefined?'未提供':JSON.stringify(row.current)}</td><td>{row.comparison===undefined?'未提供':JSON.stringify(row.comparison)}</td><td>{row.change}</td></tr>)}</tbody></table></div></details></>}
        <label className="lab-button">载入同曲人工标注<input type="file" accept=".json" onChange={e=>annotate(e.target.files?.[0])}/></label>{evaluation&&<><pre>{JSON.stringify(evaluation,null,2)}</pre><button onClick={()=>download('evaluation.json',JSON.stringify(evaluation,null,2))}>导出评估结果</button></>}
      </div>}
      </>}
      {tab==='mix-debug'&&<MixTracePanel/>}
      {tab==='listen'&&<BlindListening/>}<footer className="lab-footer">观测数据、模型估计与人工评价分别保留。计算完成不等于预测准确。</footer>
    </main>
  </div>
}
