import {endpointTreatment,validateEndpoint,type Endpoint} from '../vocal-endpoints/policy'
import type {BaselineBass} from '../vocal-bed/policy'
import type {Timing} from '../bass-swap/policy'
export type Mode='natural'|'relay'
export type Echo={sendStart:number;sendEnd:number;wetStart:number;wetEnd:number;taps:{delaySeconds:number;gain:number}[]}
export function validateEcho(pre:number,duration:number,e:Endpoint,fx:Echo){
 validateEndpoint(e,duration)
 const taps=fx.taps
 if(![pre,duration,fx.sendStart,fx.sendEnd,fx.wetStart,fx.wetEnd,...taps.flatMap(t=>[t.delaySeconds,t.gain])].every(Number.isFinite)||taps.length!==3||taps.some(t=>t.delaySeconds<=0||t.gain<0||t.gain>.5)||fx.sendStart<pre||fx.sendEnd<=fx.sendStart||Math.abs(fx.sendEnd-pre-e.tailEnd)>.002||Math.abs(fx.wetStart-fx.sendStart-Math.min(...taps.map(t=>t.delaySeconds)))>.002||fx.wetEnd<fx.sendEnd+Math.max(...taps.map(t=>t.delaySeconds))-.001||fx.wetEnd>pre+duration-.08||fx.wetEnd<=fx.wetStart||fx.wetEnd>pre+e.nextOnset-.08)throw Error('回声尾音不在已核验的空隙内')
}
export function echoTreatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode,voiceEnd:number,e:Endpoint,fx:Echo){
 validateEcho(pre,duration,e,fx)
 return {dry:endpointTreatment(pre,duration,timing,baseline,'relay',voiceEnd,e),wet:mode==='relay'?1:0}
}
