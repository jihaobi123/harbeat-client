export type Mode='natural'|'relay'
export const entryKeys=(mode:Mode)=>mode==='relay'?{master:'bAlignedMaster',vocal:'bAlignedVocal'}:{master:'bEntryMaster',vocal:'bEntryVocal'}
export function validateMetric(c:any){
 const m=c.metric,p=c.plan
 if(!m||![m.aBars,m.bBars].every(v=>Number.isInteger(v)&&v>0)||![.5,2].includes(m.relation)||m.voicePolicy!=='original-linear-fades'||!c.bpm?.every((v:number)=>Number.isFinite(v)&&v>0)||Math.abs(c.bpm[1]/c.bpm[0]/m.relation-1)>.025||p.rate!==1||!Number.isFinite(p.duration)||p.duration<=0||Math.abs(p.end-p.start-p.duration)>.002||Math.abs(p.window.end-p.window.start-p.duration)>.002||m.bBars/m.aBars!==m.relation)throw Error('半速／倍速关系或固定时间轴不成立')
 const x=m.input as number[],y=m.output as number[]
 if(!Array.isArray(x)||!Array.isArray(y)||x.length!==y.length||x.length!==m.bBars*4+1||!x.concat(y).every(Number.isFinite)||Math.max(Math.abs(x[0]),Math.abs(y[0]),Math.abs(x.at(-1)!-p.duration),Math.abs(y.at(-1)!-p.duration))>1e-6||!x.some((v,i)=>Math.abs(v-y[i])>=.012))throw Error('局部对拍必须保持同一进出点并包含实际时间修正')
 for(let i=1;i<x.length;i++){const rate=(x[i]-x[i-1])/(y[i]-y[i-1]);if(x[i]<=x[i-1]||y[i]<=y[i-1]||rate<.85||rate>1.15||Math.abs(x[i]-y[i])>.065+1e-9)throw Error('局部拍点修正超出范围')}
}
