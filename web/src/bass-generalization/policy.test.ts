import {expect,it} from 'vitest'
import {treatment,SETTINGS} from './policy'
import {bassCurves} from '../bass-swap/policy'
import {valueAt} from '../melody-overlap/policy'
const timing={duckStart:2,swapStart:3.5,swapEnd:4}
it('freezes one global EQ recipe and preserves non-bass control curves in all arms',()=>{
 const reference=bassCurves(4,8,timing,'reference')
 expect(SETTINGS).toEqual({frequency:140,maxCutDb:18})
 for(const mode of ['reference','stem','eq'] as const){const p=treatment(4,8,timing,mode);expect(p.curves.a.rest).toEqual(reference.a.rest);expect(p.curves.b.rest).toEqual(reference.b.rest);expect(p.settings).toBe(SETTINGS)}
})
it('uses the accepted independent bass envelope only in stem arm',()=>{
 expect(treatment(4,8,timing,'stem').curves).toEqual(bassCurves(4,8,timing,'swap'))
 expect(treatment(4,8,timing,'eq').curves).toEqual(bassCurves(4,8,timing,'reference'))
})
it.each(['reference','stem'] as const)('keeps the additional EQ at identity in %s',mode=>{
 const p=treatment(4,8,timing,mode);expect(p.low.a).toEqual([[0,0]]);expect(p.low.b).toEqual([[0,0]])
})
it('ties the fixed low-frequency cuts to exactly the same observed markers',()=>{
 const p=treatment(4,8,timing,'eq');expect(valueAt(p.low.a,6)).toBe(0);expect(valueAt(p.low.a,7.5)).toBe(-6);expect(valueAt(p.low.a,8)).toBe(-18)
 expect(valueAt(p.low.b,7.5)).toBe(-18);expect(valueAt(p.low.b,8)).toBe(0);expect(valueAt(p.low.b,20)).toBe(0)
 for(const points of [p.low.a,p.low.b])for(const [,db] of points){expect(db).toBeGreaterThanOrEqual(-18);expect(db).toBeLessThanOrEqual(0)}
})
it('does not modify timing input and rejects invalid ranges',()=>{
 const before=JSON.stringify(timing);treatment(4,8,timing,'eq');expect(JSON.stringify(timing)).toBe(before);expect(()=>treatment(4,3,timing,'eq')).toThrow()
})
