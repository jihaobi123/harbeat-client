import {expect,it} from 'vitest'
import {curves,correction,finalBar,valueAt} from './policy'
const bars=[{start:10,end:12,beats:[10,10.5,11,11.5],valid:true},{start:12,end:14,beats:[12,12.5,13,13.5],valid:true}]
it('uses the existing complete final measured bar without changing cues',()=>{
 const before=JSON.stringify(bars)
 expect(finalBar(bars,10,14)).toBe(12)
 expect(JSON.stringify(bars)).toBe(before)
})
it.each([
 [{...bars[1],valid:false}], [{...bars[1],beats:[12,12.5,13]}], [{...bars[1],end:NaN}], [{...bars[1],beats:[12,13,12.5,13.5]}], [{...bars[1],start:9}], [{...bars[1],end:14.2}]
])('rejects an invalid or unavailable final bar %j',bad=>expect(()=>finalBar([bad],10,14)).toThrow())
it('requires the final bar to fit inside the frozen overlap',()=>expect(()=>finalBar(bars,12.2,14)).toThrow())
it('keeps vocal/drum curves exactly equal and narrows only melody overlap',()=>{
 const a=curves(4,8,6,'reference'),b=curves(4,8,6,'short')
 for(const side of ['a','b'] as const){expect(b[side].voice).toEqual(a[side].voice);expect(b[side].drums).toEqual(a[side].drums)}
 expect(valueAt(b.a.melody,9)).toBe(1);expect(valueAt(b.b.melody,9)).toBe(0)
 expect(valueAt(b.a.melody,11)).toBe(.5);expect(valueAt(b.b.melody,11)).toBe(.5)
 expect(valueAt(b.a.melody,12)).toBe(0);expect(valueAt(b.b.melody,12)).toBe(1)
})
it('reconstructs the original reference and desired residual from master corrections',()=>{
 for(const mode of ['reference','short'] as const){const c=curves(4,8,6,mode)
  for(const side of ['a','b'] as const)for(let t=0;t<=20;t+=.03125){
   const x=c[side],h=valueAt(x.melody,t),v=valueAt(x.voice,t),d=valueAt(x.drums,t)
   const master=.7,vocal=.15,drum=-.22
   const signal=master*h+vocal*valueAt(correction(x.voice,x.melody),t)+drum*valueAt(correction(x.drums,x.melody),t)
   expect(signal).toBeCloseTo((master-vocal-drum)*h+vocal*v+drum*d,12)
   if(mode==='reference')expect(signal).toBeCloseTo(master*v,12)
  }
 }
})
it.each([[4,8,8],[4,8,-1],[NaN,8,6],[4,Infinity,6]])('rejects invalid timing',(...args)=>expect(()=>curves(args[0],args[1],args[2],'short')).toThrow())
it('preserves the existing 65ms local gate tolerance while retaining the frozen exit',()=>{
 expect(finalBar([{...bars[1],end:13.97}],10,14)).toBe(12)
})
