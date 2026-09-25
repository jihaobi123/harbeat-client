import {planV31} from '../v31-release/release'
import type {Plan,Track} from '../realtime/planner'
import {sourceBound} from '../v30/planner'
import {buildV30Eq} from '../v30/eq'
import {alignedVocalOverlap,type OverlapMeasure} from './score'
export const OVERLAP_POLICY_VERSION = 'vocal-overlap-v1'
export type VocalOverlapEvidence = OverlapMeasure & {
  version:string;baselinePlanId:string;baselineStart:number;baselineEnd:number;oldScore:number;newScore:number;
  oldVocalProduct:number;shiftSec:number;originalCandidateCount:number;timingCandidateCount:number;
  anchor:{to:string;windowId:string;assetSha256:string;rate:number;duration:number};
}
export type OverlapPlan = Plan & {vocalOverlap:VocalOverlapEvidence}
function requireBoundVocals(t:Track) {
  const snapshot=t.preprocessing,vad=snapshot?.vocalActivity,source=vad?.source as Record<string,unknown>|undefined
  if (!sourceBound(t) || !snapshot || snapshot.reportId!==t.reportId ||
      t.alignment?.source.reportId!==t.reportId || snapshot.reportSha256!==t.provenance?.reportSha256 ||
      snapshot.masterSha256!==t.provenance?.masterSha256 ||
      snapshot.bindingChecks?.reportHash!==true || snapshot.bindingChecks?.masterHash!==true ||
      Object.values(snapshot.bindingChecks).some(v=>v!==true) ||
      vad?.status!=='ready' || vad.time_origin!=='master_audio_start' || vad.unit!=='ms' ||
      source?.track_id!==t.id || !t.provenance?.runId || source?.analysis_run_id!==t.provenance.runId ||
      source?.vocal_sha256!==t.provenance?.vocalSha256 || !Array.isArray(t.vocals) ||
      !Array.isArray(vad.intervals) || t.vocals.length!==vad.intervals.length ||
      t.vocals.some(([s,e],i)=>Math.abs(s-vad.intervals[i].start_ms/1000)>1e-9 ||
        Math.abs(e-vad.intervals[i].end_ms/1000)>1e-9 ||
        !Number.isFinite(vad.intervals[i].start_ms) || !Number.isFinite(vad.intervals[i].end_ms)))
    throw Error(t.title+' 人声区间与绑定的原始报告不一致或尚未就绪')
}
export const planVocalOverlap:typeof planV31 = (a,tracks,position,intent,ready,budget=18,requireReady=true,timingGate) => {
  let original:ReturnType<typeof planV31>
  try {original = planV31(a,tracks,position,intent,ready,budget,requireReady,timingGate)}
  catch(error){return {best:null,candidates:[],rejected:[],exclusions:[{trackId:a.id,track:a.title,
    code:'vocal_overlap_unavailable',reason:'人声选点实验的基础证据无效：'+(error as Error).message,count:1}]}}
  const baseline = original.best
  if (!baseline) return original
  const b = tracks.find(t=>t.id===baseline.to)!
  const sameMaterial = original.candidates.filter(p =>
    p.to===baseline.to && p.window.id===baseline.window.id &&
    p.window.start===baseline.window.start && p.window.end===baseline.window.end &&
    p.asset.sha256===baseline.asset.sha256 && p.asset.url===baseline.asset.url &&
    p.rate===baseline.rate && p.duration===baseline.duration)
  const exclusions = [...original.exclusions]
  const excluded = original.candidates.length-sameMaterial.length
  if (excluded) exclusions.push({trackId:b.id,track:b.title,code:'controlled_material',
    reason:'固定正式 V3.1 选中的 B 片段、变速和完整重叠时长；其余素材不参与本次选点对照',count:excluded})
  try {
    requireBoundVocals(a);requireBoundVocals(b)
    const candidates:OverlapPlan[] = sameMaterial.map(p => {
      const measure = alignedVocalOverlap(a.vocals,b.vocals,
        {aStart:p.start,bStart:p.window.start,bEnd:p.window.end,duration:p.duration,rate:p.rate})
      const oldVocalProduct = p.aVocal*p.bVocal
      const score = p.score+.3*(oldVocalProduct-measure.weightedOverlap)
      const decision = p.decision ? {...p.decision,policyVersion:OVERLAP_POLICY_VERSION,
        score:{...p.decision.score,total:score,components:p.decision.score.components.map(c=>c.key==='vocal' ?
          {...c,label:'对齐后按渐变音量加权的同时人声',value:measure.weightedOverlap,contribution:-.3*measure.weightedOverlap}:c)},
        strategy:{...p.decision.strategy,id:'vocal_overlap_v30_dynamic_eq',selectionReason:'固定正式版 B 片段与重叠时长，只替换人声评分来比较 A 的可执行交接位置。',
          eq:{...p.decision.strategy.eq,lowReason:'此处是 V3 基础模板；实际低频控制点见 v30Eq，沿用正式版动态 EQ 规则。',highReason:'此处是 V3 基础模板；实际高频控制点见 v30Eq。'},
          limitations:p.decision.strategy.limitations.map(s=>s.startsWith('人声判断')?'中频模板触发仍沿用各自窗口占比；选点人声项改为对齐后同时活动的渐变加权积分。':s)},
      } : undefined
      return {...p,score,decision,reason:p.reason+' · 同步人声冲突 '+(100*measure.weightedOverlap).toFixed(1)+'%（渐变加权代理）',
        vocalOverlap:{...measure,version:OVERLAP_POLICY_VERSION,
          baselinePlanId:baseline.id,baselineStart:baseline.start,baselineEnd:baseline.end,
          oldScore:p.score,newScore:score,oldVocalProduct,shiftSec:p.start-baseline.start,
          originalCandidateCount:original.candidates.length,timingCandidateCount:sameMaterial.length,
          anchor:{to:baseline.to,windowId:baseline.window.id,assetSha256:baseline.asset.sha256,rate:baseline.rate,duration:baseline.duration}}}
    })
    candidates.sort((x,y)=>y.score-x.score || x.end-y.end || x.id.localeCompare(y.id))
    const chosen = candidates[0]
    const best:OverlapPlan = {...chosen,v30Eq:buildV30Eq(a,b,chosen)}
    return {...original,best,candidates,exclusions}
  } catch (error) {
    return {...original,best:null,candidates:[],exclusions:[...exclusions,
      {trackId:b.id,track:b.title,code:'vocal_overlap_unavailable',reason:'人声选点实验不可用：'+(error as Error).message,count:1}]}
  }
}
