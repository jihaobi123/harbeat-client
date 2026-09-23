import {vocalPresence,energyAt,type Track,type Plan,type Intent,type planNext} from '../realtime/planner'
import {explainPlan} from '../realtime/decision'
import {buildAutomation} from './automation'
const bound=(t:Track)=>!!t.alignment&&t.alignment.status==='candidate'&&t.alignment.source.masterSha256===t.provenance?.masterSha256&&t.alignment.source.reportSha256===t.provenance?.reportSha256&&t.alignment.source.reportId===t.reportId&&t.alignment.source.vocalSha256===t.provenance?.vocalSha256
function completeGrid(t:Track,start:number,end:number,count:number){
 const bars=t.alignment?.bars||[],i=bars.findIndex(b=>Math.abs(b.start-start)<=.065),span=bars.slice(i,i+count)
 return i>=0&&Number.isInteger(count)&&count>0&&span.length===count&&span.every((b,j)=>b.valid&&b.beats.length===4&&(!j||Math.abs(span[j-1].end-b.start)<.001))&&Math.abs(span.at(-1)!.end-end)<=.065
}
export function phrasePlan(_catalog:Track[],mode:'section'|'phrase',a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,budget:number,requireReady=true):ReturnType<typeof planNext>{
 const candidates:Plan[]=[],exclusions:ReturnType<typeof planNext>['exclusions']=[]
 const deny=(t:Track,code:string,reason:string,windowId?:string)=>{const old=exclusions.find(x=>x.trackId===t.id&&x.code===code&&x.windowId===windowId);if(old)old.count++;else exclusions.push({trackId:t.id,track:t.title,code,reason,windowId,count:1})}
 if(!bound(a)){deny(a,'alignment_unavailable','缺少来源一致的乐句与拍点预处理');return {best:null,candidates,exclusions,rejected:[]}}
 for(const exit of a.alignment!.exits){
  if(mode==='section'&&!exit.sectionAligned){deny(a,'section_incomplete','此候选只满足声学乐句完整，未同时满足模型段尾；没有自动降级');continue}
  if(exit.cut<=position+.25||exit.cut>position+budget||exit.cut>=a.duration-.1)continue
  if(exit.tailEnd>exit.cut-.15||(exit.nextVoiceStart!==null&&exit.nextVoiceStart<exit.cut+.08)){deny(a,'outgoing_phrase_cut','尾音未结束、退场时间不足，或下一句已开始');continue}
  for(const b of tracks){if(b.id===a.id||(intent.targetId&&b.id!==intent.targetId))continue
   if(!bound(b)){deny(b,'alignment_unavailable','下一首缺少来源一致的乐句预处理');continue}
   for(const w of b.windows){const asset=w.variants[a.id];if(!asset)continue
    const rate=asset.rate,d=asset.duration,start=exit.cut-d
    if(!Number.isFinite(rate)||rate<.8||rate>1.2||!Number.isFinite(d)||d<.5||Math.abs((w.end-w.start)/rate-d)>.001||w.end+12>b.duration||start<position+.25)continue
    if(!b.sections.some(s=>s.start<=w.start+.001&&s.end>=w.end-.001)){deny(b,'entry_cross_section','B 进入素材跨越模型段落',w.id);continue}
    if(!completeGrid(a,start,exit.cut,w.bars)||!completeGrid(b,w.start,w.end,w.bars)){deny(b,'incomplete_observed_grid','A 转场或 B 进入窗口缺少完整、连续的实际四拍小节',w.id);continue}
    const gridError=Math.min(...a.alignment!.bars.filter(x=>x.valid).map(x=>Math.abs(x.start-start)))
    const phrase=b.alignment!.phrases.find(x=>x.tailEnd>w.start)
    if(!phrase||phrase.start<w.start+.02){deny(b,'incoming_half_phrase','B 起点已经在声学乐句中，或未留开始前余量',w.id);continue}
    const voice=start+(phrase.start<=w.end?(phrase.start-w.start)/rate:d+phrase.start-w.end),gap=voice-exit.tailEnd,maxGap=Math.max(1.2,120/a.bpm)
    if(gap<-.00001){deny(b,'vocal_overlap','B 人声会早于 A 受保护尾音结束',w.id);continue}
    if(gap>maxGap){deny(b,'vocal_gap','A 尾音结束至 B 首句空缺超过两拍（最低 1.2 秒）',w.id);continue}
    const prepared=ready.has(b.native.url)&&ready.has(asset.url);if(requireReady&&!prepared){deny(b,'asset_not_ready','素材尚未解码，准备后重新检查',w.id);continue}
    const p:Plan={id:`phrase:${mode}:${a.id}:${exit.id}:${b.id}:${w.id}`,from:a.id,to:b.id,window:w,asset,start,end:exit.cut,duration:d,rate,restore:exit.cut-Math.min(d,120/a.bpm),aVocal:vocalPresence(a.vocals||[],start,exit.cut),bVocal:vocalPresence(b.vocals||[],w.start,w.end),aEnergy:energyAt(a,start,exit.cut),bEnergy:energyAt(b,w.start,w.end),midDuck:false,gridError,prepared,score:-(exit.cut-position)-gap,section:a.sections.find(s=>s.end===exit.sectionEnd)?.label||'phrase',reason:`${exit.sectionAligned?'模型段尾与声学句尾相容':'完整声学乐句模式'}；A 尾音保持至 ${exit.tailEnd.toFixed(3)} 秒，B 人声晚 ${gap.toFixed(3)} 秒进入`,phrase:{exit,incomingPhraseId:phrase.id,incomingVocalSource:phrase.start,incomingVocalRender:voice,vocalGap:gap,fadeStart:Math.max(start,exit.tailEnd),mode,aSource:a.alignment!.source,bSource:b.alignment!.source}}
    p.decision=explainPlan(a,b,p,position,intent,budget,exit.sectionAligned);p.decision.policyVersion='phrase-candidate-v1';p.decision.score={total:p.score,components:[{key:'wait',label:'完成等待秒数',value:exit.cut-position,weight:-1,contribution:-(exit.cut-position)},{key:'vocalGap',label:'保护尾音至 B 首句间距',value:gap,weight:-1,contribution:-gap}],interpretation:'仅在通过全部约束的候选中比较等待和人声间距；不是听感评分',tieBreak:'规则分降序，其次稳定 ID'};p.decision.pointReasons=[p.reason,`小节最后一拍 ${exit.lastBeat.toFixed(3)} 秒；退出用下一小节首拍 ${exit.cut.toFixed(3)} 秒，二者分列`];p.decision.strategy.selectionReason='先保护完整声学乐句和可执行拍点，再控制人声空缺；没有将模型候选当作语义句末';p.decision.strategy.limitations=['原始 VAD 与分离人声联合保护；没有歌词真值','当前明确选择的段落或乐句模式，不自动降级'];candidates.push(p)
   }
  }
 }
 candidates.sort((x,y)=>y.score-x.score||x.id.localeCompare(y.id));if(!candidates.length&&!exclusions.length)deny(a,'no_future_exit','本次范围没有同时满足句尾、下一句保护与拍点的退出点')
 return {best:candidates[0]||null,candidates,exclusions,rejected:exclusions.map(x=>({track:x.track,reason:x.reason}))}
}
export const makePhrasePlanner=(tracks:Track[],mode:'section'|'phrase',eq:'fixed'|'adaptive'):typeof planNext=>(a,ts,pos,intent,ready,budget=18,required=true)=>{
 const r=phrasePlan(tracks,mode,a,ts,pos,intent,ready,budget,required)
 if(r.best){const p=r.best,automation=buildAutomation(a,ts.find(t=>t.id===p.to)!,p,eq);r.best={...p,automation}
  const strategy=r.best.decision!.strategy;strategy.id='phrase_'+eq;strategy.gain.curve='A 尾音前保持，尾音后线性退出；B 线性进入';strategy.eq={...strategy.eq,aLowDb:automation.aEq[0].low,aHighDb:automation.aEq[0].high,bLowDb:automation.bEq[0].low,bHighDb:automation.bEq[0].high,lowReason:eq==='adaptive'?'此处数值为起始值；实际逐步参数由源频段功率计算，完整曲线见 automation':'A 尾音前保持干声，之后使用原低频模板；B 沿用原 EQ',highReason:'完整时序以本次 automation 为准'};strategy.restore.reason='按计划恢复时刻平滑恢复 B 的原声';strategy.midDuck.reason='B 首句已在 A 保护尾音之后，频段调整以本次 automation 为准'
 }
 return r
}
