import {bassCurves,type Timing} from '../bass-swap/policy'
import type {Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export type BaselineBass='reference'|'stem'
export type Relay={aVoiceEnd:number;bEntry:number;bEnd:number;aIntervals:number[][];bIntervals:number[][]}
export function validateRelay(start:number,end:number,duration:number,r:Relay){
 if(![start,end,duration,r.aVoiceEnd,r.bEntry,r.bEnd].every(Number.isFinite)||duration<=0||Math.abs(end-start-duration)>.002||r.bEnd<=r.bEntry||r.aIntervals.concat(r.bIntervals).some(x=>x.length!==2||!x.every(Number.isFinite)||x[1]<=x[0]))throw Error('人声交接时间无效')
 const active=r.aIntervals.filter(([s,e])=>s<end&&e>start)
 const coverage=active.reduce((n,[s,e])=>n+Math.max(0,Math.min(e,end)-Math.max(s,start)),0)
 const last=Math.max(...active.map(x=>x[1]))
 if(coverage<2||Math.abs(last-r.aVoiceEnd)>.001||end-last<.5||end-last>3||last<start+.55*duration||r.bIntervals.some(([s,e])=>s<r.bEnd+.15&&e>r.bEntry-.3))throw Error('现有接点没有足够的人声交接空间')
}
export function treatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode,voiceEnd:number):{bass:ReturnType<typeof bassCurves>;a:{bed:Points;voice:Points};b:{bed:Points;voice:Points}}{
 const bass=bassCurves(pre,duration,timing,baseline==='stem'?'swap':'reference'),end=pre+duration
 if(mode==='natural')return {bass,a:{bed:bass.a.rest,voice:bass.a.rest},b:{bed:bass.b.rest,voice:bass.b.rest}}
 return {bass,a:{bed:[[0,1],[pre,1],[pre+duration*.4,0],[end,0]],voice:[[0,1],[pre+voiceEnd+.15,1],[end,0]]},b:{bed:[[0,0],[pre,0],[pre+duration*.4,1],[end,1]],voice:bass.b.rest}}
}
