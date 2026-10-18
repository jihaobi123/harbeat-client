import {expect,it} from 'vitest'
import {cutCurves} from './policy'
import {valueAt} from '../melody-overlap/policy'
it('keeps both original vocal curves and changes only accompaniment exchange',()=>{
 const n=cutCurves(4,8,.005,'natural'),s=cutCurves(4,8,.005,'relay')
 for(const t of [0,4,6,10,11.994,11.9975,12,14]){
  for(const side of ['a','b'] as const){
   expect(s[side].voice).toEqual(n[side].voice)
   expect(valueAt(s[side].master,t)+valueAt(s[side].correction,t)).toBeCloseTo(valueAt(n[side].voice,t))
  }
  expect(valueAt(s.a.master,t)+valueAt(s.b.master,t)).toBeCloseTo(1)
 }
 expect(valueAt(s.a.master,11.994)).toBe(1);expect(valueAt(s.b.master,11.994)).toBe(0)
 expect(valueAt(s.a.master,12)).toBe(0);expect(valueAt(s.b.master,12)).toBe(1)
})
it('reconstructs unchanged original vocals plus a newly gated accompaniment',()=>{
 for(const mode of ['natural','relay'] as const)for(const t of [0,4,6.3,11.997,12,13]){
  const x=cutCurves(4,8,.005,mode)
  for(const side of ['a','b'] as const){
   const vocal=.13,bed=.27,master=vocal+bed
   expect(master*valueAt(x[side].master,t)+vocal*valueAt(x[side].correction,t)).toBeCloseTo(bed*valueAt(x[side].master,t)+vocal*valueAt(x[side].voice,t))
  }
 }
})
it('rejects nonfinite clocks, negative lead or an edge outside the original transition',()=>{
 for(const edge of [0,-1,8,9,NaN])expect(()=>cutCurves(4,8,edge,'relay')).toThrow()
 expect(()=>cutCurves(-1,8,.005,'relay')).toThrow()
})
