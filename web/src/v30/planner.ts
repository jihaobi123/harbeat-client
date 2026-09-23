import {planNext,type Track} from '../realtime/planner'
import type {ExitAssessment,V30Tune} from './types'
import {buildV30Eq} from './eq'
export function sourceBound(t:Track){const s=t.alignment?.source,p=t.provenance;return !!s&&!!p&&['masterSha256','reportSha256','vocalSha256'].every(k=>!!(s as any)[k]&&(s as any)[k]===p[k])}
export function assessExit(a:Track,end:number):ExitAssessment{
 const bound=sourceBound(a),bar=bound?a.alignment?.bars.find(b=>Math.abs(b.end-end)<.065):undefined
 const gridValid=!!bar?.valid&&bar.beats.length===4&&bar.lastBeat!==null&&bar.lastBeat<end
 const phrase=bound?a.alignment?.phrases.find(p=>p.start<end&&p.tailEnd>end):undefined
 const conflicts=bound?(a.alignment?.conflicts||[]).filter(c=>Number.isFinite(c.start)&&Number.isFinite(c.end)&&c.start<end+.25&&c.end>end-.25):[]
 const distances=a.sections.map(s=>Math.abs(s.end-end)).filter(Number.isFinite)
 return {sourceBound:bound,gridValid,lastBeat:bar?.lastBeat??null,nextDownbeat:end,sectionDistance:distances.length?Math.min(...distances):null,activePhraseId:phrase?.id??null,tailRemaining:phrase?phrase.tailEnd-end:0,sourceRows:phrase?.sourceRows??null,conflicts,reason:!bound?'预处理指纹缺失或不一致；保持 V3':!gridValid?'缺少完整实测小节；保持 V3':conflicts.length?'退出点附近的声学证据有分歧；保持 V3':phrase?'退出时仍有声学人声活动':'退出点未落在已检出的声学人声活动内（语义句尾待确认）'}
}
export function makeV30Planner(adjust:boolean,eq:'fixed'|'dynamic'):typeof planNext{return (a,tracks,pos,intent,ready,budget=18,requireReady=true)=>{
 const result=planNext(a,tracks,pos,intent,ready,budget,requireReady),original=result.best
 if(!original)return result
 const before=assessExit(a,original.end),next=a.bars.find(t=>t>original.end+.065)
 const possible=next===undefined?undefined:result.candidates.find(c=>c.to===original.to&&c.window.id===original.window.id&&c.asset.sha256===original.asset.sha256&&Math.abs(c.end-next)<.001&&Math.abs(c.duration-original.duration)<1e-6)
 const afterNext=next===undefined?undefined:assessExit(a,next)
 // Original V3 eligibility controls the budget and material; only the adjacent exit is considered.
 const improves=!!afterNext&&before.sourceBound&&before.gridValid&&afterNext.gridValid&&!before.conflicts.length&&!afterNext.conflicts.length&&((!!before.activePhraseId&&!afterNext.activePhraseId)||(!before.activePhraseId&&!afterNext.activePhraseId&&(before.sectionDistance??0)>.4&&(afterNext.sectionDistance??Infinity)<.4))
 let chosen=adjust&&possible&&improves?possible:original
 const after=assessExit(a,chosen.end)
 const reason=!adjust?'原 V3 选点；仅展示边界核验':chosen!==original?'整体后移到相邻实测小节，降低句中退出或段落错位风险；混合时长保持不变':!before.sourceBound||!before.gridValid||before.conflicts.length?before.reason:afterNext?.conflicts.length?afterNext.reason:!possible?'相邻小节不在原 V3 可执行候选内；保持原选点':'相邻小节没有明确改善；保持原选点'
 const tune:V30Tune={version:'v30-small-correction-v1',enabled:adjust,originalPlanId:original.id,originalStart:original.start,originalEnd:original.end,shiftSec:chosen.end-original.end,before,after,reason,considered:afterNext?[{end:next!,eligible:!!possible,assessment:afterNext}]:[],preserved:{duration:original.duration,assetSha256:original.asset.sha256,windowId:original.window.id,rate:original.rate,gain:'V3 full-overlap linear',budget}}
 chosen={...chosen,v30Tune:tune,reason:chosen.reason+' · '+reason}
 if(eq==='dynamic')try{chosen.v30Eq=buildV30Eq(a,tracks.find(t=>t.id===chosen.to)!,chosen)}catch(e){return {...result,best:null,exclusions:[...result.exclusions,{trackId:a.id,track:a.title,code:'v30_eq_unavailable',reason:'动态 EQ 证据不可用：'+(e as Error).message,count:1}]}}
 return {...result,best:chosen}
}}
