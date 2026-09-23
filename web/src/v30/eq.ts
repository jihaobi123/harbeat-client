import type {Track,Plan} from '../realtime/planner'
import type {EqPoint} from '../phrase/types'
import type {V30Eq} from './types'
import {sourceBound} from './planner'
const bands=['low','mid','high'] as const
const clamp=(v:number,lo:number,hi:number)=>Math.min(hi,Math.max(lo,v))
function sample(t:Track,start:number,end:number){
 const sums={low:0,mid:0,high:0},rows:number[]=[];let cover=0,cursor=start
 for(const [i,f] of (t.alignment?.bandFrames||[]).entries()){const s=Math.max(start,f.start),e=Math.min(end,f.end);if(e<=s)continue;if(s>cursor+.005)throw Error(t.title+' 频段数据有空缺');if(s<cursor-.005)throw Error(t.title+' 频段数据时间重复');for(const band of bands){const v=f[band];if(v!==null&&!Number.isFinite(v))throw Error('频段功率无效');sums[band]+=(e-s)*(v===null?0:10**(v/10))}cover+=e-s;cursor=e;rows.push(i+1)}
 if(cover<end-start-.005||cover<=0)throw Error(t.title+' 缺少所需频段数据')
 return {power:{low:sums.low/cover,mid:sums.mid/cover,high:sums.high/cover},rows,start,end}
}
function activity(t:Track,start:number,end:number){let duration=0;for(const p of t.alignment!.phrases)duration+=Math.max(0,Math.min(end,p.tailEnd)-Math.max(start,p.start));return clamp(duration/(end-start),0,1)}
export function buildV30Eq(a:Track,b:Track,p:Plan):V30Eq{
 if(!sourceBound(a)||!sourceBound(b))throw Error('原曲、报告或人声指纹不一致')
 const template={a:{low:-9,mid:0,high:-1.4},b:{low:-7,mid:p.midDuck?-5:0,high:1.2}}
 const output:V30Eq={version:'v30-eq-only-v1',a:[],b:[],template,evidence:[],sources:{a:a.alignment!.source,b:b.alignment!.source,rowIndexBase:1,bandPath:'/alignment/bandFrames'},limits:{lowHighDb:3,midDb:2,slewDbPerSec:3},limitations:['频段功率与声学人声是控制代理，不代表已校准的听感能量或语义主唱','低/中/高分析频段与 Biquad 滤波器响应不完全一致；公式为待试听规则','保留 V3 增益、20ms A EQ 启用和最后半小节 B 干湿恢复；未改变选点、素材或时长']}
 const n=Math.max(1,Math.ceil(p.duration/.25))
 for(let i=0;i<=n;i++){
  const t=p.duration*i/n,x=t/p.duration,center=Math.min(p.duration-.001,Math.max(.001,t)),left=Math.max(0,center-.25),right=Math.min(p.duration,center+.25)
  const sa=sample(a,p.start+left,p.start+right),sb=sample(b,p.window.start+left*p.rate,Math.min(p.window.end,p.window.start+right*p.rate))
  const av=activity(a,sa.start,sa.end),bv=activity(b,sb.start,sb.end),overlap=4*x*(1-x)
  const targets={a:{...template.a},b:{...template.b}}
  // Change coefficients only. Complementary deck gains are scheduled by the original transport.
  for(const band of ['low','high'] as const){const pa=sa.power[band]*10**(template.a[band]/10),pb=sb.power[band]*10**(template.b[band]/10);const ratio=10*Math.log10((pa+1e-12)/(pb+1e-12));if(pa+pb>1e-10){targets.a[band]-=overlap*clamp((ratio-3)*.35,0,3);targets.b[band]-=overlap*clamp((-ratio-3)*.35,0,3)}}
  targets.b.mid+=overlap*(p.midDuck?2-4*av*bv:-2*av*bv)
  for(const deck of ['a','b'] as const){const prev=output[deck].at(-1),point:EqPoint={t,...template[deck]};for(const band of bands){const maxStep=prev?3*(t-prev.t):0;point[band]=prev?prev[band]+clamp(targets[deck][band]-prev[band],-maxStep,maxStep):template[deck][band]}output[deck].push(point)}
  output.evidence.push({t,a:sa,b:sb,aVocal:av,bVocal:bv,overlapWeight:overlap,target:targets,rule:'低/高：模板处理后功率差超过3dB才削弱偏强一侧；中：同步人声占比调节B；限幅并限速'})
 }
 return output
}
type EqDeck={low:{gain:AudioParam};mid:{gain:AudioParam};high:{gain:AudioParam}}
export function scheduleV30Eq(a:EqDeck,b:EqDeck,at:number,eq:V30Eq){for(const [deck,points] of [[a,eq.a],[b,eq.b]] as const)for(const band of bands){const param=deck[band].gain;param.cancelScheduledValues(at);points.forEach((p,i)=>i?param.linearRampToValueAtTime(p[band],at+p.t):param.setValueAtTime(p[band],at+p.t))}}
