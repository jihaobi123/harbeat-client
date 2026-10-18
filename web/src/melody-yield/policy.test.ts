import {expect,it} from 'vitest'
import {yieldCurves} from './policy'
import {valueAt} from '../melody-overlap/policy'
it('retains both master curves and incoming other, changes only outgoing other',()=>{
 const a=yieldCurves(4,8,2,'natural'),b=yieldCurves(4,8,2,'relay')
 expect(a.a.master).toEqual(b.a.master);expect(a.b).toEqual(b.b)
 expect(a.a.correction.every(p=>p[1]===0)).toBe(true)
 expect(valueAt(b.a.master,6)+valueAt(b.a.correction,6)).toBeCloseTo(0)
 expect(valueAt(b.a.master,5)+valueAt(b.a.correction,5)).toBeCloseTo(.5)
})
it('exactly reconstructs the original master and restricts the treatment delta to other',()=>{
 for(const t of [0,4,4.1,5,6,9,12]){
  const a=yieldCurves(4,8,2,'natural'),b=yieldCurves(4,8,2,'relay'),master=.4,other=.12
  const ref=master*valueAt(a.a.master,t)+other*valueAt(a.a.correction,t)
  expect(ref).toBeCloseTo(master*valueAt(a.a.master,t))
  const changed=master*valueAt(b.a.master,t)+other*valueAt(b.a.correction,t)
  expect(changed-ref).toBeCloseTo(other*valueAt(b.a.correction,t))
 }
})
it('rejects a yield end outside the fixed overlap',()=>{
 for(const end of [0,-1,8,9,NaN])expect(()=>yieldCurves(4,8,end,'relay')).toThrow()
})
