import { useMemo, useState } from 'react'
import { Report, flatten, discoverTimelines, csv, download } from './data'
import { Curve, Segments } from './Charts'
import { dimension, dimensionNames, groupRows, sourceNames } from './dimensions'

export default function AllDimensions({report,cursor,onSeek}:{report:Report;cursor:number;onSeek:(time:number)=>void}) {
  const [selected,setSelected]=useState('rhythm'),[source,setSource]=useState(''),[filter,setFilter]=useState(''),[page,setPage]=useState(0),[chosenCurve,setChosenCurve]=useState(''),[chosenIntervals,setChosenIntervals]=useState('')
  const allSources=useMemo(()=>({...report.documents,...Object.fromEntries(Object.entries(report.extensions).map(([k,v])=>['extension_'+k,v]))}),[report])
  const rows=useMemo(()=>flatten(allSources),[allSources])
  const groups=useMemo(()=>groupRows(rows),[rows])
  const timelines=useMemo(()=>discoverTimelines(allSources),[allSources])
  const visible=groups[selected].filter(r=>(!source||r.path.startsWith('/'+source+'/'))&&(!filter||(r.path+' '+r.value).toLowerCase().includes(filter.toLowerCase())))
  const curves=timelines.curves.filter(c=>dimension(c.title)===selected&&(!source||c.title.startsWith('/'+source+'/')))
  const intervals=timelines.intervals.filter(c=>dimension(c.title)===selected&&(!source||c.title.startsWith('/'+source+'/')))
  const curve=curves.find(c=>c.title===chosenCurve)||curves[0], interval=intervals.find(c=>c.title===chosenIntervals)||intervals[0]
  const actualPage=Math.min(page,Math.max(0,Math.ceil(visible.length/100)-1))
  return <section className="lab-panel"><div className="lab-panel-title"><h2>已有分析 · 全部维度</h2><span>{Object.keys(allSources).length} 个来源与模块 · {rows.length.toLocaleString()} 个原始字段</span></div>
    <p className="lab-muted">按维度查看原有结果，曲线和字段均保留来源。没有记录的维度会明确标示；不同模型的估计分别展示。</p>
    <div className="lab-dimensions">{Object.entries(dimensionNames).map(([key,label])=><button key={key} className={selected===key?'selected':''} onClick={()=>{setSelected(key);setPage(0);setChosenCurve('');setChosenIntervals('')}}>{label}<small>{groups[key].length.toLocaleString()} 项</small></button>)}</div>
    <div className="lab-actions"><select aria-label="筛选分析来源" value={source} onChange={e=>{setSource(e.target.value);setPage(0)}}><option value="">全部来源</option>{Object.keys(allSources).map(k=><option value={k} key={k}>{sourceNames[k]||k}</option>)}</select><input aria-label="搜索当前维度" placeholder="搜索字段或数值" value={filter} onChange={e=>{setFilter(e.target.value);setPage(0)}}/><button onClick={()=>download(`${dimensionNames[selected]}.csv`,csv(visible),'text/csv;charset=utf-8')}>导出当前维度</button></div>
    {curves.length>0&&<><label className="lab-field-label">时间曲线 · {curves.length} 组<select aria-label="当前维度曲线" value={curve?.title||''} onChange={e=>setChosenCurve(e.target.value)}>{curves.map(c=><option key={c.title} value={c.title}>{c.title}</option>)}</select></label>{curve&&<Curve title={curve.title} points={curve.points} duration={report.summary.duration||report.audio.duration||1} cursor={cursor} onSeek={onSeek}/>}</>}
    {intervals.length>0&&<><label className="lab-field-label">区间标记 · {intervals.length} 组<select aria-label="当前维度区间" value={interval?.title||''} onChange={e=>setChosenIntervals(e.target.value)}>{intervals.map(c=><option key={c.title} value={c.title}>{c.title}</option>)}</select></label>{interval&&<Segments title={interval.title} segments={interval.segments} duration={report.summary.duration||report.audio.duration||1} onSeek={onSeek}/>}</>}
    <h3>{dimensionNames[selected]} · 原始字段</h3>{!visible.length?<p className="lab-notice">当前来源未提供此维度的记录。可切换来源或选择正式曲库报告查看。</p>:<><div className="lab-table-wrap"><table><thead><tr><th>来源 / 字段</th><th>原始值</th></tr></thead><tbody>{visible.slice(actualPage*100,(actualPage+1)*100).map(r=><tr key={r.path}><td>{r.path}</td><td>{r.value===null?'未知（null）':String(r.value)}</td></tr>)}</tbody></table></div><div className="lab-actions"><button disabled={actualPage===0} onClick={()=>setPage(actualPage-1)}>上一页</button><span>{actualPage+1} / {Math.ceil(visible.length/100)} 页 · 共 {visible.length.toLocaleString()} 项</span><button disabled={(actualPage+1)*100>=visible.length} onClick={()=>setPage(actualPage+1)}>下一页</button></div></>}
  </section>
}
