import type {Track, Plan, Intent} from './planner'

export const DECISION_POLICY = {
  version: 'v3-live-rules-1.audit-1',
  minimumLeadSec: .25, maximumGridErrorSec: .065, boundaryRadiusSec: .4,
  tempoRateRange: [.8, 1.2], minimumBodySec: 12, energyDelta: .025,
  vocalPaddingSec: .3, vocalMinimumSec: .5, vocalMinimumFraction: .05,
  ranking: '分数降序；同分取更早完成点；仍相同按候选 ID 字典序',
  strategy: 'v3_linear_eq',
} as const

function cue(track: Track, sec: number) {
  const nearest = track.bars.reduce((best, value, index) =>
    Math.abs(value-sec) < best.distanceSec ? {rawBarIndex:index, sourceSec:value, distanceSec:Math.abs(value-sec)} : best,
    {rawBarIndex:-1, sourceSec:0, distanceSec:Infinity})
  const boundaries = track.sections.flatMap((s,index) => [
    {sectionIndex:index,label:s.label,edge:'start',sourceSec:s.start,distanceSec:Math.abs(s.start-sec)},
    {sectionIndex:index,label:s.label,edge:'end',sourceSec:s.end,distanceSec:Math.abs(s.end-sec)},
  ]).sort((a,b)=>a.distanceSec-b.distanceSec)
  return {sourceSec:sec, rawBarIndex:nearest.distanceSec < .00001 ? nearest.rawBarIndex : null,
    nearestRawBar:nearest, section:track.sections.find(s=>s.start<=sec&&sec<s.end)||null,
    nearestSectionBoundary:boundaries[0]||null, semanticStatus:'未经人工确认；网格索引不是已确认的小节编号'}
}
function voice(track: Track, start: number, end: number, fraction: number) {
  return {sourceStartSec:start,sourceEndSec:end,
    overlappingIntervals:(track.vocals||[]).filter(([s,e])=>e+.3>start&&s-.3<end),
    paddedUnionFraction:fraction,paddedUnionSec:fraction*(end-start),
    presencePassed:fraction>=.05&&fraction*(end-start)>=.5,
    basis:'原曲时间轴；区间两侧扩展 0.3 秒，裁剪到交接窗口并合并重叠后计算；B 阈值沿用 V3 的原曲秒数'}
}
export function explainPlan(a:Track,b:Track,p:Plan,position:number,intent:Intent,budget:number,boundary:boolean) {
  const wait=p.end-position
  const components=[
    {key:'base',label:'基础分',value:1,weight:1,contribution:1},
    {key:'waiting',label:'等待时间占预算比例',value:wait/budget,weight:-.5,contribution:-wait/budget*.5},
    {key:'tempo',label:'变速幅度',value:Math.abs(p.rate-1),weight:-1.4,contribution:-Math.abs(p.rate-1)*1.4},
    {key:'vocal',label:'双窗口人声占比乘积',value:p.aVocal*p.bVocal,weight:-.3,contribution:-p.aVocal*p.bVocal*.3},
    {key:'boundary',label:'靠近 A 段落边界',value:boundary?1:0,weight:.16,contribution:boundary?.16:0},
    {key:'fourBars',label:'四小节窗口',value:p.window.bars===4?1:0,weight:.05,contribution:p.window.bars===4?.05:0},
    {key:'style',label:'模型风格相同',value:a.style===b.style?1:0,weight:.04,contribution:a.style===b.style?.04:0},
  ]
  return {
    policyVersion:DECISION_POLICY.version,intent,positionSourceSec:position,budgetSec:budget,
    cues:{aMixStart:cue(a,p.start),aExit:cue(a,p.end),bEntry:cue(b,p.window.start),bBodyStart:cue(b,p.window.end)},
    pointReasons:[
      `A 在原曲 ${p.end.toFixed(3)} 秒退出，来自原始小节网格；等待 ${wait.toFixed(3)} 秒，预算 ${budget.toFixed(3)} 秒。`,
      `B 从原曲 ${p.window.start.toFixed(3)} 秒进入，到 ${p.window.end.toFixed(3)} 秒完成 ${p.window.bars} 小节交接；该窗口已具备对应 A 速度的素材。`,
      `按交接终点反推 A 开始点 ${p.start.toFixed(3)} 秒；距最近原始首拍 ${(p.gridError*1000).toFixed(2)} ms，门槛 65 ms。`,
      boundary?'A 退出点距段落边界小于 0.4 秒，获得边界加分；段落名称仍需人工确认。':'A 退出点满足原始小节边界，但没有段落边界加分。',
    ],
    score:{total:p.score,components,interpretation:'人为规则排序分，不是音质概率；只比较满足约束的候选',tieBreak:DECISION_POLICY.ranking},
    mapping:{aBpm:a.bpm,bNativeBpm:b.bpm,rate:p.rate,bSource:[p.window.start,p.window.end],overlapSec:p.duration,
      equation:'B_source = B_entry + (contextTime - scheduledStart) × rate（名义时间映射，素材经 atempo 与精确长度裁剪／补齐）',
      afterHandoff:'B 正文从窗口末端恢复原速'},
    features:{style:{a:a.style,b:b.style,aModelScore:a.styleScore,bModelScore:b.styleScore},
      energy:{a:p.aEnergy,b:p.bEnergy,aWindow:[position,position+8],bWindow:[p.window.end,Math.min(b.duration,p.window.end+16)],minimumDelta:.025,
        use:intent.kind==='up'||intent.kind==='down'?'方向硬筛选；不是排序加分':'仅记录，没有参与本次能量方向筛选'},
      vocalA:voice(a,p.start,p.end,p.aVocal),vocalB:voice(b,p.window.start,p.window.end,p.bVocal)},
    strategy:{id:'v3_linear_eq',selectionReason:'本版本固定采用已认可 V3 的线性淡化和 EQ 模板；只搜索歌曲、进入窗口和交接时间，不在多种混音算法间择优。',
      alternativesEvaluated:[],gain:{a:[.76,0],b:[0,.76],curve:'linear'},
      eq:{lowHz:140,highHz:3600,midHz:1200,midQ:1.05,aLowDb:-9,aHighDb:-1.4,bLowDb:-7,bHighDb:1.2,
        lowReason:'沿用 V3 固定低频衰减，控制叠加；本次没有依据频谱遮蔽自适应计算衰减量。',highReason:'沿用 V3 固定高频参数。'},
      midDuck:{enabled:p.midDuck,bMidDb:p.midDuck?-5:0,reason:p.midDuck?'A、B 各自窗口的人声占比均 ≥5%，且扩展后并集时长均 ≥0.5秒，因此衰减 B 中频。':'至少一侧没有同时达到占比和时长门槛，不触发 B 中频衰减。'},
      restore:{aSourceSec:p.restore,secondsBeforeHandoff:Math.min(p.duration,120/a.bpm),reason:'交接结束前半小节，B 从滤波声线性恢复原声。'},
      limitations:['浏览器 Biquad 与原 FFmpeg 非逐样本等价','人声判断使用各自窗口占比，不等同于两侧逐帧同时唱歌','没有用调性、和弦、乐器或审美分选择本次模板']},
    sources:{a:{trackId:a.id,reportId:a.reportId,nativeSha256:a.native.sha256,provenance:a.provenance},
      b:{trackId:b.id,reportId:b.reportId,nativeSha256:b.native.sha256,entrySha256:p.asset.sha256,provenance:b.provenance}},
    warnings:[...new Set([...(a.warnings||[]),...(b.warnings||[])])],
  }
}
