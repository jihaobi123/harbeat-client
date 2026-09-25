import {it,expect} from 'vitest'
import {stemGainPoints,referenceCurves} from './automation'
import {bridgeCurves,valueAt} from './policy'
it('master/vocal residual routing equals requested bed and voice at every breakpoint',()=>{
 const p={start:50,end:58,duration:8,rate:1,bEntry:0,bEnd:8,bVoiceStart:9,aVoiceEnd:57,bars:4}
 const curves=bridgeCurves(p,4)
 for(const [bed,voice] of [[curves.aBed,curves.aVoice],[curves.bBed,curves.bVoice]]){
  const delta=stemGainPoints(bed,voice)
  for(let t=0;t<20;t+=.03)expect(valueAt(bed,t)+valueAt(delta,t)).toBeCloseTo(valueAt(voice,t),10)
 }
})
it('reference retains full linear overlap and original EQ wet/dry timing',()=>{
 const c=referenceCurves(4,8,11)
 expect(valueAt(c.aGain,8)).toBe(.5);expect(valueAt(c.bGain,8)).toBe(.5)
 expect(valueAt(c.aWet,4)).toBe(0);expect(valueAt(c.aWet,4.02)).toBe(1)
 expect(valueAt(c.bWet,11)).toBe(1);expect(valueAt(c.bWet,12)).toBe(0)
})
