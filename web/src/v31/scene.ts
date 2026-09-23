import type {Track,Plan} from '../realtime/planner'
import {mergeSections} from '../guarded/planner'
export type Span={start:number;end:number;label?:string}
export const sectionName=(label:string)=>({intro:'前奏',verse:'主歌',chorus:'副歌',bridge:'桥段',outro:'尾奏',instrumental:'器乐段',break:'间奏',solo:'独奏',unknown:'未分类'}[label]||label)
export function sourceAtRenderTime(p:Plan,side:'a'|'b',t:number):number|null{
 if(side==='a')return t>p.duration?null:p.start+t
 if(t<0)return null
 return t<p.duration?p.window.start+t*p.rate:p.window.end+t-p.duration
}
function clip(xs:Span[],start:number,end:number){return xs.map(x=>({...x,start:Math.max(start,x.start),end:Math.min(end,x.end)})).filter(x=>x.end>x.start)}
function union(xs:Span[]){const out:Span[]=[];for(const x of xs.map(x=>({...x})).sort((a,b)=>a.start-b.start)){const last=out.at(-1);if(last&&x.start<=last.end)last.end=Math.max(last.end,x.end);else out.push(x)}return out}
function bMap(xs:Span[],p:Plan,hi:number){return [...clip(xs,p.window.start,p.window.end).map(x=>({...x,start:(x.start-p.window.start)/p.rate,end:(x.end-p.window.start)/p.rate})),...clip(xs,p.window.end,p.window.end+hi-p.duration).map(x=>({...x,start:p.duration+x.start-p.window.end,end:p.duration+x.end-p.window.end}))]}
export function buildScene(a:Track,b:Track,p:Plan,requestPosition:number){
 const protection=(p as Plan&{protection?:any}).protection,min=-Math.min(4,p.start),max=p.duration+Math.min(8,b.duration-p.window.end)
 const aMap=(xs:Span[])=>clip(xs,p.start+min,p.end).map(x=>({...x,start:x.start-p.start,end:x.end-p.start}))
 const aVocals=aMap((a.vocals||[]).map(([start,end])=>({start,end}))),bVocals=bMap((b.vocals||[]).map(([start,end])=>({start,end})),p,max)
 const overlaps=union(union(aVocals).flatMap(x=>union(bVocals).map(y=>({start:Math.max(0,x.start,y.start),end:Math.min(p.duration,x.end,y.end)}))).filter(x=>x.end>x.start))
 const ending=mergeSections(a.sections).find(s=>s.start<=p.start&&s.end>p.start),sectionEnd=protection?.exit?.sectionEnd??ending?.end??null
 return {min,max,duration:p.duration,waitSec:p.end-requestPosition,requestPosition,sectionEnd,sectionTailSec:sectionEnd===null?null:p.end-sectionEnd,
  protected:!!protection,certainty:protection?.automaticExit?'声学候选；段落标签和歌词句末未经人工确认':'模型段落与人声活动区间，不等同于歌词句子',
  aSections:aMap(mergeSections(a.sections)),bSections:bMap(mergeSections(b.sections),p,max),aVocals,bVocals,overlaps,overlapSec:a.vocals===null||b.vocals===null?null:overlaps.reduce((s,x)=>s+x.end-x.start,0),
  aCutInVocal:a.vocals?.some(([s,e])=>s<p.end&&e>p.end)??null,
  entryRole:p.window.role,entrySec:[p.window.start,p.window.end],exitSection:protection?.exit?.label||ending?.label||'unknown',
  why:[protection?`等 ${Math.max(0,p.end-requestPosition).toFixed(1)} 秒，在模型段尾后的低人声活动点退出。`:`等 ${Math.max(0,p.end-requestPosition).toFixed(1)} 秒，取等待、变速、人声占比等规则评分最高的候选。`,
   protection?'B 进入片段通过无人声与同段落检查，A 退出后才接 B 正文。':`B 从「${sectionName(p.window.role)}」取 ${p.window.bars} 小节；人声占比用于扣分和中频衰减，并非必须无重叠。`,
   `两版沿用 V3 渐变与 EQ。此转场持续 ${p.duration.toFixed(2)} 秒，B 中频 ${p.midDuck?'衰减 5 dB':'保持原值'}，接管后恢复原速。`]}
}
export type Scene=ReturnType<typeof buildScene>
