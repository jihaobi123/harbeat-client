import {planNext as original} from './baseline/planner'
import {vocalPresence,energyAt,type Track,type Plan,type Asset} from '../realtime/planner'
import {explainPlan} from '../realtime/decision'
const defaults={vocalPenalty:.3,boundaryBonus:.16,horizonSec:18,waitScaleSec:18,midDb:-5}
export const experiments={
 baseline:{...defaults,title:'V3 实时基线',change:'冻结旧规划规则；不使用能量、风格目标'},
 vocal:{...defaults,vocalPenalty:.6,title:'① 人声避让',change:'只把人声排序扣分系数从 0.3 提高到 0.6'},
 boundary:{...defaults,boundaryBonus:.30,title:'② 乐段完整性',change:'只把段落边界奖励从 0.16 提高到 0.30'},
 horizon:{...defaults,horizonSec:30,title:'③ 等待范围',change:'只把可搜索范围从 18 秒扩大到 30 秒；等待扣分仍按 18 秒计算'},
 eq:{...defaults,midDb:-8,title:'④ 固定选点 · EQ',change:'固定曲对和全部选点；只把 B 中频衰减从 -5 改为 -8 dB'},
 material:{...defaults,title:'⑤ 固定时长 · 进入片段',change:'固定 A 进出点、时长、速度和 EQ；B 从另一段同长素材进入，随后续播对应正文'},
 length:{...defaults,title:'⑥ 固定交接点 · 转场长度',change:'固定 A 退出与 B 正文接管点、变速比例、EQ 深度；重叠由 4 小节缩短到 2 小节'},
} as const
export type TrialId=keyof typeof experiments
export type RankingId='baseline'|'vocal'|'boundary'|'horizon'
export function allReady(tracks:Track[]){return new Set(tracks.flatMap(t=>[t.native.url,...t.windows.flatMap(w=>Object.values(w.variants).map(a=>a.url))]))}
export function planTrial(a:Track,tracks:Track[],position:number,id:RankingId,targetId?:string){
 const cfg=experiments[id],intent={kind:'next' as const,...(targetId?{targetId}:{})}
 const result=original(a,tracks,position,intent,allReady(tracks),cfg.horizonSec)
 const candidates=result.candidates.map(raw=>{
  const p=raw as Plan,wait=p.end-position,boundary=p.decision!.score.components.find(c=>c.key==='boundary')!.value
  p.score+=-(cfg.vocalPenalty-.3)*p.aVocal*p.bVocal+(cfg.boundaryBonus-.16)*boundary+wait/cfg.horizonSec*.5-wait/cfg.waitScaleSec*.5
  // Exact baseline ordering retains original floating-point scores.
  if(id==='baseline')p.score=raw.decision!.score.total
  const d=p.decision!;d.policyVersion=`quality-trial-1:${id}`;d.pointReasons.unshift(cfg.change)
  for(const c of d.score.components){if(c.key==='vocal'){c.weight=-cfg.vocalPenalty;c.contribution=c.value*c.weight}if(c.key==='boundary'){c.weight=cfg.boundaryBonus;c.contribution=c.value*c.weight}if(c.key==='waiting'){c.value=wait/cfg.waitScaleSec;c.contribution=-c.value*.5;c.label='等待秒数 / 固定18秒标尺'}}
  d.score.total=p.score;return p
 }).sort((a,b)=>b.score-a.score||a.end-b.end||a.id.localeCompare(b.id))
 return {...result,candidates,best:candidates[0]||null}
}
export type LengthAsset={sourceTrackId:string;sourceMasterSha256:string;start:number;end:number;rate:number;asset:Asset}
export type FixedCase={id:string;aId:string;bId:string;position:number;windowId:string;end:number;alternateWindowId:string}
export function fixedTrial(tracks:Track[],id:'eq'|'material'|'length',lengthAsset?:LengthAsset,spec?:FixedCase){
 const a=tracks.find(t=>spec?t.id===spec.aId:t.title==='Big Girls'),b=tracks.find(t=>spec?t.id===spec.bId:t.title==='Cold');if(!a||!b)throw new Error('固定对照需要 Big Girls 和 Cold')
 const position=spec?.position??15
 const reference=planTrial(a,tracks,position,'baseline',b.id).candidates.find(p=>p.window.id===(spec?.windowId??'w0-4')&&Math.abs(p.end-(spec?.end??27.04))<.001)
 if(!reference)throw new Error('固定对照的原始窗口缺失，不能替换为别的选点')
 const baseline=JSON.parse(JSON.stringify(reference)) as Plan,variant=JSON.parse(JSON.stringify(reference)) as Plan
 if(id==='material'){
  const w=b.windows.find(w=>w.id===(spec?.alternateWindowId??'w16-4')),asset=w?.variants[a.id]
  if(!w||!asset||Math.abs(asset.duration-baseline.duration)>1/44100||Math.abs(asset.rate-baseline.rate)>1e-8)throw new Error('替换素材与基线时长或速度不一致')
  variant.window=w;variant.asset=asset
 }
 if(id==='length'){
  const x=lengthAsset
  if(!x||x.sourceTrackId!==b.id||x.sourceMasterSha256!==b.provenance?.masterSha256||Math.abs(x.end-baseline.window.end)>.001||Math.abs(x.start-(baseline.window.start+baseline.window.end)/2)>.001||Math.abs(x.rate-baseline.rate)>1e-8||Math.abs(x.asset.duration*2-baseline.duration)>2/44100)throw new Error('长度对照素材缺失或来源／映射不一致')
  variant.asset=x.asset;variant.window={...baseline.window,id:'fixed-tail-2',start:x.start,end:x.end,bars:2,variants:{[a.id]:{...x.asset,rate:x.rate}}};variant.duration=x.asset.duration;variant.start=variant.end-variant.duration
  if(variant.start<position+.25||Math.min(...a.bars.map(v=>Math.abs(v-variant.start)))>.065)throw new Error('缩短窗口无法在同一请求时刻按拍执行')
 }
 for(const [label,p] of [['baseline',baseline],['variant',variant]] as const){
  p.id+=`:fixed-${id}-${label}`;p.score=0;p.restore=p.end-Math.min(p.duration,120/a.bpm);p.aVocal=vocalPresence(a.vocals!,p.start,p.end);p.bVocal=vocalPresence(b.vocals!,p.window.start,p.window.end);p.bEnergy=energyAt(b,p.window.end,p.window.end+16);p.gridError=Math.min(...a.bars.map(v=>Math.abs(v-p.start)))
  p.decision=explainPlan(a,b,p,position,{kind:'next',targetId:b.id},18,true);p.decision.policyVersion=`quality-fixed-1:${id}:${label}`;p.decision.pointReasons=['固定对照使用基线可执行候选，不是普通下一首的最高分结果。',label==='baseline'?'固定曲对参照：4 小节窗口，原 EQ。':experiments[id].change]
  p.decision.score={total:0,components:[],interpretation:'固定选点试验，不参与候选排序；这里的 0 不是音质评分',tieBreak:'不适用'}
  p.decision.strategy.selectionReason='固定曲对实验；除指定变量及其必然时间／素材变化外，沿用同一 V3 声音处理。'
  p.decision.strategy.midDuck.bMidDb=p.midDuck?(id==='eq'&&label==='variant'?-8:-5):0
  p.decision.strategy.midDuck.reason='沿用参照的人声触发决定以固定其他变量；该值不表示人声冲突已经解决。'
 }
 return {a,b,position,baseline,variant}
}
