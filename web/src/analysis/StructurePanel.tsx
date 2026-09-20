import { Report } from './data'
import { Segments } from './Charts'

type Source={id:string;title:string;kind:string;note:string;segments:any[]}
const names:Record<string,string>={intro:'前奏',verse:'主歌',chorus:'副歌','pre-chorus':'预副歌',bridge:'桥段',inst:'器乐段',outro:'尾奏',silence:'静音段',buildup:'推进段',drop:'Drop',breakdown:'Breakdown'}
function segments(items:any[]) {
  return (Array.isArray(items)?items:[]).map(s=>({...s,
    start:s.start??s.start_sec??s.start_ms/1000,end:s.end??s.end_sec??s.end_ms/1000,
    label:s.label??s.edmformer_label_candidate??s.name??'unknown',
  })).filter(s=>Number.isFinite(s.start)&&Number.isFinite(s.end)&&s.start>=0&&s.end>s.start)
}

export function structureSources(report:Report):Source[] {
  const sources:Source[]=[],docs=report.documents,doc=docs[report.primary_source||'core']||{},core=doc.analysis||doc
  const songformer=docs['songformer-sections']
  if(songformer?.status==='ready')sources.push({id:'songformer-sections',title:'SongFormer · 歌曲结构',kind:'model',note:'模型估计；保留主歌、副歌、器乐段等原始标签，边界可点击试听核对。',segments:segments(songformer.segments)})
  const published=core.sections
  if(published){const producer=published.source; sources.push({id:'core-sections',title:producer==='songformer'?'SongFormer · 已发布歌曲结构':'已有歌曲结构',kind:'model',note:`来源：${producer||report.primary_source||'core'}${published.fallback_used?' · 使用了降级结果':''}。标签按此来源的定义展示。`,segments:segments(Array.isArray(published)?published:published.items)})}
  const edm=docs['edm-structure']
  if(edm?.status==='ready')sources.push({id:'edm-structure',title:'EDM · 舞曲功能候选',kind:'candidate',note:'独立候选结果，可能标为 buildup、drop、breakdown；不等同于主歌／副歌，也不表示已通过人工验证。',segments:segments(edm.segments)})
  if(core.phrase_map?.length)sources.push({id:'core-phrase-map',title:'旧规则 · 乐句与能量分段',kind:'legacy',note:'旧 phrase_map 按乐句位置与能量贴标签；不能据此认定高能量段就是 Drop。原值保留用于对照。',segments:segments(core.phrase_map)})
  if(!sources.length&&report.timeline.sections.length)sources.push({id:'original',title:'原始结构记录',kind:'original',note:'此报告尚未提供可直接展示的独立结构模型结果。',segments:segments(report.timeline.sections)})
  return sources.filter(s=>s.segments.length)
}

export default function StructurePanel({report,onSeek}:{report:Report;onSeek:(t:number)=>void}) {
  const sources=structureSources(report),duration=report.summary.duration||report.audio.duration||1
  return <section className="lab-structure-sources"><h3>段落识别 · 按来源对照</h3>
    {!sources.length&&<p className="lab-notice">本曲没有可用的结构记录。</p>}
    {sources.length>0&&sources.every(s=>s.kind==='legacy')&&<p className="lab-notice">本曲目前只有旧规则分段，尚未接入可用的 SongFormer／EDM 结构结果。</p>}
    {sources.map(source=>{const labels=[...new Set(source.segments.map(s=>s.label))];const end=Math.max(...source.segments.map(s=>s.end));return <div key={source.id} className="lab-structure-source">
      <p className="lab-muted">{source.note}</p><p className="lab-structure-legend">{labels.map(label=>`${label}（${names[label]||'原始标签'}）`).join(' · ')}</p>
      {end<duration-Math.max(5,duration*.05)&&<p className="lab-alert">该来源仅覆盖到 {end.toFixed(1)} 秒，全曲 {duration.toFixed(1)} 秒。剩余部分尚无结构记录。</p>}
      <Segments title={source.title} segments={source.segments} duration={duration} onSeek={onSeek}/>
    </div>})}
  </section>
}
