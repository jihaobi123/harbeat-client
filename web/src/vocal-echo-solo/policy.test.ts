import {expect,it} from 'vitest'
import {echoTreatment} from './policy'
import {treatment} from '../vocal-bed/policy'
const e={tailEnd:6,nextOnset:13,fadeStart:6.5,fadeEnd:6.7},fx={sendStart:9.5,sendEnd:10,wetStart:9.75,wetEnd:10.79,taps:[{delaySeconds:.25,gain:.26},{delaySeconds:.5,gain:.117},{delaySeconds:.75,gain:.052}]},timing={duckStart:2,swapStart:3,swapEnd:4}
it('uses original natural dry curves in both arms, with only a wet return toggle',()=>{
 const a=echoTreatment(4,8,timing,'reference','natural',6,e,fx),b=echoTreatment(4,8,timing,'reference','relay',6,e,fx)
 expect(a.dry).toEqual(treatment(4,8,timing,'reference','natural',6));expect(b.dry).toEqual(a.dry)
 expect(a.dry.a.voice).toEqual([[0,1],[4,1],[12,0]]);expect(a.dry.a.bed).toEqual(a.dry.a.voice)
 expect(a.wet).toBe(0);expect(b.wet).toBe(1)
})
it('rejects independent bass treatment and a wet tail outside the frozen gap',()=>{
 expect(()=>echoTreatment(4,8,timing,'stem','relay',6,e,fx)).toThrow()
 expect(()=>echoTreatment(4,8,timing,'reference','relay',6,e,{...fx,wetEnd:12})).toThrow()
})
it('ends the post-EQ wet return at the declared safe support boundary',()=>{
 const x=echoTreatment(4,8,timing,'reference','relay',6,e,fx)
 expect((x as any).wetReturn).toEqual([[0,1],[10.78,1],[10.79,0],[12,0]])
})
