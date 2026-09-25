import {planNext,type Track,type Intent,type Plan} from '../realtime/planner'
import {localBeatGate} from './beatAlignment'
import {requireBoundVocals} from '../vocal-overlap/planner'
import {alignedVocalOverlap} from '../vocal-overlap/score'
import {buildV30Eq} from '../v30/eq'
import {nativeSegment} from './segments'
export const AUTOMATIC_POLICY='continuous-auto-quality-v1'
export type AutomaticPlanner=(a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,requireReady?:boolean)=>ReturnType<typeof planNext>&{planningPosition:number}

// Source-bound acoustic proxies, not calibrated perceptual loudness or LUFS.
function level(t:Track,start:number,end:number){
 let cursor=start,total=0,rms=0,low=0
 for(const f of t.alignment!.bandFrames){
  const s=Math.max(start,f.start),e=Math.min(end,f.end);if(e<=s)continue
  if(Math.abs(s-cursor)>.005)throw Error('频段证据不连续')
  if([f.rmsDbfs,f.low].some(v=>v!==null&&!Number.isFinite(v)))throw Error('频段证据无效')
  rms+=(e-s)*(f.rmsDbfs===null?0:10**(f.rmsDbfs/10));low+=(e-s)*(f.low===null?0:10**(f.low/10));total+=e-s;cursor=e
 }
 if(total<end-start-.005||total<=0)throw Error('频段证据不完整')
 return {rms:10*Math.log10(rms/total+1e-12),low:10*Math.log10(low/total+1e-12)}
}
const near=(t:Track,time:number)=>t.sections.some(s=>Math.min(Math.abs(s.start-time),Math.abs(s.end-time))<.4)
export const planAutomaticQuality:AutomaticPlanner=(a,tracks,position,intent,ready,requireReady=false)=>{
 const last=a.bars.filter(t=>t<a.duration-.1).at(-1)??a.duration-.1
 const budget=Math.max(0,last-position+.0001)
 const exclusions:ReturnType<typeof planNext>['exclusions']=[]
 const exclude=(t:Track,code:string,error:unknown)=>exclusions.push({trackId:t.id,track:t.title,code,reason:String(error),count:1})
 try{requireBoundVocals(a)}catch(error){exclude(a,'vocal_overlap_unavailable',error);return {best:null,candidates:[],rejected:[],exclusions,planningPosition:position}}
 const bound=tracks.filter(b=>{if(b.id===a.id||intent.targetId&&b.id!==intent.targetId)return false;try{requireBoundVocals(b);return true}catch(error){exclude(b,'vocal_overlap_unavailable',error);return false}})
 const raw=planNext(a,bound,position,intent,ready,budget,requireReady,(a,b,cue)=>{
  if(cue.end<last*.5)return '自动续播至少保留一半实测音乐'
  const prepared=[b.native.url,cue.window.variants[a.id]?.url,nativeSegment(b,cue.window.end).asset.url].every(url=>ready.has(url))
  if(cue.start<position+(prepared?.25:12))return '完整素材准备提前量不足'
  return localBeatGate(a,b,cue)
 })
 exclusions.push(...raw.exclusions)
 const levels=new Map<string,ReturnType<typeof level>>()
 const sample=(t:Track,s:number,e:number)=>{const key=`${t.id}:${s}:${e}`;let v=levels.get(key);if(!v){v=level(t,s,e);levels.set(key,v)}return v}
 const candidates:Plan[]=[]
 for(const p of raw.candidates){const b=bound.find(t=>t.id===p.to)!
  try{
   const measure=alignedVocalOverlap(a.vocals!,b.vocals!,{aStart:p.start,bStart:p.window.start,bEnd:p.window.end,duration:p.duration,rate:p.rate})
   const al=sample(a,p.start,p.end),bl=sample(b,p.window.start,p.window.end)
   const phraseCut=a.alignment!.phrases.some(x=>x.start<p.end&&x.tailEnd>p.end)
   const incomingCut=b.alignment!.phrases.some(x=>x.start<p.window.start&&x.tailEnd>p.window.start)
   const components=p.decision!.score.components.map(c=>c.key==='waiting'?{...c,label:'自动续播不惩罚等待',value:0,contribution:0}:c.key==='vocal'?{...c,label:'对齐后按渐变音量加权的同时人声',value:measure.weightedOverlap,contribution:-.3*measure.weightedOverlap}:c)
   for(const [key,label,value,weight] of [
    ['incomingBoundary','B 进入点靠近段落边界',near(b,p.window.start)?1:0,.08],
    ['phraseCut','声学人声活动中途退出或进入',Number(phraseCut)+Number(incomingCut),-.08],
    ['levelChange','原始 RMS 连续性代理',Math.min(1,Math.abs(al.rms-bl.rms)/12),-.1],
    ['bassChange','原始低频连续性代理',Math.min(1,Math.abs(al.low-bl.low)/12),-.08],
    ['retention','剩余实测音乐比例',(last-p.end)/last,-.12],
   ] as const)components.push({key,label,value,weight,contribution:value*weight})
   const score=components.reduce((sum,c)=>sum+c.contribution,0)
   candidates.push({...p,score,decision:{...p.decision!,policyVersion:AUTOMATIC_POLICY,score:{...p.decision!.score,total:score,components,tieBreak:'分数降序；同分保留更多当前歌曲；再按 ID'},strategy:{...p.decision!.strategy,id:'automatic_quality_v30_dynamic_eq',selectionReason:'比较候选歌曲、全部进入窗口和后段退出点；沿用已认可完整渐进交接与动态 EQ。'}},reason:p.reason+' · 自动择优；同步人声 '+(100*measure.weightedOverlap).toFixed(1)+'%'})
  }catch(error){exclude(b,'automatic_evidence_unavailable',error)}
 }
 candidates.sort((x,y)=>y.score-x.score||y.end-x.end||x.id.localeCompare(y.id))
 // Prefer the last 35%; expand only if no fully validated choice survives.
 for(const floor of [.65,.5]){
  const region=candidates.filter(p=>p.end>=last*floor)
  for(const p of region){try{const best={...p,v30Eq:buildV30Eq(a,bound.find(t=>t.id===p.to)!,p)};return {...raw,best,candidates:region,exclusions,planningPosition:position}}catch(error){exclude(bound.find(t=>t.id===p.to)!,'v30_eq_unavailable',error);candidates.splice(candidates.indexOf(p),1)}}
 }
 return {...raw,best:null,candidates:[],exclusions,planningPosition:position}
}
