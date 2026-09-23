import type {Plan,Track} from '../realtime/planner'
import type {GainPoint,EqPoint,TransitionAutomation} from './types'
export function gainAt(points:GainPoint[],t:number){for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];if(t<=b.t)return a.value+(b.value-a.value)*Math.max(0,(t-a.t)/Math.max(.00001,b.t-a.t))}return points.at(-1)!.value}
function sample(track:Track,start:number,end:number){
 const f=track.alignment?.bandFrames;if(!f||track.alignment?.source.masterSha256!==track.provenance?.masterSha256)throw Error('频段能量缺失或来源未绑定，无法使用动态 EQ')
 const rows=f.flatMap((x,i)=>{const w=Math.max(0,Math.min(end,x.end)-Math.max(start,x.start));return w?[{x,w,row:i+1}]:[]}),width=end-start
 if(rows.reduce((n,x)=>n+x.w,0)<width-.011)throw Error('频段能量未覆盖实际交接区间')
 const values={} as Record<'low'|'mid'|'high',number>
 for(const key of ['low','mid','high'] as const){if(rows.some(x=>x.x[key]!==null&&!Number.isFinite(x.x[key])))throw Error('频段能量不是有效数值');values[key]=rows.reduce((n,{x,w})=>n+(x[key]===null?0:10**(x[key]!/10))*w,0)/width}
 return {power:values,source:[start,end],rows:rows.map(x=>x.row),nullMeans:'源分析零功率帧；不是缺失曲线'}
}
export function buildAutomation(a:Track,b:Track,p:Plan,kind:'fixed'|'adaptive'):TransitionAutomation{
 if(!p.phrase)throw Error('缺少乐句保护依据')
 const d=p.duration,hold=Math.max(0,p.phrase.fadeStart-p.start)
 if(!Number.isFinite(hold)||d-hold<.149)throw Error('句尾之后没有足够的退场时间')
 const aGain:GainPoint[]=hold>0?[{t:0,value:1},{t:hold,value:1},{t:d,value:0}]:[{t:0,value:1},{t:d,value:0}],bGain:GainPoint[]=[{t:0,value:0},{t:d,value:1}]
 const aEq:EqPoint[]=[],bEq:EqPoint[]=[],evidence:any[]=[],restore=Math.max(0,Number.isFinite(p.restore)?p.restore-p.start:d-Math.min(.6,d/3)),times=[...new Set([0,hold,Math.min(d,hold+.1),restore,d,...Array.from({length:Math.ceil(d/.5)},(_,i)=>Math.min(d,i*.5))])].sort((x,y)=>x-y)
 for(const t of times){let ae={t,low:0,mid:0,high:0},be={t,low:0,mid:0,high:0}
  const recovery=t>restore?(d-t)/Math.max(.001,d-restore):1
  if(kind==='fixed'){
   if(t>hold){const wet=Math.min(1,(t-hold)/.1);ae={t,low:-9*wet,mid:0,high:-1.4*wet}}
   be={t,low:-7*recovery,mid:0,high:1.2*recovery}
  }else{
   const lo=Math.max(0,Math.min(d-.1,t-.25)),hi=Math.min(d,lo+.5),aa=sample(a,p.start+lo,p.start+hi),bb=sample(b,p.window.start+lo*p.rate,p.window.start+hi*p.rate),ga=gainAt(aGain,t),gb=gainAt(bGain,t)
   const bands:any={};for(const band of ['low','mid','high'] as const){const pa=aa.power[band],pb=bb.power[band],outA=pa*ga*ga,outB=pb*gb*gb,ceiling=Math.max(pa,pb)*10**(.8/10),combined=outA+outB,cap={low:9,mid:4,high:3}[band]
    const wanted=outB>1e-12&&combined>ceiling?Math.min(cap,Math.max(0,-10*Math.log10(Math.max(1e-12,ceiling-outA)/outB))):0
    be[band]=wanted&&recovery?-wanted*recovery:0;bands[band]={aPower:pa,bPower:pb,combinedPower:combined,ceilingPower:ceiling,requestedReductionDb:wanted,appliedDb:be[band]}
   }
   evidence.push({t,a:aa,b:bb,gainA:ga,gainB:gb,bands,reason:'保持 A 句尾的干声；B 仅在预测叠加频段超过较强单曲 +0.8 dB 时衰减，最后平滑恢复原声'})
  }
  aEq.push(ae);bEq.push(be)
 }
 return {version:'phrase-automation-v1',kind,aGain,bGain,aEq,bEq,evidence,limitations:['声学乐句候选不是歌词语义真值','EQ 由预分析的源时间频段功率前馈驱动，不是麦克风或扬声器闭环测量','频段功率与实际滤波器响应并非逐频率等价；衰减限幅后仍可能超出预测目标','B 入口保调变速，正文接管仍沿用 V3 恢复原速；未调整该变量']}
}
