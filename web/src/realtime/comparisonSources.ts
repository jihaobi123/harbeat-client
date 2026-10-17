import type {Plan,Track} from './planner'
import {nativeSegment,nativeSegments} from '../continuous/segments'
export function comparisonSources(a:Track,b:Track,plan:Plan,position:number,skipWaiting:boolean){
 const offset=Math.max(0,(skipWaiting?plan.start:position)-4)
 const from=nativeSegment(a,offset),to=nativeSegment(b,plan.window.end)
 const assets=[...nativeSegments(a).filter(s=>s.end>offset&&s.start<plan.end),...nativeSegments(b).filter(s=>s.end>plan.window.end&&s.start<plan.window.end+8)].map(s=>s.asset)
 return {offset,from,to,assets}
}
