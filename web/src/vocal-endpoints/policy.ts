import {treatment,type BaselineBass} from '../vocal-bed/policy'
import type {Timing} from '../bass-swap/policy'
export type Mode='natural'|'relay'
export type Endpoint={tailEnd:number;nextOnset:number;fadeStart:number;fadeEnd:number}
export function validateEndpoint(e:Endpoint,duration:number){
 if(![...Object.values(e),duration].every(Number.isFinite)||e.tailEnd<0||e.fadeStart<e.tailEnd+.079||e.fadeEnd<=e.fadeStart||e.fadeEnd>duration||e.nextOnset<duration+.079)throw Error('人声尾音与空隙核验未通过')
}
export function endpointTreatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode,voiceEnd:number,e:Endpoint){
 validateEndpoint(e,duration)
 const x=treatment(pre,duration,timing,baseline,'relay',voiceEnd)
 if(mode==='relay')x.a.voice=[[0,1],[pre+e.fadeStart,1],[pre+e.fadeEnd,0],[pre+duration,0]]
 return x
}
