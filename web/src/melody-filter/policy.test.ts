import {expect,it} from 'vitest'
import {filterPlan} from './policy'
export const example=()=>({pre:4,post:8,bpm:[107,106],plan:{start:10,end:14.48,duration:4.48,rate:1,window:{start:20,end:24.48}},filter:{type:'highpass',startHz:20,endHz:1800,Q:Math.SQRT1_2,edgeSeconds:.02,sourceStart:12.22,sourceBar:{start:12.22,end:14.48,beats:[12.22,12.78,13.35,13.91],valid:true}}})
it('filters only the frozen last bar with original master/voice gain curves in both arms',()=>{
 const c=example(),raw=JSON.stringify(c),a=filterPlan(c,'natural'),b=filterPlan(c,'relay')
 expect(b.a).toEqual([[0,1],[4,1],[8.48,0]]);expect(b.b).toEqual([[0,0],[4,0],[8.48,1]]);expect(a.a).toEqual(b.a);expect(a.b).toEqual(b.b)
 expect(a.mix).toEqual([[0,0]]);expect(b.start).toBeCloseTo(6.22);expect(b.frequency).toEqual([[0,20],[b.start,20],[8.48,1800]]);expect(b.mix.at(-1)).toEqual([8.48,1]);expect(JSON.stringify(c)).toBe(raw)
})
it('rejects changed cutoff, resonant Q, stale bar evidence or shifted source clock',()=>{
 const c=example();for(const f of [{...c.filter,endHz:3000},{...c.filter,Q:4},{...c.filter,Q:NaN},{...c.filter,Q:undefined},{...c.filter,edgeSeconds:.2},{...c.filter,sourceStart:12},{...c.filter,sourceBar:{...c.filter.sourceBar,valid:false}},{...c.filter,sourceBar:{...c.filter.sourceBar,beats:[12.22,13]}}])expect(()=>filterPlan({...c,filter:f},'relay')).toThrow()
 expect(()=>filterPlan({...c,plan:{...c.plan,window:{start:20,end:25}}},'relay')).toThrow()
})
