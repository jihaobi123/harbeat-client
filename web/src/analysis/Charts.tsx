import { useId } from 'react'
import { Point, timeLabel } from './data'

export function Curve({ title, points, duration, cursor, onSeek, color = '#6557c8', domain, unit = '', maxGapSec }: {
  title: string; points: Point[]; duration: number; cursor: number; onSeek: (t: number) => void; color?: string; domain?: [number, number]; unit?: string; maxGapSec?: number
}) {
  const id = useId().replace(/:/g, '')
  const width = 900, height = 130, left = 52, right = 15, top = 10, bottom = 27
  const values = points.map(p => p.value)
  const low = domain?.[0] ?? (values.length ? Math.min(...values) : 0)
  const high = domain?.[1] ?? (values.length ? Math.max(...values) : 1)
  const range = high-low || 1
  const x = (v: number) => left + v/Math.max(duration, 1)*(width-left-right)
  const y = (v: number) => top + (1-(v-low)/range)*(height-top-bottom)
  // Keep every computed point in the report; this path is only the display view.
  const path = points.map((p,i) => `${i && !(maxGapSec && p.time-points[i-1].time>maxGapSec) ? 'L' : 'M'}${x(p.time).toFixed(2)},${y(p.value).toFixed(2)}`).join(' ')
  return <section className="lab-curve"><div className="lab-curve-title"><b>{title}</b><span>{points.length ? `${points.length} 个采样点 · ${unit || '数值'}` : '没有可用数据'}</span></div>
    {points.length > 0 && <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} onClick={event => {
      const rect = event.currentTarget.getBoundingClientRect(); const pos = (event.clientX-rect.left)/rect.width*width
      onSeek(Math.max(0,Math.min(duration,(pos-left)/(width-left-right)*duration)))
    }}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop stopColor={color} stopOpacity=".16"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      {[0,.5,1].map(r => <g key={r}><line x1={left} x2={width-right} y1={y(low+range*r)} y2={y(low+range*r)} stroke="#e9e9ee"/><text x={left-8} y={y(low+range*r)+4} textAnchor="end">{(low+range*r).toFixed(2)}</text></g>)}
      {!maxGapSec&&<path d={`${path} L${x(points[points.length-1].time)},${height-bottom} L${x(points[0].time)},${height-bottom} Z`} fill={`url(#${id})`}/>}

      <path d={path} stroke={color} strokeWidth="1.7" fill="none"/>
      <line x1={x(cursor)} x2={x(cursor)} y1={top} y2={height-bottom} stroke="#182c38" strokeDasharray="3 3"/>
      {[0,.25,.5,.75,1].map(r=><text key={r} x={x(duration*r)} y={height-5} textAnchor={r===1?'end':r===0?'start':'middle'}>{timeLabel(duration*r)}</text>)}
    </svg>}
  </section>
}

export function Segments({ title, segments, duration, onSeek, collapseList=false }: {title:string; segments:any[]; duration:number; onSeek:(t:number)=>void; collapseList?:boolean}) {
  return <section className="lab-segments"><div className="lab-curve-title"><b>{title}</b><span>{segments.length} 个区间</span></div>
    <div className="lab-segment-strip">{segments.map((s,i)=><button key={i} style={{width:`${(s.end-s.start)/Math.max(duration,1)*100}%`,left:`${s.start/Math.max(duration,1)*100}%`,background:['#e8e4fa','#dbece6','#ffebd4','#e2eaf4'][i%4]}} onClick={()=>onSeek(s.start)} title={`${s.label} ${s.cluster || ''} ${timeLabel(s.start)}–${timeLabel(s.end)}`}>{s.cluster || s.label}</button>)}</div>
    {collapseList?<details><summary>展开全部 {segments.length} 个区间，点击定位</summary><div className="lab-segment-list">{segments.map((s,i)=><button key={i} onClick={()=>onSeek(s.start)}><span>{s.cluster && <em>{s.cluster} · </em>}{s.label || '区间'}</span><small>{timeLabel(s.start)} — {timeLabel(s.end)}</small></button>)}</div></details>:<div className="lab-segment-list">{segments.map((s,i)=><button key={i} onClick={()=>onSeek(s.start)}><span>{s.cluster && <em>{s.cluster} · </em>}{s.label || '区间'}</span><small>{timeLabel(s.start)} — {timeLabel(s.end)}</small></button>)}</div>}
  </section>
}
