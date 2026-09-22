import type {Track,Window,Intent} from './planner'
export const EVIDENCE_POLICY={version:'local-intents-v1',calibrationId:'master-rms-common-digital-full-scale-v1',preSec:4,blockSec:4,sustainSec:16,minimumDeltaDb:1,maximumJumpDb:6,minimumCoverage:.98} as const
export type EnergyFrame={start:number;end:number;dbfs:number|null;coverage:number;status:string}
export type LocalStyle={start?:number;end?:number;status:string;top:{style:string;score:number;label?:string}[];reasons:string[];support?:unknown[]}
export type IntervalProfile={start:number;end:number;style:LocalStyle;energy?:EnergyFrame;sections?:{index:number;label:string;start:number;end:number}[];boundaryStatus?:string}
export type MixProfile={schema:string;policy:{calibrationId:string;energyUnit:string};source:{masterSha256:string;[key:string]:unknown};energyCurve:EnergyFrame[];energyFrames?:EnergyFrame[];sections:(IntervalProfile&{index:number;label:string})[];windows:{id:string;entry:IntervalProfile;takeover:IntervalProfile;sustain:EnergyFrame[]}[];limitations?:string[]}
const levelCache=new WeakMap<MixProfile,Map<string,{start:number;end:number;coverage:number;dbfs:number|null}>>()
function level(track:Track,start:number,end:number){
 const profile=track.mixProfile,key=`${start}:${end}`
 let cache=profile?levelCache.get(profile):undefined
 if(cache?.has(key))return cache.get(key)!
 if(profile&&!cache){cache=new Map();levelCache.set(profile,cache)}
 let power=0,covered=0,last=-Infinity,invalid=false
 for(const r of profile?.energyFrames||[]){if(!Number.isFinite(r.start)||!Number.isFinite(r.end)||r.end<=r.start){invalid=true;continue}if(r.end<=start||r.start>=end)continue;if(r.start<last-1e-6)invalid=true;last=r.end
  if(r.status!=='measured'||r.dbfs===null||!Number.isFinite(r.dbfs)||r.coverage<EVIDENCE_POLICY.minimumCoverage)continue
  const weight=Math.max(0,Math.min(end,r.end)-Math.max(start,r.start));covered+=weight*r.coverage;power+=weight*r.coverage*10**(r.dbfs/10)
 }
 const coverage=Math.min(1,covered/(end-start));const result={start,end,coverage,dbfs:!invalid&&coverage>=EVIDENCE_POLICY.minimumCoverage&&power>0?10*Math.log10(power/covered):null}
 if(cache){if(cache.size>=2048)cache.clear();cache.set(key,result)}
 return result
}
export function evaluateEvidence(a:Track,b:Track,w:Window,mixStart:number,intent:Intent){
 const policy=EVIDENCE_POLICY,direction=intent.energy||(intent.kind==='up'||intent.kind==='down'?intent.kind:'any')
 const targetStyle=intent.style||null,local=b.mixProfile?.windows.find(x=>x.id===w.id)
 const before=level(a,mixStart-policy.preSec,mixStart)
 const after=Array.from({length:4},(_,i)=>level(b,w.end+i*4,w.end+(i+1)*4))
 const deltas=after.map(x=>before.dbfs!==null&&x.dbfs!==null?x.dbfs-before.dbfs:null)
 const evidence={policy,requested:{style:targetStyle,energy:direction},aBefore:before,bAfter:after,deltasDb:deltas,
  style:{entry:local?.entry.style||null,takeover:local?.takeover.style||null},
  source:{a:a.mixProfile?.source||null,b:b.mixProfile?.source||null},
  scope:'A 混入前4秒与 B 接管后4组4秒原曲功率；共同 V3 主增益；不含叠加输出或扬声器实测'}
 const result=(accepted:boolean,code:string,reason:string)=>({accepted,code,reason,...evidence})
 if((targetStyle||direction!=='any')&&[a,b].some(t=>t.mixProfile&&(t.mixProfile.schema!=='harbeat.mix_profiles.v1'||t.mixProfile.source.masterSha256!==t.provenance?.masterSha256)))return result(false,'profile_identity','窗口档案与当前音频身份或版本不一致')
 if(targetStyle){
  const s=local?.takeover.style
  if(!local||Math.abs(local.entry.start-w.start)>.002||Math.abs(local.entry.end-w.end)>.002||Math.abs(local.takeover.start-w.end)>.002||local.takeover.end-w.end<policy.sustainSec-.002||!s||s.status!=='model_candidate')return result(false,'local_style_pending','接管后16秒缺少足够的局部风格证据，待确认；不会继承整曲标签')
  if(s.top[0]?.style!==targetStyle)return result(false,'local_style_mismatch',`接管窗口的首选模型候选 ${s.top[0]?.style||'未知'} 不符合目标 ${targetStyle}`)
 }
 if(direction!=='any'){
  if(!a.mixProfile||!b.mixProfile||before.dbfs===null||after.some(x=>x.dbfs===null)||w.end+policy.sustainSec>b.duration+.001)return result(false,'energy_missing','交接前或接管后16秒的统一尺度测量不完整；不使用整曲平均或相对曲线替代')
  if([a,b].some(t=>t.mixProfile?.policy.calibrationId!==policy.calibrationId||t.mixProfile.policy.energyUnit!=='dBFS_RMS'))return result(false,'energy_calibration','能量标尺或单位不同，不能跨曲比较')
  if(deltas.some(x=>x!==null&&Math.abs(x)>policy.maximumJumpDb))return result(false,'energy_jump',`接管后出现超过 ${policy.maximumJumpDb} dB 的功率跳变，超出实验上限`)
  if(deltas.some(x=>x===null||(direction==='up'?x<policy.minimumDeltaDb:x>-policy.minimumDeltaDb)))return result(false,'energy_not_sustained',`目标${direction==='up'?'升':'降'}能量未在接管后全部4个窗口持续至少 ${policy.minimumDeltaDb} dB；各窗口差值 ${deltas.map(x=>x?.toFixed(2)??'未知').join(' / ')} dB`)
 }
 return result(true,'local_evidence_pass',`${targetStyle?`接管窗口模型候选 ${targetStyle} 符合目标；`:''}${direction!=='any'?`接管后16秒持续${direction==='up'?'升':'降'}能量，差值 ${deltas.map(x=>x?.toFixed(2)).join(' / ')} dB`:'本次未限制能量方向'}${local?.entry.style.status==='needs_review'?'；进入片段风格待确认，接管窗口单独判断':''}`)
}
