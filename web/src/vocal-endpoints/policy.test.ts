import {describe,it,expect} from 'vitest'
import {endpointTreatment,validateEndpoint} from './policy'
const x={tailEnd:8.1,nextOnset:11.5,fadeStart:8.5,fadeEnd:8.7}
describe('source-bound vocal endpoint handover',()=>{
 it('rejects fades before tail, outside cue or across onset',()=>{for(const e of [{...x,fadeStart:8},{...x,fadeEnd:10.1},{...x,nextOnset:8.75}])expect(()=>validateEndpoint(e,10)).toThrow()})
 it('changes only outgoing voice, preserving bed bass and incoming voice',()=>{const a=endpointTreatment(4,10,{duckStart:7,swapStart:8,swapEnd:9},'stem','natural',8,x),b=endpointTreatment(4,10,{duckStart:7,swapStart:8,swapEnd:9},'stem','relay',8,x);expect(a.bass).toEqual(b.bass);expect(a.a.bed).toEqual(b.a.bed);expect(a.b).toEqual(b.b);expect(a.a.voice).not.toEqual(b.a.voice);expect(b.a.voice).toEqual([[0,1],[12.5,1],[12.7,0],[14,0]])})
})
