// Frozen legacy5190graph as a diagnostic reference; common headroom scaled0.76->0.60.
import {scheduleV30Eq} from '../v30/eq'
import {referenceCurves,schedule} from '../vocal-bridge/automation'
import {bassCurves} from '../bass-swap/policy'
import {correction,type Points} from '../melody-overlap/policy'
import type {CombinationCase} from './transport'
export function makeLegacyBassReference(ctx:BaseAudioContext,monitor:AudioNode,decoded:Record<string,AudioBuffer>,c:CombinationCase,at:number){
 const nodes:AudioNode[]=[],sources:AudioBufferSourceNode[]=[],end=c.pre+c.plan.duration,total=end+c.post,policy=bassCurves(c.pre,c.plan.duration,c.timing,'swap'),ref=referenceCurves(c.pre,c.plan.duration,end-Math.min(c.plan.duration,120/c.bpm[0]))
   const bus=ctx.createGain();bus.connect(monitor);nodes.push(bus);schedule(bus.gain,[[0,0],[.02,1],[total-.04,1],[total,0]],at)
   const filters:{a:any[];b:any[]}={a:[],b:[]}
   for(const side of ['a','b'] as const){
    const x=policy[side],gains=[x.rest,correction(x.bass,x.rest)]
    for(const [j,layer] of ['Master','Bass'].entries()){
     const input=ctx.createGain(),low=ctx.createBiquadFilter(),high=ctx.createBiquadFilter(),mid=ctx.createBiquadFilter(),wet=ctx.createGain(),dry=ctx.createGain(),gain=ctx.createGain()
     low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
     input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(gain);dry.connect(gain);gain.connect(bus)
     const wetPoints=side==='a'?ref.aWet:ref.bWet;schedule(wet.gain,wetPoints,at);schedule(dry.gain,wetPoints.map(([t,v])=>[t,1-v]),at);schedule(gain.gain,gains[j],at,.60)
     nodes.push(input,low,high,mid,wet,dry,gain);filters[side].push({low,high,mid})
     const source=(key:string,start:number,duration:number,body=false)=>{
      const s=ctx.createBufferSource(),edge=ctx.createGain();s.buffer=decoded[key];s.connect(edge);edge.connect(input)
      const points:Points=body?[[0,0],[.004,1]]:[[0,1]]
      if(side==='b'&&!body)points.push([Math.max(.004,duration-.004),1],[duration,0])
      schedule(edge.gain,points,at+start);s.start(at+start,0,duration);sources.push(s);nodes.push(edge)
     }
     if(side==='a')source('a'+layer,0,end)
     else{source('bEntry'+layer,c.pre,c.plan.duration);source('bBody'+layer,end,c.post,true)}
    }
   }
   for(let j=0;j<2;j++)scheduleV30Eq(filters.a[j],filters.b[j],at+c.pre,c.plan.v30Eq!)
 return {nodes,sources,total}
}
