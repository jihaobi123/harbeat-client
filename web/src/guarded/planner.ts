import {energyAt,vocalPresence,type Track,type Intent,type Plan,type planNext} from '../realtime/planner'
import {explainPlan} from '../realtime/decision'
export type Acoustic={method:'vocal_gap_v1';masterSha256:string;vocalSha256:string;quietStart:number;quietEnd:number;maxRmsDbfs:number;thresholdDbfs:number;frameSec:number;reportId?:string}
export type Exit={acoustic?:Acoustic;id:string;cut:number;sectionEnd:number;start:number;label:string}
export type EntryEvidence={acoustic?:Acoustic;start:number;end:number;sectionStart:number;sectionEnd:number;lane:'instrumental'|'original_silent';sourceHashes:string[];preview?:Track['native'];gridSource?:string}
export type GuardCatalog={policy?:'acoustic-v1';tracks:Track[];evidence:Record<string,{exits:Exit[];windows:Record<string,EntryEvidence>;grid?:unknown}>}
export type Reviews={exits?:Record<string,{masterSha256:string;cut:number;confirmedAt:string;phraseEnded:boolean}>;entries?:Record<string,{assetSha256:string;bodySha256:string;confirmedAt:string;noVocalEntry:boolean;bodyStartsClean:boolean}>}
export function mergeSections(sections:Track['sections']){const out:Track['sections']=[];for(const s of [...sections].sort((a,b)=>a.start-b.start)){const last=out.at(-1);if(last&&last.label===s.label&&Math.abs(last.end-s.start)<.001)last.end=s.end;else out.push({...s})}return out}
function union(xs:number[][]){const r:number[][]=[];for(const [s,e] of xs.filter(([s,e])=>e>s).sort((a,b)=>a[0]-b[0])){const last=r.at(-1);if(last&&s<=last[1])last[1]=Math.max(e,last[1]);else r.push([s,e])}return r}
export function mappedOverlap(a:number[][],b:number[][],aStart:number,bStart:number,rate:number,duration:number){const aa=union(a.map(([s,e])=>[Math.max(0,s-aStart),Math.min(duration,e-aStart)])),bb=union(b.map(([s,e])=>[Math.max(0,(s-bStart)/rate),Math.min(duration,(e-bStart)/rate)]));let total=0;for(const x of aa)for(const y of bb)total+=Math.max(0,Math.min(x[1],y[1])-Math.max(x[0],y[0]));return total}
function gapValid(p:Acoustic|undefined,t:Track,start:number,end:number){return !!p&&p.method==='vocal_gap_v1'&&p.masterSha256===t.provenance?.masterSha256&&!!p.vocalSha256&&[p.quietStart,p.quietEnd,p.maxRmsDbfs,p.thresholdDbfs,p.frameSec].every(Number.isFinite)&&p.frameSec>0&&p.frameSec<=.05&&p.thresholdDbfs<=-32&&p.maxRmsDbfs<=p.thresholdDbfs&&p.quietEnd-p.quietStart>=.199&&p.quietStart<=start+.00001&&p.quietEnd>=end-.00001}
export function guardPlan(catalog:GuardCatalog,reviews:Reviews,a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,budget:number,requireReady=true):ReturnType<typeof planNext>{
 const candidates:Plan[]=[],exclusions:ReturnType<typeof planNext>['exclusions']=[]
 const deny=(t:Track,code:string,reason:string,windowId?:string)=>{const row=exclusions.find(x=>x.trackId===t.id&&x.code===code&&x.windowId===windowId);if(row)row.count++;else exclusions.push({trackId:t.id,track:t.title,code,reason,windowId,count:1})}
 if(!Number.isFinite(position)||!catalog.evidence[a.id]){deny(a,'missing_evidence','缺少保护模式依据');return {best:null,candidates,exclusions,rejected:exclusions}}
 for(const exit of catalog.evidence[a.id].exits){
  if(exit.cut<=position+.25||exit.cut>=a.duration-.1)continue
  const ar=reviews.exits?.[`${a.id}:${exit.id}`]
  const autoExit=catalog.policy==='acoustic-v1'&&gapValid(exit.acoustic,a,exit.cut-.05,exit.cut+.05)
  if((!ar||ar.masterSha256!==a.provenance?.masterSha256||ar.cut!==exit.cut||!ar.phraseEnded||!ar.confirmedAt)&&!autoExit){deny(a,'exit_unreviewed',`${exit.cut.toFixed(3)} 秒退出点尚未试听确认：乐段已完成且人声尾音未被截断`);continue}
  if(exit.cut<exit.sectionEnd-.001||exit.cut-exit.sectionEnd>(autoExit?Math.min(4,480/a.bpm):.5)){deny(a,'invalid_section_end','退出点未落在合并后的乐段结尾附近');continue}
  if(exit.cut>position+budget){deny(a,'outside_search','已确认退出点超出本次搜索范围；继续原曲，不提前切断');continue}
  for(const b of tracks){if(b.id===a.id||(intent.targetId&&intent.targetId!==b.id))continue
   if(!b.windows.length){deny(b,'no_entry_windows','下一首没有通过人声与乐段包含检查的进入窗口');continue}
   for(const w of b.windows){const ev=catalog.evidence[b.id]?.windows[w.id],asset=w.variants[a.id]
    if(!ev||!asset){deny(b,'missing_entry','缺少来源完整的进入素材',w.id);continue}
    if(ev.start!==w.start||ev.end!==w.end||w.start<ev.sectionStart-.001||w.end>ev.sectionEnd+.001){deny(b,'cross_section','进入窗口跨越乐段或来源时间不一致',w.id);continue}
    const rate=asset.rate,duration=asset.duration,start=exit.cut-duration
    if(!Number.isFinite(rate)||rate<.8||rate>1.2||!Number.isFinite(duration)||duration<.5||Math.abs((w.end-w.start)/rate-duration)>.001||b.duration-w.end<12){deny(b,'invalid_mapping','速度、时长映射或后续正文不满足',w.id);continue}
    if(start<position+.25){deny(b,'too_late','当前时刻已错过此窗口的伴奏混入点',w.id);continue}
    const error=Math.min(...a.bars.map(x=>Math.abs(x-start)))
    if(error>.065){deny(b,'grid_mismatch','保护点与进入片段无法同时按拍对齐',w.id);continue}
    const br=reviews.entries?.[`${b.id}:${w.id}:${a.id}`]
    const autoEntry=catalog.policy==='acoustic-v1'&&ev.lane==='original_silent'&&b.vocals!==null&&!b.vocals.some(([lo,hi])=>hi>w.start&&lo<w.end+.1)&&gapValid(ev.acoustic,b,w.start,w.end+.1)
    if((!br||br.assetSha256!==asset.sha256||br.bodySha256!==b.native.sha256||!br.noVocalEntry||!br.bodyStartsClean||!br.confirmedAt)&&!autoEntry){deny(b,'entry_unreviewed','请试听确认：进入片段没有明显人声、正文接管不从半句进入、拍点可用',w.id);continue}
    if(a.vocals===null||b.vocals===null){deny(b,'missing_vocals','人声区间缺失不能当作无人声',w.id);continue}
    const paddedA=a.vocals.map(([s,e])=>[s-.3,e+.3]),paddedB=b.vocals.map(([s,e])=>[s-.3,e+.3])
    const originalOverlap=mappedOverlap(paddedA,paddedB,start,w.start,rate,duration)
    if(ev.lane==='original_silent'&&vocalPresence(b.vocals,w.start,w.end)>0&&!autoEntry){deny(b,'incoming_vocals','原曲进入片段仍检测到人声，不能作为无人声入口',w.id);continue}
    const prepared=ready.has(asset.url)&&ready.has(b.native.url)
    if(requireReady&&!prepared){deny(b,'asset_not_ready','已核验素材尚未解码；准备后重新检查时间',w.id);continue}
    const p:Plan={id:`protected:${a.id}:${exit.id}:${b.id}:${w.id}`,from:a.id,to:b.id,window:w,asset,start,end:exit.cut,duration,restore:exit.cut-Math.min(duration,120/a.bpm),rate,score:-(exit.cut-position),midDuck:false,aVocal:vocalPresence(a.vocals,start,exit.cut),bVocal:vocalPresence(b.vocals,w.start,w.end),aEnergy:energyAt(a,start-4,start),bEnergy:energyAt(b,w.end,w.end+12),gridError:error,reason:'人工核验退出点 + 无明显人声进入素材 + 同乐段窗口；不以等待代价换取提前退出',section:exit.label,prepared}
    p.decision=explainPlan(a,b,p,position,intent,budget,true);p.decision.policyVersion='protected-v1';p.decision.pointReasons=[p.reason,`A 在 ${exit.cut.toFixed(3)} 秒完整退出；B 伴奏从 ${start.toFixed(3)} 秒混入，原曲正文仅在 A 退出后接管。`];p.decision.score={total:p.score,components:[],interpretation:'先通过全部硬约束，再取最早可执行的核验点；不是音质评分',tieBreak:'完成时间、速度偏差、稳定 ID'};p.decision.strategy.selectionReason='伴奏铺入，A 完整退出后 B 原曲正文接管；无普通规划器回退';p.decision.strategy.midDuck={...p.decision.strategy.midDuck,bMidDb:0,reason:'进入素材已通过无人声明确试听确认，使用伴奏分轨或无人声原曲，未以中频压低替代避让'}
    p.decision.cues.aExit.semanticStatus='本次精确退出点已人工试听确认；不代表整曲结构成为真值'
    p.decision.cues.bEntry.semanticStatus='本次进入片段与拍点已人工试听确认'
    p.decision.cues.bBodyStart.semanticStatus='本次正文接管点已人工试听确认，不从人声半句进入'
    p.decision.features.vocalB.basis+='；这里保留原曲检测，实际进入播放已人工听验的伴奏，不能将二者混为一谈'
    p.decision.strategy.restore.reason='交接结束前半小节，B 伴奏逐渐撤去 EQ；A 完全退出时 B 原曲正文才接管'
    p.decision.strategy.limitations=['现有 VAD 不识别歌词语义；依赖精确切点的人工听验','分轨伴奏可能残留人声，须试听实际变速素材','B 正文接管恢复原速，浏览器与离线 V3 不是逐样本等价']
    ;(p as Plan&{protection:unknown}).protection={exit,entry:ev,exitReview:ar||null,entryReview:br||null,automaticExit:autoExit?exit.acoustic:null,automaticEntry:autoEntry?ev.acoustic:null,originalMappedVocalOverlapSec:originalOverlap,renderedEntryHasNoObviousVocals:'human_review_not_model_certainty',detectorActiveAtExit:vocalPresence(a.vocals,exit.cut-.2,exit.cut+.2)>0,detectorActiveAtBodyStart:vocalPresence(b.vocals,w.end-.2,w.end+.2)>0,reviewScope:'人工核验仅覆盖本次准确切点和此素材；检测与人工判断不一致时保留两者记录'}
    if(autoExit&&autoEntry){
     p.reason='段落结束后的人声低活动间隙 + 同乐段无人声原曲入口；声学自动候选，未冒充人工核验'
     p.decision.policyVersion='protected-auto-v1';p.decision.pointReasons=[p.reason,`A 模型段尾 ${exit.sectionEnd.toFixed(3)} 秒，等待人声间隙至 ${exit.cut.toFixed(3)} 秒退出；B 从 ${start.toFixed(3)} 秒铺入，A 退出后接管。`]
     p.decision.cues.aExit.semanticStatus='模型段尾后、声学低活动间隙内自动选点；歌词语义与结构标签尚未人工确认'
     p.decision.cues.bEntry.semanticStatus=p.decision.cues.bBodyStart.semanticStatus='进入窗口及正文接管点通过分离人声 RMS 检查；非人工确认'
     p.decision.strategy.selectionReason='通过自动声学保护后执行 V3 EQ 与渐变；无人工勾选前置条件，无普通规划器兜底'
     p.decision.strategy.midDuck.reason='原曲进入窗口通过人声低活动检查；A 完全退出后才到 B 正文，不依赖中频压低掩盖冲突'
     p.decision.features.vocalB.basis='保留原曲 VAD 区间及其扩展占比；自动模式同时核对未扩展 VAD 与完整进入窗口的分离人声低活动证据，没有人工确认记录'
     p.decision.strategy.limitations=['低 RMS 与模型段落均为声学代理，不能证明歌词语义句末','本次原曲入口全段人声 RMS 低于阈值；分离误差仍可能影响判断','B 正文接管恢复原速，保留 V3 行为']
     Object.assign((p as any).protection,{renderedEntryHasNoObviousVocals:'acoustic_proxy_not_human_verification',reviewScope:'无自动生成人工确认；所有自动声学证据与源文件绑定',sectionTailDelaySec:exit.cut-exit.sectionEnd})
    }
    candidates.push(p)
   }
  }
 }
 candidates.sort((x,y)=>x.end-y.end||Math.abs(x.rate-1)-Math.abs(y.rate-1)||x.id.localeCompare(y.id))
 if(!candidates.length&&!exclusions.length)deny(a,'no_future_exit',catalog.policy==='acoustic-v1'?'当前范围没有同时满足段尾、人声间隙与拍网格的退出点；继续原曲':'当前范围没有后续可核验的完整乐段结尾；继续原曲')
 return {best:candidates[0]||null,candidates,exclusions,rejected:exclusions.map(x=>({track:x.track,reason:x.reason}))}
}
