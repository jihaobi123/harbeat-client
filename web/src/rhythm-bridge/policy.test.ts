import {expect,it} from 'vitest'
import {bridgeCurves} from './policy'
import {valueAt} from '../melody-overlap/policy'
it('holds natural A drums until final bar while preserving both master fades',()=>{
 const n=bridgeCurves(4,8,6,'natural'),b=bridgeCurves(4,8,6,'relay')
 expect(n.a.master).toEqual(b.a.master);expect(n.b.master).toEqual(b.b.master)
 for(const t of [0,4,6,9,10,11,12,14]){
  const ga=valueAt(b.a.master,t)+valueAt(b.a.correction,t),gb=valueAt(b.b.master,t)+valueAt(b.b.correction,t)
  expect(ga+gb).toBeCloseTo(1)
  expect(ga).toBeCloseTo(t<=10?1:t>=12?0:(12-t)/2)
  expect(n.a.correction.every(p=>p[1]===0)).toBe(true);expect(n.b.correction.every(p=>p[1]===0)).toBe(true)
 }
})
it('changes only drum components of the original master reconstruction',()=>{
 for(const t of [0,4,5.1,8,10,11.3,12,13]){
  const n=bridgeCurves(4,8,6,'natural'),b=bridgeCurves(4,8,6,'relay')
  for(const side of ['a','b'] as const){
   const drum=.12,rest=.31,master=drum+rest
   const audio=master*valueAt(b[side].master,t)+drum*valueAt(b[side].correction,t)
   const desired=rest*valueAt(n[side].master,t)+drum*(valueAt(b[side].master,t)+valueAt(b[side].correction,t))
   expect(audio).toBeCloseTo(desired)
  }
 }
})
it('rejects invalid final-bar boundaries',()=>{
 for(const boundary of [0,-1,8,9,NaN])expect(()=>bridgeCurves(4,8,boundary,'relay')).toThrow()
})
