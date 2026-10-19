import {scheduleV30Eq} from '../v30/eq'
import {referenceCurves,schedule} from '../vocal-bridge/automation'
import {combinationPlan,type Mode} from './policy'
import {correction} from '../melody-overlap/policy'
import type {CombinationCase} from './transport'
import type {Points} from '../melody-overlap/policy'
export function makeCombinationGraph(ctx:BaseAudioContext,monitor:AudioNode,decoded:Record<string,AudioBuffer>,c:CombinationCase,mode:Mode,at:number){
 const gain=(value=0)=>{const g=ctx.createGain();g.gain.value=value;return g}
 const nodes:AudioNode[]=[],sources:AudioBufferSourceNode[]=[],combined=combinationPlan(c,mode),policy=combined.filter,end=policy.end,total=end+c.post,ref=referenceCurves(c.pre,c.plan.duration,end-Math.min(c.plan.duration,120/c.bpm[0]))
 const bus=gain();bus.connect(monitor);nodes.push(bus);schedule(bus.gain,[[0,0],[.02,1],[total-.04,1],[total,0]],at)
 const filters:{a:any[];b:any[]}={a:[],b:[]}
 for(const side of ['a','b'] as const){
  for(const layer of ['Master','Other','Bass']){
   const input=gain(1),low=ctx.createBiquadFilter(),high=ctx.createBiquadFilter(),mid=ctx.createBiquadFilter(),wet=gain(),dry=gain(),sum=gain(1),envelope=gain()
   low.type='lowshelf';low.frequency.value=140;high.type='highshelf';high.frequency.value=3600;mid.type='peaking';mid.frequency.value=1200;mid.Q.value=1.05
   input.connect(low);low.connect(high);high.connect(mid);mid.connect(wet);input.connect(dry);wet.connect(sum);dry.connect(sum);sum.connect(envelope)
   const wetPoints=side==='a'?ref.aWet:ref.bWet;schedule(wet.gain,wetPoints,at);schedule(dry.gain,wetPoints.map(([t,v])=>[t,1-v]),at)
   schedule(envelope.gain,layer==='Bass'?correction(combined.bass[side].bass,combined.bass[side].rest):layer==='Other'&&side==='b'?[[0,0]]:policy[side],at,.60)
   nodes.push(input,low,high,mid,wet,dry,sum,envelope);filters[side].push({low,high,mid})
   if(side==='a'&&layer==='Other'){
    // EQ is applied before the correction. The HP filter stays warm; both
    // correction branches carry the same original A envelope after filtering.
    const hp=ctx.createBiquadFilter(),filteredEnvelope=gain(),positive=gain(),negative=gain()
    hp.type='highpass';hp.Q.value=policy.Qdb;hp.frequency.cancelScheduledValues(at)
    policy.frequency.forEach(([t,v],i)=>i?hp.frequency.exponentialRampToValueAtTime(v,at+t):hp.frequency.setValueAtTime(v,at+t))
    sum.connect(hp);hp.connect(filteredEnvelope);filteredEnvelope.connect(positive);positive.connect(bus);envelope.connect(negative);negative.connect(bus)
    schedule(filteredEnvelope.gain,policy.a,at,.60);schedule(positive.gain,policy.mix,at);schedule(negative.gain,policy.mix.map(([t,v])=>[t,-v]),at)
    nodes.push(hp,filteredEnvelope,positive,negative)
   }else envelope.connect(bus)
   const source=(key:string,start:number,duration:number,body=false)=>{
    const s=ctx.createBufferSource(),edge=gain();s.buffer=decoded[key];s.connect(edge);edge.connect(input)
    const points:Points=body?[[0,0],[.004,1]]:[[0,1]]
    if(side==='b'&&!body)points.push([Math.max(.004,duration-.004),1],[duration,0])
    schedule(edge.gain,points,at+start);s.start(at+start,0,duration);sources.push(s);nodes.push(edge)
   }
   if(side==='a')source('a'+layer,0,end)
   else if(layer!=='Other'){source('bEntry'+layer,c.pre,c.plan.duration);if(layer!=='Bass')source('bBody'+layer,end,c.post,true)}
  }
 }
 for(let j=0;j<3;j++)scheduleV30Eq(filters.a[j],filters.b[j],at+c.pre,c.plan.v30Eq!)
 return {nodes,sources,policy:combined,total}
}
