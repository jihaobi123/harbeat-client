import {scheduleV30Eq} from '../v30/eq'
import {referenceCurves,schedule} from '../vocal-bridge/automation'
import {handoffPlan,type Mode} from './policy'
import type {LowHandoffCase} from './transport'
import type {Points} from '../melody-overlap/policy'
export function makeHandoffGraph(ctx:BaseAudioContext,monitor:AudioNode,decoded:Record<string,AudioBuffer>,c:LowHandoffCase,mode:Mode,at:number){
 const nodes:AudioNode[]=[],sources:AudioBufferSourceNode[]=[],policy=handoffPlan(c,mode),end=policy.end,total=end+c.post,ref=referenceCurves(c.pre,c.plan.duration,end-Math.min(c.plan.duration,120/c.bpm[0]))
 const bus=ctx.createGain();bus.gain.value=0;bus.connect(monitor);nodes.push(bus);schedule(bus.gain,[[0,0],[.02,1],[total-.04,1],[total,0]],at)
 const filters:{a:any[];b:any[]}={a:[],b:[]}
 for(const side of ['a','b'] as const){
  for(const layer of ['Master','Vocal']){
   const input=ctx.createGain(),low=ctx.createBiquadFilter(),high=ctx.createBiquadFilter(),mid=ctx.createBiquadFilter(),wet=ctx.createGain(),dry=ctx.createGain(),sum=ctx.createGain(),extra=ctx.createBiquadFilter(),envelope=ctx.createGain()
   wet.gain.value=0;dry.gain.value=1;envelope.gain.value=0;
   low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
   input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(sum);dry.connect(sum)
   const wetPoints=side==='a'?ref.aWet:ref.bWet;schedule(wet.gain,wetPoints,at);schedule(dry.gain,wetPoints.map(([t,v])=>[t,1-v]),at)
   extra.type='lowshelf';extra.frequency.value=policy.settings.frequency;schedule(extra.gain,policy.low[side],at)
   sum.connect(extra);extra.connect(envelope);envelope.connect(bus)
   // F(M) + V - F(V) = F(M-V) + V, including original shared EQ and fades.
   schedule(envelope.gain,policy[side],at,layer==='Master'?.36:-.36)
   if(layer==='Vocal'){const original=ctx.createGain();original.gain.value=0;sum.connect(original);original.connect(bus);schedule(original.gain,policy[side],at,.36);nodes.push(original)}
   nodes.push(input,low,high,mid,wet,dry,sum,extra,envelope);filters[side].push({low,high,mid})
   const source=(key:string,start:number,duration:number,body=false)=>{
    const s=ctx.createBufferSource(),edge=ctx.createGain();s.buffer=decoded[key];edge.gain.value=body?0:1;s.connect(edge);edge.connect(input)
    const points:Points=body?[[0,0],[.004,1]]:[[0,1]]
    if(side==='b'&&!body)points.push([Math.max(.004,duration-.004),1],[duration,0])
    schedule(edge.gain,points,at+start);s.start(at+start,0,duration);sources.push(s);nodes.push(edge)
   }
   if(side==='a')source('a'+layer,0,end)
   else{source('bEntry'+layer,c.pre,c.plan.duration);source('bBody'+layer,end,c.post,true)}
  }
 }
 for(let j=0;j<2;j++)scheduleV30Eq(filters.a[j],filters.b[j],at+c.pre,c.plan.v30Eq!)
 return {nodes,sources,policy,total}
}
