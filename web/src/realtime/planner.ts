import type {V30Tune,V30Eq} from '../v30/types'
import type {PhraseAlignment,PhraseEvidence,TransitionAutomation} from '../phrase/types'
import type {PreprocessingEvidence} from './trace'
import {explainPlan} from './decision'
import {evaluateEvidence, type MixProfile} from './evidence'
export type Asset={url:string;sha256:string;duration:number;bytes:number;rate?:number}
export type Window={id:string;start:number;end:number;bars:number;role:string;energy:number;variants:Record<string,Asset&{rate:number}>}
export type Track={alignment?:PhraseAlignment;preprocessing?:PreprocessingEvidence;mixProfile?:MixProfile;id:string;title:string;bpm:number;style:string;styleScore:number;duration:number;native:Asset;audioSegments?:{start:number;end:number;asset:Asset}[];bars:number[];sections:{start:number;end:number;label:string}[];vocals:[number,number][]|null;energy:{start:number;end:number;value:number}[];windows:Window[];warnings?:string[];reportId?:string;provenance?:Record<string,unknown>}
export type Intent={kind:'next'|'up'|'down'|'style';style?:string;energy?:'up'|'down'|'any';targetId?:string}
export type Plan={v30Tune?:V30Tune;v30Eq?:V30Eq;phrase?:PhraseEvidence;automation?:TransitionAutomation;id:string;from:string;to:string;window:Window;asset:Asset;start:number;end:number;duration:number;restore:number;rate:number;score:number;midDuck:boolean;aVocal:number;bVocal:number;aEnergy:number;bEnergy:number;gridError:number;reason:string;section:string;prepared:boolean;evidence?:ReturnType<typeof evaluateEvidence>;decision?:ReturnType<typeof explainPlan>}
export function vocalPresence(intervals:[number,number][],start:number,end:number):number{
 const padded=intervals.map(([s,e])=>[Math.max(start,s-.3),Math.min(end,e+.3)]).filter(([s,e])=>e>s).sort((a,b)=>a[0]-b[0]);let total=0,last=-Infinity
 for(const [s,e] of padded){total+=Math.max(0,e-Math.max(s,last));last=Math.max(last,e)}
 return total/Math.max(.001,end-start)
}
export function energyAt(t:Track,start:number,end:number){let sum=0,weight=0;for(const e of t.energy){const w=Math.max(0,Math.min(end,e.end)-Math.max(start,e.start));sum+=w*e.value;weight+=w}return weight?sum/weight:NaN}
export type TimingGate=(a:Track,b:Track,cue:{start:number;end:number;window:Window;rate:number;duration:number})=>string|null
export function planNext(a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,budget=18,requireReady=true,timingGate?:TimingGate){
 const candidates:Plan[]=[];const rejected:{track:string;reason:string}[]=[];const reject=(t:Track,reason:string)=>rejected.push({track:t.title,reason});const ae=energyAt(a,position,position+8)
 const exclusions:{trackId:string;track:string;windowId?:string;code:string;reason:string;count:number;samples?:{mixStart:number;exit:number;evidence:ReturnType<typeof evaluateEvidence>}[]}[]=[]
 const exclude=(t:Track,code:string,reason:string,w?:Window)=>{const old=exclusions.find(x=>x.trackId===t.id&&x.windowId===w?.id&&x.code===code);if(old)old.count++;else exclusions.push({trackId:t.id,track:t.title,windowId:w?.id,code,reason,count:1})}
 if(!a.bars.length||a.vocals===null){exclude(a,'missing_source_evidence','当前曲目缺少拍点或人声依据');return {best:null,candidates,exclusions,rejected:[{track:a.title,reason:'当前曲目缺少拍点或人声依据'}]}}
 for(const b of tracks){
  if(b.id===a.id){exclude(b,'current_track','当前播放曲目不作为下一首');continue}
  if(intent.targetId&&b.id!==intent.targetId){exclude(b,'target_mismatch','不符合用户指定歌曲');continue}
   if(b.vocals===null){reject(b,'缺少人声区间');exclude(b,'missing_vocals','缺少人声区间');continue}
  let viable=false
  for(const w of b.windows){const asset=w.variants[a.id];if(!asset){exclude(b,'missing_variant','没有匹配当前歌曲速度的进入素材',w);continue};const d=asset.duration;const rate=asset.rate
   const prepared=ready.has(asset.url)&&ready.has(b.native.url)
   if(requireReady&&!prepared){exclude(b,'asset_not_ready',`素材未解码就绪：${[!ready.has(b.native.url)?'B 原曲':'',!ready.has(asset.url)?'B 进入片段':''].filter(Boolean).join('、')}`,w);continue}
   if(!Number.isFinite(d)||d<.5){exclude(b,'invalid_duration','交接素材时长必须有限且至少 0.5 秒',w);continue}
   if(!Number.isFinite(rate)||rate<.8||rate>1.2){exclude(b,'tempo_range',`变速比例 ${rate} 不在 0.8–1.2`,w);continue}
   if(b.duration-w.end<12){exclude(b,'body_too_short','进入窗口后正文不足 12 秒',w);continue}
   for(const out of a.bars){const start=out-d;if(start<position+.25){exclude(b,'start_too_soon','A 混入点已过或提前量不足 0.25 秒',w);continue}
    if(out>position+budget){exclude(b,'deadline','A 退出点超过本次剩余等待预算',w);continue}
    if(out>=a.duration-.1){exclude(b,'source_end','A 退出点过于接近素材结束',w);continue}
    const gridError=Math.min(...a.bars.map(x=>Math.abs(x-start)));if(gridError>.065){exclude(b,'grid_error','反推 A 混入点距原始首拍超过 65 ms',w);continue}
    const timingReason=timingGate?.(a,b,{start,end:out,window:w,rate,duration:d})
    if(timingReason){exclude(b,'local_beat_alignment',timingReason,w);continue}
    const evidence=evaluateEvidence(a,b,w,start,intent)
    if(!evidence.accepted){exclude(b,evidence.code,evidence.reason,w);const entry=exclusions.find(x=>x.trackId===b.id&&x.windowId===w.id&&x.code===evidence.code)!;(entry.samples||= []).push({mixStart:start,exit:out,evidence});continue}
    const av=vocalPresence(a.vocals,start,out),bv=vocalPresence(b.vocals,w.start,w.end)
    const midDuck=av*d>=.5&&av>=.05&&bv*(w.end-w.start)>=.5&&bv>=.05
    const boundary=Math.min(...a.sections.flatMap(s=>[Math.abs(s.start-out),Math.abs(s.end-out)]))<.4
    const section=a.sections.find(s=>s.start<=out&&s.end>out)?.label||'边界'
    const wait=out-position
    const score=1-wait/budget*.5-Math.abs(rate-1)*1.4-av*bv*.3+(boundary?.16:0)+(w.bars===4?.05:0)+(a.style===b.style?.04:0)
    candidates.push({id:`${a.id}:${b.id}:${w.id}:${out.toFixed(3)}`,from:a.id,to:b.id,window:w,asset,start,end:out,duration:d,restore:out-Math.min(d,120/a.bpm),rate,score,midDuck,aVocal:av,bVocal:bv,aEnergy:ae,bEnergy:w.energy,gridError,section,prepared,evidence,reason:`${boundary?'段落边界附近':'原始小节首拍'} · ${w.bars} 小节 · ${midDuck?'双窗口人声，中频 -5 dB':'无双窗口人声触发'} · ${prepared?'素材就绪':'需要准备素材'} · ${evidence.reason}`});const chosen=candidates[candidates.length-1];chosen.decision=explainPlan(a,b,chosen,position,intent,budget,boundary);viable=true
   }
  }
  if(!viable)reject(b,requireReady?'未就绪，或等待预算／局部风格／能量持续性／拍网格／窗口长度不满足':'等待预算／局部风格／能量持续性／拍网格／窗口长度不满足')
 }
 candidates.sort((x,y)=>y.score-x.score||x.end-y.end||x.id.localeCompare(y.id));return {best:candidates[0]||null,candidates,rejected,exclusions}
}
export class RequestGate{
 revision=0;locked=false;deferred:Intent|null=null
 replace(intent:Intent){if(this.locked){this.deferred=intent;return null}return ++this.revision}
 isCurrent(token:number|null){return token!==null&&token===this.revision}
 reset(){this.revision++;this.locked=false;this.deferred=null}
}
