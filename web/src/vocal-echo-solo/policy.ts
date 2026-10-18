import {treatment,type BaselineBass} from '../vocal-bed/policy'
import type {Points} from '../melody-overlap/policy'
import type {Timing} from '../bass-swap/policy'
import type {Endpoint} from '../vocal-endpoints/policy'
import {validateEcho,type Echo} from '../vocal-echo/policy'
export {validateEcho,type Echo}
export type Mode='natural'|'relay'
export function echoTreatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode,voiceEnd:number,e:Endpoint,fx:Echo){
 validateEcho(pre,duration,e,fx)
 if(baseline!=='reference')throw Error('本轮仅允许原方案的贝斯曲线')
 const wet=mode==='relay'?1:0
 return {dry:treatment(pre,duration,timing,baseline,'natural',voiceEnd),wet,wetReturn:[[0,wet],[fx.wetEnd-.01,wet],[fx.wetEnd,0],[pre+duration,0]] as Points}
}
