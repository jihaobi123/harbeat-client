export type Point = { time: number; value: number }
export type ModuleResult = { status: string; reason?: string; elapsed_ms?: number; validation?: string; data?: any; [key: string]: any }
export type Report = {
  schema: 'harbeat.analysis_report'; version: string; id: string; title: string; created_at: string
  documents: Record<string, any>; source_hashes: Record<string, string>; primary_source: string
  summary: { bpm: number | null; key: string | null; camelot?: string | null; energy: number | string | null; duration: number }
  audio: { hash_verification?: string; sha256?: string; duration?: number; name?: string; binding?: string; catalog_track_id?: string; assets?: Record<string, MediaAsset> }
  view_sources?: Record<string,string>
  timeline: { beats: number[]; downbeats: number[]; sections: any[]; energy: any[]; bpm: any[]; stems: any[]; transitions: any[] }
  diagnostics?: {warnings: string[]; section_end_sec: number; audio_duration_sec: number}
  extensions: Record<string, ModuleResult>; evaluation: { status: string; reason?: string }
}
export type MediaAsset = {id?:string;status:string;reason?:string;duration?:number;sample_rate?:number;channels?:number;size_bytes?:number;filename?:string}
export type Row = { path: string; value: unknown }
export function flatten(value: unknown, prefix = ''): Row[] {
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value)
    if (!entries.length) return [{ path: prefix, value: Array.isArray(value) ? '[]' : '{}' }]
    return entries.flatMap(([key, child]) => flatten(child, `${prefix}/${key.replace(/~/g, '~0').replace(/\//g, '~1')}`))
  }
  return [{ path: prefix, value }]
}
export function series(points: any[], field: string): Point[] {
  return (points || []).map(p => ({ time: p.start ?? p.time ?? p.timestamp_sec ?? p.start_sec ?? (p.start_ms === undefined ? NaN : p.start_ms/1000), value: p[field] }))
    .filter(p => typeof p.time === 'number' && Number.isFinite(p.time) && typeof p.value === 'number' && Number.isFinite(p.value))
}
export function sourceDocuments(value: any, name: string): { title: string; documents: Record<string, any> }[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('需要分析对象或以曲目 ID 为键的分析集合')
  if (value.documents) return [{ title: name, documents: value.documents }]
  const keys = ['bpm','analysis','timeline','schema_name','song_id','duration','duration_sec','key','sections','bars','summary','status','segments','model']
  if (!Object.keys(value).some(k => keys.includes(k)) && Object.values(value).length && Object.values(value).every(v => v && typeof v === 'object' && !Array.isArray(v))) {
    return Object.entries(value).map(([key, v]) => ({ title: key, documents: { core: v } }))
  }
  return [{ title: name, documents: { core: value } }]
}
export function download(name: string, value: string, mime = 'application/json') {
  const url = URL.createObjectURL(new Blob([value], { type: mime }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function csv(rows: Row[]): string {
  const cell = (v: unknown) => {
    let s = v === null ? 'null' : String(v)
    if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
    return `"${s.replace(/"/g, '""')}"`
  }
  return '\ufeffpath,value\n' + rows.map(r => `${cell(r.path)},${cell(r.value)}`).join('\n')
}
export function timeLabel(t: number) { return `${Math.floor(t/60)}:${(t%60).toFixed(3).padStart(6,'0')}` }

export function discoverTimelines(documents: Record<string, any>): {curves:{title:string;points:Point[]}[]; intervals:{title:string;segments:any[]}[]} {
  const curves: {title:string;points:Point[]}[] = [], intervals: {title:string;segments:any[]}[] = []
  const timestamp = (v:any) => v.start ?? v.start_sec ?? v.time ?? v.time_sec ?? v.timestamp_sec ?? (v.start_ms === undefined ? undefined : v.start_ms/1000)
  function visit(value:any,path:string,depth:number) {
    if(!value || typeof value!=='object' || depth>12)return
    if(Array.isArray(value)) {
      const timed=value.filter(v=>v && typeof v==='object' && typeof timestamp(v)==='number')
      if(timed.length) {
        const keys=new Set<string>()
        timed.forEach(v=>Object.keys(v).forEach(k=>{if(typeof v[k]==='number'&&!/^(start|end|time|timestamp|bar_index|beat_index)/.test(k))keys.add(k)}))
        keys.forEach(k=>{const points=timed.map(v=>({time:timestamp(v),value:v[k]})).filter(p=>Number.isFinite(p.value));if(points.length)curves.push({title:`${path}/${k}`,points})})
        const segments=timed.map(v=>({...v,start:timestamp(v),end:v.end??v.end_sec??(v.end_ms===undefined?undefined:v.end_ms/1000),label:v.label??v.edmformer_label_candidate??v.chord??v.type??'区间'})).filter(v=>Number.isFinite(v.end)&&v.end>v.start)
        if(segments.length)intervals.push({title:path,segments})
        const instruments=new Map<string,Point[]>()
        timed.forEach(bar=>(bar.instrument_probabilities||[]).forEach((i:any)=>{const key=i.instrument_class;const points=instruments.get(key)||[];if(Number.isFinite(i.mean_probability))points.push({time:timestamp(bar),value:i.mean_probability});instruments.set(key,points)}))
        instruments.forEach((points,name)=>curves.push({title:`${path}/PANNs/${name}`,points}))
      }
      // Inspect nested model collections such as bars/drum_events; scalar arrays stay raw.
      value.forEach((v,i)=>{if(v&&typeof v==='object')Object.entries(v).forEach(([k,c])=>{if(c&&typeof c==='object')visit(c,`${path}/${i}/${k}`,depth+1)})})
    } else Object.entries(value).forEach(([k,v])=>visit(v,`${path}/${k}`,depth+1))
  }
  visit(documents,'',0)
  return {curves,intervals}
}

export function differences(a: unknown, b: unknown): {path:string;current:unknown;comparison:unknown;change:string}[] {
  const left=new Map(flatten(a).map(r=>[r.path,r.value])),right=new Map(flatten(b).map(r=>[r.path,r.value]))
  return [...new Set([...left.keys(),...right.keys()])].sort().filter(path=>!left.has(path)||!right.has(path)||JSON.stringify(left.get(path))!==JSON.stringify(right.get(path))).map(path=>({path,current:left.get(path),comparison:right.get(path),change:!left.has(path)?'仅对照版本':!right.has(path)?'仅当前版本':'数值不同'}))
}
