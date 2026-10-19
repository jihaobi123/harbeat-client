import {expect,it} from 'vitest'
import {combinationPlan} from './policy'
import {bassCurves} from '../bass-swap/policy'
import {valueAt} from '../melody-overlap/policy'
const c:any={pre:4,post:8,bpm:[104.9,106.6],timing:{duckStart:2,swapStart:3.5,swapEnd:4},plan:{start:10,end:16,duration:6,rate:1,window:{start:20,end:26}},filter:{type:'highpass',startHz:20,endHz:1800,Q:Math.SQRT1_2,edgeSeconds:.02,sourceStart:14,sourceBar:{start:14,end:16,beats:[14,14.5,15,15.5],valid:true}}}
it('adds exactly one filter while preserving selected single bass timing, original master curves and case',()=>{
 const snapshot=JSON.stringify(c),a=combinationPlan(c,'original'),b=combinationPlan(c,'single'),d=combinationPlan(c,'combined')
 expect(b.bass).toEqual(d.bass);expect(a.filter.mix).toEqual(b.filter.mix);expect(d.filter.mix).not.toEqual(b.filter.mix)
 expect(a.bass).toEqual(bassCurves(4,6,c.timing,'reference'));expect(b.bass).toEqual(bassCurves(4,6,c.timing,'swap'))
 expect(a.filter.a).toEqual(d.filter.a);expect(a.filter.b).toEqual(d.filter.b);expect(JSON.stringify(c)).toBe(snapshot)
})
it('bass corrections return to zero at unchanged native handoff and leave master/vocal reference untouched',()=>{
 for(const mode of ['original','single','combined'] as const){const p=combinationPlan(c,mode);for(const s of ['a','b'] as const){expect(valueAt(p.bass[s].bass,p.end)-valueAt(p.bass[s].rest,p.end)).toBe(0);expect(p.bass[s].rest).toEqual(p.filter[s])}}
})
it('rejects unsupported modes and damaged timing instead of silently playing an original arm',()=>{
 expect(()=>combinationPlan(c,'anything' as any)).toThrow();expect(()=>combinationPlan({...c,timing:{...c.timing,swapEnd:7}},'combined')).toThrow()
})
