import {treatment,type BaselineBass} from '../vocal-bed/policy'
import {endpointTreatment,validateEndpoint,type Endpoint} from '../vocal-endpoints/policy'
import type {Timing} from '../bass-swap/policy'
export type Mode='natural'|'relay'
export function handoverTreatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode,voiceEnd:number,e:Endpoint){
 validateEndpoint(e,duration)
 return mode==='natural'?treatment(pre,duration,timing,baseline,'natural',voiceEnd):endpointTreatment(pre,duration,timing,baseline,'relay',voiceEnd,e)
}
