import type {Plan,Track} from './planner'
export type PreprocessingEvidence={
 schema:string;reportId:string;reportSha256:string;masterSha256:string;reportSnapshotUrl:string;
 bindingChecks:Record<string,boolean>;sections:{source?:string;version?:string;items:{start_ms:number;end_ms:number;label:string;confidence?:number|null}[]};
 beatGrid:{bars_ms:number[];beats_ms:number[];needs_review?:boolean;[key:string]:unknown};tempo:Record<string,unknown>;
 vocalActivity:{intervals:{start_ms:number;end_ms:number}[];producer?:Record<string,any>;needs_review?:boolean;[key:string]:unknown};
 vocalRms:{points:{start:number;end:number;rms_dbfs:number|null}[];[key:string]:unknown};energy:Record<string,unknown>;genre:Record<string,unknown>;
 extensions:{name:string;status:string;path:string}[];
}
const CORE='/documents/core/analysis'
function union(intervals:number[][]){const out:number[][]=[];for(const [s,e] of intervals.map(x=>[...x]).sort((a,b)=>a[0]-b[0])){const last=out.at(-1);if(last&&s<=last[1])last[1]=Math.max(last[1],e);else out.push([s,e])}return out}
function trackTrace(t:Track,start:number,end:number,cut:number,acoustic?:any){
 const e=t.preprocessing, bound=!!e&&e.reportId===t.reportId&&e.masterSha256===t.provenance?.masterSha256&&e.reportSha256===t.provenance?.reportSha256&&Object.values(e.bindingChecks).every(Boolean)
 // Synthetic/legacy fixtures may lack provenance. Never silently claim those snapshots match.
 const source=bound?e:undefined
 const sections=t.sections.map((s,i)=>({...s,runtimeRow:i+1,sourceRows:(source?.sections.items||[]).flatMap((r,j)=>r.end_ms/1000>s.start+.00001&&r.start_ms/1000<s.end-.00001?[{row:j+1,path:`${CORE}/sections/items/${j}`,...r}]:[])})).filter(s=>s.end>=start&&s.start<=end)
 const rows=(t.vocals||[]).flatMap(([s,f],i)=>{const lo=Math.max(start,s-.3),hi=Math.min(end,f+.3);if(hi<=lo)return [];const j=source?.vocalActivity.intervals.findIndex(r=>Math.abs(r.start_ms/1000-s)<.00001&&Math.abs(r.end_ms/1000-f)<.00001)??-1;return [{runtimeRow:i+1,sourceRow:j<0?null:j+1,path:j<0?null:`/documents/vocal_activity/intervals/${j}`,raw:[s,f],padded:[s-.3,f+.3],clipped:[lo,hi]}]})
 const merged=union(rows.map(r=>r.clipped)),unionSec=merged.reduce((n,[s,f])=>n+f-s,0)
 const cues=[{name:'混入',sec:start},{name:'退出／接管',sec:cut}].map(c=>{const nearest=t.bars.map((sec,i)=>({sec,runtimeRow:i+1,distanceSec:Math.abs(sec-c.sec)})).sort((a,b)=>a.distanceSec-b.distanceSec)[0];const raw=source?.beatGrid.bars_ms.findIndex(v=>nearest&&Math.abs(v/1000-nearest.sec)<.00001)??-1,beat=source?.beatGrid.beats_ms.findIndex(v=>nearest&&Math.abs(v/1000-nearest.sec)<.00001)??-1;return {...c,nearest:nearest||null,sourceRow:raw>=0?raw+1:null,beatRow:beat>=0?beat+1:null,path:raw>=0?`${CORE}/beat_grid/bars_ms/${raw}`:beat>=0?`${CORE}/beat_grid/beats_ms/${beat}`:null,gridBasis:raw>=0?'原始小节候选':beat>=0?'来自原始拍点，按相位补出的前奏网格；非已确认小节':'未找到原始对应行'}})
 const nextInterval=(t.vocals||[]).map(([s,f],i)=>({start:s,end:f,runtimeRow:i+1})).find(r=>r.end>cut)||null
 const quietRows=acoustic?(source?.vocalRms.points||[]).flatMap((r,i)=>r.end>acoustic.quietStart&&r.start<acoustic.quietEnd?[{row:i+1,path:`/extensions/dj_signals/data/vocals/points/${i}`,...r}]:[]):[]
 return {id:t.id,title:t.title,reportId:t.reportId,reportSha256:t.provenance?.reportSha256,masterSha256:t.provenance?.masterSha256,binding:bound?'verified_snapshot':e?'snapshot_mismatch':'missing_snapshot',snapshotUrl:bound?e.reportSnapshotUrl:null,sourceWindow:[start,end],sections,cues,
  vocals:{available:t.vocals!==null,model:source?.vocalActivity.producer||null,source:source?.vocalActivity.source||null,modelProbability:null,probabilityReason:'当前报告没有保存逐帧人声概率。检测阈值与时间占比均不能当作概率。',paddingSec:.3,rows,merged,unionSec,fraction:t.vocals===null?null:unionSec/Math.max(.001,end-start),presenceThreshold:{fraction:.05,unionSec:.5},nextInterval,activeAtCut:(t.vocals||[]).some(([s,f])=>s<=cut&&f>cut)},
  acoustic:acoustic?{evidence:acoustic,sourceAsset:source?.vocalRms.asset||null,sourceAlgorithm:source?.vocalRms.source||null,rows:quietRows,sourcePath:'/extensions/dj_signals/data/vocals/points',note:'分离人声 RMS，低能量是自动声学代理；不能证明歌词语义句末'}:null,
  runtime:{bpm:t.bpm,style:t.style,styleScore:t.styleScore,native:t.native},sourceTempo:source?.tempo||null,sourceGenre:source?.genre||null,availableExtensions:source?.extensions||[]}
}
export function buildDecisionTrace(a:Track,b:Track,p:Plan,midDb=-5){
 const protection=(p as Plan&{protection?:any}).protection||null,protectedMode=!!protection,mode=protection?.automaticExit?'protected-auto':protectedMode?'protected-manual':'v3-ranking'
 const weight=(key:string,fallback:number)=>p.decision?.score.components.find(c=>c.key===key)?.weight??fallback
 const nominalTargetSec=p.window.bars*240/a.bpm, derivedRate=(p.window.end-p.window.start)/nominalTargetSec
 const features=[
  {key:'sections',name:'段落起止与标签',source:`${CORE}/sections/items`,effect:protectedMode?'硬约束：合并相邻同标签段落，A 在段尾后通过核验的点退出；B 入口不得跨段':`排序：A 退出距任意段落起止 <0.4 秒加 ${weight('boundary',.16)}；没有“必须播完段落”的硬约束`},
  {key:'beats',name:'拍点、小节候选',source:`${CORE}/beat_grid`,effect:'决定候选退出与反推混入；A 混入与网格偏差必须 ≤65 ms。网格行号不等于人工确认的小节编号'},
  {key:'tempo',name:'BPM 与变速素材',source:`${CORE}/tempo`,effect:`只接收已有对应 A 速度的 B 片段；rate=${p.rate.toFixed(6)}，范围 0.8–1.2；预制时按窗口小节数×240÷A的BPM确定目标秒数，再以B窗口原长÷目标秒数得到rate。实时使用素材记录，并不直接用两首整曲BPM相除`},
  {key:'vocals',name:'人声活动区间',source:'/documents/vocal_activity/intervals',effect:protectedMode?'硬约束：自动模式 B 入口至正文后 0.1 秒不得有未扩展 VAD 区间；A 用声学间隙保护。扩展占比仅记录，不参与排名或触发中频衰减':`排序项 ${weight('vocal',-.3)}×A占比×B占比；两侧均满足占比≥5%且并集≥0.5秒时，B 中频衰减。不是逐帧冲突或歌词检测`},
  {key:'rms',name:'分离人声 RMS',source:'/extensions/dj_signals/data/vocals/points',effect:mode==='protected-auto'?'硬约束：完整 B 入口与 A 精确退出点通过 ≤−32 dBFS 的声学间隙；实际阈值和帧见下方':mode==='protected-manual'?'不作为自动放行；使用精确点与素材的人工核验记录':'此版本未用于选点'},
  {key:'style',name:'整曲风格候选',source:'/extensions/genre/data/top',effect:protectedMode?'未参与保护版选点':`A、B 标签相同加 ${weight('style',.04)}；模型原始分数仅展示，不是混音成功率`},
  {key:'energy',name:'能量与局部风格',source:`${CORE}/energy`,effect:p.evidence?`局部条件结果：${p.evidence.reason}；旧相对能量值仅记录`:'此保护请求未用于筛选或排名'},
  {key:'unused',name:'调性、和弦、鼓组、乐器、情绪、粗糙度、动态范围',source:'/documents/core/analysis + /extensions',effect:'未用于本次固定 EQ 模板或转场排名；是否已分析见快照模块清单，不能把未使用误认为没有分析'},
 ]
 const result={v30Tune:p.v30Tune||null,v30Eq:p.v30Eq||null,schema:'harbeat.decision-trace.v1',planId:p.id,mode,features,a:trackTrace(a,p.start,p.end,p.end,protection?.automaticExit),b:trackTrace(b,p.window.start,p.window.end,p.window.end,protection?.automaticEntry),protection,
  strategy:{id:'v3_linear_eq',multipleAlgorithmsCompared:false,reason:p.decision?.strategy.selectionReason||'固定 V3 模板，搜索选点而非比较多种音效',actualBMidDb:(p.midDuck?midDb:0) as number|null,selection:p.decision?.score,automation:p.decision?.strategy,
   facts:[`转场 ${p.window.bars} 个候选小节，共 ${p.duration.toFixed(3)} 秒。`,`B 进入速率 ${p.rate.toFixed(6)}，接管后变为 1.0，原曲 BPM ${b.bpm}；目前没有渐进回速。`,`A 在混入点启用低频 −9 dB、高频 −1.4 dB，滤波声在 20 ms 内启用。`,`B 低频 −7 dB、高频 +1.2 dB、中频 ${p.midDuck?midDb:0} dB；最后 ${Math.min(p.duration,120/a.bpm).toFixed(3)} 秒恢复原声。`,...(protection?.sectionTailDelaySec!=null?[`A 比模型段尾晚 ${protection.sectionTailDelaySec.toFixed(3)} 秒退出；因此可能包含下一模型段落开头。`]:[])],interpretation:'以上是实际参数，可用于逐项试听定位；不能单凭数值认定听感问题的原因。'},
  material:{a:a.native,b:b.native,entry:p.asset,window:p.window,tempoPreparation:{beatsPerBar:4,bars:p.window.bars,aBpm:a.bpm,bNativeBpm:b.bpm,nominalTargetSec,derivedRate,assetRate:p.rate,rateMatchesRecipe:Math.abs(derivedRate-p.rate)<1e-6,actualAssetSec:p.asset.duration,formula:'targetSec = bars × 240 / A_BPM; rate = B_source_window_seconds / targetSec; actual duration includes sample rounding'},sourceMapping:{bStart:p.window.start,bEnd:p.window.end,rate:p.rate,overlapSec:p.duration,aStart:p.start,aEnd:p.end,restore:p.restore},lane:protection?.entry?.lane||'original_master'},
  limitations:['人声时间占比不是概率；模型区间不等于语义乐句','原始报告行号从 1 开始展示，JSON 路径从 0 开始','快照仅供追溯，不反向修改选点或音频处理']}
 if(p.phrase){
  result.mode='phrase-'+(p.automation?.kind||'planned')
  result.features=[{key:'phrase',name:'声学乐句与尾音',source:'/alignment/phrases + /alignment/exits',effect:'联合原始 VAD 与分离人声活动；尾音结束后才开始降低 A 增益。不将候选当作语义句末'}, {key:'beat',name:'最后一拍与下一小节首拍',source:'/alignment/bars',effect:'分列观察拍点；退出不早于保护尾音，且不能进入下一句'}, {key:'energy',name:'低中高频功率',source:'/alignment/bandFrames',effect:p.automation?.kind==='adaptive'?'按源时间映射计算预测叠加功率，逐步限幅衰减 B 的频段；完整取样行和自动化保存在日志':'本次为固定 EQ 对照；能量只展示，不改变选点或 EQ'}]
  result.strategy.id='phrase_'+(p.automation?.kind||'planned')
  result.strategy.actualBMidDb=0
  result.strategy.facts=[`A 保持到原曲 ${p.phrase.fadeStart.toFixed(3)} 秒，之后才退出。`,`小节最后一拍 ${p.phrase.exit.lastBeat.toFixed(3)} 秒，退出首拍 ${p.end.toFixed(3)} 秒。`,`B 首句映射到 A 时轴 ${p.phrase.incomingVocalRender.toFixed(3)} 秒，距保护尾音 ${p.phrase.vocalGap.toFixed(3)} 秒。`,p.automation?.kind==='adaptive'?'B 频段衰减由局部功率计算；此处中频起始值不是全程固定值。':'使用原 EQ 参数，A 的 EQ 在保护尾音之后才启用。','正文接管仍恢复原速；本轮未改变时间伸缩策略。']
  Object.assign(result,{phrase:p.phrase,actualAutomation:p.automation})
  result.strategy.interpretation='声学候选、具体控制点与实测来源分开记录；不等同于人工听感验收'
 }
 if(p.v30Tune){
  result.features.find(f=>f.key==='rms')!.effect=p.v30Tune.enabled?'通过保守声学活动与拍点做相邻小节核验；存在分歧或无明确改善时保留原 V3':'展示声学核验；选点仍由原 V3 决定'
  result.mode='v30-small-'+(p.v30Eq?'dynamic':'fixed')
  result.features.push({key:'v30_boundary',name:'小幅边界核验',source:'/alignment/phrases + /alignment/bars',effect:p.v30Tune.reason})
  result.strategy.id='v30_'+(p.v30Eq?'dynamic_eq':'fixed_eq')
  result.strategy.reason=p.v30Tune.reason
  result.strategy.facts=[`完整重叠 ${p.duration.toFixed(3)} 秒；A 从起点到终点线性退出，B 同时线性进入。`,`相对原 V3 整体后移 ${p.v30Tune.shiftSec.toFixed(3)} 秒；B 素材、变速及等待上限保持不变。`,p.v30Eq?'EQ 在 V3 模板附近随源频段功率变化：低/高最多 3 dB，中频最多 2 dB，每秒最多改变 3 dB。':'沿用 V3 固定 EQ。',`B 在最后 ${Math.min(p.duration,120/a.bpm).toFixed(3)} 秒沿用原干湿曲线恢复原声。`]
  if(p.v30Eq){result.strategy.actualBMidDb=null;result.features.push({key:'v30_eq',name:'局部频段功率与同步人声',source:'/alignment/bandFrames + /alignment/phrases',effect:'只改变 EQ 系数，不改变选点、增益或时长；每个控制点含 A/B 源时间与原始帧行号'});result.strategy.automation=undefined}
  Object.assign(result,{v30Tune:p.v30Tune,v30Eq:p.v30Eq||null})
  result.limitations.push('边界只做声学核验，未新增语义歌词识别；段落标签仍为模型候选')
 }
 return result
}
export type DecisionTrace=ReturnType<typeof buildDecisionTrace>
