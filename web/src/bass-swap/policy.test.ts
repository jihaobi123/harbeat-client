import {expect,it} from 'vitest'
import {bassTiming,bassCurves} from './policy'
import {valueAt,correction} from '../melody-overlap/policy'
const bars=[{start:10,end:12,beats:[10,10.5,11,11.5],valid:true},{start:12,end:14,beats:[12,12.5,13,13.5],valid:true}]
it('chooses existing adjacent bar and final beat without moving the frozen exit',()=>{
 const before=JSON.stringify(bars);expect(bassTiming(bars,8,14)).toEqual({duckStart:2,swapStart:3.5,swapEnd:4});expect(JSON.stringify(bars)).toBe(before)
})
it.each([bars.slice(1),[{...bars[0],valid:false},bars[1]],[{...bars[0],beats:[10,11,11,11.5]},bars[1]],[{...bars[0],end:11.9},bars[1]]])('rejects unsupported measured timing %j',(...rows)=>expect(()=>bassTiming(rows,8,14)).toThrow())
it('rejects a duck that would precede the fixed overlap',()=>expect(()=>bassTiming(bars,10.1,14)).toThrow())
it('softens A first and lets B bass take over on the next downbeat',()=>{
 const timing={duckStart:2,swapStart:3.5,swapEnd:4},c=bassCurves(4,6,timing,'swap')
 expect(valueAt(c.a.bass,6)).toBe(1);expect(valueAt(c.a.bass,7.5)).toBe(.5)
 expect(valueAt(c.b.bass,7.5)).toBe(0);expect(valueAt(c.a.bass,8)).toBe(0);expect(valueAt(c.b.bass,8)).toBe(1)
 expect(valueAt(c.b.bass,9)).toBe(1)
})
it('retains all non-bass reference gains and reconstructs reference PCM exactly',()=>{
 const timing={duckStart:2,swapStart:3.5,swapEnd:4},r=bassCurves(4,6,timing,'reference'),s=bassCurves(4,6,timing,'swap')
 for(const side of ['a','b'] as const){expect(s[side].rest).toEqual(r[side].rest)
  for(const c of [r,s])for(let t=0;t<19;t+=.03125){const x=c[side],g=valueAt(x.rest,t),b=valueAt(x.bass,t);const pcm=.7*g+.23*valueAt(correction(x.bass,x.rest),t);expect(pcm).toBeCloseTo((.7-.23)*g+.23*b,12);if(c===r)expect(pcm).toBeCloseTo(.7*g,12)}
 }
})
it.each([{duckStart:2,swapStart:2,swapEnd:4},{duckStart:-1,swapStart:3,swapEnd:4},{duckStart:2,swapStart:3,swapEnd:7},{duckStart:NaN,swapStart:3,swapEnd:4}])('rejects illegal timing %j',t=>expect(()=>bassCurves(4,6,t,'swap')).toThrow())
