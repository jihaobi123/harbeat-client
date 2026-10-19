import {expect,it} from 'vitest'
import {handoffPlan} from './policy'
const fixture=()=>({pre:4,post:8,bpm:[120,120],plan:{start:10,end:18,duration:8,rate:1,window:{start:20,end:28}},handoff:{frequency:140,maxCutDb:18,rampBeats:1,earlySource:10,lateSource:16,bars:[10,12,14,16,18]}})
it('only translates the identical one-beat low shelf exchange, preserving original fades',()=>{
 const c=fixture(),raw=JSON.stringify(c),a=handoffPlan(c,'natural'),b=handoffPlan(c,'relay');expect(a.start).toBe(4);expect(b.start).toBe(10);expect(a.a).toEqual(b.a);expect(a.b).toEqual(b.b);expect(a.low.a.map(([t,v])=>[t===0?0:t-a.start,v])).toEqual(b.low.a.map(([t,v])=>[t===0?0:t-b.start,v]));expect(a.low.b.at(-1)).toEqual([4.5,0]);expect(b.low.b.at(-1)).toEqual([10.5,0]);expect(a.low.a.at(-1)?.[1]).toBe(-18);expect(JSON.stringify(c)).toBe(raw)
})
it('rejects unsupported anchors, mutated settings and shifted source clocks',()=>{
 for(const mutate of [(c:any)=>c.handoff.lateSource=15,(c:any)=>c.handoff.earlySource=12,(c:any)=>c.handoff.bars=[10,18],(c:any)=>c.handoff.frequency=200,(c:any)=>c.handoff.rampBeats=2,(c:any)=>c.plan.window.end=29,(c:any)=>c.plan.end=17]){const c=fixture();mutate(c);expect(()=>handoffPlan(c,'relay')).toThrow()}
})
