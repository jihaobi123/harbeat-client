import {valueAt,type Points} from './policy'
/** master*bed + vocal*(voice-bed) = residual*bed + vocal*voice. */
export function stemGainPoints(bed:Points,voice:Points):Points{
 return [...new Set([...bed,...voice].map(p=>p[0]))].sort((a,b)=>a-b).map(t=>[t,valueAt(voice,t)-valueAt(bed,t)])
}
export function schedule(param:AudioParam,points:Points,at:number,scale=1){
 param.cancelScheduledValues(at)
 points.forEach(([t,v],i)=>i?param.linearRampToValueAtTime(v*scale,at+t):param.setValueAtTime(v*scale,at+t))
}
export function referenceCurves(pre:number,duration:number,restore:number){
 const end=pre+duration
 return {aGain:[[0,1],[pre,1],[end,0]] as Points,bGain:[[0,0],[pre,0],[end,1]] as Points,
 aWet:[[0,0],[pre,0],[pre+.02,1]] as Points,bWet:[[0,1],[restore,1],[end,0]] as Points}
}
