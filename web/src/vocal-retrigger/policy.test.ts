import {expect,it} from 'vitest'
import {oneShotPlan} from './policy'
const example=()=>({pre:4,post:8,baselineBass:'reference',plan:{start:10,end:18,duration:8,rate:1,window:{start:20,end:28}},fx:{sourceStart:12.97,sourceEnd:15.03,sourceOrigin:6,duration:2.06,contextStart:12.47,contextEnd:15.53,trigger:12,replayEnd:14.06,count:1,edgeSeconds:.005,quietPadSeconds:.3,captureGainPolicy:'original-a-linear-at-source',status:'requires-human-cut-review',incomingSupport:[28,30.06],outgoingSupport:[18,20.06],outgoingCoverage:{start:5,end:29},incomingCoverage:{start:18,end:32}}})
it('changes only the single replay while preserving original dry voice/master fades',()=>{
 const c=example(),a=oneShotPlan(c,'natural'),b=oneShotPlan(c,'relay');expect(a.shotGain).toBe(0);expect(b.shotGain).toBe(1);expect(a.a).toEqual([[0,1],[4,1],[12,0]]);expect(a.a).toEqual(b.a);expect(a.b).toEqual(b.b);expect(b.trigger).toBe(12);expect(b.shotEnd).toBe(14.06)
})
it('rejects moved cues, multiple triggers and absent quiet coverage',()=>{
 const c=example();for(const fx of [{...c.fx,trigger:11.9},{...c.fx,count:2},{...c.fx,incomingCoverage:{start:18,end:30}},{...c.fx,sourceEnd:17},{...c.fx,quietPadSeconds:0}])expect(()=>oneShotPlan({...c,fx},'relay')).toThrow()
})
