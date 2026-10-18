import {expect,it} from 'vitest'
import {treatment} from './policy'
import {bassCurves} from '../bass-swap/policy'
import {valueAt} from '../melody-overlap/policy'
const timing={duckStart:2,swapStart:3.5,swapEnd:4}
it.each(['reference','stem'] as const)('freezes the chosen %s bass strategy and all rest gains across both drum arms',baseline=>{
 const a=treatment(4,8,timing,baseline,'natural'),b=treatment(4,8,timing,baseline,'loop')
 expect(a.curves).toEqual(b.curves);expect(a.curves).toEqual(bassCurves(4,8,timing,baseline==='stem'?'swap':'reference'))
 expect(a.drum).toEqual({natural:[[0,0]],loop:[[0,0]]})
 for(const t of [0,3.9,4,6,10,12,20]){
  const g=valueAt(b.curves.a.rest,t)
  expect(valueAt(b.drum.natural,t)).toBeCloseTo(-g,12);expect(valueAt(b.drum.loop,t)).toBe(g)
  const master=.4,bass=.1,natural=.2,loop=.3,bg=valueAt(b.curves.a.bass,t)
  const original=master*g+bass*(bg-g),modified=original+natural*valueAt(b.drum.natural,t)+loop*valueAt(b.drum.loop,t)
  expect(modified-original).toBeCloseTo((loop-natural)*g,12)
 }
})
it('does not change its timing input and rejects invalid bass markers',()=>{
 const before=JSON.stringify(timing);treatment(4,8,timing,'stem','loop');expect(JSON.stringify(timing)).toBe(before)
 expect(()=>treatment(4,3,timing,'reference','natural')).toThrow()
})
