export type Mode='natural'|'relay'
import type {Points} from '../melody-overlap/policy'
export function oneShotPlan(c:any,mode:Mode){
 const p=c.plan,f=c.fx,end=c.pre+p.duration
 if(c.baselineBass!=='reference'||![c.pre,c.post,p.start,p.end,p.duration,p.rate,p.window.start,p.window.end,f?.sourceStart,f?.sourceEnd,f?.sourceOrigin,f?.duration,f?.trigger,f?.replayEnd,f?.contextStart,f?.contextEnd].every(Number.isFinite)||c.pre<0||c.post<=0||p.duration<=0||p.rate<=0||Math.abs(p.end-p.start-p.duration)>.002||Math.abs((p.window.end-p.window.start)/p.rate-p.duration)>.002)throw Error('Invalid original source timeline')
 if(f.count!==1||f.edgeSeconds!==.005||f.quietPadSeconds!==.3||f.captureGainPolicy!=='original-a-linear-at-source'||f.status!=='requires-human-cut-review'||Math.abs(f.sourceOrigin-(p.start-c.pre))>1e-6||f.sourceStart-f.contextStart!==.5||f.contextEnd-f.sourceEnd!==.5||Math.abs(f.duration-(f.sourceEnd-f.sourceStart))>1e-6||f.duration<.15||f.duration>3||Math.abs(f.trigger-end)>1e-6||Math.abs(f.replayEnd-end-f.duration)>1e-6||f.replayEnd+.3>end+c.post||f.contextStart<f.sourceOrigin||f.contextEnd>p.end)throw Error('Invalid one-shot window')
 for(const [support,coverage,anchor] of [[f.incomingSupport,f.incomingCoverage,p.window.end],[f.outgoingSupport,f.outgoingCoverage,p.end]] as const){if(!Array.isArray(support)||support.length!==2||![...support,coverage?.start,coverage?.end].every(Number.isFinite)||Math.abs(support[0]-anchor)>1e-6||Math.abs(support[1]-support[0]-f.duration)>1e-6||coverage.start>support[0]-.3||coverage.end<support[1]+.3)throw Error('Unobserved replay voice support')}
 const a:Points=[[0,1],[c.pre,1],[end,0]],b:Points=[[0,0],[c.pre,0],[end,1]]
 return {a,b,trigger:f.trigger,shotEnd:f.replayEnd,shotGain:mode==='relay'?1:0}
}
