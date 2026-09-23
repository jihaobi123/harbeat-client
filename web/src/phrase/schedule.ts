import type {TransitionAutomation,GainPoint,EqPoint} from './types'
type Deck={gain:GainNode;wet:GainNode;dry:GainNode;low:BiquadFilterNode;mid:BiquadFilterNode;high:BiquadFilterNode}
function curve(param:AudioParam,values:GainPoint[],at:number,scale=1){param.cancelScheduledValues(at);values.forEach((p,i)=>{if(i===0)param.setValueAtTime(p.value*scale,at+p.t);else param.linearRampToValueAtTime(p.value*scale,at+p.t)})}
function eq(deck:Deck,values:EqPoint[],at:number){for(const band of ['low','mid','high'] as const)curve(deck[band].gain,values.map(x=>({t:x.t,value:x[band]})),at)}
export function scheduleAutomation(a:Deck,b:Deck,at:number,automation:TransitionAutomation){
 for(const d of [a,b]){d.wet.gain.cancelScheduledValues(at);d.dry.gain.cancelScheduledValues(at);d.wet.gain.setValueAtTime(1,at);d.dry.gain.setValueAtTime(0,at)}
 curve(a.gain.gain,automation.aGain,at,.76);curve(b.gain.gain,automation.bGain,at,.76);eq(a,automation.aEq,at);eq(b,automation.bEq,at)
}
