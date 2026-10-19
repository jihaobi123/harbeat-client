import {expect,it} from 'vitest'
import {gapCurves} from './policy'
import {valueAt} from '../melody-overlap/policy'
it('leaves the original blend unchanged outside a local final-halfbeat gap',()=>{
 const n=gapCurves(4,8,.25,.005,'natural'),g=gapCurves(4,8,.25,.005,'relay')
 for(const t of [0,4,6,10,11.744,12.005,13])for(const side of ['a','b'] as const){expect(valueAt(g[side].master,t)).toBeCloseTo(valueAt(n[side].master,t));expect(valueAt(g[side].correction,t)).toBeCloseTo(0)}
 for(const t of [11.75,11.8,11.99,12])for(const side of ['a','b'] as const)expect(valueAt(g[side].master,t)).toBeCloseTo(0)
 expect(valueAt(g.b.master,12.0025)).toBeCloseTo(.5)
})
it('preserves original vocal gains through the gap using actual vocal correction',()=>{
 const n=gapCurves(4,8,.25,.005,'natural'),g=gapCurves(4,8,.25,.005,'relay')
 for(const t of [0,4,11.745,11.747,11.75,11.9,12,12.0025,13])for(const side of ['a','b'] as const){
  expect(g[side].voice).toEqual(n[side].voice)
  const vocal=.13,bed=.27
  expect((vocal+bed)*valueAt(g[side].master,t)+vocal*valueAt(g[side].correction,t)).toBeCloseTo(bed*valueAt(g[side].master,t)+vocal*valueAt(n[side].voice,t))
 }
})
it('rejects invalid pause length, edges and clocks',()=>{
 for(const gap of [0,-1,8,9,NaN])expect(()=>gapCurves(4,8,gap,.005,'relay')).toThrow()
 expect(()=>gapCurves(4,8,7.999,.005,'relay')).toThrow();expect(()=>gapCurves(-1,8,.25,.005,'relay')).toThrow();expect(()=>gapCurves(4,8,.25,0,'relay')).toThrow()
})
