import {expect,it} from 'vitest'
import {handoverTreatment} from './policy'
import {treatment} from '../vocal-bed/policy'
const timing={duckStart:2,swapStart:3.5,swapEnd:4}
const endpoint={tailEnd:6.2,nextOnset:9.5,fadeStart:6.5,fadeEnd:6.7}
it('uses the original natural reference rather than an already-transferred accompaniment',()=>{
 const result=handoverTreatment(4,8,timing,'stem','natural',6,endpoint)
 expect(result).toEqual(treatment(4,8,timing,'stem','natural',6))
})
it('changes only outgoing vocal and accompaniment while incoming voice and bass stay frozen',()=>{
 const a=handoverTreatment(4,8,timing,'stem','natural',6,endpoint),b=handoverTreatment(4,8,timing,'stem','relay',6,endpoint)
 expect(a.bass).toEqual(b.bass);expect(a.b.voice).toEqual(b.b.voice)
 expect(a.a.bed).not.toEqual(b.a.bed);expect(a.b.bed).not.toEqual(b.b.bed)
 expect(b.a.voice).toEqual([[0,1],[10.5,1],[10.7,0],[12,0]])
})
it('still rejects endpoints without protected tails or a guarded gap',()=>{
 expect(()=>handoverTreatment(4,8,timing,'reference','relay',6,{...endpoint,fadeStart:6})).toThrow()
 expect(()=>handoverTreatment(4,8,timing,'reference','natural',6,{...endpoint,nextOnset:7.9})).toThrow()
})
