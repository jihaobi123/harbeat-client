import {expect,it} from 'vitest'
import {combinationPlan} from './policy'
import {bassCurves} from '../bass-swap/policy'
const c:any={pre:4,post:8,bpm:[105,106],timing:{duckStart:2,swapStart:3.5,swapEnd:4},plan:{start:10,end:16,duration:6,rate:1,window:{start:20,end:26}},filter:{type:'highpass',startHz:20,endHz:1800,Q:Math.SQRT1_2,edgeSeconds:.02,sourceStart:14,sourceBar:{start:14,end:16,beats:[14,14.5,15,15.5],valid:true}}}
it('uses filter alone as the explicit new single and adds only unchanged bass to combined',()=>{
 const f={...c,singleTechnique:'filter'},a=combinationPlan(f,'original'),s=combinationPlan(f,'single'),b=combinationPlan(f,'combined')
 expect(s.filter).toEqual(b.filter);expect(s.bass).toEqual(a.bass)
 expect(s.bass).toEqual(bassCurves(4,6,c.timing,'reference'))
 expect(b).toEqual(combinationPlan(c,'combined'))
 expect(a).toEqual(combinationPlan(c,'original'))
 expect(b.bass).toEqual(bassCurves(4,6,c.timing,'swap'))
})
it('retains old bass baseline and rejects unsupported single references',()=>{
 expect(combinationPlan(c,'single').bass).toEqual(bassCurves(4,6,c.timing,'swap'))
 expect(()=>combinationPlan({...c,singleTechnique:'drums'},'single')).toThrow()
})
